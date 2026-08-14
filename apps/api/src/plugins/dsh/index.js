/**
 * memory-recall-dsh — DeepSeek Harness (dsh) 的 Memory Recall 客户端插件
 *
 * 对标 opencode 插件 memory-recall-opencode，为 dsh 提供：
 *   1. 记忆工具：memory_store / memory_search / memory_profile / memory_list / memory_forget；
 *   2. 自动召回：agent/pre-step 时按策略（once/smart/always）调 POST /context-inject，
 *      把召回上下文以 <system-reminder> 框定消息折入本轮请求；
 *   3. 自动捕获：turn/end 时把会话摘要写入长期记忆（extract 蒸馏 / raw 原文）。
 *
 * 依赖契约（与 dsh 生态一致）：
 *   - 只 import @deepseek-ai/schemastery（Config 校验）、@deepseek-ai/dsh-llm
 *     （createUserMessage）、@deepseek-ai/dsh-tools（defineTool）；
 *   - 声明 inject: ["agents", "tools"]，由宿主 dsh 组合提供；
 *   - 所有对外调用 fail-open：后端不可达 / 未配置 Key 只记日志，不阻断对话。
 *
 * 标签约定：userTag = keyId（跨项目），projectTag = {keyId}_project-<cwd 目录名>；
 * keyId 优先取配置，缺省在启动时 GET /auth/verify 自动解析。
 */
import z from "@deepseek-ai/schemastery";
import { createUserMessage } from "@deepseek-ai/dsh-llm";
import { resolveConfig, projectTagFor, detectLocale, shouldTriggerRecall } from "./config.js";
import { MemoryRecallClient, buildInjectConfig } from "./client.js";
import { buildInjectionText, contextDigest, firstUserText, hasInjectedDigest, hasDirectUserMessage } from "./context.js";
import { registerTools } from "./tools.js";
import { createCaptureHandler } from "./capture.js";

/** Cordis 插件名（loader 诊断用） */
const name = "memory-recall-dsh";

/** 需要的宿主服务：agents（pre-step 事件）+ tools（工具注册） */
const inject = ["agents", "tools"];

/** Schemastery 配置校验（patch config 中只写想覆盖的字段即可，其余走默认/环境变量） */
const Config = z.object({
  apiKey: z.string(),
  baseUrl: z.string(),
  keyId: z.string(),
  userName: z.string(),
  containerTag: z.string(),
  projectTagOverride: z.string(),
  autoRecall: z.boolean(),
  autoCapture: z.boolean(),
  injectionStrategy: z.string(),
  maxMemories: z.number(),
  maxProfileItems: z.number(),
  maxStaticProfileItems: z.number(),
  injectProfile: z.boolean(),
  enableChunksSearch: z.boolean(),
  maxChunks: z.number(),
  language: z.string(),
  similarityThreshold: z.number(),
  enableGraphRecall: z.boolean(),
  enableEntityRecall: z.boolean(),
  graphMaxDepth: z.number(),
  graphMaxNodes: z.number(),
  smartRecallKeywords: z.array(z.string()),
  minRecallQueryLength: z.number(),
  captureMode: z.string(),
  captureMinLength: z.number(),
  captureMaxChars: z.number(),
  requestTimeoutMs: z.number(),
  writeTimeoutMs: z.number(),
  debug: z.boolean(),
});

/**
 * 插件主体。
 * @param ctx - cordis Context
 * @param config - patch 传入的配置（部分字段可缺省）
 */
