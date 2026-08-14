/**
 * memory-recall-dsh 后端 HTTP 客户端
 *
 * 契约与 opencode 插件 client.ts 对齐：X-API-Key 头 + /auth/verify 解析 keyId，
 * 统一召回走 POST /context-inject，其余走 /memories /search /profile。
 * 所有请求带超时；调用方（工具 / 注入 / 捕获）负责 fail-open。
 *
 * 双模式：
 *   - 服务端（node）：被 index.js 作为 ESM 库 import（文件底部 export）；
 *   - 浏览器端（dsh web）：作为客户端插件 bundle 由 dsh 客户端模块系统 import()
 *     求值。模块必须调用 window.__ModuleLoader__.load({ id, factory }) 注册插件
 *     （factory 返回 { name, inject, apply } 形状）；只 export 不注册会报：
 *     "bundle ... loaded without registering ... via __ModuleLoader__.load"。
 *     注册块放在文件底部，node 环境无 window 自动跳过。
 */

/** 后端 /context-inject 的注入配置（字段与后端 ContextInjectConfig 对齐，已做边界夹取） */
export function buildInjectConfig(resolved, { injectProfile } = {}) {
  return {
    inject_profile: injectProfile === true && resolved.injectProfile,
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

export class ConfigurationError extends Error {
  constructor(message) {
    super(message);
    this.name = "ConfigurationError";
  }
}

export class MemoryRecallClient {
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

  /** POST /memories → 新建记忆 */
  addMemory(content, containerTag, { isStatic = false, type = null } = {}, externalSignal) {
    const metadata = type ? { type } : {};
    return this.#request("/memories", {
      method: "POST",
      timeoutMs: this.writeTimeoutMs,
      body: {
        content,
        container_tag: containerTag,
        is_static: isStatic,
        metadata,
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

// ── 浏览器端插件注册（dsh web bundle 环境；node 下 typeof window 为 undefined 自动跳过）──
// dsh 客户端模块系统 import() 本文件后会检查是否已通过 __ModuleLoader__.load 注册，
// 未注册即报 "loaded without registering"。注册的 factory 返回 cordis 插件形状
// { name, inject, apply }（与 dsh-lan-access 等官方/既有客户端插件一致）。
if (typeof window !== "undefined" && typeof window.__ModuleLoader__ !== "undefined") {
  window.__ModuleLoader__.load({
    id: "memory-recall-dsh",
    factory: (require) => {
      var module = { exports: {} };
      var exports = module.exports;
      Object.defineProperty(exports, Symbol.toStringTag, { value: "Module" });

      // 插件形状：name / inject / apply（组合装载校验：函数或带 apply 的对象）
      exports.name = "memory-recall-dsh";
      exports.inject = [];
      exports.apply = function apply(ctx) {
        ctx?.logger?.info?.("[memory-recall-dsh] browser client plugin loaded");
      };

      // 顺带暴露 HTTP 客户端（bundle 内自包含，供浏览器侧调试/扩展使用）
      exports.MemoryRecallClient = MemoryRecallClient;
      exports.buildInjectConfig = buildInjectConfig;
      exports.ConfigurationError = ConfigurationError;
      return module.exports;
    }
  });
}
