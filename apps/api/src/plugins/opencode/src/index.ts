import type { Plugin, PluginInput, Hooks } from "@opencode-ai/plugin";
import { loadConfig, isConfigured, getUserTag, getProjectTag, type InjectionStrategy } from "./config";
import { ApiClient } from "./client";
import { createTool, detectMemoryKeyword } from "./tool";
import { injectContextFromBackend, getMemoryNudge, getAiGuidance, type ContextResult } from "./context";
import { detectLocaleFromText, getLocale, type Locale } from "./i18n";
import { initLogging } from "./logging";
import { CompactionHook } from "./compaction";
import { EventHandler } from "./events";
import { DocumentTracker } from "./document-tracker";
import { FileWatcher } from "./file-watcher";
import {
  SessionTrackerManager,
  calculateDynamicRecallSize,
} from "./tracker";
import { shouldTriggerRecall, findTriggerKeyword } from "./recall-trigger";
import { TaskQueue, type Task } from "./queue";

const sessionTrackerManager = new SessionTrackerManager();

// 注入失败 toast 节流（ADR-0005）：按 sessionID 计数，每会话最多 3 次，之后静默。
const toastThrottle = new Map<string, number>();
const MAX_TOASTS_PER_SESSION = 3;

interface TextPart {
  type: "text";
  text: string;
}

function isTextPart(part: unknown): part is TextPart {
  return typeof part === "object" && part !== null && (part as {type?: string}).type === "text" && typeof (part as {text?: unknown}).text === "string";
}

