import { describe, test, expect } from "bun:test";
import {
  InjectedMemoryTracker,
  SessionTrackerManager,
  calculateDynamicRecallSize,
  scanConversationHistory,
  filterMemoriesForInjection,
  type ConversationMessage,
} from "../src/tracker";

describe("InjectedMemoryTracker", () => {
  test("tracks injected memory IDs", () => {
    const tracker = new InjectedMemoryTracker(10);
    expect(tracker.has("mem_1")).toBe(false);
    
    tracker.add("mem_1");
    expect(tracker.has("mem_1")).toBe(true);
  });

  test("LRU eviction removes oldest entries", () => {
    const tracker = new InjectedMemoryTracker(3);
    
    tracker.add("mem_1");
    tracker.add("mem_2");
    tracker.add("mem_3");
    tracker.add("mem_4");
    
    expect(tracker.has("mem_1")).toBe(false);
    expect(tracker.has("mem_4")).toBe(true);
  });

  test("clear removes all entries", () => {
    const tracker = new InjectedMemoryTracker(10);
    
    tracker.add("mem_1");
    tracker.add("mem_2");
    tracker.clear();
    
    expect(tracker.size()).toBe(0);
  });

  test("filterNew returns only untracked items", () => {
    const tracker = new InjectedMemoryTracker(10);
    tracker.add("mem_1");
    
    const items = [
      { id: "mem_1", content: "A" },
      { id: "mem_2", content: "B" },
      { id: "mem_3", content: "C" },
    ];
    
    const filtered = tracker.filterNew(items);
    
    expect(filtered.length).toBe(2);
    expect(filtered[0].id).toBe("mem_2");
    expect(filtered[1].id).toBe("mem_3");
  });
});

describe("SessionTrackerManager", () => {
  test("returns different trackers for different sessions", () => {
    const manager = new SessionTrackerManager();
    
    const tracker1 = manager.getTracker("session_1");
    const tracker2 = manager.getTracker("session_2");
    
    tracker1.add("mem_1");
    
    expect(tracker1.has("mem_1")).toBe(true);
    expect(tracker2.has("mem_1")).toBe(false);
  });

  test("clearSession removes tracker for specific session", () => {
    const manager = new SessionTrackerManager();
    
    const tracker = manager.getTracker("session_1");
    tracker.add("mem_1");
    
    manager.clearSession("session_1");
    const newTracker = manager.getTracker("session_1");
    
    expect(newTracker.size()).toBe(0);
  });
});

describe("calculateDynamicRecallSize", () => {
  test("returns near full max for short conversations", () => {
    const result = calculateDynamicRecallSize(2, 10);
    expect(result).toBe(9);
  });

  test("reduces recall for long conversations", () => {
    const result = calculateDynamicRecallSize(10, 10);
    expect(result).toBeLessThan(10);
    expect(result).toBe(5);
  });

  test("respects minimum of 2", () => {
    const result = calculateDynamicRecallSize(100, 3);
    expect(result).toBe(2);
  });

  test("maximum reduction is 50%", () => {
    const result = calculateDynamicRecallSize(20, 10);
    expect(result).toBe(5);
  });
});

describe("scanConversationHistory", () => {
  test("filters memories already in AI responses", () => {
    const memories = [
      { id: "mem_1", content: "Alice is a product manager", similarity: 0.9 },
      { id: "mem_2", content: "Bob works at Google", similarity: 0.8 },
    ];
    
    const history: ConversationMessage[] = [
      { role: "user", content: "Who is Alice?" },
      { role: "assistant", content: "Alice is a product manager that I know about." },
    ];
    
    const result = scanConversationHistory(memories, history);
    
    expect(result.length).toBe(1);
    expect(result[0].id).toBe("mem_2");
  });

  test("keeps memories not in history", () => {
    const memories = [
      { id: "mem_1", content: "New information", similarity: 0.9 },
    ];
    
    const history: ConversationMessage[] = [
      { role: "assistant", content: "Some other content" },
    ];
    
    const result = scanConversationHistory(memories, history);
    
    expect(result.length).toBe(1);
  });

  test("limits scan to recent messages", () => {
    const memories = [
      { id: "mem_1", content: "Alice is a product manager", similarity: 0.9 },
    ];
    
    const history: ConversationMessage[] = Array(20).fill(null).map((_, i) => ({
      role: "assistant" as const,
      content: `Message ${i}`,
    }));
    history[5] = { role: "assistant", content: "Alice is a product manager" };
    
    const result = scanConversationHistory(memories, history, 10);
    
    expect(result.length).toBe(1);
  });
});

describe("filterMemoriesForInjection", () => {
  test("applies all filters in sequence", () => {
    const tracker = new InjectedMemoryTracker(10);
    tracker.add("mem_1");
    
    const memories = [
      { id: "mem_1", content: "Already injected", similarity: 0.9 },
      { id: "mem_2", content: "Low similarity", similarity: 0.3 },
      { id: "mem_3", content: "Good memory", similarity: 0.8 },
    ];
    
    const result = filterMemoriesForInjection(memories, tracker, 0.5);
    
    expect(result.length).toBe(1);
    expect(result[0].id).toBe("mem_3");
  });

  test("filters by threshold", () => {
    const tracker = new InjectedMemoryTracker(10);
    
    const memories = [
      { id: "mem_1", content: "High", similarity: 0.9 },
      { id: "mem_2", content: "Medium", similarity: 0.6 },
      { id: "mem_3", content: "Low", similarity: 0.4 },
    ];
    
    const result = filterMemoriesForInjection(memories, tracker, 0.5);
    
    expect(result.length).toBe(2);
  });
});
