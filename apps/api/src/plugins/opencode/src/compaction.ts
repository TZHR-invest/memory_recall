import * as fs from "fs";
import * as path from "path";
import * as os from "os";
import type { OpencodeClient } from "@opencode-ai/sdk";
import type { ApiClient } from "./client";
import type { Config } from "./config";
import type { Logger } from "./logging";
import { detectLocaleFromText, getLocale, type Locale } from "./i18n";
import { shouldSave } from "./summary-extractor";

const MESSAGE_STORAGE = path.join(os.homedir(), ".opencode", "messages");
const PART_STORAGE = path.join(os.homedir(), ".opencode", "parts");

const DEFAULT_THRESHOLD = 0.8;
const MIN_TOKENS_FOR_COMPACTION = 50000;
const COMPACTION_COOLDOWN_MS = 30000;
const DEFAULT_CONTEXT_LIMIT = 200000;

interface CompactionState {
  lastCompactionTime: Map<string, number>;
  compactionInProgress: Set<string>;
  summarizedSessions: Set<string>;
  savedSummarySessions: Set<string>;
  latestSummaries: Map<string, { content: string; timestamp: number }>;
  agentConfigCheckpoints: Map<string, AgentConfig>;
  todoSnapshots: Map<string, TodoItem[]>;
}

interface AgentConfig {
  agent?: string;
  model?: {
    providerID: string;
    modelID: string;
  };
  tools?: Record<string, boolean>;
}

interface TodoItem {
  content: string;
  status: string;
  priority: string;
}

interface MessageInfo {
  id?: string;
  sessionID?: string;
  role?: string;
  agent?: string;
  model?: {
    providerID?: string;
    modelID?: string;
  };
  path?: {
    cwd?: string;
    root?: string;
  };
  tokens?: {
    input?: number;
    output?: number;
    cache?: {
      read?: number;
    };
  };
  summary?: boolean;
  finish?: boolean;
  providerID?: string;
  modelID?: string;
}

function createCompactionPrompt(projectMemories: string[], locale: Locale): string {
  const localeData = getLocale(locale);
  const sections = localeData.session_summary_sections;

  let memoriesSection = "";
  if (projectMemories.length > 0) {
    const memoriesList = projectMemories.map((m) => `- ${m}`).join("\n");
    if (locale === "zh_CN") {
      memoriesSection = `
## 项目知识（来自 Memory Recall）
以下项目特定知识应在摘要中保留和引用：
${memoriesList}
`;
    } else {
      memoriesSection = `
## Project Knowledge (from Memory Recall)
The following project-specific knowledge should be preserved and referenced in the summary:
${memoriesList}
`;
    }
  }

  const activeContextHint = locale === "zh_CN"
    ? `- **文件**: 当前正在编辑或频繁引用的文件路径
- **进行中的代码**: 正在开发的关键代码片段、函数签名或数据结构
- **状态与变量**: 与当前工作相关的重要变量名、配置值或运行时状态`
    : `- **Files**: Paths of files currently being edited or frequently referenced
- **Code in Progress**: Key code snippets, function signatures, or data structures under active development
- **State & Variables**: Important variable names, configuration values, or runtime state relevant to ongoing work`;

  const nextActionHint = locale === "zh_CN"
    ? `- 一句话描述压缩后应立即执行的任务
- 例如："继续实现 XXX 函数" 或 "运行测试并修复失败用例"
- 避免模糊描述，要具体到文件路径或函数名`
    : `- One sentence describing the task to execute immediately after compaction
- Example: "Continue implementing XXX function" or "Run tests and fix failing cases"
- Avoid vague descriptions; be specific about file paths or function names`;

  return `[COMPACTION CONTEXT INJECTION]

CRITICAL: Use ONLY the section headers below. Do NOT use any other headers like "## Goal" or "## Summary".

Your summary MUST have EXACTLY these 7 sections in this order:

${sections.user_requests}
- List all original user requests exactly as they were stated
- Preserve the user's exact wording and intent

${sections.final_goal}
- What the user ultimately wanted to achieve
- The end result or deliverable expected

${sections.work_completed}
- What has been done so far
- Files created/modified
- Features implemented
- Problems solved

${sections.remaining_tasks}
- What still needs to be done
- Pending items from the original request
- Follow-up tasks identified during the work

${sections.active_working_context}
${activeContextHint}

${sections.must_not_do}
- Things that were explicitly forbidden
- Approaches that failed and should not be retried
- User's explicit restrictions or preferences
- Anti-patterns identified during the session

${sections.next_action}
${nextActionHint}
${memoriesSection}
This context is critical for maintaining continuity after compaction.
`;
}

