# ADR-0020: Claim 原子化——粒度判据与拆条策略

> 状态: Accepted
> 系统: crystal
> 日期: 2026-08-19
> 关联: [目标模型](../initiatives/crystal/foundation.md)（已拍板 #36–39）· [Claim 原子化外部调研](../notes/research/2026-08-19-claim-atomicity/README.md)（五平台收敛）· [文档类例外讨论](../notes/2026-08-19-document-claim-atomicity-discussion.md)（用户定案）· [M2.1 里程碑](../initiatives/crystal/milestone.md)

## 背景

现实库 22 条 claim 粒度失控：15 字（"张三喜欢喝咖啡"）到 2383 字（整篇架构文档照抄）。
foundation 已拍板「一次 Evidence 可衍生 0..N 个 Claim」，但实现对账只有 0..1——多条独立结论被塞进
一条 claim，导致：召回混合向量噪音、裁决只能整条 supersede 连带误杀正确子结论、不同主题证据
reinforce 进同一 claim 抬高置信度。

外部调研（round-01 五平台无预设 + round-02 五平台反馈式追问 + 收敛轮回项目内核对）收敛出粒度判据
与拆条策略；用户评审补充文档类例外与双上限设计。

## 决策

1. **粒度判据 = 独立生命周期，非字数**：两个部分未来可能被分别裁决（一个被纠正/失效/取代，
   另一个仍成立）→ 是则拆。落地四测试：独立检索 / 独立纠正（最强信号）/ 独立失效 / 独立证据。
2. **整篇文档原文照抄不是"粗 Claim"是"分层错误"**：原文属 Evidence，Claim 只放提炼出的
   可独立维护结论。
3. **拆条形态 = 平行原子 Claim + 轻量 `event_key`**：一条 Evidence → 0..N 条平行原子 Claim，
   每条带 `event_key`（非实体、无 truth lifecycle、不可被用户裁决、仅"同一次 Evidence 中一起拆出"
   的 grouping hint，不参与真值）；**不做 Group/Decision 实体**（Entity/主题 P2 不进核心的约束下，
   持久化分组 = 半实体网络雏形）；碎片化靠召回时动态聚合。
4. **宁可多拆不要漏拆**：错误可恢复性不对称——拆粗破坏用户裁决历史（旧粗结论的 confirm 无法自动
   映射到新细结论）、拆细可合并（加"泛化/合并"边在展示层组装，不破坏各细结论 confirm 记录）。
5. **拆条与碰撞判定分步**：LLM ① 拆条（输出 N 条原子断言，不含冲突/支持字段）→ 检索候选
   （embedding，非 LLM）→ LLM ② 碰撞判定批处理（N 条新结论 + 各自检索到的候选一次传入）。
6. **claim_kind 无类型级硬上限**，软规则：fact/constraint 积极拆、preference 折入 context、
   **learned-pattern 保留"条件–做法–结果"最小完整结构**（防因果断链）。
7. **证据引用带 `evidence_quote`**（原文精确子句）：拆条本身切断置信度污染（不同主题证据不再
   reinforce 进同一 claim）；quote 主要为溯源 UX（点开证据高亮），不用字符级 offset 坐标。
8. **文档类例外**：原子判据适用于对话类/长消息；有路径文档（P2 采集）走"概括 + 指针"
   （claim = 文档存在 + 路径 + 主题，细节按路径读原文）。
9. **双上限 + 默认隔离**：evidence 字数上限（1500 字）+ 拆出条目上限（15 条）；超上限默认不进系统
   计算（不自动拆条/对账）、evidence 原文保留在证据层、留存 workbench 人工裁决（不静默丢弃，
   MR-017 教训）。

## 理由

- 判据来自五平台收敛（ChatGPT"四独立" + Claude"独立可证伪性" + Gemini"四判据" + Grok/doubao
  "可独立证伪单元"），且与 foundation 已拍板（适用条件折入句子 / 0..N 拆条 / Claim 可裁决）兼容；
- event_key 满足"Entity/主题 P2 不进核心"约束（非实体、非关系表、无 truth），为二期 Decision/Group
  留演进钩子；
- "宁可多拆"的对称性论证（Claude）与"合并不破坏 confirm"的前提在实现合并语义时验证；
- 双上限 + 人工放行符合"个人记忆、用户信任优先"——自动拆条拆坏大文本的污染比不处理更糟；
- evidence_quote 用原文子句而非 offset，规避中文清洗/tokenizer 错位（Gemini/doubao 一致）。

## 后果

- 正面：原子 claim 可独立裁决（correct 不再连带误杀）、置信度不再被无关证据抬高、召回按主题精确命中、
  谱系边语义清晰；
- 负面/代价：claim 数量增长（存储/对账成本上升，个人规模可承受）；拆条质量依赖 LLM
  （分布监控 + 定向抽检兜底）；工作台出现"待裁决"视图承载超上限 evidence；
- 需跟进：event_key 二期演进为 Decision/Group 的时机（真实 usage pattern 触发）；
  合并（泛化）语义验证"不破坏 confirm 记录"；双上限阈值按 workbench 裁决数据调整。

*状态: Accepted · 日期: 2026-08-19*
