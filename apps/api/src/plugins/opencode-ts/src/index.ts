import type { Plugin, PluginInput, Hooks } from "@opencode-ai/plugin";
import { loadConfig, isConfigured, getUserTag, getProjectTag } from "./config";
import { ApiClient } from "./client";
import { createTool, detectMemoryKeyword } from "./tool";
import { injectContext, getMemoryNudge, type ContextResult } from "./context";
import { detectLocaleFromText } from "./i18n";
import { initLogging } from "./logging";
import { CompactionHook } from "./compaction";
import { EventHandler } from "./events";
import { DocumentTracker } from "./document-tracker";
import { FileWatcher } from "./file-watcher";

const injectedSessions = new Set<string>();

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

  let documentTracker: DocumentTracker | null = null;
  if (config.enableDocumentTracking && isConfigured(config)) {
    documentTracker = new DocumentTracker(client, config, input.directory);
    documentTracker.scanAndMemorize().then((count) => {
      if (count > 0) {
        logger.info("Documents tracked", { count });
      }
    }).catch((e) => {
      logger.error("Document tracking failed", { error: String(e) });
    });
  }

  let fileWatcher: FileWatcher | null = null;
  if (config.enableDocumentTracking && documentTracker) {
    fileWatcher = new FileWatcher(config, documentTracker, logger, input.directory);
    fileWatcher.start().catch((e) => {
      logger.warn("File watcher failed to start", { error: String(e) });
    });
  }

  const tool = createTool(client, config);

  const compactionHook = new CompactionHook(client, config, tags, logger, input.directory);

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

    if (injectedSessions.has(sessionId)) return;
    injectedSessions.add(sessionId);

    try {
      const result = await injectContext(client, userMessage, userTag, projectTag, {
        injectProfile: config.injectProfile,
        maxProfileItems: config.maxProfileItems,
        maxProjectMemories: config.maxProjectMemories,
        maxMemories: config.maxMemories,
        language: config.language,
        enableChunksSearch: config.enableChunksSearch,
        maxChunks: config.maxChunks,
        chunksSimilarityThreshold: config.chunksSimilarityThreshold,
        chunksDocTypes: config.chunksDocTypes,
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
        logger.contextInjected({
          sessionId,
          durationMs: Date.now() - startTime,
          contextLength: result.context.length,
          profileCount: result.profileCount,
          projectCount: result.projectCount,
          userCount: result.userCount,
          chunksCount: result.chunksCount,
        });
      }
    } catch (e) {
      logger.error("Context injection failed", { error: String(e) });
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
    const eventType = eventData.event?.type;
    if (!eventType) return;

    // Skip high-frequency UI events
    if (SKIP_EVENTS.has(eventType)) return;

    logger.eventReceived({ eventType });

    const handlers = eventHandler.getHandlers();
    if (eventType in handlers) {
      await handlers[eventType](eventData.event as { type: string; properties?: Record<string, unknown> }, null);
    }
  };

  const experimentalSessionCompacting: NonNullable<Hooks["experimental.session.compacting"]> = async (inputData, outputData) => {
    const sessionId = inputData.sessionID;
    logger.info("Session compacting", { sessionId });

    if (config.enableSummaryCapture) {
      try {
        const projectMemories = await client.listMemories(projectTag, 5);
        if (projectMemories.length > 0) {
          const context = projectMemories.map((m) => "- " + m.content).join("\n");
          outputData.context.push("[Project Memories]\n" + context);
        }
      } catch (e) {
        logger.error("Failed to inject project memories during compaction", { error: String(e) });
      }
    }
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