function apply(ctx, config = {}) {
  const resolved = resolveConfig(config);
  const client = new MemoryRecallClient({
    baseUrl: resolved.baseUrl,
    apiKey: resolved.apiKey,
    requestTimeoutMs: resolved.requestTimeoutMs,
    writeTimeoutMs: resolved.writeTimeoutMs,
    debug: resolved.debug,
  });
  const logger = ctx.logger;

  // ── keyId 解析（配置 > /auth/verify 自动获取）────────────────────────────
  const tagState = {
    keyId: resolved.keyId,
    verified: resolved.keyId !== null && resolved.keyId !== undefined,
    verifying: null,
  };

  /**
   * 解析某 agent 的 user/project tag。
   * @param agent - 调用方 agent（可为 null：日志 / 捕获路径用进程 cwd）
   * @returns {user, project} | null（未配置或验证失败）
   */
  const resolveTags = async (agent) => {
    if (resolved.containerTag) {
      return { user: resolved.containerTag, project: resolved.containerTag };
    }
    if (!client.isConfigured()) return null;
    if (!tagState.verified && tagState.verifying === null) {
      tagState.verifying = client.verify()
        .then((result) => {
          tagState.keyId = result.key_id ?? result.container_tag ?? null;
          tagState.verified = tagState.keyId !== null;
          return tagState.keyId;
        })
        .catch((error) => {
          logger?.warn?.("[memory-recall-dsh] /auth/verify 失败（插件继续运行，tag 解析将重试）: %s",
            error instanceof Error ? error.message : String(error));
          tagState.verifying = null;
          return null;
        });
    }
    const keyId = tagState.verified ? tagState.keyId : await tagState.verifying;
    if (!keyId) return null;
    const cwd = agent?.session?.header?.cwd ?? process.cwd();
    return {
      user: keyId,
      project: resolved.projectTagOverride ?? projectTagFor(keyId, cwd),
    };
  };

  // 启动自检：验证 key + 打印标签（异步，不阻塞启动）
  if (client.isConfigured()) {
    void resolveTags(null).then((tags) => {
      if (tags) {
        logger?.info?.("[memory-recall-dsh] 已连接 %s（userTag=%s, projectTag=%s）", resolved.baseUrl, tags.user, tags.project);
      } else {
        logger?.warn?.("[memory-recall-dsh] 无法解析容器 tag（检查 API Key / 后端连通性）");
      }
    });
  } else {
    logger?.warn?.("[memory-recall-dsh] 未配置 API Key（patch config.apiKey 或环境变量 MEMORY_RECALL_API_KEY）——记忆工具与自动召回将不生效");
  }

  // ── 工具注册 ────────────────────────────────────────────────────────────
  registerTools(ctx, { client, config: resolved, resolveTags });

  // ── 自动捕获：turn/end 落库 ─────────────────────────────────────────────
  ctx.on("session/event", createCaptureHandler({ client, config: resolved, resolveTags, logger }));

  // ── 自动召回：agent/pre-step 注入上下文 ─────────────────────────────────
  ctx.on("agent/pre-step", async ({ agent, messages, step, signal }, next) => {
    const decision = await next();
    if (!resolved.autoRecall) return decision;
    if (decision.kind === "reject" || step !== 1 || signal?.aborted) return decision;
    if (!client.isConfigured()) return decision;

    const tags = await resolveTags(agent).catch(() => null);
    if (!tags) return decision;

    try {
      const text = firstUserText(decision.messages);
      if (!text || text.length < resolved.minRecallQueryLength) return decision;

      const isFirst = !hasDirectUserMessage(agent);
      let shouldInject;
      if (resolved.injectionStrategy === "always") {
        shouldInject = true;
      } else if (resolved.injectionStrategy === "once") {
        shouldInject = isFirst;
      } else {
        shouldInject = isFirst || shouldTriggerRecall(text, resolved.smartRecallKeywords);
      }
      if (!shouldInject) return decision;

      const result = await client.injectContext(
        tags.user,
        tags.project,
        text,
        buildInjectConfig(resolved, { injectProfile: isFirst }),
        signal,
      );
      if (!result?.context || result.context.trim().length === 0) return decision;

      const locale = detectLocale(text, resolved.language);
      const rendered = buildInjectionText(result.context, locale);
      const digest = contextDigest(rendered);
      if (hasInjectedDigest(agent, digest)) return decision;

      const message = createUserMessage({
        content: [{ type: "text", text: rendered }],
        source: {
          kind: "plugin",
          plugin: name,
          form: "snapshot",
          sections: [{ name, text: rendered }],
        },
      });
      if (resolved.debug) {
        logger?.debug?.("[memory-recall-dsh] 注入召回上下文 %s（策略=%s, 首次=%s, 命中 %d 项）",
          digest.slice(0, 8), resolved.injectionStrategy, isFirst,
          result.stats?.capped_count ?? 0);
      }
      return { kind: "enter", messages: [...decision.messages, message] };
    } catch (error) {
      logger?.warn?.("[memory-recall-dsh] 自动召回失败（不影响本轮）: %s",
        error instanceof Error ? error.message : String(error));
      return decision;
    }
  }, { prepend: true });
}

export { Config, apply, inject, name };