function getMessageDir(sessionId: string): string | null {
  if (!fs.existsSync(MESSAGE_STORAGE)) return null;

  const directPath = path.join(MESSAGE_STORAGE, sessionId);
  if (fs.existsSync(directPath)) return directPath;

  const dirs = fs.readdirSync(MESSAGE_STORAGE, { withFileTypes: true });
  for (const dir of dirs) {
    if (dir.isDirectory()) {
      const sessionPath = path.join(MESSAGE_STORAGE, dir.name, sessionId);
      if (fs.existsSync(sessionPath)) return sessionPath;
    }
  }

  return null;
}

function getOrCreateMessageDir(sessionId: string): string {
  if (!fs.existsSync(MESSAGE_STORAGE)) {
    fs.mkdirSync(MESSAGE_STORAGE, { recursive: true });
  }

  const directPath = path.join(MESSAGE_STORAGE, sessionId);
  if (fs.existsSync(directPath)) return directPath;

  const dirs = fs.readdirSync(MESSAGE_STORAGE, { withFileTypes: true });
  for (const dir of dirs) {
    if (dir.isDirectory()) {
      const sessionPath = path.join(MESSAGE_STORAGE, dir.name, sessionId);
      if (fs.existsSync(sessionPath)) return sessionPath;
    }
  }

  fs.mkdirSync(directPath, { recursive: true });
  return directPath;
}

function findNearestMessageWithFields(messageDir: string): MessageInfo | null {
  try {
    const files = fs
      .readdirSync(messageDir)
      .filter((f) => f.endsWith(".json"))
      .sort()
      .reverse();

    for (const file of files) {
      try {
        const content = fs.readFileSync(path.join(messageDir, file), "utf-8");
        const msg = JSON.parse(content) as MessageInfo;
        if (msg.agent && msg.model?.providerID && msg.model?.modelID) {
          return msg;
        }
      } catch {
        continue;
      }
    }
  } catch {
    return null;
  }
  return null;
}

function generateMessageId(): string {
  const timestamp = Math.floor(Date.now() / 1000).toString(16);
  const random = Math.random().toString(16).slice(2, 14);
  return `msg_${timestamp}${random}`;
}

function generatePartId(): string {
  const timestamp = Math.floor(Date.now() / 1000).toString(16);
  const random = Math.random().toString(16).slice(2, 10);
  return `prt_${timestamp}${random}`;
}

function extractSummaryContent(messageId: string): string | null {
  const partDir = path.join(PART_STORAGE, messageId);
  if (!fs.existsSync(partDir)) return null;

  try {
    const files = fs.readdirSync(partDir).filter(f => f.endsWith('.json'));
    for (const file of files) {
      try {
        const content = fs.readFileSync(path.join(partDir, file), 'utf-8');
        const part = JSON.parse(content) as { type?: string; text?: string };
        if (part.type === 'text' && part.text && part.text.trim()) {
          return part.text.trim();
        }
      } catch {
        continue;
      }
    }
  } catch {
    return null;
  }
  return null;
}

