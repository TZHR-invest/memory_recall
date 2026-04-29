import * as fs from "fs";
import * as path from "path";
import type { Config } from "./config";
import type { DocumentTracker } from "./document-tracker";
import type { Logger } from "./logging";
import type { TaskQueue } from "./queue";

const DEBOUNCE_MS = 500;

export class FileWatcher {
  private config: Config;
  private documentTracker: DocumentTracker;
  private logger: Logger | null;
  private directory: string;
  private taskQueue: TaskQueue | null;
  private watcher: fs.FSWatcher | null = null;
  private pendingChanges: Map<string, number> = new Map();
  private debounceTimer: NodeJS.Timeout | null = null;
  private running = false;

  constructor(
    config: Config,
    documentTracker: DocumentTracker,
    logger: Logger | null,
    directory: string,
    taskQueue?: TaskQueue
  ) {
    this.config = config;
    this.documentTracker = documentTracker;
    this.logger = logger;
    this.directory = directory;
    this.taskQueue = taskQueue || null;
  }

  private shouldTrack(filePath: string): boolean {
    if (!fs.existsSync(filePath) || !fs.statSync(filePath).isFile()) {
      return false;
    }

    const fileName = path.relative(this.directory, filePath);
    for (const pattern of this.config.trackedDocPatterns) {
      if (pattern.startsWith("*")) {
        if (fileName.endsWith(pattern.slice(1))) return true;
      } else if (pattern.includes("*")) {
        // 转义正则特殊字符，但保留 * 作为通配符
        const escaped = pattern
          .replace(/\./g, "\\.")
          .replace(/\+/g, "\\+")
          .replace(/\?/g, "\\?");
        const regex = new RegExp(
          "^" + escaped.replace(/\*\*/g, ".*").replace(/\*/g, "[^/]*") + "$"
        );
        if (regex.test(fileName)) return true;
      } else {
        if (fileName === pattern) return true;
      }
    }

    return false;
  }

  private async processDebouncedChanges(): Promise<void> {
    if (this.pendingChanges.size === 0) return;

    const changes = Array.from(this.pendingChanges.keys());
    this.pendingChanges.clear();

    if (this.logger) {
      this.logger.debug("Processing debounced file changes", { count: changes.length });
    }

    for (const relPath of changes) {
      try {
        const filePath = path.join(this.directory, relPath);

        // 检查文件是否有变化
        const hasChanged = await this.documentTracker.hasFileChanged(filePath);

        if (!hasChanged) {
          continue; // 无变化，跳过
        }

        // 如果启用异步队列，使用队列
        if (this.config.asyncQueue.enabled && this.taskQueue) {
          const taskId = this.taskQueue.enqueue("import-doc", {
            filePath,
            relativePath: relPath,
          });
          if (this.logger) {
            this.logger.debug("File change queued", { path: relPath, taskId });
          }
        } else {
          // 同步模式（默认）
          await this.documentTracker.checkFile(filePath);
        }
      } catch (e) {
        if (this.logger) {
          this.logger.error("Failed to process file change", { filePath: relPath, error: String(e) });
        }
      }
    }
  }

  private scheduleDebounce(): void {
    if (this.debounceTimer) {
      clearTimeout(this.debounceTimer);
    }
    this.debounceTimer = setTimeout(() => {
      this.processDebouncedChanges().catch(() => {});
    }, DEBOUNCE_MS);
  }

  private onFileChanged(filePath: string, event: "created" | "modified" | "deleted"): void {
    if (!this.shouldTrack(filePath)) return;

    const relPath = path.relative(this.directory, filePath);

    if (event === "deleted") {
      if (this.logger) {
        this.logger.documentTracked({ filePath: relPath, action: "deleted" });
      }
      return;
    }

    this.pendingChanges.set(relPath, Date.now());

    if (this.logger) {
      this.logger.debug("File change detected", { path: relPath, type: event });
    }

    this.scheduleDebounce();
  }

  async start(): Promise<void> {
    if (this.running) return;

    const watchDir = this.directory;
    if (!fs.existsSync(watchDir)) return;

    this.running = true;

    try {
      this.watcher = fs.watch(
        watchDir,
        { recursive: true, persistent: false },
        (event, filename) => {
          if (!filename) return;
          const filePath = path.join(watchDir, filename);

          if (filePath.includes("node_modules") || filePath.includes(".git")) return;

          const eventType = event === "rename" ? "created" : "modified";
          this.onFileChanged(filePath, eventType);
        }
      );

      if (this.logger) {
        this.logger.info("File watcher started", { directory: watchDir });
      }
    } catch (e) {
      if (this.logger) {
        this.logger.warn("File watcher failed to start", { error: String(e) });
      }
      this.running = false;
    }
  }

  async stop(): Promise<void> {
    if (!this.running) return;

    this.running = false;

    if (this.watcher) {
      this.watcher.close();
      this.watcher = null;
    }

    if (this.debounceTimer) {
      clearTimeout(this.debounceTimer);
      this.debounceTimer = null;
    }

    if (this.logger) {
      this.logger.info("File watcher stopped");
    }
  }

  get isRunning(): boolean {
    return this.running;
  }
}
