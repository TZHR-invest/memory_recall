import type { ApiClient } from "./client";
import type { Config } from "./config";
import type { Logger } from "./logging";

/**
 * CompactionHook
 *
 * 压缩收敛到官方 hook：`experimental.session.compacting` 只向 `output.context`
 * 追加 AI guidance + 项目记忆，不设置 `output.prompt`（保留官方默认锚定摘要更新语义）。
 * 压缩触发完全交给原生 `compaction.auto`（默认开）+ 手动 `/compact`。
 *
 * 删除项（ADR-0007 / ADR-0008 / ADR-0006）：
 * - 预压缩：checkAndTriggerCompaction / injectHookMessage / createCompactionPrompt
 * - 摘要捕获：waitForSummaryMessage / handleSummaryMessage / saveSummaryAsMemory
 * - 现场恢复：captureAgentConfig / recoverAgentConfig / captureTodos / restoreTodos
 * - 会话摘要写入记忆库（数据边界：摘要不是知识）
 *
 * hook 内 fail-open 防御层（官方源码核实 Plugin.trigger 无 try/catch）：
 * 所有可能抛错的调用必须兜住，失败只记日志，绝不阻断压缩主流程。
 */

const DEFAULT_CONTEXT_TIMEOUT_MS = 3000;

export class CompactionHook {
  private client: ApiClient;
  private config: Config;
  private tags: { user: string; project: string };
  private logger: Logger | null;

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

  async injectCompactionContext(
    sessionId: string,
    context: string[],
    aiGuidance: string[]
  ): Promise<void> {
    try {
      if (aiGuidance.length > 0) {
        context.push(aiGuidance.join("\n"));
      }

      const projectMemories = await this.fetchProjectMemories();
      if (projectMemories.length > 0) {
        const prefix = this.config.language === "zh_CN" ? "## 持久记忆" : "## Persistent Memory";
        context.push(prefix + "\n" + projectMemories.map((m) => `- ${m}`).join("\n"));
      }

      if (this.logger) {
        this.logger.info("Compaction context injected", { sessionID: sessionId, memories: projectMemories.length });
      }
    } catch (e) {
      if (this.logger) {
        this.logger.warn("Compaction context injection failed (fail-open)", { sessionID: sessionId, error: String(e) });
      }
    }
  }

  private async fetchProjectMemories(): Promise<string[]> {
    try {
      const result = await Promise.race([
        this.client.listMemories(this.tags.project, this.config.maxProjectMemories),
        new Promise<never>((_, reject) =>
          setTimeout(() => reject(new Error("listMemories timeout")), DEFAULT_CONTEXT_TIMEOUT_MS)
        ),
      ]);

      return result
        .map((m) => m.content)
        .filter((c): c is string => Boolean(c))
        .filter((c) => !c.startsWith("[Session Summary]") && !c.startsWith("[会话摘要]"))
        .slice(0, this.config.maxProjectMemories);
    } catch (e) {
      if (this.logger) {
        this.logger.warn("Failed to fetch project memories for compaction", { error: String(e) });
      }
      return [];
    }
  }
}

