# 发现：思考型 LLM（deepseek）max_tokens 不足导致 content 为空

> 类型: 工程发现 · 日期: 2026-08-19 · 系统: crystal（M2.1 拆条开发）
> 关联: [reconcile_service.py](../../../apps/api/src/api/crystal/reconcile_service.py)（拆条 LLM ① / 碰撞 LLM ②）

## 现象

M2.1 拆条落地后，真实库采样发现：**deepseek-v4-flash 对拆条 prompt 间歇性返回空字符串**，
`aextract_json` 解析空 → 拆条失败 → 短文本降级原文、长文本隔离。单独调用偶尔成功、
连续调用基本失败，排查一度误判为"模型不稳定 / 服务端限流"。

## 根因（数据定位）

直接调原始 API 打印完整响应（不经过 client 的 `message.content` 取值）：

```
content: ''                          ← 实际答案为空
reasoning_content: '我们只需要输出JSON。需要拆分原子主张。分析原文。...'  ← 思考链一大坨
usage: completion_tokens=3998, reasoning_tokens=3998   ← token 全耗在思考上
```

**机制**：deepseek-v4-flash 是**思考型（reasoning）模型**，复杂任务会先输出长思考链到
`reasoning_content`。当 `max_tokens` 预算较小（如 4000）时，**思考链吃光预算，
`content` 一个 token 都没生成** → 返回空字符串 → 解析失败。

- 简单内容（"张三喜欢喝咖啡"）成功：思考短，content 有空间；
- 复杂内容（列表/多决策/Markdown 文档）失败：思考长，token 被 thinking 吃光；
- 间歇性：模型思考长度随机波动（同一 prompt 时好时坏）；
- doubao（非推理模式或思考短）稳定成功 → 曾误判为"deepseek 不稳定、doubao 稳定"。

## 修复

**LLM 调用 max_tokens 从 1500/3000/4000/500 统一提到 16000**（reconcile_service.py 4 处）。
验证：`max_tokens=4000` → content 空；`max_tokens=16000` → content 621 字正常 JSON
（实际 completion_tokens 只用了 1003，16000 只是给思考链留足空间，不浪费）。

## 影响面

- **已修**：crystal 对账全链路（拆条 ① + 碰撞 ② + 提炼）4 处；
- **未修（后续）**：v5 的 `memories.py` / `services/core/document_processor.py` /
  `services/core/llm_entity_extraction.py` 里的 `aextract_json` 若 max_tokens 也小，
  切到 deepseek 时同样会踩（v5 将退役，M5 时处理或退役即无关）。

## 经验

1. **思考型模型的"返回空"先查 reasoning_content + usage.reasoning_tokens**，
   别急着归因"模型不稳定/限流"；
2. max_tokens 对思考型模型要按"思考链 + 答案"双份预算，简单任务 4000 不够就试 8000/16000；
3. 排查外部 LLM 行为差异时，直接打原始响应（`achat_with_system` + 完整 message dump）
   比黑盒猜快得多。

*状态: 已定位并修复 · 日期: 2026-08-19*
