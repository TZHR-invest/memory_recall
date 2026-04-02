import { describe, test, expect, beforeEach } from "bun:test";
import { computeCosineSimilarity, semanticDeduplicate, createDeduplicableItem, type DeduplicableItem } from "../src/semantic-dedup";
import type { ApiClient } from "../src/client";

describe("computeCosineSimilarity", () => {
  test("returns 1.0 for identical vectors", () => {
    const vector = [1, 2, 3, 4, 5];
    const similarity = computeCosineSimilarity(vector, vector);
    expect(similarity).toBeCloseTo(1.0, 5);
  });

  test("returns 0.0 for orthogonal vectors", () => {
    const a = [1, 0, 0];
    const b = [0, 1, 0];
    const similarity = computeCosineSimilarity(a, b);
    expect(similarity).toBeCloseTo(0.0, 5);
  });

  test("returns -1.0 for opposite vectors", () => {
    const a = [1, 2, 3];
    const b = [-1, -2, -3];
    const similarity = computeCosineSimilarity(a, b);
    expect(similarity).toBeCloseTo(-1.0, 5);
  });

  test("returns 0.0 for vectors of different dimensions", () => {
    const a = [1, 2, 3];
    const b = [1, 2, 3, 4];
    const similarity = computeCosineSimilarity(a, b);
    expect(similarity).toBe(0);
  });

  test("returns 0.0 for empty vectors", () => {
    const similarity = computeCosineSimilarity([], []);
    expect(similarity).toBe(0);
  });

  test("returns 0.0 for zero vectors", () => {
    const a = [0, 0, 0];
    const b = [1, 2, 3];
    const similarity = computeCosineSimilarity(a, b);
    expect(similarity).toBe(0);
  });

  test("handles typical embedding vectors", () => {
    const a = [0.1, 0.2, 0.3, 0.4, 0.5];
    const b = [0.1, 0.2, 0.3, 0.4, 0.5];
    const similarity = computeCosineSimilarity(a, b);
    expect(similarity).toBeCloseTo(1.0, 5);
  });

  test("calculates correct similarity for similar vectors", () => {
    const a = [1, 0, 0];
    const b = [0.707, 0.707, 0];
    const similarity = computeCosineSimilarity(a, b);
    expect(similarity).toBeCloseTo(0.707, 2);
  });
});

describe("createDeduplicableItem", () => {
  test("creates item with profile source", () => {
    const item = createDeduplicableItem("我叫张三", "profile");
    expect(item.content).toBe("我叫张三");
    expect(item.source).toBe("profile");
    expect(item.priority).toBe(4);
  });

  test("creates item with projectMemory source", () => {
    const item = createDeduplicableItem("项目记忆", "projectMemory", "mem_123");
    expect(item.content).toBe("项目记忆");
    expect(item.source).toBe("projectMemory");
    expect(item.priority).toBe(3);
    expect(item.id).toBe("mem_123");
  });

  test("creates item with userMemory source", () => {
    const item = createDeduplicableItem("用户记忆", "userMemory");
    expect(item.source).toBe("userMemory");
    expect(item.priority).toBe(2);
  });

  test("creates item with chunk source", () => {
    const item = createDeduplicableItem("文档片段", "chunk");
    expect(item.source).toBe("chunk");
    expect(item.priority).toBe(1);
  });
});

