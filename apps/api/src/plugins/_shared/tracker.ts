/**
 * 共享核 - 注入记忆去重与会话追踪（宿主无关）
 * 概念中立：使用 MemoryLike 通用接口，不依赖 opencode 的 client/context 宿主类型。
 */

export interface MemoryLike {
  id: string;
  content: string;
  similarity: number;
}

export class InjectedMemoryTracker {
  private injectedIds: Map<string, number> = new Map();
  private maxSize: number;
  private hasInitialInjection: boolean = false;

  constructor(maxSize: number = 100) {
    this.maxSize = maxSize;
  }

  has(memoryId: string): boolean {
    return this.injectedIds.has(memoryId);
  }

  add(memoryId: string): void {
    if (this.injectedIds.has(memoryId)) {
      this.injectedIds.set(memoryId, Date.now());
      return;
    }

    if (this.injectedIds.size >= this.maxSize) {
      const oldest = [...this.injectedIds.entries()]
        .sort((a, b) => a[1] - b[1])[0];
      if (oldest) {
        this.injectedIds.delete(oldest[0]);
      }
    }

    this.injectedIds.set(memoryId, Date.now());
  }

  addMany(memoryIds: string[]): void {
    for (const id of memoryIds) {
      this.add(id);
    }
  }

  clear(): void {
    this.injectedIds.clear();
    this.hasInitialInjection = false;
  }

  size(): number {
    return this.injectedIds.size;
  }

  markInitialInjected(): void {
    this.hasInitialInjection = true;
  }

  needsInitialInjection(): boolean {
    return !this.hasInitialInjection;
  }

  filterNew<T extends { id: string }>(items: T[]): T[] {
    return items.filter(item => !this.has(item.id));
  }
}

export class SessionTrackerManager {
  private trackers: Map<string, InjectedMemoryTracker> = new Map();
  private maxSize: number;

  constructor(maxSize: number = 100) {
    this.maxSize = maxSize;
  }

  getTracker(sessionId: string): InjectedMemoryTracker {
    let tracker = this.trackers.get(sessionId);
    if (!tracker) {
      tracker = new InjectedMemoryTracker(this.maxSize);
      this.trackers.set(sessionId, tracker);
    }
    return tracker;
  }

  clearSession(sessionId: string): void {
    this.trackers.delete(sessionId);
  }

  clearAll(): void {
    this.trackers.clear();
  }
}

export function calculateDynamicRecallSize(
  conversationLength: number,
  maxMemories: number
): number {
  const reduction = Math.min(0.5, conversationLength * 0.05);
  return Math.max(2, Math.floor(maxMemories * (1 - reduction)));
}

export interface ConversationMessage {
  role: "user" | "assistant";
  content: string;
}

export function scanConversationHistory<T extends MemoryLike>(
  memories: T[],
  history: ConversationMessage[],
  maxScanLength: number = 10
): T[] {
  const recentHistory = history.slice(-maxScanLength);

  const aiContent = recentHistory
    .filter(m => m.role === "assistant")
    .map(m => m.content)
    .join("\n");

  return memories.filter(m => {
    const contentSnippet = m.content.slice(0, 100);
    return !aiContent.includes(contentSnippet);
  });
}

export function filterMemoriesForInjection<T extends MemoryLike>(
  memories: T[],
  tracker: InjectedMemoryTracker,
  threshold: number = 0.5,
  history?: ConversationMessage[]
): T[] {
  let filtered = tracker.filterNew(memories);

  filtered = filtered.filter(m => m.similarity >= threshold);

  if (history && history.length > 0) {
    filtered = scanConversationHistory(filtered, history);
  }

  return filtered;
}