function injectHookMessage(
  sessionId: string,
  hookContent: string,
  originalMessage: MessageInfo
): boolean {
  if (!hookContent || !hookContent.trim()) return false;

  const messageDir = getOrCreateMessageDir(sessionId);
  const fallback = findNearestMessageWithFields(messageDir);

  const now = Date.now();
  const messageId = generateMessageId();
  const partId = generatePartId();

  const resolvedAgent = originalMessage.agent || fallback?.agent || "general";

  let resolvedModel: { providerID: string; modelID: string } | undefined;
  if (originalMessage.model?.providerID && originalMessage.model?.modelID) {
    resolvedModel = {
      providerID: originalMessage.model.providerID,
      modelID: originalMessage.model.modelID,
    };
  } else if (fallback?.model?.providerID && fallback?.model?.modelID) {
    resolvedModel = {
      providerID: fallback.model.providerID,
      modelID: fallback.model.modelID,
    };
  }

  const messageMeta: Record<string, unknown> = {
    id: messageId,
    sessionID: sessionId,
    role: "user",
    time: { created: now },
    agent: resolvedAgent,
  };

  if (resolvedModel) {
    messageMeta.model = resolvedModel;
  }
  if (originalMessage.path?.cwd) {
    messageMeta.path = {
      cwd: originalMessage.path.cwd,
      root: originalMessage.path.root || "/",
    };
  }

  const textPart: Record<string, unknown> = {
    id: partId,
    type: "text",
    text: hookContent,
    synthetic: true,
    time: { start: now, end: now },
    messageID: messageId,
    sessionID: sessionId,
  };

  try {
    fs.writeFileSync(
      path.join(messageDir, `${messageId}.json`),
      JSON.stringify(messageMeta, null, 2)
    );

    const partDir = path.join(PART_STORAGE, messageId);
    fs.mkdirSync(partDir, { recursive: true });
    fs.writeFileSync(
      path.join(partDir, `${partId}.json`),
      JSON.stringify(textPart, null, 2)
    );

    return true;
  } catch {
    return false;
  }
}

export class CompactionHook {
  private client: ApiClient;
  private config: Config;
  private tags: { user: string; project: string };
  private logger: Logger | null;
  private directory: string;
  private opencodeClient: OpencodeClient | null = null;
  private state: CompactionState = {
    lastCompactionTime: new Map(),
    compactionInProgress: new Set(),
    summarizedSessions: new Set(),
    savedSummarySessions: new Set(),
    latestSummaries: new Map(),
    agentConfigCheckpoints: new Map(),
    todoSnapshots: new Map(),
  };

  constructor(
    client: ApiClient,
    config: Config,
    tags: { user: string; project: string },
    logger: Logger | null,
    directory: string,
    opencodeClient?: OpencodeClient
  ) {
    this.client = client;
    this.config = config;
    this.tags = tags;
    this.logger = logger;
    this.directory = directory;
    this.opencodeClient = opencodeClient || null;
  }

  setOpenCodeClient(client: OpencodeClient): void {
    this.opencodeClient = client;
  }

  private async fetchProjectMemoriesForCompaction(sessionId?: string): Promise<string[]> {
    const memories: string[] = [];
    
    if (sessionId) {
      const cachedSummary = this.state.latestSummaries.get(sessionId);
      if (cachedSummary) {
        const locale = this.config.language === "auto" ? "en_US" : this.config.language;
        const prefix = locale === "zh_CN" ? "[会话摘要]\n" : "[Session Summary]\n";
        memories.push(prefix + cachedSummary.content);
        if (this.logger) {
          this.logger.debug("Using cached latest summary", {
            sessionID: sessionId,
            contentLength: cachedSummary.content.length,
            age: Date.now() - cachedSummary.timestamp,
          });
        }
      }
    }

    try {
      const dbMemories = await this.client.listMemories(this.tags.project, this.config.maxProjectMemories);
      const dbContents = dbMemories
        .map((m) => m.content)
        .filter((c): c is string => Boolean(c));
      memories.push(...dbContents);
    } catch {
      // Continue with cached summary only
    }

    return memories;
  }

  async injectCompactionContext(summarizeCtx: {
    sessionID: string;
    providerID?: string;
    modelID?: string;
    directory?: string;
    agent?: string;
  }): Promise<void> {
    if (this.logger) {
      this.logger.info("Injecting compaction context", { sessionID: summarizeCtx.sessionID });
    }

    const projectMemories = await this.fetchProjectMemoriesForCompaction(summarizeCtx.sessionID);
    const locale = this.config.language === "auto" ? "en_US" : this.config.language;
    const prompt = createCompactionPrompt(projectMemories, locale as Locale);

    const success = injectHookMessage(summarizeCtx.sessionID, prompt, {
      agent: summarizeCtx.agent,
      model: {
        providerID: summarizeCtx.providerID,
        modelID: summarizeCtx.modelID,
      },
      path: { cwd: summarizeCtx.directory || this.directory },
    });

    if (success && this.logger) {
      this.logger.info("Context injected with project memories", {
        sessionID: summarizeCtx.sessionID,
        memoriesCount: projectMemories.length,
      });
    }
  }

