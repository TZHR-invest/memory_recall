# Claim 原子化规范与迭代计划（M2.1）

> 状态: 生效（v1 定案） · 系统: crystal · 版本: v1.1 · 最后更新: 2026-08-19
> 关联: [目标模型](foundation.md)（语义裁判，已拍板 #36–39）· [对账技术设计](reconciliation-design.md)（写路径实现）·
> [里程碑](milestone.md)（M2.1 行）· [外部调研](../../notes/research/2026-08-19-claim-atomicity/README.md)（原子判据）·
> [ADR-0020](../../decisions/0020-claim-atomicity.md)（决策）· [文档类例外讨论](../../notes/2026-08-19-document-claim-atomicity-discussion.md)（用户定案）·
> [crystal PRD](prd.md)（US-R*/A*）
> 定位: 本文是 crystal **M2.1 迭代的规范本体**——为什么原子化、原子判据（已定案）、
> 拆条流程、reinforce 边界、文档类例外、双上限、存量处理、验收标准。

## 0. 一句话

**对账写路径的语义补全：把「一条 evidence → 至多一条 claim」升级为「一条 evidence → 0..N 条原子 claim」，
并定义"原子"的判据、拆条流程与双上限；存量 19 条 active 宽 claim 全部清理重建（等用户确认）。**

## 1. 背景与动机（2026-08-19 数据核查）

现实库 22 条 claim（19 active + 3 superseded），粒度分布暴露三个问题：

| 观察 | 证据 | 后果 |
|------|------|------|
| **粒度无统一标准** | statement 长度跨 15 字（"张三喜欢喝咖啡"）~ 2383 字（整篇 LensDiary 架构文档原文） | 召回混合向量噪音大；无法按主题精确命中 |
| **一条 evidence 只产一条 claim** | foundation 已拍板「一次 Evidence 可衍生 0..N 个 Claim」（§对象模型），实现只有 0..1（`reconcile_service.py` 冲突路径新建一个取代 claim）；`ev_6c942673f7ab463ebe6107`（含 1)2)3)4) 四条决策）→ 1 条 430 字 claim | 多条独立结论被塞进一条，无法独立裁决/演变 |
| **reinforce 吸不同主题证据** | `cl_41962824d0a84524b8c64d`（statement 只覆盖 Core Architecture）挂了 5 条不同主题 evidence（架构/测试/依赖/API/结构）→ content_confidence 0.8533 虚高 | statement 未体现的内容抬高置信度；裁决精度受损（整条 supersede 连带误杀正确子结论） |

## 2. 为什么原子化（定位：语义补全，非新系统）

- foundation 已拍板「Claim 只存简单断言、适用条件折入句子」（#5/#10）与「0..N 拆条」——**原子化是补齐已拍板但未落地的语义**，不是新方向；
- 原子 claim 是**可裁决单元**：confirm/correct/forget 精确作用于单条结论，不连带误杀；
- 原子 claim 是**可信度单元**：reinforce 只认 statement 覆盖的证据，置信度不虚高；
- 原子 claim 是**演变单元**：supersedes/generalizes 边语义清晰，宽 claim 的 N:1 取代混乱消除。

## 3. 原子判据（已定案 2026-08-19，依据外部调研 99-final + ADR-0020）

> **粒度不由字数/句子数决定，由「独立生命周期」决定：**
> **两个部分未来可能被分别裁决（一个被纠正/失效/取代，另一个仍成立）→ 是则拆。**

落地四测试（对每个候选 claim 问）：

| # | 测试 | 问题 | 示例 |
|---|------|------|------|
| 1 | **独立检索** | 未来只问其中一部分，系统是否希望只返回这一部分？ | "初期最多几个源？" 只要 20，不是 Miniflux+五类+四阶段 |
| 2 | **独立纠正**（最强信号） | 用户是否可能只纠正其中一部分，不牵连其他？ | ≤20 → ≤30，Miniflux/五类/四阶段不该被作废 |
| 3 | **独立失效** | A 过期时 B 是否必然同时过期？ | Miniflux 换 TinyRSS 时 20 源上限可不变 |
| 4 | **独立证据** | A 与 B 的支持证据是否可能不同？ | E1 说选型、E2 说上限 → 分别支持 C1/C2 |

