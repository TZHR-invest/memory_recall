import type { ApiClientCrystal } from "./client";
import type { Config } from "./config";
import type { Logger } from "../../_shared/logging.ts";

const DEFAULT_CONTEXT_TIMEOUT_MS = 3000;

export class CompactionHook {
  private client: ApiClientCrystal;
  private config: Config;
  private scope: string | null;
  private logger: Logger | null;
  constructor(client: ApiClientCrystal, config: Config, scope: string | null, logger: Logger | null) {
    this.client = client; this.config = config; this.scope = scope; this.logger = logger;
  }
  async injectCompactionContext(sessionId: string, context: string[], aiGuidance: string[]): Promise<void> {
    try {
      if (aiGuidance.length > 0) context.push(aiGuidance.join("\n"));
      const claims = await this.fetchProjectClaims();
      if (claims.length > 0) {
        const prefix = this.config.language === "zh_CN" ? "## 持久记忆" : "## Persistent Memory";
        context.push(prefix + "\n" + claims.map((m) => `- ${m}`).join("\n"));
      }
      if (this.logger) this.logger.info("Compaction context injected", { sessionID: sessionId, memories: claims.length });
    } catch (e) {
      if (this.logger) this.logger.warn("Compaction context injection failed (fail-open)", { sessionID: sessionId, error: String(e) });
    }
  }
  private async fetchProjectClaims(): Promise<string[]> {
    try {
      const result = await Promise.race([
        this.client.listClaims({ scope: this.scope, limit: this.config.maxProjectMemories }),
        new Promise<never>((_, reject) => setTimeout(() => reject(new Error("listClaims timeout")), DEFAULT_CONTEXT_TIMEOUT_MS)),
      ]);
      const items = (result as { items: Array<{ statement: string }> }).items || [];
      return items.map((m) => m.statement).filter(Boolean).filter((c) => !c.startsWith("[Session Summary]") && !c.startsWith("[会话摘要]")).slice(0, this.config.maxProjectMemories);
    } catch (e) {
      if (this.logger) this.logger.warn("Failed to fetch project claims for compaction", { error: String(e) });
      return [];
    }
  }
}
