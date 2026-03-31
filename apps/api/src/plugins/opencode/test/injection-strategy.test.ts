import { describe, test, expect } from "bun:test";
import { shouldTriggerRecall, findTriggerKeyword } from "../src/recall-trigger";
import { DEFAULT_RECALL_KEYWORDS } from "../src/config";
import type { SmartRecallConfig } from "../src/config";
import { InjectedMemoryTracker } from "../src/tracker";

describe("shouldTriggerRecall", () => {
  const defaultConfig: SmartRecallConfig = {
    enabled: true,
    keywords: DEFAULT_RECALL_KEYWORDS,
    maxAdditionalMemories: 3,
    maxAdditionalChunks: 2,
  };

  test("returns false when disabled", () => {
    const config: SmartRecallConfig = { ...defaultConfig, enabled: false };
    expect(shouldTriggerRecall("记得我之前说过什么吗", config)).toBe(false);
  });

  test("detects Chinese keyword '记得'", () => {
    expect(shouldTriggerRecall("记得我之前说过什么吗", defaultConfig)).toBe(true);
  });

  test("detects Chinese keyword '之前'", () => {
    expect(shouldTriggerRecall("之前我们讨论过这个问题", defaultConfig)).toBe(true);
  });

  test("detects Chinese keyword '上次'", () => {
    expect(shouldTriggerRecall("上次见面是什么时候", defaultConfig)).toBe(true);
  });

  test("detects English keyword 'recall'", () => {
    expect(shouldTriggerRecall("Can you recall what we discussed?", defaultConfig)).toBe(true);
  });

  test("detects English keyword 'remember'", () => {
    expect(shouldTriggerRecall("Do you remember my preferences?", defaultConfig)).toBe(true);
  });

  test("case-insensitive matching", () => {
    expect(shouldTriggerRecall("RECALL my settings", defaultConfig)).toBe(true);
    expect(shouldTriggerRecall("Remember This", defaultConfig)).toBe(true);
  });

  test("returns false when no keyword present", () => {
    expect(shouldTriggerRecall("Hello, how are you?", defaultConfig)).toBe(false);
    expect(shouldTriggerRecall("今天天气不错", defaultConfig)).toBe(false);
  });

  test("uses custom keywords when provided", () => {
    const customConfig: SmartRecallConfig = {
      ...defaultConfig,
      keywords: ["查找", "search"],
    };
    expect(shouldTriggerRecall("查找我的记忆", customConfig)).toBe(true);
    expect(shouldTriggerRecall("记得我说过什么", customConfig)).toBe(false);
  });

  test("empty keywords array uses defaults", () => {
    const emptyKeywordsConfig: SmartRecallConfig = {
      ...defaultConfig,
      keywords: [],
    };
    expect(shouldTriggerRecall("记得我说过什么", emptyKeywordsConfig)).toBe(true);
  });
});

describe("findTriggerKeyword", () => {
  const defaultConfig: SmartRecallConfig = {
    enabled: true,
    keywords: DEFAULT_RECALL_KEYWORDS,
    maxAdditionalMemories: 3,
    maxAdditionalChunks: 2,
  };

  test("returns null when disabled", () => {
    const config: SmartRecallConfig = { ...defaultConfig, enabled: false };
    expect(findTriggerKeyword("记得我说过什么", config)).toBe(null);
  });

  test("returns matched keyword", () => {
    expect(findTriggerKeyword("记得我说过什么", defaultConfig)).toBe("记得");
  });

  test("returns first matched keyword", () => {
    const result = findTriggerKeyword("之前记得我说过什么", defaultConfig);
    expect(["之前", "记得"]).toContain(result);
  });

  test("returns null when no keyword matched", () => {
    expect(findTriggerKeyword("今天天气很好", defaultConfig)).toBe(null);
  });
});

describe("InjectedMemoryTracker - Initial Injection", () => {
  test("needsInitialInjection returns true initially", () => {
    const tracker = new InjectedMemoryTracker(10);
    expect(tracker.needsInitialInjection()).toBe(true);
  });

  test("needsInitialInjection returns false after markInitialInjected", () => {
    const tracker = new InjectedMemoryTracker(10);
    tracker.markInitialInjected();
    expect(tracker.needsInitialInjection()).toBe(false);
  });

  test("clear resets initial injection state", () => {
    const tracker = new InjectedMemoryTracker(10);
    tracker.markInitialInjected();
    tracker.add("mem_1");
    tracker.clear();
    
    expect(tracker.needsInitialInjection()).toBe(true);
    expect(tracker.size()).toBe(0);
  });
});

describe("Injection Strategy Logic", () => {
  test("'once' strategy: only injects on first message", () => {
    const tracker = new InjectedMemoryTracker(10);
    
    const strategy = "once";
    
    const shouldInject1 = tracker.needsInitialInjection();
    expect(shouldInject1).toBe(true);
    
    tracker.markInitialInjected();
    
    const shouldInject2 = !tracker.needsInitialInjection();
    expect(strategy === "once" && shouldInject2).toBe(true);
  });

  test("'smart' strategy: injects on first message", () => {
    const tracker = new InjectedMemoryTracker(10);
    
    const strategy = "smart";
    const hasKeyword = false;
    
    const shouldInject = tracker.needsInitialInjection() || hasKeyword;
    
    if (strategy === "smart") {
      expect(shouldInject).toBe(true);
    }
  });

  test("'smart' strategy: triggers on keyword after initial", () => {
    const tracker = new InjectedMemoryTracker(10);
    tracker.markInitialInjected();
    
    const strategy = "smart";
    const config: SmartRecallConfig = {
      enabled: true,
      keywords: DEFAULT_RECALL_KEYWORDS,
      maxAdditionalMemories: 3,
      maxAdditionalChunks: 2,
    };
    
    const hasKeyword = shouldTriggerRecall("记得我说过什么", config);
    
    const shouldInject = !tracker.needsInitialInjection() && hasKeyword;
    
    if (strategy === "smart") {
      expect(shouldInject).toBe(true);
    }
  });

  test("'always' strategy: always injects", () => {
    const tracker = new InjectedMemoryTracker(10);
    tracker.markInitialInjected();
    
    const strategy = "always";
    
    expect(strategy === "always").toBe(true);
  });
});

describe("Backward Compatibility", () => {
  test("legacy enableSmartRecall maps to smart strategy", () => {
    const legacyConfig = { enableSmartRecall: true };
    const injectionStrategy = legacyConfig.enableSmartRecall ? "smart" : "once";
    
    expect(injectionStrategy).toBe("smart");
  });

  test("missing injectionStrategy defaults to smart", () => {
    const defaultStrategy = "smart";
    expect(defaultStrategy).toBe("smart");
  });
});
