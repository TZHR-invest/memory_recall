/* 本文件由 build-bundle.mjs 从 client-lib.js 自动生成，勿手改；改库后重跑 node build-bundle.mjs */
window.__ModuleLoader__.load({
  id: "memory-recall-dsh",
  factory: (require) => {
    var module = { exports: {} };
    var exports = module.exports;
    Object.defineProperty(exports, Symbol.toStringTag, { value: "Module" });

    // ── 以下为 client-lib.js 源码（已剥离 export）──
/**
 * memory-recall-dsh 后端 HTTP 客户端
 *
 * 契约与 opencode 插件 client.ts 对齐：X-API-Key 头 + /auth/verify 解析 keyId，
 * 统一召回走 POST /context-inject，其余走 /memories /search /profile。
 * 所有请求带超时；调用方（工具 / 注入 / 捕获）负责 fail-open。
 *
 * 本文件是 node（服务端）ESM 库，被 index.js import。
 * 浏览器端 bundle（client.js）由 build-bundle.mjs 从本文件生成：
 * dsh web 用 <script> 标签按 classic script 加载 bundle（不能含 import/export，
 * 必须顶层 window.__ModuleLoader__.load 注册），详见 build-bundle.mjs。
 */

/** 后端 /context-inject 的注入配置（字段与后端 ContextInjectConfig 对齐，已做边界夹取） */
function buildInjectConfig(resolved, { injectProfile, excludeMemoryIds } = {}) {
  return {
    inject_profile: injectProfile === true && resolved.injectProfile,
    exclude_memory_ids: excludeMemoryIds ?? [],
    max_profile_items: resolved.maxProfileItems,
    max_static_profile_items: resolved.maxStaticProfileItems,
    max_memories: resolved.maxMemories,
    max_chunks: resolved.maxChunks,
    enable_semantic_dedup: true,
    dedup_threshold: 0.85,
    enable_memory_graph: resolved.enableGraphRecall,
    memory_graph_depth: resolved.graphMaxDepth,
    memory_graph_nodes: resolved.graphMaxNodes,
    enable_entity_graph: resolved.enableEntityRecall,
    entity_graph_depth: resolved.graphMaxDepth,
    entity_graph_nodes: resolved.graphMaxNodes,
    memory_similarity_threshold: resolved.similarityThreshold,
    language: resolved.language,
    enable_chunks_search: resolved.enableChunksSearch,
    chunks_similarity_threshold: 0.45,
    entity_chunk_threshold: 0.30,
  };
}

class ConfigurationError extends Error {
  constructor(message) {
    super(message);
    this.name = "ConfigurationError";
  }
}

class MemoryRecallClient {
  constructor({ baseUrl, apiKey, requestTimeoutMs = 30000, writeTimeoutMs = 90000, debug = false }) {
    this.baseUrl = baseUrl;
    this.apiKey = apiKey ?? null;
    this.requestTimeoutMs = requestTimeoutMs;
    this.writeTimeoutMs = writeTimeoutMs;
    this.debug = debug;
  }

  isConfigured() {
    return typeof this.apiKey === "string" && this.apiKey.length > 0;
  }

  /** 带超时 + 外部取消信号的 fetch */
  async #fetchWithTimeout(path, options = {}, externalSignal, timeoutMs) {
    const budget = timeoutMs ?? this.requestTimeoutMs;
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(new Error(`timeout after ${budget}ms`)), budget);
    const onExternalAbort = () => controller.abort(externalSignal?.reason ?? new Error("aborted"));
    if (externalSignal) {
      if (externalSignal.aborted) {
        clearTimeout(timeoutId);
        throw new Error("request aborted");
      }
      externalSignal.addEventListener("abort", onExternalAbort, { once: true });
    }
    try {
      const response = await fetch(`${this.baseUrl}${path}`, {
        ...options,
        signal: controller.signal,
      });
      if (!response.ok) {
        const detail = await response.text().catch(() => "");
        throw new Error(`API ${response.status}: ${detail.slice(0, 500)}`);
      }
      return response;
    } finally {
      clearTimeout(timeoutId);
      externalSignal?.removeEventListener("abort", onExternalAbort);
    }
  }

  async #request(path, { method = "GET", body, externalSignal, timeoutMs } = {}) {
    if (!this.isConfigured()) {
      throw new ConfigurationError("API key not configured");
    }
    const response = await this.#fetchWithTimeout(path, {
      method,
      headers: {
        "Content-Type": "application/json",
        "X-API-Key": this.apiKey,
      },
      body: body !== undefined ? JSON.stringify(body) : undefined,
    }, externalSignal, timeoutMs);
    return response.json();
  }

  /** GET /auth/verify → { key_id, container_tag, user_name, ... } */
  verify(externalSignal) {
    return this.#request("/auth/verify", { externalSignal });
  }

  /**
   * POST /memories → 新建记忆
   * @param asyncProcess - true 时后端后台处理 embedding/实体提取/关系检测，
   *   立即返回 status="processing"（写入从 25s+ 降到 <1s）；默认 false 保持同步
   *   （可立即搜索到）。
   */
  addMemory(content, containerTag, { isStatic = false, type = null, asyncProcess = false } = {}, externalSignal) {
    const metadata = type ? { type } : {};
    return this.#request("/memories", {
      method: "POST",
      timeoutMs: this.writeTimeoutMs,
      body: {
        content,
        container_tag: containerTag,
        is_static: isStatic,
        metadata,
        async_process: asyncProcess,
      },
      externalSignal,
    });
  }

  /**
   * POST /memories/{id}/update → 版本化修正（旧记忆 is_latest=false + updates 关系）。
   * ADR-0009：过时记忆应版本化修正，勿 forget+store（会丢失版本链）。
   */
  updateMemory(memoryId, content, { asyncProcess = false } = {}, externalSignal) {
    return this.#request(`/memories/${encodeURIComponent(memoryId)}/update`, {
      method: "POST",
      timeoutMs: this.writeTimeoutMs,
      body: {
        content,
        async_process: asyncProcess,
      },
      externalSignal,
    });
  }

  /** POST /search → { results: [{id, content, similarity, ...}] } */
  search(query, containerTag, { limit = 10, threshold = 0.4 } = {}, externalSignal) {
    return this.#request("/search", {
      method: "POST",
      body: {
        query,
        container_tag: containerTag,
        limit,
        threshold,
      },
      externalSignal,
    });
  }

  /** GET /profile → { profile: {static, dynamic}, searchResults } */
  profile(containerTag, query = null, externalSignal) {
    const params = new URLSearchParams({ container_tag: containerTag });
    if (query) params.append("query", query);
    return this.#request(`/profile?${params.toString()}`, { externalSignal });
  }

  /** GET /memories → { memories: [...] } */
  listMemories(containerTag, limit = 20, externalSignal) {
    const params = new URLSearchParams({ container_tag: containerTag, limit: String(limit) });
    return this.#request(`/memories?${params.toString()}`, { externalSignal });
  }

  /** POST /memories/{id}/forget → 删除记忆 */
  forgetMemory(memoryId, externalSignal) {
    return this.#request(`/memories/${encodeURIComponent(memoryId)}/forget`, {
      method: "POST",
      externalSignal,
    });
  }

  /** POST /context-inject → 统一召回（画像 + 记忆 + 文档片段 + 图谱） */
  injectContext(userTag, projectTag, query, config, externalSignal) {
    return this.#request("/context-inject", {
      method: "POST",
      body: {
        user_tag: userTag,
        project_tag: projectTag,
        query,
        config: config ?? {},
        include_trace: false,
      },
      externalSignal,
    });
  }

  /** 从 /context-inject 响应中提取已注入的记忆 ID（project + user 容器） */
  injectedMemoryIdsFrom(result) {
    if (!result?.sources) return [];
    const memories = Array.isArray(result.sources.memories) ? result.sources.memories : [];
    const userMemories = Array.isArray(result.sources.user_memories) ? result.sources.user_memories : [];
    return [...memories, ...userMemories]
      .map((m) => m?.id)
      .filter((id) => typeof id === "string" && id.length > 0);
  }

  /** POST /extract-memory → LLM 蒸馏会话摘要（不落库，落库由插件做） */
  extractMemory(summary, language = "zh_CN", externalSignal) {
    return this.#request("/extract-memory", {
      method: "POST",
      timeoutMs: this.writeTimeoutMs,
      body: { summary, language },
      externalSignal,
    });
  }
}

    // ── 插件形状：name / inject / apply（组合装载校验：函数或带 apply 的对象）──
    exports.name = "memory-recall-dsh";
    exports.inject = [];
    exports.apply = function apply(ctx) {
      ctx?.logger?.info?.('[memory-recall-dsh] browser client plugin loaded');
    };

    // 顺带暴露 HTTP 客户端（bundle 内自包含，供浏览器侧调试/扩展使用）
    exports.MemoryRecallClient = MemoryRecallClient;
    exports.buildInjectConfig = buildInjectConfig;
    exports.ConfigurationError = ConfigurationError;
    return module.exports;
  }
});
