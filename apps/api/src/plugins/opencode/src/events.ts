import type { Config } from "./config";
import type { Logger } from "./logging";
import type { CompactionHook } from "./compaction";

interface Event {
  type: string;
  properties?: Record<string, unknown>;
}

/**
 * EventHandler
 *
 * 压缩收敛后事件处理大幅精简：
 * - 保留 `session.deleted`：清理节流状态（toast 节流）
 * - 删除 `session.compacted` 恢复处理（现场恢复已删，ADR-0008）
 * - 删除摘要相关触发与 `message.updated` 预压缩判定（ADR-0007）
 *
 * 注：SessionTrackerManager 的生命周期由 index.ts 在 session.deleted 时清理；
 * 本类保留对 CompactionHook 的依赖位仅用于未来可能的清理扩展，
 * 当前 CompactionHook 已无状态。
 */
export class EventHandler {
  private config: Config;
  private compactionHook: CompactionHook;
  private tags: { user: string; project: string };
  private logger: Logger | null;

  constructor(
    config: Config,
    compactionHook: CompactionHook,
    tags: { user: string; project: string },
    logger: Logger | null
  ) {
    this.config = config;
    this.compactionHook = compactionHook;
    this.tags = tags;
    this.logger = logger;
  }

  async handleSessionDeleted(event: Event): Promise<void> {
    const props = event.properties || {};
    const sessionInfo = props.info as Record<string, unknown> | undefined;
    const sessionId = sessionInfo?.id as string | undefined;

    if (this.logger) {
      this.logger.eventReceived({ eventType: "session.deleted", sessionId });
    }
  }

  getHandlers(): Record<string, (event: Event, ctxClient: unknown) => Promise<void>> {
    return {
      "session.deleted": (e) => this.handleSessionDeleted(e),
    };
  }
}
