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

export interface ChunkSearchResult {
  id: string;
  content: string;
  document_id: string;
  document_title?: string;
  document_type?: string;
  position?: number;
  similarity: number;
}

export interface HybridSearchResult {
  id: string;
  content: string;
  source: "memory" | "chunk";
  similarity: number;
  document_title?: string;
  document_type?: string;
}

export interface Profile {
  static: string[];
  dynamic: string[];
}

export interface ProfileResponse {
  profile: Profile;
  searchResults?: SearchResult[];
}

export class ConfigurationError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "ConfigurationError";
  }
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
    body?: unknown
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
      REQUEST_TIMEOUT_MS
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
    memoryType?: string
  ): Promise<Memory> {
    const response = await this.request<Memory>("/memories", "POST", {
      content,
      container_tag: containerTag,
      is_static: isStatic,
      metadata: memoryType ? { type: memoryType } : undefined,
    });
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
    query?: string
  ): Promise<ProfileResponse> {
    const params = new URLSearchParams({ container_tag: containerTag });
    if (query) {
      params.append("query", query);
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

  async searchChunks(
    query: string,
    containerTag: string,
    limit: number = 10,
    threshold: number = 0.5,
    docTypes?: string[]
  ): Promise<ChunkSearchResult[]> {
    const response = await this.request<{ results: ChunkSearchResult[] }>(
      "/documents/search",
      "POST",
      {
        query,
        container_tag: containerTag,
        limit,
        threshold,
        doc_types: docTypes,
      }
    );
    return response.results || [];
  }

  async searchHybrid(
    query: string,
    containerTag: string,
    limit: number = 10,
    threshold: number = 0.5,
    sources?: ("memory" | "chunk")[]
  ): Promise<HybridSearchResult[]> {
    const response = await this.request<{ results: HybridSearchResult[] }>(
      "/search/hybrid",
      "POST",
      {
        query,
        container_tag: containerTag,
        limit,
        threshold,
        sources,
      }
    );
    return response.results || [];
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
}