**整篇文档原文照抄不是"粗 Claim"是"分层错误"**：原文属 Evidence，Claim 只放提炼出的可独立维护结论。

**statement 长度参考**（工程 heuristic，非硬限制，进监控）：理想 15–80 字（中文），可接受上限约 150 字，极短 <10 字语义完整也接受；超限且仍可拆则优先拆。

## 3.1 拆条形态（已定案）

- 一条 Evidence → **0..N 条平行原子 Claim**，各自 `claim_kind` / `claim_evidence` / 单事务写；
- 每条带轻量 **`event_key`**（同一次 Evidence/决策表达中一起拆出的 grouping hint）：
  非实体、无 truth lifecycle、不可被用户裁决、**不参与真值**（成员被 supersede 不连带失效同 key 其他成员）；
- **不做 Group/Decision 实体**（Entity/主题 P2 不进核心）；碎片化靠召回时动态聚合；
- 二期观察到真实 usage pattern（同一决策多 claim 频繁一起召回/展示/裁决）再演进成
  Decision/Group，event_key 可平滑迁移。

## 3.2 拆条质量策略（已定案）

- **宁可多拆不要漏拆**（错误可恢复性不对称）：拆粗破坏用户裁决历史；拆细可合并
  （"泛化/合并"边展示层组装，不破坏各细结论 confirm 记录——合并语义实现时验证该前提）；
- **拆条与碰撞判定分步**：LLM ① 拆条（输出 N 条，不含冲突/支持字段）→ 检索候选（embedding，非 LLM）→
  LLM ② 碰撞判定批处理（N 条新结论 + 各自候选一次传入，输出按 claim_id 索引的判断数组）；
- **质量监控**：拆出条数分布 / 单条长度分布 / 单条引用 span 占原文比例，落尾部定向抽检。

## 3.3 claim_kind 软规则（已定案，无硬上限）

| claim_kind | 粒度倾向 | 说明 |
|-----------|---------|------|
| fact / constraint | 积极拆 | 客观事实/硬约束，边界清晰，独立纠正最常发生 |
| preference | 折入 context | 防过度泛化（"在 XX 场景下偏好 Y"，不提炼成全局结论） |
| learned-pattern | **保留"条件–做法–结果"最小完整结构** | 拆碎丢因果，工程价值流失 |

## 4. reinforce 边界（已定案）

- **拆条本身切断置信度污染**：不同主题证据不再 reinforce 进同一 claim（每个原子 claim 只累加
  真正支持它的证据）；这是解决"5 条不同主题证据抬高 0.8533"的根源手段；
- reinforce 只认「与 claim statement 同主题的新独立证据」；不同主题证据 → 建新 claim；
- 同源复述闸门沿用（v1 独立性闸门）；inference 提取证据权重恒 0（沿用）。

## 4.1 证据引用：evidence_quote（已定案）

- 拆条输出带 **`evidence_quote`**（LLM 从原文复制出的支撑子句，必须原文精确子串）：
  - 对置信度：增益极低（拆条已切断污染）；
  - 对 UX：增益极高（点开证据高亮一句话 vs 甩整篇原文）；
- **不用字符级 offset 坐标**（清洗/tokenizer 差异必错位）；存 JSONB，前端字符串匹配高亮。

## 4.2 文档类例外与双上限（2026-08-19 用户定案）

**文档类例外**：
- 原子判据适用于**对话类 / 长消息**；
- **有路径文档**（P2 采集时）走**"概括 + 指针"**：claim = 文档存在 + 路径 + 主题，
  细节按路径读原文（不复制内容、防过时）——**后置 P2 跟文档采集一起**；
- **无路径"文档样"长消息**（现实库那批 2383/1722/1657 字）**当长消息处理**：
  保留 evidence + 按对话类拆条（不舍弃、不概括）——见[讨论文档](../../notes/2026-08-19-document-claim-atomicity-discussion.md) §四论证。

**双上限 + 默认隔离（防过度拆分）**：

