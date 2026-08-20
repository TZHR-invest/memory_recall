import type { Config } from "./config";
import { createHash } from "crypto";

// crystal /api/v2 客户端 — 薄适配层，仅含差异映射，其余能力复用 _shared
// 契约见 docs/initiatives/crystal/api-contract.md v1 §2

export class ConfigurationError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "ConfigurationError";
  }
}

// ---------- 实体类型（对齐后端 crystal schema） ----------

export interface Evidence {
  evidence_id: string;
  content: string;
  source_kind: string;
  scope: string | null;
  owner_type: string;
  owner_id: string;
  observed_at: string | null;
  created_at: string | null;
  source_ref?: Record<string, unknown> | null;
  extraction_type?: string | null;
  processing?: { state: string; current_step: string; last_error?: unknown; updated_at?: string | null };
  processing_state?: string;
}

export interface Claim {
  claim_id: string;
  statement: string;
  claim_kind: string;
  content_confidence: number | null;
  scope: string | null;
  status: string;
  created_at: string | null;
}

export interface SearchResultClaim {
  claim_id: string;
  statement: string;
  claim_kind: string;
  content_confidence: number | null;
  status: string;
  scope: string | null;
  scores?: Record<string, number>;
  evidence_refs?: Array<{ evidence_id: string; role: string }>;
}

export interface SearchResponse {
  results: SearchResultClaim[];
  explain?: Record<string, unknown>;
  trace_id?: string;
}

export interface ContextInjectResponse {
  profile: Array<{ claim_id: string; statement: string }>;
  memories: SearchResultClaim[];
  excluded?: string[] | null;
  explain?: Record<string, unknown>;
  trace_id?: string;
}

// ---------- 工具 ----------

const REQUEST_TIMEOUT_MS = 30000;
const KEY_ID_PREFIX_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}_/;

export function verifyScopeOwnership(scope: string | null, keyId: string | null): string | null {
  if (scope === null || scope === undefined) return null;
  if (!scope) return null;
  if (keyId && scope.startsWith(`${keyId}_`)) {
    throw new ConfigurationError(
      `Scope must not contain the API key prefix. Pass the project part only (e.g. 'project-memory_recall'); owner_id is resolved from your API key automatically. Got scope="${scope}"`
    );
  }
  if (KEY_ID_PREFIX_RE.test(scope)) {
    throw new ConfigurationError(
      `Scope must not start with a key-id shaped prefix (uuid + '_'). Scope is project-part only; ownership is resolved from your API key. Got scope="${scope}"`
    );
  }
  return scope;
}

export function computeIdempotencyKey(content: string, scope: string | null): string {
  const raw = `${content}|${scope ?? ""}`;
  return createHash("sha256").update(raw, "utf8").digest("hex").slice(0, 32);
}

async function fetchWithTimeout(url: string, options: RequestInit, timeoutMs: number): Promise<Response> {
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const response = await fetch(url, { ...options, signal: controller.signal });
    return response;
  } finally {
    clearTimeout(timeoutId);
  }
}

// ---------- ApiClientCrystal ----------

export class ApiClientCrystal {
  private config: Config;
  private scope: string | null;

  constructor(config: Config, scope: string | null) {
    this.config = config;
    this.scope = scope;
  }

  getScope(): string | null {
    return this.scope;
  }

  // 统一请求：携带 X-API-Key，解包 {code,message,data} 信封
  private async request<T>(path: string, method: string = "GET", body?: unknown, timeoutMs: number = REQUEST_TIMEOUT_MS): Promise<T> {
    if (!this.config.apiKey) throw new ConfigurationError("API key not configured");
    const url = `${this.config.baseUrl}${path}`;
    const headers: Record<string, string> = {
      "Content-Type": "application/json",
      "X-API-Key": this.config.apiKey,
    };
    const response = await fetchWithTimeout(url, { method, headers, body: body ? JSON.stringify(body) : undefined }, timeoutMs);
    const text = await response.text();
    let json: Record<string, unknown> = {};
    try { json = text ? JSON.parse(text) : {}; } catch { json = { message: text }; }

    if (!response.ok) {
      // 后端统一错误信封 {code, message}
      const msg = (json.message as string) || (json.detail as string) || text || `HTTP ${response.status}`;
      throw new Error(`API error ${response.status}: ${msg}`);
    }
    // 成功信封 {code:0, message:"ok", data:{...}} → 解包 data
    if (json && typeof json.code === "number" && "data" in json) {
      if (json.code !== 0) throw new Error(`API error ${json.code}: ${json.message}`);
      return (json.data as T) ?? (json as unknown as T);
    }
    return json as T;
  }

  // ---- Evidence 写侧 ----

  async addEvidence(content: string, scope: string | null, timeoutMs?: number): Promise<{ evidence_id: string; processing_state: string; accepted: boolean }> {
    const effScope = verifyScopeOwnership(scope, this.config.keyId);
    const idempotency_key = computeIdempotencyKey(content, effScope);
    const observed_at = new Date().toISOString();
    return this.request("/api/v2/evidence", "POST", {
      content,
      source_kind: "agent_add",
      scope: effScope,
      observed_at,
      source_ref: { plugin: "opencode-crystal" },
      idempotency_key,
    }, timeoutMs);
  }