  async saveSummaryAsMemory(sessionId: string, summaryContent: string): Promise<string | null> {
    // Session Summary 不再保存到记忆数据库
    // 原因：Session Summary 是会话状态，不是知识，保存到记忆会引入噪音
    // 仅保留内存缓存用于压缩恢复
    if (this.logger) {
      this.logger.debug("Session Summary not saved to memory (disabled)", {
        sessionID: sessionId,
        contentLength: summaryContent.length,
      });
    }
    
    // 仍然更新内存缓存，供压缩恢复使用
    this.state.savedSummarySessions.add(sessionId);
    this.state.latestSummaries.set(sessionId, {
      content: summaryContent,
      timestamp: Date.now(),
    });
    
    return null;
  }

  markSummarized(sessionId: string): void {
    this.state.summarizedSessions.add(sessionId);
  }

  getLatestSummary(sessionId: string): string | null {
    const cached = this.state.latestSummaries.get(sessionId);
    if (!cached) return null;

    const MAX_CACHE_AGE = 5 * 60 * 1000;
    if (Date.now() - cached.timestamp > MAX_CACHE_AGE) {
      this.state.latestSummaries.delete(sessionId);
      return null;
    }

    return cached.content;
  }

  async captureAgentConfig(sessionId: string): Promise<void> {
    if (!this.opencodeClient || !sessionId) return;

    try {
      const response = await this.opencodeClient.session.messages({
        path: { id: sessionId },
        query: { directory: this.directory },
      });

      const messages = (response as { data?: Array<{ info?: MessageInfo }> }).data || [];
      const lastUserMessage = [...messages].reverse().find((m) => m.info?.role === "user");

      if (lastUserMessage?.info) {
        const info = lastUserMessage.info;
        const model = info.model?.providerID && info.model?.modelID
          ? { providerID: info.model.providerID, modelID: info.model.modelID }
          : undefined;

        const config: AgentConfig = {
          agent: info.agent,
          model,
          tools: (info as MessageInfo & { tools?: Record<string, boolean> }).tools,
        };

        this.state.agentConfigCheckpoints.set(sessionId, config);

        if (this.logger) {
          this.logger.debug("Captured agent config checkpoint", {
            sessionID: sessionId,
            agent: config.agent,
            hasModel: !!config.model,
            hasTools: !!config.tools,
          });
        }
      }
    } catch (e) {
      if (this.logger) {
        this.logger.error("Failed to capture agent config", { error: String(e) });
      }
    }
  }

  async recoverAgentConfig(sessionId: string): Promise<boolean> {
    if (!this.opencodeClient) return false;

    const checkpoint = this.state.agentConfigCheckpoints.get(sessionId);
    if (!checkpoint?.agent) return false;

    try {
      // 注意：不使用 noReply: true，让 agent 能继续工作
      await this.opencodeClient.session.promptAsync({
        path: { id: sessionId },
        body: {
          agent: checkpoint.agent,
          ...(checkpoint.model ? { model: checkpoint.model } : {}),
          ...(checkpoint.tools ? { tools: checkpoint.tools } : {}),
          parts: [{ type: "text", text: "[System: Resuming previous task context]" }],
        },
        query: { directory: this.directory },
      });

      if (this.logger) {
        this.logger.info("Recovered agent config after compaction", {
          sessionID: sessionId,
          agent: checkpoint.agent,
          hasModel: !!checkpoint.model,
        });
      }

      this.state.agentConfigCheckpoints.delete(sessionId);
      return true;
    } catch (e) {
      if (this.logger) {
        this.logger.error("Failed to recover agent config", { error: String(e) });
      }
      return false;
    }
  }