| 上限 | 阈值 | 作用 |
|------|------|------|
| evidence 字数上限 | 1500 字 | 挡住"整篇文档样"超大文本 |
| 拆出条目上限 | 15 条 | 挡住"为拆而拆"密度异常 |

**超上限处理（默认隔离，不丢弃）**：
1. 不自动拆条/不对账（`evidence_processing` 保持 pending）；
2. evidence 原文完整保留（Evidence 不可再生，不删）；
3. 留存 workbench「待裁决」视图，人工决定：手动拆分 / 概括 / 忽略 / 删除；
4. 人工放行后才进入系统。

阈值是工程初值，按 workbench 裁决数据积累调整。

## 5. 迭代阶段（对齐 milestone §3.5 文档门槛：缺文档不动代码）

| 阶段 | 产出 | 前置依赖 |
|------|------|---------|
| **P0 外部调研** | [调研卡](../../notes/research/2026-08-19-claim-atomicity/README.md)：round-01（无预设多平台）→ round-02（追问收敛）→ 收敛轮 → 99-final（判据 + 拆条模式 + 边界） | 用户手动执行各平台 ✅ 已完成 |
| **P1 语义定稿** | foundation 回写（#36–39）+ **ADR-0020** + STATUS ADR 跟踪表登记 | ✅ 已完成（2026-08-19） |
| **P2 规范 + 设计** | 本文档定案回填 + `reconciliation-design.md` 升 v2（拆条事务）+ entity-attributes 增量 + README 配套表 | 进行中 |
| **P3 实现 + 验证** | reconcile_service 拆条路径 + prompt 原子性约束 + 双上限隔离 + 存量清理重建（dry-run→用户确认→执行）+ 测试（单元/集成/实跑/v5 回归）+ 真实库 E2E + STATUS 收尾 | P2 + 用户确认存量清理 |

## 6. 存量处理（用户已拍板：全部清理重建，等确认后执行）

- 范围：crystal.claim 全部 22 条（19 active + 3 superseded）+ 关联 claim_evidence / lineage_edge / claim_activity；
- 方式：备份 → 清理 → 从 evidence 重新对账（新拆条逻辑）→ 验证粒度分布；
- 文档样长消息（无路径、超上限）默认隔离留存 workbench，不自动拆条；
- 等用户确认后执行（P3 阶段）。

## 7. 验收标准

- [ ] 对账：一条含多独立结论的 evidence → 产出 N 条原子 claim，各自 claim_kind / claim_evidence / 单事务写；
- [ ] 原子性：statement 长度/句数分布收敛（无 2383 字级宽 claim）；无"编号列表/多决策段落"形态；
- [ ] reinforce：不同主题证据不再 reinforce 进同一 claim（集成测试断言）；
- [ ] 裁决：correct 只取代目标原子 claim，不连带误杀（E2E 验证）；
- [ ] 双上限：超 1500 字 / 超 15 条 → 默认隔离进 workbench 待裁决（集成测试断言）；
- [ ] 存量：22 条宽 claim 清理重建完成，粒度分布达标；
- [ ] 质量指标（调研 R10）：**Correction Blast Radius**（一次纠正误伤多少本不该受影响的信息）、
  **Evidence Contamination**（支持证据中只支持 claim 一部分的比例）、**Reconstruction Rate**
  （靠 claim + event_key 能否恢复原决策整体）——三项进入洞察面统计；
- [ ] 测试：crystal 单元 + 集成全绿，v5 回归 402 过。

## 8. 明确不做 / 推后

- 不做 claim 的"手动拆分"UI 动作（P3 用脚本重建，UI 拆分留待后续按需）；
- 不做 statement 结构化（subject/predicate 落列）——适用条件折入句子的语义保持；
- 不做「拆条后重新 generalize」自动触发（观察期数据再说）；
- **不做文档概括提炼**（后置 P2 跟文档采集一起，走"概括 + 指针"）；
- **不做"批量整合/延迟提升"**（个人规模拆条立即做已足够；价值引擎后置，milestone §5）。

*状态: 生效（v1.1 定案） · 最后更新: 2026-08-19*
