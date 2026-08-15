/**
 * memory-recall-dsh context.js 单元测试
 * 覆盖 2026-08-15 修复：hasDirectUserMessage / hasInjectedDigest 改用
 * session.deriveMessages()（dsh-session 的 Session 无 events 成员，旧实现
 * 恒返回 undefined → smart/once 策略退化为每轮注入 + 会话内去重失效）。
 */
import { test } from "node:test";
import assert from "node:assert/strict";
import { hasDirectUserMessage, hasInjectedDigest, contextDigest } from "../context.js";

function fakeAgent(messages) {
  return {
    session: {
      deriveMessages: () => messages,
    },
  };
}

const userMsg = (text) => ({
  role: "user",
  source: { kind: "user" },
  content: [{ type: "text", text }],
});
const pluginMsg = (text) => ({
  role: "user",
  source: { kind: "plugin", plugin: "memory-recall-dsh" },
  content: [{ type: "text", text }],
});
const modelMsg = () => ({
  role: "assistant",
  source: { kind: "model" },
  content: [{ type: "text", text: "reply" }],
});

test("hasDirectUserMessage: 有直接用户输入返回 true", () => {
  const agent = fakeAgent([modelMsg(), userMsg("你好")]);
  assert.equal(hasDirectUserMessage(agent), true);
});

test("hasDirectUserMessage: 仅插件注入不算直接输入", () => {
  const agent = fakeAgent([modelMsg(), pluginMsg("召回上下文")]);
  assert.equal(hasDirectUserMessage(agent), false);
});

test("hasDirectUserMessage: 空会话返回 false", () => {
  assert.equal(hasDirectUserMessage(fakeAgent([])), false);
  // 旧实现读 session.events（不存在）恒返回 false——新实现必须区分"无消息"与"有用户消息"
  const noEventsAgent = { session: {} };
  assert.equal(hasDirectUserMessage(noEventsAgent), false);
});

test("hasInjectedDigest: 命中同 digest 的插件注入返回 true", () => {
  const text = "召回上下文内容";
  const digest = contextDigest(text);
  const agent = fakeAgent([userMsg("问题"), pluginMsg(text)]);
  assert.equal(hasInjectedDigest(agent, digest), true);
});

test("hasInjectedDigest: 不同 digest / 无插件消息返回 false", () => {
  const agent = fakeAgent([userMsg("问题"), pluginMsg("其他内容")]);
  assert.equal(hasInjectedDigest(agent, contextDigest("不存在的摘要")), false);
  assert.equal(hasInjectedDigest(fakeAgent([userMsg("问题")]), contextDigest("x")), false);
  assert.equal(hasInjectedDigest({ session: {} }, contextDigest("x")), false);
});

test("hasInjectedDigest: 真实 dsh-session Session 形态（无 events、有 deriveMessages）", () => {
  const realLike = {
    session: {
      // 故意不带 events 成员（真实 Session 类没有它）
      deriveMessages: () => [userMsg("你好"), pluginMsg("注入A")],
    },
  };
  assert.equal(hasDirectUserMessage(realLike), true);
  assert.equal(hasInjectedDigest(realLike, contextDigest("注入A")), true);
});
