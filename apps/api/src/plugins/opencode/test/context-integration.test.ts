import { describe, test, expect, beforeEach } from "bun:test";
import { formatContext, injectContext, deduplicateWithSemanticLayer, type ContextOptions, type CrossScopeDedupResult } from "../src/context";
import type { Profile, Memory, SearchResult, ChunkSearchResult, ApiClient } from "../src/client";
import type { SemanticDedupConfig } from "../src/config";

describe("formatContext with semantic deduplication", () => {
  const createMemory = (id: string, content: string): Memory => ({
    id,
    content,
    container_tag: "test",
    is_static: true,
    is_latest: true,
    created_at: new Date().toISOString(),
  });

  const createUserMemory = (id: string, content: string, similarity: number): SearchResult => ({
    id,
    content,
    similarity,
  });

  const createChunk = (id: string, content: string, document_id: string, similarity: number): ChunkSearchResult => ({
    id,
    content,
    document_id,
    similarity,
  });

  test("formats context with dedupedResult provided", () => {
    const profile: Profile = {
      static: ["我叫张三"],
      dynamic: ["最近在做项目"],
    };

    const projectMemories = [createMemory("pm_1", "项目记忆")];
    const userMemories = [createUserMemory("um_1", "用户记忆", 0.9)];
    const chunks = [createChunk("ch_1", "文档片段", "doc_1", 0.8)];

    const dedupedResult: CrossScopeDedupResult = {
      staticFacts: ["我叫张三"],
      dynamicFacts: ["最近在做项目"],
      dedupedProjectMemories: projectMemories,
      dedupedUserMemories: userMemories,
      dedupedChunks: chunks,
      dedupStats: {
        projectMemoriesFiltered: 0,
        userMemoriesFiltered: 0,
        chunksFiltered: 0,
      },
    };

    const options: ContextOptions = {
      profile,
      projectMemories,
      userMemories,
      projectChunks: chunks,
      locale: "zh_CN",
      maxProfileItems: 5,
      maxProjectItems: 10,
      maxUserItems: 5,
      maxChunksItems: 3,
      dedupedResult,
    };

    const context = formatContext(options);

    expect(context).toContain("我叫张三");
    expect(context).toContain("最近在做项目");
    expect(context).toContain("项目记忆");
    expect(context).toContain("用户记忆");
  });

  test("formats context without dedupedResult (fallback to hash dedup)", () => {
    const profile: Profile = {
      static: ["永久特征"],
      dynamic: [],
    };

    const projectMemories = [createMemory("pm_1", "项目记忆")];
    const userMemories = [createUserMemory("um_1", "用户记忆", 0.9)];
    const chunks = [createChunk("ch_1", "文档片段", "doc_1", 0.8)];

    const options: ContextOptions = {
      profile,
      projectMemories,
      userMemories,
      projectChunks: chunks,
      locale: "en_US",
      maxProfileItems: 5,
      maxProjectItems: 10,
      maxUserItems: 5,
      maxChunksItems: 3,
    };

    const context = formatContext(options);

    expect(context).toContain("Static Facts");
    expect(context).toContain("永久特征");
    expect(context).toContain("Project Memories");
    expect(context).toContain("Related Memories");
  });

  test("omits empty sections after deduplication", () => {
    const profile: Profile = {
      static: ["唯一的profile内容"],
      dynamic: [],
    };

    const projectMemories = [createMemory("pm_1", "唯一的profile内容")];
    const userMemories = [createUserMemory("um_1", "唯一的profile内容", 0.9)];
    const chunks = [createChunk("ch_1", "唯一的profile内容", "doc_1", 0.8)];

    const options: ContextOptions = {
      profile,
      projectMemories,
      userMemories,
      projectChunks: chunks,
      locale: "zh_CN",
      maxProfileItems: 5,
      maxProjectItems: 10,
      maxUserItems: 5,
      maxChunksItems: 3,
    };

    const context = formatContext(options);

    expect(context).toContain("唯一的profile内容");
    expect(context).not.toContain("Project Memories");
    expect(context).not.toContain("Related Memories");
    expect(context).not.toContain("Project Documents");
  });
});

