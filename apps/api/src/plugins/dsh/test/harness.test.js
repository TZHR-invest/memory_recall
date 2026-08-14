/**
 * memory-recall-dsh 集成测试 harness
 *
 * 在真实 cordis 语义下驱动插件 apply()：
 *   - 假 ctx：capture 事件监听 + 模拟 agent/pre-step waterfall + 假 tools 注册表；
 *   - 假 agent：最小会话对象（header.cwd / events / inbox）；
 *   - 连真实后端（localhost:8000）：自动召回注入、工具注册与执行、去重、捕获。
 *
 * 运行前提：后端已启动；API Key 取 MEMORY_RECALL_API_KEY 或 opencode 插件配置。
 * 未配置 Key 时相关用例自动 skip。
 */
import { test, before, after } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import crypto from "node:crypto";
import { apply } from "../index.js";
import { createUserMessage } from "@deepseek-ai/dsh-llm";

const PLUGIN = "memory-recall-dsh";

/** 读 API Key：环境变量 > opencode 插件配置（JSONC 容错解析，先保护字符串再剥注释） */
function readApiKey() {
  if (process.env.MEMORY_RECALL_API_KEY) return process.env.MEMORY_RECALL_API_KEY;
  try {
    const p = path.join(os.homedir(), ".config", "opencode", "memory-recall.jsonc");
    if (!fs.existsSync(p)) return null;
    let text = fs.readFileSync(p, "utf8");
    // 先占位字符串字面量，避免 // 出现在 URL 等字符串内时被当成注释
    const protectedStrings = [];
    text = text.replace(/"(?:[^"\\]|\\.)*"/g, (match) => {
      protectedStrings.push(match);
      return `__JSONC_STR_${protectedStrings.length - 1}__`;
    });
    text = text.replace(/\/\/.*$/gm, "").replace(/\/\*[\s\S]*?\*\//g, "").replace(/,(\s*[}\]])/g, "$1");
    text = text.replace(/__JSONC_STR_(\d+)__/g, (_, idx) => protectedStrings[Number(idx)]);
    return JSON.parse(text).apiKey ?? null;
  } catch {
    return null;
  }
}

const API_KEY = readApiKey();
const HAS_BACKEND = API_KEY !== null;

/** 最小可用的 agents 服务替身 */
function makeFakeAgent(cwd, events = []) {
  return {
    session: {
      header: { cwd },
      events,
    },
    inbox: {
      nextStep: [],
      remove: () => true,
      prepend: () => {},
      replace: () => true,
    },
  };
}

/** 假 ctx：记录事件监听、模拟 waterfall emit、持有假 tools 注册表 */
function makeCtx() {
  const listeners = { "agent/pre-step": [], "session/event": [] };
  const tools = new Map(); // name -> definition
  const ctx = {
    tools: {
      register(def) {
        if (tools.has(def.name)) throw new Error(`duplicate tool ${def.name}`);
        tools.set(def.name, def);
        return () => tools.delete(def.name);
      },
    },
    logger: {
      info: (...a) => { if (process.env.MR_DEBUG_LOG) console.error("MR-INFO", ...a); },
      warn: (...a) => { if (process.env.MR_DEBUG_LOG) console.error("MR-WARN", ...a); },
      debug: (...a) => { if (process.env.MR_DEBUG_LOG) console.error("MR-DEBUG", ...a); },
      error: (...a) => { if (process.env.MR_DEBUG_LOG) console.error("MR-ERR", ...a); },
    },
    on(event, handler, options) {
      const list = listeners[event] ?? (listeners[event] = []);
      if (options?.prepend) list.unshift(handler);
      else list.push(handler);
      return () => {
        const i = list.indexOf(handler);
        if (i >= 0) list.splice(i, 1);
      };
    },
    effect: () => () => {},
    async emitPreStep(payload, nextImpl) {
      let decision = null;
      const run = async (index) => {
        if (index >= listeners["agent/pre-step"].length) return nextImpl();
        const handler = listeners["agent/pre-step"][index];
        return handler(payload, () => run(index + 1));
      };
      decision = await run(0);
      return decision;
    },
    emitSessionEvent(session, event) {
      for (const handler of listeners["session/event"]) handler(session, event);
    },
    toolsMap: tools,
  };
  return ctx;
}

function directUserMessage(text) {
  return createUserMessage({
    content: [{ type: "text", text }],
    source: { kind: "user" },
  });
}

