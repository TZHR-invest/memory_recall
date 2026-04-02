import type { ApiClient } from "./client";
import { getEmbeddingCache } from "./embedding-cache";

export function computeCosineSimilarity(a: number[], b: number[]): number {
  if (a.length !== b.length) {
    return 0;
  }

  if (a.length === 0) {
    return 0;
  }

  let dotProduct = 0;
  let normA = 0;
  let normB = 0;

  for (let i = 0; i < a.length; i++) {
    dotProduct += a[i] * b[i];
    normA += a[i] * a[i];
    normB += b[i] * b[i];
  }

  if (normA === 0 || normB === 0) {
    return 0;
  }

  return dotProduct / (Math.sqrt(normA) * Math.sqrt(normB));
}

export type DedupSource = "profile" | "projectMemory" | "userMemory" | "chunk";

export interface DeduplicableItem {
  content: string;
  source: DedupSource;
  priority: number;
  id?: string;
  embedding?: number[];
}

const SOURCE_PRIORITY: Record<DedupSource, number> = {
  profile: 4,
  projectMemory: 3,
  userMemory: 2,
  chunk: 1,
};

export function createDeduplicableItem(
  content: string,
  source: DedupSource,
  id?: string
): DeduplicableItem {
  return {
    content,
    source,
    priority: SOURCE_PRIORITY[source],
    id,
  };
}

export interface SemanticDedupResult {
  items: DeduplicableItem[];
  stats: {
    total: number;
    removed: number;
    bySource: Record<DedupSource, { kept: number; removed: number }>;
  };
}

export async function semanticDeduplicate(
  client: ApiClient,
  items: DeduplicableItem[],
  threshold: number,
  maxBatchSize: number = 50
): Promise<SemanticDedupResult> {
  if (items.length <= 1) {
    return {
      items,
      stats: {
        total: items.length,
        removed: 0,
        bySource: {
          profile: { kept: 0, removed: 0 },
          projectMemory: { kept: 0, removed: 0 },
          userMemory: { kept: 0, removed: 0 },
          chunk: { kept: 0, removed: 0 },
        },
      },
    };
  }

  const cache = getEmbeddingCache();

  const missingContents = cache.getMissing(items.map((i) => i.content));
  if (missingContents.length > 0) {
    const batches: string[][] = [];
    for (let i = 0; i < missingContents.length; i += maxBatchSize) {
      batches.push(missingContents.slice(i, i + maxBatchSize));
    }

    for (const batch of batches) {
      try {
        const embeddings = await client.embedBatch(batch);
        if (embeddings) {
          for (let i = 0; i < batch.length; i++) {
            if (embeddings[i]) {
              cache.set(batch[i], embeddings[i]);
            }
          }
        }
      } catch (error) {
        console.warn("Failed to compute embeddings for batch:", error);
      }
    }
  }

  for (const item of items) {
    if (!item.embedding) {
      item.embedding = cache.get(item.content) || undefined;
    }
  }

  const itemsWithEmbeddings = items.filter((i) => i.embedding);
  const itemsWithoutEmbeddings = items.filter((i) => !i.embedding);

  const sortedItems = [...itemsWithEmbeddings].sort(
    (a, b) => b.priority - a.priority
  );

  const kept: DeduplicableItem[] = [];
  const removed: DeduplicableItem[] = [];

  for (const item of sortedItems) {
    let isDuplicate = false;

    for (const keptItem of kept) {
      if (keptItem.embedding && item.embedding) {
        const similarity = computeCosineSimilarity(
          keptItem.embedding,
          item.embedding
        );

        if (similarity >= threshold) {
          isDuplicate = true;
          removed.push(item);
          break;
        }
      }
    }

    if (!isDuplicate) {
      kept.push(item);
    }
  }

  kept.push(...itemsWithoutEmbeddings);

  const stats: SemanticDedupResult["stats"] = {
    total: items.length,
    removed: removed.length,
    bySource: {
      profile: { kept: 0, removed: 0 },
      projectMemory: { kept: 0, removed: 0 },
      userMemory: { kept: 0, removed: 0 },
      chunk: { kept: 0, removed: 0 },
    },
  };

  for (const item of kept) {
    stats.bySource[item.source].kept++;
  }
  for (const item of removed) {
    stats.bySource[item.source].removed++;
  }

  return {
    items: kept,
    stats,
  };
}
