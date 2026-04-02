import { computeContentHash } from "./context";

interface CacheEntry {
  embedding: number[];
  lastAccessed: number;
}

export class EmbeddingCache {
  private cache: Map<string, CacheEntry> = new Map();
  private maxSize: number;

  constructor(maxSize: number = 1000) {
    this.maxSize = maxSize;
  }

  get(content: string): number[] | null {
    const key = computeContentHash(content);
    const entry = this.cache.get(key);

    if (entry) {
      entry.lastAccessed = Date.now();
      return entry.embedding;
    }

    return null;
  }

  set(content: string, embedding: number[]): void {
    const key = computeContentHash(content);

    if (this.cache.size >= this.maxSize && !this.cache.has(key)) {
      this.evictLRU();
    }

    this.cache.set(key, {
      embedding,
      lastAccessed: Date.now(),
    });
  }

  has(content: string): boolean {
    const key = computeContentHash(content);
    return this.cache.has(key);
  }

  getMany(contents: string[]): Map<string, number[] | null> {
    const result = new Map<string, number[] | null>();

    for (const content of contents) {
      result.set(content, this.get(content));
    }

    return result;
  }

  setMany(entries: Array<{ content: string; embedding: number[] }>): void {
    for (const { content, embedding } of entries) {
      this.set(content, embedding);
    }
  }

  getMissing(contents: string[]): string[] {
    return contents.filter((content) => !this.has(content));
  }

  clear(): void {
    this.cache.clear();
  }

  size(): number {
    return this.cache.size;
  }

  private evictLRU(): void {
    let oldestKey: string | null = null;
    let oldestTime = Infinity;

    for (const [key, entry] of this.cache.entries()) {
      if (entry.lastAccessed < oldestTime) {
        oldestTime = entry.lastAccessed;
        oldestKey = key;
      }
    }

    if (oldestKey) {
      this.cache.delete(oldestKey);
    }
  }
}

let globalCache: EmbeddingCache | null = null;

export function getEmbeddingCache(maxSize: number = 1000): EmbeddingCache {
  if (!globalCache) {
    globalCache = new EmbeddingCache(maxSize);
  }
  return globalCache;
}

export function clearEmbeddingCache(): void {
  if (globalCache) {
    globalCache.clear();
  }
}
