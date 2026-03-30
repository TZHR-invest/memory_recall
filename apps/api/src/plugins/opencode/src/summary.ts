import type { ApiClient } from "./client";
import type { Config } from "./config";
import type { Logger } from "./logging";
import type { Locale } from "./i18n";
import { getLocale } from "./i18n";

const MIN_SUMMARY_LENGTH = 100;

export class SummaryCapture {
  private client: ApiClient;
  private config: Config;
  private tags: { user: string; project: string };
  private logger: Logger | null;
  private summarizedSessions: Set<string> = new Set();

  constructor(
    client: ApiClient,
    config: Config,
    tags: { user: string; project: string },
    logger: Logger | null
  ) {
    this.client = client;
    this.config = config;
    this.tags = tags;
    this.logger = logger;
  }

  markForCapture(sessionId: string): void {
    this.summarizedSessions.add(sessionId);
  }

  isMarked(sessionId: string): boolean {
    return this.summarizedSessions.has(sessionId);
  }

  removeMark(sessionId: string): void {
    this.summarizedSessions.delete(sessionId);
  }

  async captureFromMessages(
    sessionId: string,
    messages: Array<{ info?: Record<string, unknown>; parts?: Array<{ type?: string; text?: string }> }>,
    locale: Locale
  ): Promise<string | null> {
    if (!this.config.enableSummaryCapture) return null;

    let summaryMessage: typeof messages[0] | null = null;
    for (const m of messages) {
      const info = m.info || {};
      if (info.role === "assistant" && info.summary === true) {
        summaryMessage = m;
        break;
      }
    }

    if (!summaryMessage) return null;

    const parts = summaryMessage.parts || [];
    const textParts = parts
      .filter((p) => p.type === "text" && p.text)
      .map((p) => p.text as string);
    const summaryContent = textParts.join("\n");

    if (summaryContent.length < MIN_SUMMARY_LENGTH) {
      if (this.logger) {
        this.logger.warn("Summary too short", {
          sessionID: sessionId,
          length: summaryContent.length,
        });
      }
      return null;
    }

    const localeData = getLocale(locale);
    const formattedContent = `${localeData.session_summary}\n${summaryContent}`;

    try {
      const result = await this.client.addMemory(
        formattedContent,
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
}
