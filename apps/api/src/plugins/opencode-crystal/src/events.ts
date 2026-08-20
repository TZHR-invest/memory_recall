import type { Config } from "./config";
import type { Logger } from "../../_shared/logging.ts";
import type { CompactionHook } from "./compaction";

interface Event { type: string; properties?: Record<string, unknown>; }

export class EventHandler {
  private config: Config;
  private compactionHook: CompactionHook;
  private scope: string | null;
  private logger: Logger | null;
  constructor(config: Config, compactionHook: CompactionHook, scope: string | null, logger: Logger | null) {
    this.config = config; this.compactionHook = compactionHook; this.scope = scope; this.logger = logger;
  }
  async handleSessionDeleted(event: Event): Promise<void> {
    const props = event.properties || {};
    const info = props.info as Record<string, unknown> | undefined;
    const sessionId = info?.id as string | undefined;
    if (this.logger) this.logger.eventReceived({ eventType: "session.deleted", sessionId });
  }
  getHandlers(): Record<string, (event: Event, ctxClient: unknown) => Promise<void>> {
    return { "session.deleted": (e) => this.handleSessionDeleted(e) };
  }
}
