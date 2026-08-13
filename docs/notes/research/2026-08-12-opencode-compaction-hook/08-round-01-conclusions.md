# Round 1 统一理解

> 类型: 调研（统一理解）
> 调研: 2026-08-12-opencode-compaction-hook
> 说明: 统一理解表 + 第一轮结论

## 统一理解（Agent 填写）

| 问题 | 各平台一致性 | 冲突 / 证据倾向 | 结论 | 是否已由源码验证 |
|------|-------------|----------------|------|------------------|
| Q1 | 触发时机（摘要 LLM 前）5/5；input 仅 `sessionID` 4/5；`context` 追加、`prompt` 完全替换且 prompt 优先 4/5；多插件串行共享 output、context 累积、prompt 后写覆盖 5/5；experimental 不稳定 5/5 | doubao：prompt 设置后 context 仍追加（与源码 `??` 短路矛盾）；Gemini：context 会作为变量传入自定义 prompt 渲染器（无此机制）；Claude：当前类型未定义该 hook（1.15.13/1.18.0 类型均存在；"未知 hook 名静默跳过"成立） | 核心契约确认，context-only 方案正确；doubao/Gemini 的该点不采信 | 是（compaction.ts L380-385、plugin/index.ts trigger、plugin d.ts） |
| Q2 | 触发时机（压缩成功后、插入 continue 前）与 `enabled=false` 语义 4/5；`session.compacted` 在其后只读通知 5/5；多插件后写覆盖 4/5 | input 字段：ChatGPT/Grok 与源码一致（`sessionID/agent/model/provider/message/overflow`，output 仅 `enabled`）；Gemini（`cause/summary/reason`）与 doubao（`sessionId/auto/summary/tokenStats/assistantEndedNaturally/hasPendingToolCalls`）为编造型错误；Claude 未找到源码（实际存在） | 采用 ChatGPT/Grok 版本；其余字段不采信 | 是（compaction.ts ~L494、plugin d.ts 1.15.13） |
| Q3 | Claude（R3-2）给出触发公式与默认值，与源码一致；补充社区调参与两个已知问题（#27706/#13980） | Claude 称 `MAX_PRESERVE_RECENT_TOKENS=15_000`、`tail_turns` 未设则不限轮次——与 v1.18.16 源码不符（源码为 8_000、默认 2），不采信 | 默认值以 v1.18.16 源码为准；社区调参经验进入 README 指引，不阻塞实现 | 是（公式与默认值）；Claude 两处数字不采信 |
| Q4 | — | 决策已定（ADR-0008），历史不影响当前版本 | 不跑 | 是（当前版本保留语义） |
| Q5 | — | 源码已回答：同一条管线、hook 必触发、summarize 无自定义 prompt | 不跑 | 是 |
| Q6 | — | 删除捕获/恢复后无需监听压缩完成 | 不跑（未来需要再调研） | 部分 |
| Q7 | — | 决策=不替换 prompt，原生锚定自动生效 | 不跑 | 是 |
| Q8 | ChatGPT/Grok/doubao 一致：生态多数插件只 push context（OMO 默认、goal、swarm、smart-compaction）；高风险是设置 `output.prompt` 的插件（hashpress-opencode、opencode-plugin-compaction-prompt、OMO customCompactionPrompt 开关）；最佳实践=只 push context、不注册 autocontinue、hook 开头检测 prompt 已存在则 warn+skip、fail-open | 项目清单细节各平台有出入（OMO 是否默认注册 autocontinue、是否可开 prompt 等），以实际安装版本为准 | context-only 策略正确；实施时加"prompt 已存在检测" + README 兼容性声明 | 否（生态信息，以源码规则为准） |

统一结论（哪些直接进入 ADR / 实施计划，哪些需要项目内验证）：

### 第一轮统一结论（2026-08-12）

1. **Q1/Q2 与 ADR-0007/0008 无冲突，且强化了现有决策**：只用 `output.context`、
   不替换 prompt、不依赖 `autocontinue` 做恢复，全部成立。
2. **平台准确度分层**：ChatGPT 与 Grok 的源码级结论最可靠（字段、时序、replay 分支都对）；
   Claude 诚实但漏检了 autocontinue；Gemini 与 doubao 在 input/output 字段上出现编造型错误。
   证明"外部回答是素材不是事实"，字段细节一律回源码确认。
3. **新风险确认（源码核实）**：`Plugin.trigger` 对每个 hook 的调用没有 try/catch，
   hook 抛错会使 trigger Effect 失败，可能中断本次压缩。→ 实施计划需补充：
   插件 hook 内整体 try/catch，失败只记日志，绝不影响压缩主流程。
4. **新边界确认**（ChatGPT/Grok 与源码一致）：compact LLM 无工具（`tools: {}`）、
   history 在 hook 前已 select，`output.context` 是插件干预压缩的唯一通道。
5. **Claude 的"类型未定义"只对旧版本可能成立**：@opencode-ai/plugin 1.15.13 已包含两个钩子类型；
   但"写错/未实现 hook 名会被静默跳过"成立，升级 opencode 后需验证 hook 实际被调用（打日志）。

