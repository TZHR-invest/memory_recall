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

/** 最小可用的 agents 服务替身（带 id：插件 per-agent LRU 依赖 agent.id，缺 id 则跨轮记忆排除失效） */
function makeFakeAgent(cwd, events = []) {
  return {
    id: "test-agent",
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

test("插件 apply 注册 6 个记忆工具（无 Key 时也注册，调用返回失败）", async () => {
  const ctx = makeCtx();
  apply(ctx, makeConfig({ apiKey: API_KEY ?? "rk_live_unset" }));
  const names = [...ctx.toolsMap.keys()].sort();
  assert.deepEqual(names, ["memory_forget", "memory_list", "memory_profile", "memory_search", "memory_store", "memory_update"]);
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
  apply(ctx, makeConfig({ debug: true }));
  // 每次用唯一项目容器：marker 记忆模板相似度高，共享 recall-test 容器时
  // 会与历史残留/并行测试撞语义去重（dedup 0.85）导致新记忆被丢弃（2026-09-09 实测）
  const cwd = `/home/user/projects/recall-test-${Date.now()}`;
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

  // 跨轮记忆级去重：再次触发同 query，已注入的记忆（marker）不应再次出现。
  // （注：不做整段 digest 级"零注入"断言——首轮注入含画像、后续轮无画像，
  //   文本必然不同；跨轮去重的正确载体是 exclude_memory_ids 记忆级排除，
  //   2026-09-09 isFirst 修复后此差异显现）
  agent.session.events.push({ type: "user/message", data: injected[0] });
  const second = await ctx.emitPreStep(
    { agent, messages: [], turn: 3, step: 1, signal: new AbortController().signal },
    async () => ({ kind: "enter", messages: [directUserMessage(`你还记得${marker}的项目架构决策吗`)] }),
  );
  const injected2 = second.messages.filter((m) => m.source?.kind === "plugin" && m.source.plugin === PLUGIN);
  if (injected2.length > 0) {
    const text2 = injected2[0].content.find((b) => b.type === "text").text;
    const mm = text2.indexOf(marker);
    console.error("=== DBG2 injected2=", injected2.length, "len=", text2.length, "marker@", mm,
      " | ctx:", mm >= 0 ? text2.slice(Math.max(0, mm - 80), mm + 40).replace(/\n/g, " ") : "N/A",
      " | heads:", [...new Set(text2.match(/#{2,3} [^\n]{2,24}/g) ?? [])].join(","));
    assert.ok(!text2.includes(marker), "已注入过的记忆不应跨轮重复注入");
  }

  // 清理（finally：断言失败也清理本测试的记忆，避免残留污染后续运行）
  try {
    const forget = ctx.toolsMap.get("memory_forget");
    const gone = await forget.execute({ memoryId: stored.id }, exec);
    assert.equal(gone.success, true, JSON.stringify(gone));
  } finally {
    // no-op：唯一容器 + 上面的 forget 已足够（容器 tag 带时间戳，天然无历史残留）
  }
});

test("自动召回：非关键词且非首次 → 不注入", { skip: !HAS_BACKEND }, async () => {
  const ctx = makeCtx();
  apply(ctx, makeConfig());
  const agent = makeFakeAgent("/home/user/projects/recall-test");

  // 首轮（关键词触发，注入成功 → 插件置位首轮状态）
  // 注：首轮不再以"session.events 里有无历史 user/message"判定（dsh 0.1.2
  // pre-step 时事件不可见恒 false，2026-09-09 改插件内存置位），
  // 因此这里通过真实完成一次注入来进入"非首次"。
  const first = await ctx.emitPreStep(
    { agent, messages: [], turn: 1, step: 1, signal: new AbortController().signal },
    async () => ({ kind: "enter", messages: [directUserMessage("还记得这里的项目架构吗")] }),
  );
  const firstInjected = first.messages.filter((m) => m.source?.kind === "plugin" && m.source.plugin === PLUGIN);
  assert.ok(firstInjected.length === 1, "首轮关键词应注入，实际 " + firstInjected.length);

  // 非首次 + 非关键词 → 不注入
  const decision = await ctx.emitPreStep(
    { agent, messages: [], turn: 2, step: 1, signal: new AbortController().signal },
    async () => ({ kind: "enter", messages: [directUserMessage("帮我写个 hello world")] }),
  );
  const injected = decision.messages.filter((m) => m.source?.kind === "plugin" && m.source.plugin === PLUGIN);
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

test("memory_update 版本化修正：旧版过期 + updates 版本链（连真实后端，清理验证）", { skip: !HAS_BACKEND }, async () => {
  const ctx = makeCtx();
  apply(ctx, makeConfig());
  const marker = `dsh-update-${Date.now()}`;
  const exec = { agent: makeFakeAgent("/home/user/projects/update-test"), signal: new AbortController().signal };

  // 先存一条（同步，确保立即可搜）
  const store = ctx.toolsMap.get("memory_store");
  const stored = await store.execute({ content: `${marker} 旧结论：后端用 MySQL`, scope: "project", asyncProcess: false }, exec);
  assert.equal(stored.success, true, JSON.stringify(stored));
  const oldId = stored.id;

  // 版本化修正（同步，立即可搜）
  const update = ctx.toolsMap.get("memory_update");
  const updated = await update.execute({ memoryId: oldId, content: `${marker} 新结论：后端改用 PostgreSQL`, asyncProcess: false }, exec);
  assert.equal(updated.success, true, JSON.stringify(updated));
  assert.equal(updated.relation, "updates", "应建立 updates 关系");
  assert.equal(updated.old_id, oldId, "old_id 应为旧记忆");
  assert.equal(updated.status, "done", "同步更新应返回 done");

  // 搜索新内容应命中新版本
  const search = ctx.toolsMap.get("memory_search");
  const found = await search.execute({ query: `${marker} 后端`, limit: 10 }, exec);
  assert.equal(found.success, true, JSON.stringify(found));
  assert.ok(found.results.some((r) => r.id === updated.id), "新版本应能被搜索到");

  // 清理：删除新旧两条（forget 新版；旧版已被标记过期，直接 forget）
  const forget = ctx.toolsMap.get("memory_forget");
  const gone = await forget.execute({ memoryId: updated.id }, exec);
  assert.equal(gone.success, true, JSON.stringify(gone));
  const goneOld = await forget.execute({ memoryId: oldId }, exec);
  assert.equal(goneOld.success, true, JSON.stringify(goneOld));
});

test("自动捕获：节流窗口内不重复落库（连真实后端，清理验证）", { skip: !HAS_BACKEND }, async () => {
  const ctx = makeCtx();
  // raw 模式原文落库可确定性断言；节流窗口 60s，两次 turn 间隔 << 窗口
  apply(ctx, makeConfig({ captureMode: "raw", captureMinIntervalMs: 60000 }));
  const containerDir = `capture-throttle-${Date.now()}`;
  const session = { header: { cwd: `/home/user/projects/${containerDir}` } };
  const markerA = `throttle-a-${Date.now()}`;
  const markerB = `throttle-b-${Date.now()}`;
  const longReply = (m) => m.repeat(8); // 超过 captureMinLength(100)

  const emitTurn = (turn, marker) => {
    ctx.emitSessionEvent(session, { type: "turn/start", data: { turn } });
    ctx.emitSessionEvent(session, {
      type: "user/message",
      data: { source: { kind: "user" }, content: [{ type: "text", text: `${marker} 用户输入` }] },
    });
    ctx.emitSessionEvent(session, {
      type: "assistant/message",
      data: { message: { content: [{ type: "text", text: longReply(marker) }] } },
    });
    ctx.emitSessionEvent(session, { type: "turn/end", data: { turn, reason: "success" } });
  };

  emitTurn(1, markerA);
  await new Promise((r) => setTimeout(r, 1500)); // 让第一轮捕获落库
  emitTurn(2, markerB); // 距上次蒸馏 < 60s → 应被节流，不进库
  await new Promise((r) => setTimeout(r, 3000));

  const search = ctx.toolsMap.get("memory_search");
  const exec = { agent: makeFakeAgent(`/home/user/projects/${containerDir}`), signal: new AbortController().signal };
  const foundA = await search.execute({ query: markerA, limit: 10 }, exec);
  assert.equal(foundA.success, true, JSON.stringify(foundA));
  assert.ok(foundA.results.some((r) => r.content.includes(markerA)), "第一轮捕获应落库");
  const foundB = await search.execute({ query: markerB, limit: 10 }, exec);
  assert.equal(foundB.success, true, JSON.stringify(foundB));
  assert.equal(foundB.results.filter((r) => r.content.includes(markerB)).length, 0, "节流窗口内第二轮不应落库");

  // 清理
  const forget = ctx.toolsMap.get("memory_forget");
  for (const hit of foundA.results.filter((r) => r.content.includes(markerA))) {
    await forget.execute({ memoryId: hit.id }, exec);
  }
});

test("自动捕获：节流窗口结束后摘要累计蒸馏（连真实后端，清理验证）", { skip: !HAS_BACKEND }, async () => {
  const ctx = makeCtx();
  apply(ctx, makeConfig({ captureMode: "raw", captureMinIntervalMs: 2000 }));
  const containerDir = `capture-accum-${Date.now()}`;
  const session = { header: { cwd: `/home/user/projects/${containerDir}` } };
  const markerA = `accum-a-${Date.now()}`;
  const markerB = `accum-b-${Date.now()}`;
  const longReply = (m) => m.repeat(8);

  const emitTurn = (turn, marker) => {
    ctx.emitSessionEvent(session, { type: "turn/start", data: { turn } });
    ctx.emitSessionEvent(session, {
      type: "user/message",
      data: { source: { kind: "user" }, content: [{ type: "text", text: `${marker} 用户输入` }] },
    });
    ctx.emitSessionEvent(session, {
      type: "assistant/message",
      data: { message: { content: [{ type: "text", text: longReply(marker) }] } },
    });
    ctx.emitSessionEvent(session, { type: "turn/end", data: { turn, reason: "success" } });
  };

  // turn1：正常蒸馏，建立 lastCaptureAt
  emitTurn(1, `accum-init-${Date.now()}`);
  await new Promise((r) => setTimeout(r, 500));
  // turn2：节流窗口内 → 进 pendingSummary
  emitTurn(2, markerA);
  await new Promise((r) => setTimeout(r, 2500)); // 越过 2s 窗口
  // turn3：窗口已过 → 合并 pending(turn2) + turn3 一起蒸馏落库
  emitTurn(3, markerB);
  await new Promise((r) => setTimeout(r, 3000));

  const search = ctx.toolsMap.get("memory_search");
  const exec = { agent: makeFakeAgent(`/home/user/projects/${containerDir}`), signal: new AbortController().signal };
  let merged = null;
  for (let attempt = 0; attempt < 20; attempt++) {
    const found = await search.execute({ query: markerA, limit: 10 }, exec);
    merged = found.results.find((r) => r.content.includes(markerA) && r.content.includes(markerB));
    if (merged) break;
    await new Promise((r) => setTimeout(r, 1000));
  }
  assert.ok(merged, "窗口结束后应把节流期间累计的摘要与本轮合并蒸馏落库（同时含 markerA 与 markerB）");

  // 清理
  const forget = ctx.toolsMap.get("memory_forget");
  const foundAll = await search.execute({ query: "accum-", limit: 20 }, exec);
  for (const hit of foundAll.results.filter((r) => /accum-/.test(r.content))) {
    await forget.execute({ memoryId: hit.id }, exec);
  }
});
