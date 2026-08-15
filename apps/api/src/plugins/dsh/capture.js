/**
 * memory-recall-dsh 自动捕获
 *
 * 监听 session/event（仅实时追加事件；会话恢复的种子重放不会再次触发），
 * 在 turn/end 时把该轮 user + assistant 文本组装成摘要：
 *   - captureMode "extract"（默认）：POST /extract-memory 用后端 LLM 蒸馏出值得保存的
 *     记忆再逐条落库（type=preference 自动归为永久特征）；蒸馏无价值或失败时回退 raw。
 *   - captureMode "raw"：直接把摘要存为 conversation 类型记忆（截断到 captureMaxChars）。
 * 全程 fire-and-forget + fail-open，绝不阻塞或打断 agent 主流程。
 *
 * 膨胀治理（2026-08-16）：
 *   - 批上限与 prompt 一致：蒸馏结果最多写 5 条（slice(0, 5)）。
 *   - 会话级节流：两次蒸馏间隔 < captureMinIntervalMs（默认 10 分钟）时，本轮摘要
 *     累计进 pendingSummary，窗口结束后与下轮摘要合并蒸馏 —— 信息不丢
 *     （对话原文本就完整保留在 session 事件流，这里只是暂缓入长期记忆库）。
 *   - 捕获落库带 metadata._capture=true 标记，后端按捕获来源走 0.85 相似去重。
 */
import { textFromContent, buildSessionSummary } from "./context.js";

export function createCaptureHandler({ client, config, resolveTags, logger }) {
  /** session -> { turn, userText, assistantText } */
  const sessions = new WeakMap();
  /** session -> 上次蒸馏时间戳（会话级节流） */
  const lastCaptureAt = new WeakMap();
  /** session -> 节流窗口内累计的摘要文本（超 captureMaxChars 截尾） */
  const pendingSummary = new WeakMap();

  /** 组装合并摘要（节流窗口累计 + 本轮），超长截尾并保留尾部（最新信息） */
  function mergeSummaries(pending, thisTurn, maxChars) {
    const merged = pending ? `${pending}\n\n${thisTurn}` : thisTurn;
    return merged.length > maxChars ? merged.slice(-maxChars) : merged;
  }

  const capture = async (summary, session) => {
    if (!summary || summary.trim().length < config.captureMinLength) return;
    // tag 必须从会话 cwd 推导（多项目并存时各归其位），不能退回进程 cwd
    const tags = await resolveTags({ session });
    if (!tags) return;

    if (config.captureMode === "extract") {
      try {
        // 传落库容器 tag 做去重检索，保证检索与落库同域（2026-08-16）
        const extracted = await client.extractMemory(summary, config.language === "en_US" ? "en_US" : "zh_CN", tags.project);
        if (extracted?.has_worthwhile && Array.isArray(extracted.memories) && extracted.memories.length > 0) {
          // 与蒸馏 prompt"最多 5 条"对齐：LLM 偶发超限时截断，防单轮超写（2026-08-16）
          for (const m of extracted.memories.slice(0, 5)) {
            const type = ["preference", "constraint", "learned-pattern"].includes(m.type) ? m.type : "learned-pattern";
            await client.addMemory(m.content, tags.project, {
              isStatic: type === "preference",
              type,
              asyncProcess: true, // 后台写入，捕获路径无需等待 embedding
              metadata: { _capture: true }, // 标记捕获来源：后端按 0.85 阈值去重
            });
          }
          logger?.info?.("[memory-recall-dsh] 蒸馏捕获 %d 条记忆", extracted.memories.length);
          return;
        }
        // 蒸馏判断"无值得保存的内容"：尊重判断，不落库（不再回退 raw 存全文，
        // 避免把临时对话灌进长期记忆）；仅接口报错才走下方 raw 回退保全信息
        logger?.debug?.("[memory-recall-dsh] 蒸馏判定无可保存记忆，跳过本轮捕获");
        return;
      } catch (error) {
        logger?.warn?.("[memory-recall-dsh] /extract-memory 失败，回退 raw 捕获: %s", error instanceof Error ? error.message : String(error));
      }
    }

    try {
      await client.addMemory(summary, tags.project, {
        type: "conversation",
        asyncProcess: true, // 后台写入
        metadata: { _capture: true },
      });
      logger?.info?.("[memory-recall-dsh] 已捕获会话摘要（%d 字符）", summary.length);
    } catch (error) {
      logger?.warn?.("[memory-recall-dsh] 捕获失败: %s", error instanceof Error ? error.message : String(error));
    }
  };

  return (session, event) => {
    if (!config.autoCapture || !client.isConfigured()) return;
    // 跳过子 agent 会话：subagent 是任务分解的临时执行者，其对话不应作为记忆入库
    if (session?.header?.origin === "subagent") return;
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

        const thisTurn = buildSessionSummary(state.userText, state.assistantText, config.captureMaxChars);
        if (!thisTurn || thisTurn.trim().length < config.captureMinLength) break;

        const now = Date.now();
        const interval = Number(config.captureMinIntervalMs) || 0;
        if (interval > 0 && now - (lastCaptureAt.get(session) || 0) < interval) {
          // 节流窗口内：累计摘要，窗口结束后与下轮合并蒸馏（信息不丢）
          const pending = pendingSummary.get(session) || "";
          pendingSummary.set(session, mergeSummaries(pending, thisTurn, config.captureMaxChars));
          break;
        }

        const pending = pendingSummary.get(session) || "";
        pendingSummary.delete(session);
        lastCaptureAt.set(session, now);
        void capture(mergeSummaries(pending, thisTurn, config.captureMaxChars), session);
        break;
      }
      default:
        break;
    }
  };
}