async function server(input: PluginInput, options: Record<string, unknown> = {}): Promise<Hooks> {
  const config = loadConfig(options);
  const userTag = getUserTag(config);
  const projectTag = getProjectTag(config, input.directory);

  const logger = initLogging(config.logFile, config.logLevel);

  const client = new ApiClient(config, userTag, projectTag);

  const tags = { user: userTag, project: projectTag };

  logger.pluginInitialized({
    directory: input.directory,
    userTag,
    projectTag,
    configured: isConfigured(config),
  });

  if (!isConfigured(config)) {
    logger.warn("API key not configured", { hint: "Set MEMORY_RECALL_API_KEY or add apiKey to config" });
  }

  if (options.enableSmartRecall !== undefined && options.injectionStrategy === undefined) {
    logger.warn("Config deprecation: 'enableSmartRecall' is deprecated. Use 'injectionStrategy' instead.", {
      hint: "Set 'injectionStrategy: \"smart\"' for smart recall, or 'injectionStrategy: \"always\"' for legacy behavior"
    });
  }

  let documentTracker: DocumentTracker | null = null;
  if (config.enableDocumentTracking && isConfigured(config)) {
    // DocumentTracker created but NOT auto-importing - user must trigger via tool
    documentTracker = new DocumentTracker(client, config, input.directory);
    logger.info("Document tracker ready", { 
      hint: "Use 'import-docs' mode in memory-recall tool to import project documents" 
    });
  }

  // 初始化异步队列（如果启用）
  let taskQueue: TaskQueue | undefined;
  if (config.asyncQueue.enabled) {
    taskQueue = new TaskQueue({
      maxConcurrency: config.asyncQueue.maxConcurrency,
      maxSize: config.asyncQueue.maxSize,
      retryPolicy: config.asyncQueue.retryPolicy,
    });

    // 设置任务执行器
    taskQueue.setExecutor(async (task: Task) => {
      const timeoutMs = config.asyncQueue.taskTimeoutMs;
      if (task.type === "add") {
        const { content, containerTag, isStatic, memoryType } = task.payload;
        if (content && containerTag) {
          await client.addMemory(content, containerTag, isStatic || false, memoryType, timeoutMs);
        }
      } else if (task.type === "import-doc") {
        if (documentTracker && task.payload.filePath) {
          await documentTracker.importSingleFile(task.payload.filePath, timeoutMs);
        }
      }
    });

    // 启动队列处理
    taskQueue.start();
    logger.info("Async queue started", { 
      maxConcurrency: config.asyncQueue.maxConcurrency,
      maxSize: config.asyncQueue.maxSize 
    });
  }

  // 初始化文件监听（在 taskQueue 之后）
  let fileWatcher: FileWatcher | null = null;
  if (config.enableDocumentTracking && documentTracker) {
    fileWatcher = new FileWatcher(config, documentTracker, logger, input.directory, taskQueue);
    fileWatcher.start().catch((e) => {
      logger.warn("File watcher failed to start", { error: String(e) });
    });
  }

  const tool = createTool(client, config, documentTracker, taskQueue);

  const opencodeClient = input.client;
  const compactionHook = new CompactionHook(client, config, tags, logger);

  const eventHandler = new EventHandler(config, compactionHook, tags, logger);

  const chatMessageHook: NonNullable<Hooks["chat.message"]> = async (inputData, outputData) => {
    const sessionId = inputData.sessionID;
    const messageId = outputData.message?.id;
    const startTime = Date.now();

    if (!messageId) return;

    const parts = outputData.parts || [];
    const textParts = parts.filter(isTextPart);
    if (textParts.length === 0) return;

    const userMessage = textParts.map((p) => p.text).join("\n");
    if (!userMessage.trim()) return;

    const locale = detectLocaleFromText(userMessage, config.language);

    if (detectMemoryKeyword(userMessage)) {
      const nudge = getMemoryNudge(locale);
      outputData.parts.push({
        id: "prt_memory_nudge_" + Date.now(),
        sessionID: sessionId,
        messageID: messageId,
        type: "text",
        text: nudge,
        synthetic: true,
      } as never);
      logger.keywordDetected({ sessionId, keyword: "detected", language: locale });
    }

    const tracker = sessionTrackerManager.getTracker(sessionId);
    const strategy = config.injectionStrategy;
    
    let shouldInject = false;
    let isInitialInjection = false;
    let triggerKeyword: string | null = null;
    
    if (strategy === "once") {
      if (tracker.needsInitialInjection()) {
        shouldInject = true;
        isInitialInjection = true;
      }
    } else if (strategy === "smart") {
      if (tracker.needsInitialInjection()) {
        shouldInject = true;
        isInitialInjection = true;
      } else if (shouldTriggerRecall(userMessage, config.smartRecall)) {
        shouldInject = true;
        isInitialInjection = false;
        triggerKeyword = findTriggerKeyword(userMessage, config.smartRecall);
      }
    } else {
      shouldInject = true;
      isInitialInjection = tracker.needsInitialInjection();
    }

    if (!shouldInject) return;

    const maxMemoriesToUse = isInitialInjection 
      ? config.maxMemories 
      : config.smartRecall.maxAdditionalMemories;
    
    const maxChunksToUse = isInitialInjection 
      ? config.initialInjection.maxChunks 
      : config.smartRecall.maxAdditionalChunks;

    const dynamicMaxMemories = config.dynamicRecallSize
      ? calculateDynamicRecallSize(tracker.size(), maxMemoriesToUse)
      : maxMemoriesToUse;

    try {
      const result: ContextResult = await injectContextFromBackend(client, userMessage, userTag, projectTag, {
        injectProfile: isInitialInjection ? config.initialInjection.profile : false,
        maxProfileItems: config.maxProfileItems,
        maxStaticProfileItems: config.maxStaticProfileItems,
        maxProjectMemories: isInitialInjection ? config.maxProjectMemories : config.smartRecall.maxAdditionalMemories,
        maxMemories: dynamicMaxMemories,
        maxChunks: maxChunksToUse,
        language: config.language,
        semanticDedup: config.semanticDedup,
        enableGraphRecall: config.enableGraphRecall,
        enableEntityRecall: config.enableEntityRecall,
        graphMaxDepth: config.graphMaxDepth,
        graphMaxNodes: config.graphMaxNodes,
        enableChunksSearch: config.enableChunksSearch,
        chunksSimilarityThreshold: config.chunksSimilarityThreshold,
        similarityThreshold: config.similarityThreshold,
        entityChunkThreshold: config.entityChunkThreshold,
      });

      if (result.context) {
        outputData.parts.unshift({
          id: "prt_memory_context_" + Date.now(),
          sessionID: sessionId,
          messageID: messageId,
          type: "text",
          text: result.context,
          synthetic: true,
        } as never);
        
        tracker.addMany(result.injectedMemoryIds);
        
        if (isInitialInjection) {
          tracker.markInitialInjected();
        }
        
        logger.contextInjected({
          sessionId,
          durationMs: Date.now() - startTime,
          contextLength: result.context.length,
          profileCount: result.profileCount,
          projectCount: result.projectCount,
          userCount: result.userCount,
          chunksCount: result.chunksCount,
          graphCount: result.graphCount,
          entityCount: result.entityCount,
          injectionStrategy: strategy,
          isInitial: isInitialInjection,
          triggerKeyword: triggerKeyword,
        });
      }
    } catch (e) {
      logger.error("Context injection failed", { sessionId, error: String(e) });

      // toast 节流：错误详情只进日志，toast 每会话最多 3 次，之后不再打扰
      const shown = toastThrottle.get(sessionId) || 0;
      if (shown < MAX_TOASTS_PER_SESSION) {
        toastThrottle.set(sessionId, shown + 1);
        const remaining = MAX_TOASTS_PER_SESSION - (shown + 1);
        const msg = remaining > 0
          ? "Memory recall failed to inject context"
          : "Memory recall errors will no longer be shown; see ~/.memory-recall-opencode.log";
        try {
          await opencodeClient.tui.showToast({
            body: { title: "Memory Recall", message: msg, variant: "warning", duration: 2500 },
          }).catch(() => {});
        } catch {
          // toast 失败不影响主流程
        }
      }
    }
  };

  // Skip UI events that don't need processing
  const SKIP_EVENTS = new Set([
    "tui.toast.show",
    "tui.toast.hide",
    "tui.status",
    "tui.render",
    "tui.focus",
    "tui.blur",
  ]);

  const eventHook: NonNullable<Hooks["event"]> = async (eventData) => {
    if (!config.enableEventHandling) return;

    const eventType = eventData.event?.type;
    if (!eventType) return;

    // Skip high-frequency UI events
    if (SKIP_EVENTS.has(eventType)) return;

    logger.eventReceived({ eventType });

    if (eventType === "session.deleted") {
      const info = (eventData.event?.properties?.info as Record<string, unknown>) || {};
      const sessionId = info.id as string | undefined;
      if (sessionId) {
        toastThrottle.delete(sessionId);
        sessionTrackerManager.clearSession(sessionId);
      }
    }

    const handlers = eventHandler.getHandlers();
    if (eventType in handlers) {
      await handlers[eventType](eventData.event as { type: string; properties?: Record<string, unknown> }, opencodeClient);
    }
  };

  const experimentalSessionCompacting: NonNullable<Hooks["experimental.session.compacting"]> = async (inputData, outputData) => {
    const sessionId = inputData.sessionID;
    logger.info("Session compacting", { sessionId });

    // 共存检测：若已有其他插件设置 output.prompt 接管压缩，则跳过注入，避免静默失效
    if ((outputData as { prompt?: unknown }).prompt !== undefined) {
      logger.warn("Skipping compaction context: another plugin took over via output.prompt", { sessionId });
      return;
    }

    const locale = config.language === "auto"
      ? (detectLocaleFromText("", config.language) as Locale)
      : (config.language as Locale);
    const aiGuidance = getAiGuidance(locale === "zh_CN");

    // hook 内 fail-open：注入失败只记日志，绝不阻断压缩主流程
    await compactionHook.injectCompactionContext(sessionId, outputData.context, aiGuidance);
  };

  return {
    tool,
    "chat.message": chatMessageHook,
    "experimental.session.compacting": experimentalSessionCompacting,
    event: eventHook,
  };
}

const plugin: Plugin = server;

export default plugin;
export { server };
