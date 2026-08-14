/**
 * bundle.test.js — 浏览器端 bundle（client.js）与 ESM 库（client-lib.js）同步性 + 注册形态
 *
 * dsh web 用 classic script 加载 client.js（不能含 import/export），
 * 必须顶层 window.__ModuleLoader__.load 注册 { name, inject, apply }。
 * 本测试保证：生成产物不漂移、语法合法、注册形态正确。
 */
import { test } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import vm from "node:vm";
import { fileURLToPath } from "node:url";
import { buildClientBundle } from "../build-bundle.mjs";

const HERE = fileURLToPath(new URL("..", import.meta.url));
const LIB = fs.readFileSync(HERE + "/client-lib.js", "utf8");
const BUNDLE = fs.readFileSync(HERE + "/client.js", "utf8");

test("client.js 与 client-lib.js 同步（改库后需重跑 node build-bundle.mjs）", () => {
  assert.equal(BUNDLE, buildClientBundle(LIB), "client.js 已过期——请重跑 node build-bundle.mjs");
});

test("bundle 是合法 classic script（无 import/export 语句）", () => {
  const stripped = BUNDLE.replace(/\/\*[\s\S]*?\*\/|\/\/[^\n]*/g, "");
  assert.doesNotMatch(stripped, /\b(import|export)\b/, "bundle 不应含 import/export 语句");
  // classic script 解析检查
  assert.doesNotThrow(() => new Function(BUNDLE));
});

test("bundle 求值后通过 __ModuleLoader__.load 注册插件形状", () => {
  let handoff = null;
  const sandbox = {
    window: { __ModuleLoader__: { load: (h) => { handoff = h; } } },
    console,
    fetch: () => Promise.reject(new Error("no fetch")),
    URLSearchParams,
    setTimeout,
    clearTimeout,
    AbortController,
  };
  vm.createContext(sandbox);
  vm.runInContext(BUNDLE, sandbox);

  assert.ok(handoff, "bundle 未调用 __ModuleLoader__.load");
  assert.equal(handoff.id, "memory-recall-dsh");

  const plugin = handoff.factory((spec) => { throw new Error("不应 require: " + spec); });
  assert.equal(plugin.name, "memory-recall-dsh");
  // vm 域的数组与测试域原型不同，deepStrictEqual 会因引用不等失败，用跨域安全的断言
  assert.ok(Array.isArray(plugin.inject));
  assert.equal(plugin.inject.length, 0);
  assert.equal(typeof plugin.apply, "function");
  assert.equal(typeof plugin.MemoryRecallClient, "function");
  assert.equal(typeof plugin.buildInjectConfig, "function");
  assert.equal(typeof plugin.ConfigurationError, "function");
});

test("client-lib.js 仍是 ESM 库（index.js 依赖的导出齐全）", async () => {
  const lib = await import("../client-lib.js");
  assert.equal(typeof lib.MemoryRecallClient, "function");
  assert.equal(typeof lib.buildInjectConfig, "function");
  assert.equal(typeof lib.ConfigurationError, "function");
});