  async getEvidence(evidenceId: string): Promise<Evidence> {
    return this.request<Evidence>(`/api/v2/evidence/${evidenceId}`, "GET");
  }

  async listEvidence(opts: { scope?: string | null; limit?: number; cursor?: string } = {}): Promise<{ items: Evidence[]; next_cursor: string | null; has_more: boolean }> {
    const params = new URLSearchParams();
    if (opts.scope !== undefined) {
      const s = verifyScopeOwnership(opts.scope ?? null, this.config.keyId);
      if (s !== null) params.set("scope", s);
    }
    if (opts.limit) params.set("limit", String(opts.limit));
    if (opts.cursor) params.set("cursor", opts.cursor);
    const qs = params.toString();
    return this.request(`/api/v2/evidence${qs ? `?${qs}` : ""}`, "GET");
  }

  async getEvidenceClaims(evidenceId: string): Promise<{ evidence_id: string; claims: Claim[] }> {
    return this.request(`/api/v2/evidence/${evidenceId}/claims`, "GET");
  }

  // ---- 召回读侧 ----

  async search(query: string, scope: string | null, opts: { limit?: number; include_explain?: boolean; claim_kind?: string } = {}): Promise<SearchResponse> {
    const effScope = verifyScopeOwnership(scope, this.config.keyId);
    return this.request("/api/v2/search", "POST", {
      query,
      scope: effScope,
      claim_kind: opts.claim_kind ?? null,
      limit: opts.limit ?? 10,
      include_explain: opts.include_explain ?? false,
    });
  }

  async contextInject(query: string | null, scope: string | null, opts: { include_explain?: boolean; exclude_claim_ids?: string[] } = {}): Promise<ContextInjectResponse> {
    const effScope = verifyScopeOwnership(scope, this.config.keyId);
    return this.request("/api/v2/context-inject", "POST", {
      query: query ?? undefined,
      scope: effScope,
      include_explain: opts.include_explain ?? false,
      exclude_claim_ids: opts.exclude_claim_ids ?? undefined,
    });
  }

  async getClaim(claimId: string): Promise<Claim & { evidence?: unknown[]; lineage?: unknown[] }> {
    return this.request(`/api/v2/claims/${claimId}`, "GET");
  }

  async getClaimLineage(claimId: string): Promise<Record<string, unknown>> {
    return this.request(`/api/v2/claims/${claimId}/lineage`, "GET");
  }

  // ---- 工作台裁决 ----

  async confirmClaim(claimId: string): Promise<Record<string, unknown>> {
    return this.request(`/api/v2/workbench/claims/${claimId}/confirm`, "POST", {});
  }

  async correctClaim(claimId: string, newStatement: string, reason?: string): Promise<Record<string, unknown>> {
    return this.request(`/api/v2/workbench/claims/${claimId}/correct`, "POST", {
      new_statement: newStatement,
      reason: reason ?? "用户纠正",
      source_ref: { plugin: "opencode-crystal" },
    });
  }

  async forgetClaim(claimId: string, reason?: string): Promise<Record<string, unknown>> {
    return this.request(`/api/v2/workbench/claims/${claimId}/forget`, "POST", { reason: reason ?? "用户遗忘" });
  }

  async promoteScope(claimId: string, action: "adopt" | "reject", reason?: string): Promise<Record<string, unknown>> {
    return this.request(`/api/v2/workbench/claims/${claimId}/promote-scope`, "POST", { action, reason });
  }

  async listClaims(opts: { scope?: string | null; limit?: number; cursor?: string; status?: string; claim_kind?: string } = {}): Promise<{ items: Claim[]; next_cursor: string | null; has_more: boolean; count?: number }> {
    const params = new URLSearchParams();
    if (opts.scope !== undefined) {
      const s = verifyScopeOwnership(opts.scope ?? null, this.config.keyId);
      if (s !== null) params.set("scope", s);
    }
    if (opts.status) params.set("status", opts.status);
    if (opts.claim_kind) params.set("claim_kind", opts.claim_kind);
    if (opts.limit) params.set("limit", String(opts.limit));
    if (opts.cursor) params.set("cursor", opts.cursor);
    const qs = params.toString();
    return this.request(`/api/v2/workbench/claims${qs ? `?${qs}` : ""}`, "GET");
  }

  async getWorkbenchOverview(): Promise<Record<string, unknown>> {
    return this.request("/api/v2/workbench/overview", "GET");
  }

  async getWorkbenchGraph(withEvidence = true): Promise<Record<string, unknown>> {
    return this.request(`/api/v2/workbench/graph?with_evidence=${withEvidence}`, "GET");
  }

  async getWorkbenchReviews(opts: { type?: string; limit?: number; cursor?: string } = {}): Promise<Record<string, unknown>> {
    const params = new URLSearchParams();
    if (opts.type) params.set("type", opts.type);
    if (opts.limit) params.set("limit", String(opts.limit));
    if (opts.cursor) params.set("cursor", opts.cursor);
    const qs = params.toString();
    return this.request(`/api/v2/workbench/reviews${qs ? `?${qs}` : ""}`, "GET");
  }

  async getWorkbenchReview(traceId: string): Promise<Record<string, unknown>> {
    return this.request(`/api/v2/workbench/reviews/${traceId}`, "GET");
  }
}
