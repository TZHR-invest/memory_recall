import type { Config } from "./config";

export interface Memory {
  id: string;
  content: string;
  container_tag: string;
  is_static: boolean;
  is_latest: boolean;
  created_at: string;
  metadata?: Record<string, unknown>;
}

export interface SearchResult {
  id: string;
  content: string;
  similarity: number;
  container_tag?: string;
}

// Graph-related interfaces for knowledge graph recall
export interface GraphNode {
  id: string;
  type: "memory";
  content: string;
  is_static: boolean;
  is_latest: boolean;
  is_inference: boolean;
  created_at?: string;
  entities?: Record<string, string[]>;
}

export interface GraphEdge {
  source: string;
  target: string;
  type: "updates" | "extends" | "derives";
  confidence: number;
}

export interface GraphResponse {
  nodes: GraphNode[];
  edges: GraphEdge[];
  total_count: number;
  has_more: boolean;
}

export interface RelatedMemory {
  id: string;
  content: string;
  relation_type: "updates" | "extends" | "derives";
  confidence: number;
  created_at?: string;
}

export interface Profile {
  static: string[];
  dynamic: string[];
}

export interface ProfileResponse {
  profile: Profile;
  searchResults?: SearchResult[];
}

export interface ContextInjectConfig {
  inject_profile?: boolean;
  max_profile_items?: number;
  max_static_profile_items?: number;
  max_memories?: number;
  max_chunks?: number;
  enable_semantic_dedup?: boolean;
  dedup_threshold?: number;
  enable_memory_graph?: boolean;
  memory_graph_depth?: number;
  memory_graph_nodes?: number;
  enable_entity_graph?: boolean;
  entity_graph_depth?: number;
  entity_graph_nodes?: number;
  memory_similarity_threshold?: number;
  language?: string;
  enable_chunks_search?: boolean;
  chunks_similarity_threshold?: number;
  entity_chunk_threshold?: number;
}

export interface ContextInjectSource {
  profile: string[];
  memories: Array<{ id: string; content: string }>;
  user_memories?: Array<{ id: string; content: string }>;
  chunks: Array<{ id: string; content: string }>;
  user_chunks?: Array<{ id: string; content: string }>;
}

export interface ContextInjectStats {
  total_items: number;
  after_dedup: number;
  deduped_count: number;
  profile_count: number;
  project_memories_count?: number;
  user_memories_count?: number;
  memories_count: number;
  chunks_count: number;
}

export interface ContextInjectResponse {
  context: string;
  sources: ContextInjectSource;
  stats: ContextInjectStats;
}

export class ConfigurationError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "ConfigurationError";
  }
}

export interface GraphRecallConfig {
  enableGraphRecall: boolean;
  enableEntityRecall: boolean;
  graphMaxDepth: number;
  graphMaxNodes: number;
}

const GRAPH_CONFIG_DEFAULTS: GraphRecallConfig = {
  enableGraphRecall: true,
  enableEntityRecall: true,
  graphMaxDepth: 2,
  graphMaxNodes: 5,
};

export function validateGraphConfig(config: Partial<GraphRecallConfig>): GraphRecallConfig {
  const result: GraphRecallConfig = {
    enableGraphRecall: config.enableGraphRecall ?? GRAPH_CONFIG_DEFAULTS.enableGraphRecall,
    enableEntityRecall: config.enableEntityRecall ?? GRAPH_CONFIG_DEFAULTS.enableEntityRecall,
    graphMaxDepth: config.graphMaxDepth ?? GRAPH_CONFIG_DEFAULTS.graphMaxDepth,
    graphMaxNodes: config.graphMaxNodes ?? GRAPH_CONFIG_DEFAULTS.graphMaxNodes,
  };

  if (result.graphMaxDepth < 1 || result.graphMaxDepth > 5) {
    throw new ConfigurationError(
      `graphMaxDepth must be between 1 and 5, got ${result.graphMaxDepth}`
    );
  }

  if (result.graphMaxNodes < 1 || result.graphMaxNodes > 20) {
    throw new ConfigurationError(
      `graphMaxNodes must be between 1 and 20, got ${result.graphMaxNodes}`
    );
  }

  return result;
}

const REQUEST_TIMEOUT_MS = 30000; // 30 seconds - API can be slow due to embedding generation

async function fetchWithTimeout(
  url: string,
  options: RequestInit,
  timeoutMs: number
): Promise<Response> {
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), timeoutMs);

  try {
    const response = await fetch(url, {
      ...options,
      signal: controller.signal,
    });
    return response;
  } finally {
    clearTimeout(timeoutId);
  }
}

export class ApiClient {
  private config: Config;
  private userTag: string;
  private projectTag: string;

  constructor(config: Config, userTag: string, projectTag: string) {
    this.config = config;
    this.userTag = userTag;
    this.projectTag = projectTag;
  }