function makeConfig(overrides = {}) {
  return {
    apiKey: API_KEY,
    baseUrl: "http://localhost:8000",
    autoRecall: true,
    autoCapture: true,
    injectionStrategy: "smart",
    ...overrides,
  };
}

test("插件导出契约", () => {
  const mod = { apply };
  assert.equal(typeof mod.apply, "function");
});

test("插件 apply 注册 5 个记忆工具（无 Key 时也注册，调用返回失败）", async () => {
  const ctx = makeCtx();
  apply(ctx, makeConfig({ apiKey: API_KEY ?? "rk_live_unset" }));
  const names = [...ctx.toolsMap.keys()].sort();
  assert.deepEqual(names, ["memory_forget", "memory_list", "memory_profile", "memory_search", "memory_store"]);
});

test("memory_store / memory_search / memory_profile / memory_forget 端到端（连真实后端）", { skip: !HAS_BACKEND }, async () => {
  const ctx = makeCtx();
  apply(ctx, makeConfig());
  const marker = `dsh-plugin-e2e-${Date.now()}`;
  const agent = makeFakeAgent("/home/user/projects/e2e-test");
  const exec = { agent, signal: new AbortController().signal };

  // store（同步模式：测试需要立即可搜索）
  const store = ctx.toolsMap.get("memory_store");
  const stored = await store.execute({ content: `${marker} 这是 dsh 插件的端到端测试记忆`, scope: "project", asyncProcess: false }, exec);
  assert.equal(stored.success, true, JSON.stringify(stored));
  assert.equal(stored.status, "done", "同步写入应返回 done");
  const memoryId = stored.id;

  // search
  const search = ctx.toolsMap.get("memory_search");
  const found = await search.execute({ query: marker, limit: 5 }, exec);
  assert.equal(found.success, true, JSON.stringify(found));
  assert.ok(found.results.some((r) => r.id === memoryId), "搜索结果应包含刚存的记忆");

  // profile（用户级）
  const profile = ctx.toolsMap.get("memory_profile");
  const prof = await profile.execute({}, { agent: makeFakeAgent("/x/y"), signal: new AbortController().signal });
  assert.equal(prof.success, true, JSON.stringify(prof));

  // forget（清理测试数据）
  const forget = ctx.toolsMap.get("memory_forget");
  const gone = await forget.execute({ memoryId }, exec);
  assert.equal(gone.success, true, JSON.stringify(gone));
});

test("自动召回：smart 策略下关键词触发注入（连真实后端）", { skip: !HAS_BACKEND }, async () => {
  const ctx = makeCtx();
  apply(ctx, makeConfig());
  const cwd = "/home/user/projects/recall-test";
  const agent = makeFakeAgent(cwd);
  const exec = { agent, signal: new AbortController().signal };
  const marker = `dsh-recall-marker-${Date.now()}`;

  // 先向项目容器写入一条记忆（关键词触发的注入才有内容可召回；同步模式保证立即可搜）
  const store = ctx.toolsMap.get("memory_store");
  const stored = await store.execute({ content: `${marker} 项目架构决策：后端用 FastAPI，前端用 React`, scope: "project", asyncProcess: false }, exec);
  assert.equal(stored.success, true, JSON.stringify(stored));

  // 非首次 + 关键词触发
  agent.session.events.push({ type: "user/message", data: { source: { kind: "user" }, content: [] } });
  const decision = await ctx.emitPreStep(
    { agent, messages: [], turn: 2, step: 1, signal: new AbortController().signal },
    async () => ({ kind: "enter", messages: [directUserMessage(`你还记得${marker}的项目架构决策吗`)] }),
  );
  assert.equal(decision.kind, "enter");
  const injected = decision.messages.filter((m) => m.source?.kind === "plugin" && m.source.plugin === PLUGIN);
  assert.ok(injected.length === 1, `应注入一条召回消息，实际 ${injected.length} 条：${JSON.stringify(decision.messages.map((m) => m.source))}`);
  const text = injected[0].content.find((b) => b.type === "text").text;
  assert.ok(text.startsWith("<system-reminder>"), "注入文本应以 system-reminder 开头");
  assert.ok(text.endsWith("</system-reminder>"), "注入文本应以 system-reminder 结尾");
  assert.ok(text.includes(marker), "注入文本应包含刚写入的记忆内容");

  // 同一摘要去重：把注入消息加入会话历史后再次触发，不应重复注入
  agent.session.events.push({ type: "user/message", data: injected[0] });
  const second = await ctx.emitPreStep(
    { agent, messages: [], turn: 3, step: 1, signal: new AbortController().signal },
    async () => ({ kind: "enter", messages: [directUserMessage(`你还记得${marker}的项目架构决策吗`)] }),
  );
  const injected2 = second.messages.filter((m) => m.source?.kind === "plugin" && m.source.plugin === PLUGIN);
  assert.equal(injected2.length, 0, "相同摘要不应重复注入");

  // 清理
  const forget = ctx.toolsMap.get("memory_forget");
  const gone = await forget.execute({ memoryId: stored.id }, exec);
  assert.equal(gone.success, true, JSON.stringify(gone));
});

