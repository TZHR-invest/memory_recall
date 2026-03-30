/**
 * Structured JSON logging for Memory Recall OpenCode plugin
 * Uses async writes to avoid blocking the main thread
 */

import * as fs from "fs";
import * as path from "path";
import * as os from "os";

export type LogLevel = "debug" | "info" | "warn" | "error";

const LEVEL_PRIORITY: Record<LogLevel, number> = {
  debug: 0,
  info: 1,
  warn: 2,
  error: 3,
};

interface LogEntry {
  timestamp: string;
  level: LogLevel;
  message: string;
  data?: Record<string, unknown>;
}

export class Logger {
  private logFile: string;
  private level: LogLevel;
  private writeQueue: string[] = [];
  private flushScheduled = false;

  constructor(logFile: string = "~/.memory-recall-opencode.log", level: LogLevel = "info") {
    this.logFile = logFile.replace(/^~/, os.homedir());
    this.level = level;
    this.ensureLogFile();
    this.writeSessionStart();
  }

  private ensureLogFile(): void {
    const dir = path.dirname(this.logFile);
    if (!fs.existsSync(dir)) {
      fs.mkdirSync(dir, { recursive: true });
    }
    if (!fs.existsSync(this.logFile)) {
      fs.writeFileSync(this.logFile, "");
    }
  }

  private writeSessionStart(): void {
    this.write("info", "Session started", {});
  }

  private shouldLog(level: LogLevel): boolean {
    return LEVEL_PRIORITY[level] >= LEVEL_PRIORITY[this.level];
  }

  private scheduleFlush(): void {
    if (this.flushScheduled) return;
    this.flushScheduled = true;

    setImmediate(() => {
      this.flush();
      this.flushScheduled = false;
    });
  }

  private flush(): void {
    if (this.writeQueue.length === 0) return;

    const content = this.writeQueue.join("");
    this.writeQueue = [];

    fs.writeFile(this.logFile, content, { flag: "a", encoding: "utf-8" }, () => {});
  }

  private write(level: LogLevel, message: string, data?: Record<string, unknown>): void {
    if (!this.shouldLog(level)) {
      return;
    }

    const entry: LogEntry = {
      timestamp: new Date().toISOString(),
      level,
      message,
    };

    if (data && Object.keys(data).length > 0) {
      entry.data = data;
    }

    this.writeQueue.push(JSON.stringify(entry) + "\n");
    this.scheduleFlush();
  }

  debug(message: string, data?: Record<string, unknown>): void {
    this.write("debug", message, data);
  }

  info(message: string, data?: Record<string, unknown>): void {
    this.write("info", message, data);
  }

  warn(message: string, data?: Record<string, unknown>): void {
    this.write("warn", message, data);
  }

  error(message: string, data?: Record<string, unknown>): void {
    this.write("error", message, data);
  }

  toolExecution(params: {
    mode: string;
    scope?: string;
    success: boolean;
    durationMs?: number;
    error?: string;
  }): void {
    const data: Record<string, unknown> = {
      mode: params.mode,
      success: params.success,
    };
    if (params.scope) data.scope = params.scope;
    if (params.durationMs) data.duration_ms = params.durationMs;
    if (params.error) data.error = params.error;

    this.write(params.success ? "info" : "error", "Tool executed", data);
  }

  contextInjected(params: {
    sessionId: string;
    durationMs: number;
    profileCount?: number;
    projectCount?: number;
    userCount?: number;
    chunksCount?: number;
    contextLength?: number;
    graphCount?: number;
    entityCount?: number;
  }): void {
    this.write("info", "Context injected", {
      session_id: params.sessionId,
      duration_ms: params.durationMs,
      profile_count: params.profileCount || 0,
      project_count: params.projectCount || 0,
      user_count: params.userCount || 0,
      chunks_count: params.chunksCount || 0,
      context_length: params.contextLength || 0,
      graph_count: params.graphCount || 0,
      entity_count: params.entityCount || 0,
    });
  }

  compactionTriggered(params: {
    sessionId: string;
    usageRatio: number;
    threshold: number;
    totalTokens: number;
  }): void {
    this.write("info", "Compaction triggered", {
      session_id: params.sessionId,
      usage_ratio: Math.round(params.usageRatio * 100) / 100,
      threshold: params.threshold,
      total_tokens: params.totalTokens,
    });
  }

  compactionComplete(params: { sessionId: string; durationMs: number }): void {
    this.write("info", "Compaction complete", {
      session_id: params.sessionId,
      duration_ms: params.durationMs,
    });
  }

  summaryCaptured(params: {
    sessionId: string;
    memoryId: string;
    contentLength: number;
  }): void {
    this.write("info", "Session summary captured", {
      session_id: params.sessionId,
      memory_id: params.memoryId,
      content_length: params.contentLength,
    });
  }

  keywordDetected(params: {
    sessionId: string;
    keyword: string;
    language: string;
  }): void {
    this.write("debug", "Memory keyword detected", {
      session_id: params.sessionId,
      keyword: params.keyword,
      language: params.language,
    });
  }

  documentTracked(params: {
    filePath: string;
    action: string;
    memoryId?: string;
  }): void {
    const data: Record<string, unknown> = {
      file_path: params.filePath,
      action: params.action,
    };
    if (params.memoryId) data.memory_id = params.memoryId;
    this.write("info", "Document tracked", data);
  }

  pluginInitialized(params: {
    directory: string;
    userTag: string;
    projectTag: string;
    configured: boolean;
  }): void {
    this.write("info", "Plugin initialized", {
      directory: params.directory,
      user_tag: params.userTag,
      project_tag: params.projectTag,
      configured: params.configured,
    });
  }

  eventReceived(params: { eventType: string; sessionId?: string }): void {
    const data: Record<string, unknown> = { event_type: params.eventType };
    if (params.sessionId) data.session_id = params.sessionId;
    this.write("debug", "Event received", data);
  }
}

let _logger: Logger | null = null;

export function getLogger(
  logFile: string = "~/.memory-recall-opencode.log",
  level: LogLevel = "info",
  reload: boolean = false
): Logger {
  if (!_logger || reload) {
    _logger = new Logger(logFile, level);
  }
  return _logger;
}

export function initLogging(logFile: string, level: LogLevel): Logger {
  return getLogger(logFile, level, true);
}
