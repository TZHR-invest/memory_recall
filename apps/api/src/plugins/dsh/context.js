/**
 * memory-recall-dsh 上下文格式化与消息工具
 *
 * 注入消息复用 dsh 生态的 <system-reminder> 框定模式（与 dsh-agent-instructions 一致），
 * 让模型明确这是"可参考的召回上下文"；内容中的 </system-reminder> 会被转义，
 * 防止后端文本关闭插件自有的框。
 */
import { createHash } from "node:crypto";

/** 转义内容中的 </system-reminder>，防止仓库/记忆文本关闭插件框定 */
export function escapeReminder(text) {
  return String(text).replace(/<\/system-reminder>/g, "<\\/system-reminder>");
}

/** 注入引导语（中英双语，按检测到的 locale 选用） */
function guidanceLines(locale) {
  const zh = locale === "zh_CN";
  return zh
    ? [
        "以下是从长期记忆中召回的上下文，可能与当前任务相关。",
        "请优先参考已注入的记忆内容，无需重复探索代码库；",
        "若与你的既有信息冲突，以记忆中的最新版本（标注为更新/补充的条目）为准。",
      ]
    : [
        "The following context was recalled from long-term memory and may be relevant to the current task.",
        "Prefer this recalled context over re-exploring the codebase;",
        "when it conflicts with your existing information, trust the newest memory version (items marked as updated/extends).",
      ];
}

/**
 * 组装注入文本（system-reminder 框 + 引导语 + 后端 context）。
 * @param backendContext - /context-inject 返回的 context 字符串
 * @param locale - zh_CN | en_US
 */
export function buildInjectionText(backendContext, locale = "zh_CN") {
  const body = [
    "<system-reminder>",
    "The following recalled memories may be relevant to your work. Use them as guidance when applicable; more specific instructions take precedence.",
    "",
    ...guidanceLines(locale),
    "",
    escapeReminder(backendContext).trimEnd(),
    "</system-reminder>",
  ].join("\n");
  return body;
}

/** sha1 摘要（用于会话内去重） */
export function contextDigest(text) {
  return createHash("sha1").update(String(text)).digest("hex");
}

/** 从消息列表中取第一条直接用户输入（source.kind === "user"）的文本 */
export function firstUserText(messages) {
  if (!Array.isArray(messages)) return null;
  for (const message of messages) {
    if (!message || message.role !== "user") continue;
    if (message.source?.kind !== undefined && message.source.kind !== "user") continue;
    const text = textFromContent(message.content);
    if (text && text.trim().length > 0) return text.trim();
  }
  return null;
}

/** 提取 content blocks 中的文本（拼接） */
export function textFromContent(content) {
  if (!Array.isArray(content)) return "";
  return content
    .filter((block) => block && block.type === "text" && typeof block.text === "string")
    .map((block) => block.text)
    .join("\n");
}

/** 会话内去重：检查 agent 会话历史中是否已注入过同一摘要的召回消息 */
export function hasInjectedDigest(agent, digest) {
  // 2026-08-15 修复：dsh-session 的 Session 没有 events 成员（公开 API 是
  // deriveMessages()），此前读 agent.session.events 恒为 undefined，会话内
  // 去重静默失效——同一摘要的召回可跨轮重复注入。
  const messages = agent?.session?.deriveMessages?.();
  if (!Array.isArray(messages)) return false;
  for (const message of messages) {
    if (!message || message.role !== "user") continue;
    if (message.source?.kind !== "plugin" || message.source.plugin !== "memory-recall-dsh") continue;
    const text = textFromContent(message.content);
    if (text && contextDigest(text) === digest) return true;
  }
  return false;
}

/** 会话内是否已存在直接用户输入（用于判定"首次请求"；插件注入不算） */
export function hasDirectUserMessage(agent) {
  // 2026-08-15 修复：dsh-session 的 Session 没有 events 成员（公开 API 是
  // deriveMessages()），此前读 agent.session.events 恒为 undefined → 恒返回
  // false → isFirst 恒 true → smart/once 策略退化为每轮注入。
  const messages = agent?.session?.deriveMessages?.();
  if (!Array.isArray(messages)) return false;
  for (const message of messages) {
    if (!message || message.role !== "user") continue;
    if (message.source?.kind === "user") return true;
  }
  return false;
}

/** 组装捕获摘要（user + assistant，截断到 captureMaxChars） */
export function buildSessionSummary(userText, assistantText, maxChars) {
  const parts = [];
  if (userText && userText.trim()) {
    parts.push(`[user]\n${userText.trim()}`);
  }
  if (assistantText && assistantText.trim()) {
    parts.push(`[assistant]\n${assistantText.trim()}`);
  }
  const joined = parts.join("\n\n");
  if (joined.length <= maxChars) return joined;
  return `${joined.slice(0, maxChars)}\n\n[truncated]`;
}