describe("deduplicateWithSemanticLayer", () => {
  const createMemory = (id: string, content: string): Memory => ({
    id,
    content,
    container_tag: "test",
    is_static: true,
    is_latest: true,
    created_at: new Date().toISOString(),
  });

  const createUserMemory = (id: string, content: string, similarity: number): SearchResult => ({
    id,
    content,
    similarity,
  });

  const createChunk = (id: string, content: string, document_id: string, similarity: number): ChunkSearchResult => ({
    id,
    content,
    document_id,
    similarity,
  });

  const createMockClient = (embeddings: Map<string, number[]>): Partial<ApiClient> => {
    return {
      embedBatch: async (texts: string[]) => {
        const results: number[][] = [];
        for (const text of texts) {
          const embedding = embeddings.get(text);
          if (embedding) {
            results.push(embedding);
          } else {
            results.push(Array(1024).fill(0));
          }
        }
        return results;
      },
    } as Partial<ApiClient>;
  };

  test("falls back to hash dedup when semantic dedup is disabled", async () => {
    const profile: Profile = {
      static: ["profile内容"],
      dynamic: [],
    };

    const projectMemories = [createMemory("pm_1", "项目记忆")];
    const userMemories = [createUserMemory("um_1", "用户记忆", 0.9)];
    const chunks = [createChunk("ch_1", "文档片段", "doc_1", 0.8)];

    const client = createMockClient(new Map()) as ApiClient;
    const config: SemanticDedupConfig = {
      enabled: false,
      threshold: 0.85,
      maxBatchSize: 50,
    };

    const result = await deduplicateWithSemanticLayer(
      client,
      profile,
      projectMemories,
      userMemories,
      chunks,
      config
    );

    expect(result.staticFacts).toContain("profile内容");
    expect(result.dedupedProjectMemories).toHaveLength(1);
    expect(result.dedupStats.semanticStats).toBeUndefined();
  });

  test("performs semantic dedup when enabled", async () => {
    const embeddings = new Map<string, number[]>([
      ["profile内容", [1, 0, 0]],
      ["项目记忆", [0, 1, 0]],
      ["用户记忆", [0, 0, 1]],
      ["文档片段", [1, 1, 0]],
    ]);

    const profile: Profile = {
      static: ["profile内容"],
      dynamic: [],
    };

    const projectMemories = [createMemory("pm_1", "项目记忆")];
    const userMemories = [createUserMemory("um_1", "用户记忆", 0.9)];
    const chunks = [createChunk("ch_1", "文档片段", "doc_1", 0.8)];

    const client = createMockClient(embeddings) as ApiClient;
    const config: SemanticDedupConfig = {
      enabled: true,
      threshold: 0.85,
      maxBatchSize: 50,
    };

    const result = await deduplicateWithSemanticLayer(
      client,
      profile,
      projectMemories,
      userMemories,
      chunks,
      config
    );

    expect(result.staticFacts).toContain("profile内容");
    expect(result.dedupStats.semanticStats).toBeDefined();
  });

  test("gracefully handles embedding API failure", async () => {
    const failingClient = {
      embedBatch: async () => {
        throw new Error("Embedding API failed");
      },
    } as Partial<ApiClient>;

    const profile: Profile = {
      static: ["profile内容"],
      dynamic: [],
    };

    const projectMemories = [createMemory("pm_1", "项目记忆")];
    const userMemories: SearchResult[] = [];
    const chunks: ChunkSearchResult[] = [];

    const config: SemanticDedupConfig = {
      enabled: true,
      threshold: 0.85,
      maxBatchSize: 50,
    };

    const result = await deduplicateWithSemanticLayer(
      failingClient as ApiClient,
      profile,
      projectMemories,
      userMemories,
      chunks,
      config
    );

    expect(result.staticFacts).toContain("profile内容");
    expect(result.dedupedProjectMemories).toHaveLength(1);
  });
});
