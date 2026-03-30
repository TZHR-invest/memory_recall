import * as fs from "fs";
import * as path from "path";
import * as os from "os";
import type { ApiClient } from "./client";
import type { Config } from "./config";
import type { Logger } from "./logging";
import { detectLocaleFromText, getLocale, type Locale } from "./i18n";

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

  return `[COMPACTION CONTEXT INJECTION]

When summarizing this session, you MUST include the following sections in your summary:

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

${sections.must_not_do}
- Things that were explicitly forbidden
- Approaches that failed and should not be retried
- User's explicit restrictions or preferences
- Anti-patterns identified during the session
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
  private state: CompactionState = {
    lastCompactionTime: new Map(),
    compactionInProgress: new Set(),
    summarizedSessions: new Set(),
  };

  constructor(
    client: ApiClient,
    config: Config,
    tags: { user: string; project: string },
    logger: Logger | null,
    directory: string
  ) {
    this.client = client;
    this.config = config;
    this.tags = tags;
    this.logger = logger;
    this.directory = directory;
  }

  private async fetchProjectMemoriesForCompaction(): Promise<string[]> {
    try {
      const memories = await this.client.listMemories(this.tags.project, this.config.maxProjectMemories);
      return memories
        .map((m) => m.content)
        .filter((c): c is string => Boolean(c));
    } catch {
      return [];
    }
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

    const projectMemories = await this.fetchProjectMemoriesForCompaction();
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
    const minSummaryLength = 100;
    if (!summaryContent || summaryContent.length < minSummaryLength) {
      if (this.logger) {
        this.logger.warn("Summary too short to save", {
          sessionID: sessionId,
          length: summaryContent.length,
        });
      }
      return null;
    }

    try {
      const locale = this.config.language === "auto" ? "en_US" : this.config.language;
      const prefix = locale === "zh_CN" ? "[会话摘要]\n" : "[Session Summary]\n";

      const result = await this.client.addMemory(
        prefix + summaryContent,
        this.tags.project,
        false,
        "conversation"
      );

      if (result?.id) {
        if (this.logger) {
          this.logger.summaryCaptured({
            sessionId,
            memoryId: result.id,
            contentLength: summaryContent.length,
          });
        }
        return result.id;
      }
    } catch (e) {
      if (this.logger) {
        this.logger.error("Failed to save summary", { error: String(e) });
      }
    }
    return null;
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
      await this.injectCompactionContext({
        sessionID: sessionId,
        providerID: providerId,
        modelID: modelId,
        directory: this.directory,
        agent,
      });

      this.state.summarizedSessions.add(sessionId);

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

  async handleSummaryMessage(
    sessionId: string,
    messageInfo: MessageInfo,
    ctxClient: unknown
  ): Promise<void> {
    if (!this.state.summarizedSessions.has(sessionId)) return;

    this.state.summarizedSessions.delete(sessionId);

    if (!this.config.enableSummaryCapture) return;
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
      }
      return;
    }

    if (eventType === "message.updated") {
      const info = (props.info as MessageInfo) || {};
      const sessionId = info.sessionID;
      if (!sessionId) return;

      if (info.role === "assistant" && info.summary === true && info.finish) {
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