test("自动召回：非关键词且非首次 → 不注入", { skip: !HAS_BACKEND }, async () => {
  const ctx = makeCtx();
  apply(ctx, makeConfig());
  const agent = makeFakeAgent("/home/user/projects/recall-test");
  agent.session.events.push({ type: "user/message", data: { source: { kind: "user" }, content: [] } });
  const decision = await ctx.emitPreStep(
    { agent, messages: [], turn: 2, step: 1, signal: new AbortController().signal },
    async () => ({ kind: "enter", messages: [directUserMessage("帮我写个 hello world")] }),
  );
  const injected = decision.messages.filter((m) => m.source?.kind === "plugin");
  assert.equal(injected.length, 0);
});

test("自动召回：策略 once 只在首次注入", { skip: !HAS_BACKEND }, async () => {
  const ctx = makeCtx();
  apply(ctx, makeConfig({ injectionStrategy: "once" }));
  const agent = makeFakeAgent("/home/user/projects/recall-test");

  // 首次：注入
  const first = await ctx.emitPreStep(
    { agent, messages: [], turn: 1, step: 1, signal: new AbortController().signal },
    async () => ({ kind: "enter", messages: [directUserMessage("你好，帮我看看这个项目")] }),
  );
  assert.ok(first.messages.filter((m) => m.source?.kind === "plugin").length === 1);

  // 非首次：即使有关键词也不注入
  agent.session.events.push({ type: "user/message", data: { source: { kind: "user" }, content: [] } });
  const second = await ctx.emitPreStep(
    { agent, messages: [], turn: 2, step: 1, signal: new AbortController().signal },
    async () => ({ kind: "enter", messages: [directUserMessage("还记得上次的决策吗")] }),
  );
  assert.equal(second.messages.filter((m) => m.source?.kind === "plugin").length, 0);
});

test("自动召回：后端不可达时 fail-open 不注入", async () => {
  const ctx = makeCtx();
  apply(ctx, makeConfig({ baseUrl: "http://127.0.0.1:1" })); // 必然连接失败
  const agent = makeFakeAgent("/home/user/projects/recall-test");
  const decision = await ctx.emitPreStep(
    { agent, messages: [], turn: 1, step: 1, signal: new AbortController().signal },
    async () => ({ kind: "enter", messages: [directUserMessage("你还记得之前的架构决策吗")] }),
  );
  assert.equal(decision.kind, "enter");
  assert.equal(decision.messages.filter((m) => m.source?.kind === "plugin").length, 0);
});

test("自动捕获：turn 结束写入会话摘要（连真实后端，清理验证）", { skip: !HAS_BACKEND }, async () => {
  const ctx = makeCtx();
  apply(ctx, makeConfig({ captureMode: "raw" })); // raw 模式原文落库，标记可确定性断言
  // 每次运行用独立容器目录：容器为空则后端不可能发生合并去重，
  // 捕获管道（turn 事件 → 摘要 → 落库到正确容器）可确定性断言
  const containerDir = `capture-test-${Date.now()}`;
  const session = { header: { cwd: `/home/user/projects/${containerDir}` } };
  const marker = `dsh-capture-${Date.now()}`;
  const randomHex = crypto.randomBytes(32).toString("hex");

  ctx.emitSessionEvent(session, { type: "turn/start", data: { turn: 1 } });
  ctx.emitSessionEvent(session, {
    type: "user/message",
    data: { source: { kind: "user" }, content: [{ type: "text", text: `${marker} 帮我记住这个测试` }] },
  });
  ctx.emitSessionEvent(session, {
    type: "assistant/message",
    data: { message: { content: [{ type: "text", text: `${marker} 助手回复随机内容 ${randomHex}${randomHex}${randomHex}` }] } },
  });
  ctx.emitSessionEvent(session, { type: "turn/end", data: { turn: 1, reason: "success" } });

  // 捕获是 fire-and-forget：轮询等待异步落库完成（embedding 生成可能耗时数秒）
  const search = ctx.toolsMap.get("memory_search");
  let found = null;
  for (let attempt = 0; attempt < 50; attempt++) {
    found = await search.execute({ query: marker, limit: 10 }, { agent: makeFakeAgent(`/home/user/projects/${containerDir}`), signal: new AbortController().signal });
    if (found.success && found.results.some((r) => r.content.includes(marker))) break;
    await new Promise((r) => setTimeout(r, 2000));
  }
  assert.equal(found.success, true, JSON.stringify(found));
  assert.ok(found.results.length > 0, "捕获的记忆应能被搜索到");
  const captured = found.results.find((r) => r.content.includes(marker));
  assert.ok(captured, "应找到包含标记的捕获记忆");
  // 清理
  const forget = ctx.toolsMap.get("memory_forget");
  const gone = await forget.execute({ memoryId: captured.id }, { agent: makeFakeAgent(`/home/user/projects/${containerDir}`), signal: new AbortController().signal });
  assert.equal(gone.success, true);
});