  async captureTodos(sessionId: string): Promise<void> {
    if (!this.opencodeClient || !sessionId) return;

    try {
      const response = await this.opencodeClient.session.todo({
        path: { id: sessionId },
      });

      const todos = (response as { data?: TodoItem[] })?.data || [];
      if (todos.length > 0) {
        this.state.todoSnapshots.set(sessionId, todos);

        if (this.logger) {
          this.logger.debug("Captured todo snapshot", {
            sessionID: sessionId,
            count: todos.length,
          });
        }
      }
    } catch (e) {
      if (this.logger) {
        this.logger.debug("Failed to capture todos (API may not be available)", { error: String(e) });
      }
    }
  }

  async restoreTodos(sessionId: string): Promise<void> {
    const snapshot = this.state.todoSnapshots.get(sessionId);
    if (!snapshot || snapshot.length === 0) return;

    try {
      const currentResponse = await this.opencodeClient?.session.todo({
        path: { id: sessionId },
      });

      const currentTodos = (currentResponse as { data?: TodoItem[] })?.data || [];
      if (currentTodos.length > 0) {
        this.state.todoSnapshots.delete(sessionId);
        if (this.logger) {
          this.logger.debug("Skipped todo restore (todos already present)", {
            sessionID: sessionId,
            count: currentTodos.length,
          });
        }
        return;
      }

      const writer = await this.resolveTodoWriter();
      if (!writer) {
        if (this.logger) {
          this.logger.debug("Skipped todo restore (Todo.update unavailable)", {
            sessionID: sessionId,
          });
        }
        return;
      }

      try {
        await writer({ sessionID: sessionId, todos: snapshot });
        if (this.logger) {
          this.logger.info("Restored todos after compaction", {
            sessionID: sessionId,
            count: snapshot.length,
          });
        }
      } catch (e) {
        if (this.logger) {
          this.logger.error("Failed to restore todos", {
            sessionID: sessionId,
            error: String(e),
          });
        }
      }
    } catch (e) {
      if (this.logger) {
        this.logger.debug("Failed to restore todos", { error: String(e) });
      }
    } finally {
      this.state.todoSnapshots.delete(sessionId);
    }
  }

  private async resolveTodoWriter(): Promise<((params: { sessionID: string; todos: TodoItem[] }) => Promise<void>) | null> {
    try {
      // eslint-disable-next-line @typescript-eslint/no-require-imports
      const mod = await import(/* webpackIgnore: true */ "opencode/session/todo");
      const update = (mod as { Todo?: { update?: unknown } }).Todo?.update;
      if (typeof update === "function") {
        return update as (params: { sessionID: string; todos: TodoItem[] }) => Promise<void>;
      }
    } catch {
      return null;
    }
    return null;
  }

  clearSessionState(sessionId: string): void {
    this.state.agentConfigCheckpoints.delete(sessionId);
    this.state.todoSnapshots.delete(sessionId);
    this.state.latestSummaries.delete(sessionId);
    this.state.summarizedSessions.delete(sessionId);
    this.state.savedSummarySessions.delete(sessionId);
  }

