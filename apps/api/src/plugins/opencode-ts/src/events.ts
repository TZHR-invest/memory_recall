import type { Config } from "./config";
import type { Logger } from "./logging";
import type { CompactionHook } from "./compaction";

interface Event {
  type: string;
  properties?: Record<string, unknown>;
}

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

  async handleMessageUpdated(event: Event, ctxClient: unknown): Promise<void> {
    const props = event.properties || {};
    const info = props.info as Record<string, unknown> | undefined;
    const sessionId = info?.sessionID as string | undefined;

    if (this.logger) {
      this.logger.eventReceived({ eventType: "message.updated", sessionId });
    }

    await this.compactionHook.handleEvent(event, ctxClient);
  }

  async handleSessionIdle(event: Event, ctxClient: unknown): Promise<void> {
    const props = event.properties || {};
    const sessionId = props.sessionID as string | undefined;

    if (this.logger) {
      this.logger.eventReceived({ eventType: "session.idle", sessionId });
    }

    await this.compactionHook.handleEvent(event, ctxClient);
  }

  async handleSessionDeleted(event: Event): Promise<void> {
    const props = event.properties || {};
    const sessionInfo = props.info as Record<string, unknown> | undefined;
    const sessionId = sessionInfo?.id as string | undefined;

    if (this.logger) {
      this.logger.eventReceived({ eventType: "session.deleted", sessionId });
    }

    await this.compactionHook.handleEvent(
      { type: "session.deleted", properties: { info: { id: sessionId } } },
      null
    );
  }

  getHandlers(): Record<string, (event: Event, ctxClient: unknown) => Promise<void>> {
    return {
      "message.updated": (e, c) => this.handleMessageUpdated(e, c),
      "session.idle": (e, c) => this.handleSessionIdle(e, c),
      "session.deleted": (e) => this.handleSessionDeleted(e),
    };
  }
}