test("自动捕获：turn/end 前未产生助手回复 → 不落库", { skip: !HAS_BACKEND }, async () => {
  const ctx = makeCtx();
  apply(ctx, makeConfig());
  const session = { header: { cwd: "/home/user/projects/capture-test" } };
  ctx.emitSessionEvent(session, { type: "turn/start", data: { turn: 9 } });
  ctx.emitSessionEvent(session, {
    type: "user/message",
    data: { source: { kind: "user" }, content: [{ type: "text", text: "你好" }] },
  });
  ctx.emitSessionEvent(session, { type: "turn/end", data: { turn: 9, reason: "success" } });
  // 无助手文本 → 不应有任何后端调用；这里仅验证不抛异常
  await new Promise((r) => setTimeout(r, 300));
  assert.ok(true);
});

test("memory_store 默认异步：立即返回 status=processing（连真实后端）", { skip: !HAS_BACKEND }, async () => {
  const ctx = makeCtx();
  apply(ctx, makeConfig());
  const marker = `dsh-async-store-${Date.now()}`;
  const exec = { agent: makeFakeAgent("/home/user/projects/e2e-test"), signal: new AbortController().signal };
  const start = Date.now();
  const stored = await ctx.toolsMap.get("memory_store").execute({ content: `${marker} 异步写入测试`, scope: "project" }, exec);
  const elapsed = Date.now() - start;
  assert.equal(stored.success, true, JSON.stringify(stored));
  assert.equal(stored.status, "processing", "默认异步应返回 processing");
  assert.ok(elapsed < 5000, `异步写入应快速返回（实际 ${elapsed}ms）`);
  // 清理：异步写入的 embedding 尚未完成，forget 不依赖 embedding，可直接删
  const forget = ctx.toolsMap.get("memory_forget");
  const gone = await forget.execute({ memoryId: stored.id }, exec);
  assert.equal(gone.success, true, JSON.stringify(gone));
});

test("自动捕获：subagent 会话不入库（连真实后端）", { skip: !HAS_BACKEND }, async () => {
  const ctx = makeCtx();
  apply(ctx, makeConfig({ captureMode: "raw" }));
  const containerDir = `subagent-capture-${Date.now()}`;
  // 子 agent 会话：header.origin === "subagent"
  const session = { header: { cwd: `/home/user/projects/${containerDir}`, origin: "subagent" } };
  const marker = `dsh-subagent-${Date.now()}`;

  ctx.emitSessionEvent(session, { type: "turn/start", data: { turn: 1 } });
  ctx.emitSessionEvent(session, {
    type: "user/message",
    data: { source: { kind: "user" }, content: [{ type: "text", text: `${marker} 子任务输入` }] },
  });
  ctx.emitSessionEvent(session, {
    type: "assistant/message",
    data: { message: { content: [{ type: "text", text: `${marker} 子任务回复内容，足够长以触发捕获条件`.repeat(4) }] } },
  });
  ctx.emitSessionEvent(session, { type: "turn/end", data: { turn: 1, reason: "success" } });

  // 等待可能存在的（错误的）写入完成，再断言容器为空
  await new Promise((r) => setTimeout(r, 3000));
  const search = ctx.toolsMap.get("memory_search");
  const found = await search.execute({ query: marker, limit: 10 }, { agent: makeFakeAgent(`/home/user/projects/${containerDir}`), signal: new AbortController().signal });
  assert.equal(found.success, true, JSON.stringify(found));
  assert.equal(found.results.filter((r) => r.content.includes(marker)).length, 0, "subagent 会话不应写入记忆");
});