  async checkAndTriggerCompaction(
    sessionId: string,
    lastAssistant: MessageInfo,
    ctxClient: unknown
  ): Promise<void> {
    if (this.state.compactionInProgress.has(sessionId)) return;

    const lastCompaction = this.state.lastCompactionTime.get(sessionId) || 0;
    if (Date.now() - lastCompaction < COMPACTION_COOLDOWN_MS) return;

    if (lastAssistant.summary === true) return;

    const tokens = lastAssistant.tokens;
    if (!tokens) {
      if (this.logger) {
        this.logger.debug("No tokens info in message", { sessionID: sessionId });
      }
      return;
    }

    let modelId = lastAssistant.modelID || "";
    let providerId = lastAssistant.providerID || "";
    let agent: string | undefined;

    const messageDir = getMessageDir(sessionId);
    const storedMessage = messageDir ? findNearestMessageWithFields(messageDir) : null;

    if (!providerId || !modelId) {
      if (storedMessage?.model?.providerID) {
        providerId = storedMessage.model.providerID;
      }
      if (storedMessage?.model?.modelID) {
        modelId = storedMessage.model.modelID;
      }
    }

    if (storedMessage) {
      agent = storedMessage.agent;
    }

    const contextLimit = DEFAULT_CONTEXT_LIMIT;

    const cacheRead = tokens.cache?.read || 0;
    const totalUsed = (tokens.input || 0) + cacheRead + (tokens.output || 0);

    if (totalUsed < MIN_TOKENS_FOR_COMPACTION) {
      if (this.logger) {
        this.logger.debug("Below min tokens threshold", {
          sessionID: sessionId,
          totalUsed,
          minRequired: MIN_TOKENS_FOR_COMPACTION,
        });
      }
      return;
    }

    const usageRatio = totalUsed / contextLimit;

    if (this.logger) {
      this.logger.info("Compaction check", {
        sessionID: sessionId,
        totalUsed,
        contextLimit,
        usageRatio: Math.round(usageRatio * 100) / 100,
        threshold: this.config.compactionThreshold,
        willTrigger: usageRatio >= this.config.compactionThreshold,
      });
    }

    if (usageRatio < this.config.compactionThreshold) return;

    this.state.compactionInProgress.add(sessionId);
    this.state.lastCompactionTime.set(sessionId, Date.now());

    if (!providerId || !modelId) {
      this.state.compactionInProgress.delete(sessionId);
      return;
    }

    if (this.logger) {
      this.logger.compactionTriggered({
        sessionId,
        usageRatio,
        threshold: this.config.compactionThreshold,
        totalTokens: totalUsed,
      });
    }

    try {
      if (this.opencodeClient) {
        await this.opencodeClient.tui.showToast({
          body: {
            title: "Preemptive Compaction",
            message: `Context at ${Math.round(usageRatio * 100)}% - compacting with Memory Recall context...`,
            variant: "warning",
            duration: 3000,
          },
        }).catch(() => {});
      }

      await this.injectCompactionContext({
        sessionID: sessionId,
        providerID: providerId,
        modelID: modelId,
        directory: this.directory,
        agent,
      });

      this.state.summarizedSessions.add(sessionId);

      if (this.opencodeClient) {
        await this.opencodeClient.session.summarize({
          path: { id: sessionId },
          body: { providerID: providerId, modelID: modelId },
          query: { directory: this.directory },
        });

        await this.opencodeClient.tui.showToast({
          body: {
            title: "Compaction Complete",
            message: "Session compacted with Memory Recall context.",
            variant: "success",
            duration: 2000,
          },
        }).catch(() => {});
      }

      this.state.compactionInProgress.delete(sessionId);

      if (this.logger) {
        this.logger.compactionComplete({ sessionId, durationMs: 0 });
      }
    } catch (e) {
      if (this.logger) {
        this.logger.error("Compaction failed", { sessionID: sessionId, error: String(e) });
      }
      this.state.compactionInProgress.delete(sessionId);
    }
  }

  private async waitForSummaryMessage(
    sessionId: string,
    maxAttempts: number = 10,
    delayMs: number = 500
  ): Promise<{ content: string; messageId: string } | null> {
    if (!this.opencodeClient) return null;

    for (let attempt = 0; attempt < maxAttempts; attempt++) {
      if (attempt > 0) {
        await new Promise(resolve => setTimeout(resolve, delayMs));
      }

      try {
        const resp = await this.opencodeClient.session.messages({
          path: { id: sessionId },
          query: { directory: this.directory },
        });

        const messages = (resp.data ?? resp) as Array<{ 
          id?: string;
          info: { role?: string; summary?: boolean }; 
          parts?: Array<{ type: string; text?: string; synthetic?: boolean }> 
        }>;

        const summaryMessages = messages.filter(m => 
          m.info.role === "assistant" && m.info.summary === true
        );

        if (summaryMessages.length > 0) {
          const latestSummary = summaryMessages[summaryMessages.length - 1];
          
          if (latestSummary?.parts) {
            // 过滤掉 synthetic parts（如 nudge 指令），避免系统指令被保存到记忆中
            const textParts = latestSummary.parts.filter(
              p => p.type === "text" && p.text && !p.synthetic
            );
            const summaryContent = textParts.map(p => p.text).join("\n");

            if (summaryContent && summaryContent.length >= 100) {
              if (this.logger) {
                this.logger.debug("Summary message found", {
                  sessionID: sessionId,
                  attempt: attempt + 1,
                  contentLength: summaryContent.length,
                });
              }
              return {
                content: summaryContent,
                messageId: latestSummary.id || "",
              };
            }
          }
        }

        if (this.logger) {
          this.logger.debug("Waiting for summary generation", {
            sessionID: sessionId,
            attempt: attempt + 1,
            maxAttempts,
          });
        }
      } catch (e) {
        if (this.logger) {
          this.logger.warn("Failed to fetch messages during polling", {
            sessionID: sessionId,
            attempt: attempt + 1,
            error: String(e),
          });
        }
      }
    }

    return null;
  }