describe("semanticDeduplicate", () => {
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

  test("keeps items with low similarity", async () => {
    const embeddings = new Map<string, number[]>([
      ["我叫张三", [1, 0, 0]],
      ["我喜欢Python", [0, 1, 0]],
    ]);

    const client = createMockClient(embeddings) as ApiClient;
    const items = [
      createDeduplicableItem("我叫张三", "profile"),
      createDeduplicableItem("我喜欢Python", "profile"),
    ];

    const result = await semanticDeduplicate(client, items, 0.85, 50);

    expect(result.items).toHaveLength(2);
    expect(result.stats.removed).toBe(0);
  });

  test("removes items with high similarity", async () => {
    const embeddings = new Map<string, number[]>([
      ["我叫张三", [1, 0, 0]],
      ["我的名字是张三", [0.99, 0.01, 0]],
    ]);

    const client = createMockClient(embeddings) as ApiClient;
    const items = [
      createDeduplicableItem("我叫张三", "profile"),
      createDeduplicableItem("我的名字是张三", "userMemory"),
    ];

    const result = await semanticDeduplicate(client, items, 0.85, 50);

    expect(result.items).toHaveLength(1);
    expect(result.items[0].content).toBe("我叫张三");
    expect(result.stats.removed).toBe(1);
  });

  test("respects priority order: profile > projectMemory > userMemory > chunk", async () => {
    const embeddings = new Map<string, number[]>([
      ["张三", [1, 0, 0]],
      ["张三", [1, 0, 0]],
      ["张三", [1, 0, 0]],
      ["张三", [1, 0, 0]],
    ]);

    const client = createMockClient(embeddings) as ApiClient;
    const items = [
      createDeduplicableItem("张三", "chunk"),
      createDeduplicableItem("张三", "userMemory"),
      createDeduplicableItem("张三", "projectMemory"),
      createDeduplicableItem("张三", "profile"),
    ];

    const result = await semanticDeduplicate(client, items, 0.85, 50);

    expect(result.items).toHaveLength(1);
    expect(result.items[0].source).toBe("profile");
  });

  test("keeps profile over userMemory when semantically similar", async () => {
    const embeddings = new Map<string, number[]>([
      ["我在字节跳动工作", [1, 0, 0]],
      ["工作单位是字节跳动", [0.95, 0.05, 0]],
    ]);

    const client = createMockClient(embeddings) as ApiClient;
    const items = [
      createDeduplicableItem("我在字节跳动工作", "profile"),
      createDeduplicableItem("工作单位是字节跳动", "userMemory"),
    ];

    const result = await semanticDeduplicate(client, items, 0.85, 50);

    expect(result.items).toHaveLength(1);
    expect(result.items[0].source).toBe("profile");
    expect(result.stats.bySource.profile.kept).toBe(1);
    expect(result.stats.bySource.userMemory.removed).toBe(1);
  });

  test("handles items without embeddings", async () => {
    const client = createMockClient(new Map()) as ApiClient;
    const items = [
      createDeduplicableItem("内容A", "profile"),
      createDeduplicableItem("内容B", "projectMemory"),
    ];

    const result = await semanticDeduplicate(client, items, 0.85, 50);

    expect(result.items.length).toBeGreaterThanOrEqual(2);
  });

  test("handles empty items array", async () => {
    const client = createMockClient(new Map()) as ApiClient;
    const result = await semanticDeduplicate(client, [], 0.85, 50);

    expect(result.items).toHaveLength(0);
    expect(result.stats.total).toBe(0);
    expect(result.stats.removed).toBe(0);
  });

  test("handles single item", async () => {
    const embeddings = new Map<string, number[]>([
      ["单个项目", [1, 0, 0]],
    ]);

    const client = createMockClient(embeddings) as ApiClient;
    const items = [createDeduplicableItem("单个项目", "profile")];

    const result = await semanticDeduplicate(client, items, 0.85, 50);

    expect(result.items).toHaveLength(1);
    expect(result.stats.removed).toBe(0);
  });

  test("threshold behavior: lower threshold removes more items", async () => {
    const embeddings = new Map<string, number[]>([
      ["A", [1, 0, 0]],
      ["B", [0.87, 0.35, 0]],
      ["C", [0, 1, 0]],
    ]);

    const client = createMockClient(embeddings) as ApiClient;
    const items = [
      createDeduplicableItem("A", "profile"),
      createDeduplicableItem("B", "userMemory"),
      createDeduplicableItem("C", "projectMemory"),
    ];

    const result90 = await semanticDeduplicate(client, [...items], 0.90, 50);
    const result85 = await semanticDeduplicate(client, [...items], 0.85, 50);

    expect(result90.items.length).toBeGreaterThanOrEqual(result85.items.length);
  });

  test("correctly updates stats by source", async () => {
    const embeddings = new Map<string, number[]>([
      ["profile内容", [1, 0, 0]],
      ["project重复", [1, 0, 0]],
      ["user重复", [1, 0, 0]],
      ["chunk重复", [1, 0, 0]],
      ["唯一内容", [0, 1, 0]],
    ]);

    const client = createMockClient(embeddings) as ApiClient;
    const items = [
      createDeduplicableItem("profile内容", "profile"),
      createDeduplicableItem("project重复", "projectMemory"),
      createDeduplicableItem("user重复", "userMemory"),
      createDeduplicableItem("chunk重复", "chunk"),
      createDeduplicableItem("唯一内容", "projectMemory"),
    ];

    const result = await semanticDeduplicate(client, items, 0.85, 50);

    expect(result.stats.bySource.profile.kept).toBe(1);
    expect(result.stats.bySource.projectMemory.removed).toBe(1);
    expect(result.stats.bySource.projectMemory.kept).toBe(1);
    expect(result.stats.bySource.userMemory.removed).toBe(1);
    expect(result.stats.bySource.chunk.removed).toBe(1);
  });
});
