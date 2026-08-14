/**
 * memory-recall-dsh 自动捕获
 *
 * 监听 session/event（仅实时追加事件；会话恢复的种子重放不会再次触发），
 * 在 turn/end 时把该轮 user + assistant 文本组装成摘要：
 *   - captureMode "extract"（默认）：POST /extract-memory 用后端 LLM 蒸馏出值得保存的
 *     记忆再逐条落库（type=preference 自动归为永久特征）；蒸馏无价值或失败时回退 raw。
 *   - captureMode "raw"：直接把摘要存为 conversation 类型记忆（截断到 captureMaxChars）。
 * 全程 fire-and-forget + fail-open，绝不阻塞或打断 agent 主流程。
 */
import { textFromContent, buildSessionSummary } from "./context.js";

export function createCaptureHandler({ client, config, resolveTags, logger }) {
  /** session -> { turn, userText, assistantText } */
  const sessions = new WeakMap();

  const capture = async (state, session) => {
    // tag 必须从会话 cwd 推导（多项目并存时各归其位），不能退回进程 cwd
    const tags = await resolveTags({ session });
    if (!tags) return;

    const summary = buildSessionSummary(state.userText, state.assistantText, config.captureMaxChars);
    if (!summary || summary.trim().length < config.captureMinLength) return;

    if (config.captureMode === "extract") {
      try {
        const extracted = await client.extractMemory(summary, config.language === "en_US" ? "en_US" : "zh_CN");
        if (extracted?.has_worthwhile && Array.isArray(extracted.memories) && extracted.memories.length > 0) {
          for (const m of extracted.memories.slice(0, 10)) {
            const type = ["preference", "constraint", "learned-pattern"].includes(m.type) ? m.type : "learned-pattern";
            await client.addMemory(m.content, tags.project, {
              isStatic: type === "preference",
              type,
            });
          }
          logger?.info?.("[memory-recall-dsh] 蒸馏捕获 %d 条记忆", extracted.memories.length);
          return;
        }
      } catch (error) {
        logger?.warn?.("[memory-recall-dsh] /extract-memory 失败，回退 raw 捕获: %s", error instanceof Error ? error.message : String(error));
      }
    }

    try {
      await client.addMemory(summary, tags.project, { type: "conversation" });
      logger?.info?.("[memory-recall-dsh] 已捕获会话摘要（%d 字符）", summary.length);
    } catch (error) {
      logger?.warn?.("[memory-recall-dsh] 捕获失败: %s", error instanceof Error ? error.message : String(error));
    }
  };

  return (session, event) => {
    if (!config.autoCapture || !client.isConfigured()) return;
    switch (event.type) {
      case "turn/start": {
        sessions.set(session, { turn: event.data.turn, userText: "", assistantText: "" });
        break;
      }
      case "user/message": {
        const state = sessions.get(session);
        if (!state) break;
        // 只收直接用户输入；插件注入（source.kind=plugin）与工具结果（kind=tool）不算
        if (event.data?.source?.kind !== "user") break;
        const text = textFromContent(event.data.content).trim();
        if (text) state.userText = state.userText ? `${state.userText}\n${text}` : text;
        break;
      }
      case "assistant/message": {
        const state = sessions.get(session);
        if (!state) break;
        const text = textFromContent(event.data?.message?.content).trim();
        if (text) state.assistantText = state.assistantText ? `${state.assistantText}\n${text}` : text;
        break;
      }
      case "turn/end": {
        const state = sessions.get(session);
        sessions.delete(session);
        if (!state) break;
        if (state.assistantText.trim().length < config.captureMinLength) break;
        void capture(state, session);
        break;
      }
      default:
        break;
    }
  };
}