  async handleSummaryMessage(
    sessionId: string,
    messageInfo: MessageInfo,
    ctxClient: unknown
  ): Promise<void> {
    if (!this.state.summarizedSessions.has(sessionId)) return;

    this.state.summarizedSessions.delete(sessionId);

    if (!this.config.enableSummaryCapture) return;

    // Use polling to wait for summary generation
    if (this.opencodeClient) {
      if (this.logger) {
        this.logger.info("Waiting for summary generation", { sessionID: sessionId });
      }

      const result = await this.waitForSummaryMessage(sessionId);
      
      if (result) {
        const memoryId = await this.saveSummaryAsMemory(sessionId, result.content);
        if (memoryId && this.logger) {
          this.logger.info("Summary saved as memory (from API)", {
            sessionID: sessionId,
            memoryID: memoryId,
            contentLength: result.content.length,
          });
        }
        return;
      }

      if (this.logger) {
        this.logger.warn("Summary not found after polling, falling back to file system", {
          sessionID: sessionId,
        });
      }
    }

    // Fallback to file system extraction
    const messageId = messageInfo.id;
    if (!messageId) {
      if (this.logger) {
        this.logger.warn("No message ID in summary", { sessionID: sessionId });
      }
      return;
    }

    const summaryContent = extractSummaryContent(messageId);
    if (!summaryContent) {
      if (this.logger) {
        this.logger.warn("Could not extract summary content", { 
          sessionID: sessionId, 
          messageID: messageId 
        });
      }
      return;
    }

    try {
      const memoryId = await this.saveSummaryAsMemory(sessionId, summaryContent);
      if (memoryId && this.logger) {
        this.logger.info("Summary saved as memory (from file)", {
          sessionID: sessionId,
          memoryID: memoryId,
          contentLength: summaryContent.length,
        });
      }
    } catch (e) {
      if (this.logger) {
        this.logger.error("Failed to save summary", { 
          sessionID: sessionId, 
          error: String(e) 
        });
      }
    }
  }

  async handleEvent(event: { type: string; properties?: Record<string, unknown> }, ctxClient: unknown): Promise<void> {
    const eventType = event.type;
    const props = event.properties || {};

    if (eventType === "session.deleted") {
      const sessionInfo = (props.info as Record<string, unknown>) || {};
      const sessionId = sessionInfo.id as string | undefined;
      if (sessionId) {
        this.state.lastCompactionTime.delete(sessionId);
        this.state.compactionInProgress.delete(sessionId);
        this.state.summarizedSessions.delete(sessionId);
        this.state.savedSummarySessions.delete(sessionId);
        this.state.latestSummaries.delete(sessionId);
      }
      return;
    }

    if (eventType === "message.updated") {
      const info = (props.info as MessageInfo) || {};
      const sessionId = info.sessionID;
      if (!sessionId) return;

      // Check if this is a summary message (explicit)
      if (info.role === "assistant" && info.summary === true && info.finish) {
        await this.handleSummaryMessage(sessionId, info, ctxClient);
        return;
      }

      // OpenCode may not set summary: true, so we check summarizedSessions
      if (info.role === "assistant" && info.finish && this.state.summarizedSessions.has(sessionId)) {
        await this.handleSummaryMessage(sessionId, info, ctxClient);
        return;
      }

      if (info.role !== "assistant" || !info.finish) return;

      await this.checkAndTriggerCompaction(sessionId, info, ctxClient);
      return;
    }

    if (eventType === "session.idle") {
      const sessionId = props.sessionID as string | undefined;
      if (!sessionId) return;
    }
  }
}