  private async request<T>(
    path: string,
    method: string = "GET",
    body?: unknown,
    timeoutMs: number = REQUEST_TIMEOUT_MS
  ): Promise<T> {
    if (!this.config.apiKey) {
      throw new ConfigurationError("API key not configured");
    }

    const url = `${this.config.baseUrl}${path}`;
    const headers: Record<string, string> = {
      "Content-Type": "application/json",
      "X-API-Key": this.config.apiKey,
    };

    const response = await fetchWithTimeout(
      url,
      {
        method,
        headers,
        body: body ? JSON.stringify(body) : undefined,
      },
      timeoutMs
    );

    if (!response.ok) {
      const errorText = await response.text();
      throw new Error(`API error ${response.status}: ${errorText}`);
    }

    return response.json() as Promise<T>;
  }

  async addMemory(
    content: string,
    containerTag: string,
    isStatic: boolean = false,
    memoryType?: string,
    timeoutMs?: number
  ): Promise<Memory> {
    const response = await this.request<Memory>(
      "/memories",
      "POST",
      {
        content,
        container_tag: containerTag,
        is_static: isStatic,
        metadata: memoryType ? { type: memoryType } : undefined,
      },
      timeoutMs
    );
    return response;
  }

  async search(
    query: string,
    containerTag: string,
    limit: number = 10
  ): Promise<SearchResult[]> {
    const response = await this.request<{ results: SearchResult[] }>(
      "/search",
      "POST",
      {
        query,
        container_tag: containerTag,
        limit,
        threshold: this.config.similarityThreshold,
      }
    );
    return response.results || [];
  }

  async getProfile(
    containerTag: string,
    query?: string,
    maxStatic?: number,
    maxDynamic?: number
  ): Promise<ProfileResponse> {
    const params = new URLSearchParams({ container_tag: containerTag });
    if (query) {
      params.append("query", query);
    }
    if (maxStatic !== undefined) {
      params.append("max_static", Math.min(maxStatic, 50).toString());
    }
    if (maxDynamic !== undefined) {
      params.append("max_dynamic", Math.min(maxDynamic, 50).toString());
    }
    return this.request<ProfileResponse>(`/profile?${params.toString()}`);
  }

  async listMemories(
    containerTag: string,
    limit: number = 20
  ): Promise<Memory[]> {
    const params = new URLSearchParams({
      container_tag: containerTag,
      limit: limit.toString(),
    });
    const response = await this.request<{ memories: Memory[] }>(
      `/memories?${params.toString()}`
    );
    return response.memories || [];
  }

  async forgetMemory(memoryId: string): Promise<void> {
    await this.request(`/memories/${memoryId}/forget`, "POST");
  }

  async getGraph(
    containerTag: string,
    options?: {
      limit?: number;
      offset?: number;
      isStatic?: boolean;
    }
  ): Promise<GraphResponse> {
    const params = new URLSearchParams({ container_tag: containerTag });
    if (options?.limit) {
      params.append("limit", options.limit.toString());
    }
    if (options?.offset) {
      params.append("offset", options.offset.toString());
    }
    if (options?.isStatic !== undefined) {
      params.append("is_static", options.isStatic.toString());
    }
    return this.request<GraphResponse>(`/graph?${params.toString()}`);
  }

  async getRelatedMemories(
    memoryId: string,
    relationTypes?: ("updates" | "extends" | "derives")[]
  ): Promise<RelatedMemory[]> {
    const params = new URLSearchParams();
    if (relationTypes && relationTypes.length > 0) {
      params.append("relation_types", relationTypes.join(","));
    }
    const response = await this.request<{ relations: RelatedMemory[] }>(
      `/memories/${memoryId}/relations?${params.toString()}`
    );
    return response.relations || [];
  }

  getUserTag(): string {
    return this.userTag;
  }

  getProjectTag(): string {
    return this.projectTag;
  }

  async validateConfiguration(): Promise<void> {
    if (!this.config.apiKey) {
      throw new ConfigurationError(
        "API key not found. Set MEMORY_RECALL_API_KEY environment variable or add 'apiKey' to ~/.config/opencode/memory-recall.jsonc"
      );
    }

    try {
      await this.request("/health", "GET");
    } catch (e) {
      throw new ConfigurationError(
        `Cannot connect to Memory Recall API at ${this.config.baseUrl}: ${e}`
      );
    }
  }

  async injectContext(
    userTag: string,
    projectTag: string,
    query?: string,
    config?: ContextInjectConfig
  ): Promise<ContextInjectResponse> {
    return this.request<ContextInjectResponse>("/context-inject", "POST", {
      user_tag: userTag,
      project_tag: projectTag,
      query,
      config: config || {},
    });
  }

  async extractMemoryFromSummary(
    summary: string,
    language: string = "zh_CN"
  ): Promise<{ memories: Array<{ content: string; type: string; reason: string }>; has_worthwhile: boolean }> {
    return this.request("/extract-memory", "POST", {
      summary,
      language,
    });
  }
}
