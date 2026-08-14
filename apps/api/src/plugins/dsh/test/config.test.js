/**
 * config.js 单元测试（无外部依赖，纯函数）
 */
import { test } from "node:test";
import assert from "node:assert/strict";
import {
  resolveConfig,
  projectTagFor,
  projectDirName,
  detectLocale,
  shouldTriggerRecall,
  DEFAULT_RECALL_KEYWORDS,
  INJECTION_STRATEGIES,
} from "../config.js";

test("resolveConfig 默认值", () => {
  const c = resolveConfig({});
  assert.equal(c.apiKey, null);
  assert.equal(c.baseUrl, "http://localhost:8000");
  assert.equal(c.autoRecall, true);
  assert.equal(c.autoCapture, true);
  assert.equal(c.injectionStrategy, "smart");
  assert.equal(c.maxMemories, 5);
  assert.equal(c.captureMode, "extract");
  assert.equal(c.smartRecallKeywords, DEFAULT_RECALL_KEYWORDS);
});

test("resolveConfig 环境变量兜底", () => {
  process.env.MEMORY_RECALL_API_KEY = "rk_live_test";
  process.env.MEMORY_RECALL_BASE_URL = "http://example.com:9000/";
  try {
    const c = resolveConfig({});
    assert.equal(c.apiKey, "rk_live_test");
    assert.equal(c.baseUrl, "http://example.com:9000"); // 尾部斜杠被去除
  } finally {
    delete process.env.MEMORY_RECALL_API_KEY;
    delete process.env.MEMORY_RECALL_BASE_URL;
  }
});

test("resolveConfig patch 覆盖环境变量", () => {
  process.env.MEMORY_RECALL_API_KEY = "rk_live_env";
  try {
    const c = resolveConfig({ apiKey: "rk_live_patch", baseUrl: "http://x:1" });
    assert.equal(c.apiKey, "rk_live_patch");
  } finally {
    delete process.env.MEMORY_RECALL_API_KEY;
  }
});

test("resolveConfig 边界夹取（防止后端 422）", () => {
  const c = resolveConfig({
    maxMemories: 999,
    graphMaxDepth: -3,
    similarityThreshold: 5,
    requestTimeoutMs: 0,
  });
  assert.equal(c.maxMemories, 20);
  assert.equal(c.graphMaxDepth, 1);
  assert.equal(c.similarityThreshold, 1);
  assert.equal(c.requestTimeoutMs, 1000);
});

test("resolveConfig 非法策略抛错", () => {
  assert.throws(() => resolveConfig({ injectionStrategy: "nope" }));
  assert.throws(() => resolveConfig({ captureMode: "nope" }));
  assert.ok(INJECTION_STRATEGIES.includes("smart"));
});

test("projectTagFor / projectDirName", () => {
  assert.equal(projectDirName("/a/b/my-project"), "my-project");
  assert.equal(projectDirName("/a/b/my-project/"), "my-project");
  assert.equal(projectDirName(""), "default");
  assert.equal(projectTagFor("key-1", "/home/user/repos/foo"), "key-1_project-foo");
});

test("detectLocale", () => {
  assert.equal(detectLocale("帮我查一下项目架构", "auto"), "zh_CN");
  assert.equal(detectLocale("how does this work", "auto"), "en_US");
  assert.equal(detectLocale("anything", "zh_CN"), "zh_CN");
});

test("shouldTriggerRecall", () => {
  assert.equal(shouldTriggerRecall("你还记得之前的架构决策吗", DEFAULT_RECALL_KEYWORDS), true);
  assert.equal(shouldTriggerRecall("please recall the earlier design", DEFAULT_RECALL_KEYWORDS), true);
  assert.equal(shouldTriggerRecall("今天天气不错", DEFAULT_RECALL_KEYWORDS), false);
  assert.equal(shouldTriggerRecall("", DEFAULT_RECALL_KEYWORDS), false);
});
