# 99 · 最终结论 + 实施映射（Claim 原子化调研定案）

> 归属: [README](README.md) 调研卡 · 日期: 2026-08-19
> 输入: round-01 五平台（[08-round-01-conclusions](08-round-01-conclusions.md)）+ round-02 五平台
> （[09-round-02-conclusions](09-round-02-conclusions.md)）+ 收敛轮回项目内核对（foundation /
> reconciliation-design / 当前实现 / schema）
> 性质: 本文是**调研最终结论**，作为 M2.1 的原子判据定案；实施细节进 [claim-atomicity.md](../../../initiatives/crystal/claim-atomicity.md)
> 与 [reconciliation-design.md v2](../../../initiatives/crystal/reconciliation-design.md)。

## 一、最终结论（五平台收敛 + 项目内核对通过）

### C1. 粒度判据（核心，全平台收敛）

> **一条 Claim 的粒度不由字数/句子数决定，由「独立生命周期」决定：**
> **两个部分未来是否可能被分别裁决（一个被纠正/失效/取代，另一个仍成立）→ 是则拆。**

落地为四条可操作测试（ChatGPT「四独立」+ Claude「独立可证伪性」+ Gemini「四判据」收敛）：

| # | 测试 | 问题 | 项目内示例 |
|---|------|------|-----------|
| 1 | **独立检索** | 未来只问其中一部分，系统是否希望只返回这一部分？ | "初期最多多少个源？" 只想要 20，不是 Miniflux+五类+四阶段 |
| 2 | **独立纠正** | 用户是否可能只纠正其中一部分，不牵连其他？ | ≤20 → ≤30，Miniflux/五类/四阶段不该被作废 |
| 3 | **独立失效** | A 过期时 B 是否必然同时过期？ | Miniflux 换 TinyRSS 时 20 源上限可不变 |
| 4 | **独立证据** | A 与 B 的支持证据是否可能不同？ | E1 说选型、E2 说上限 → 分别支持 C1/C2 |

**最强的拆分信号 = 独立纠正（测试 2）**——用户在工作台可能局部微调的部分必须独立成 Claim。

### C2. 整篇文档/长原文不是"粗 Claim"，是"分层错误"

- 2383 字架构文档照抄 = Evidence 被误标成 Claim，不是粒度问题；
- 规则：**原文属于 Evidence；Claim 只保存从证据提炼出的可独立维护的结论**（全平台一致）。

### C3. 拆条形态：平行原子 Claim + 轻量 event_key（项目内裁决）

- **一期不做 Group/Decision 实体**（Entity/主题 P2 不进核心的约束下，任何持久化分组都是半实体网络雏形）；
- Claim 加可选 **`event_key`** 弱组织字段：非实体、无 truth lifecycle、不可被用户裁决、
  只是"这些 Claim 从同一次 Evidence/决策表达中一起拆出来"的 grouping hint；
  **event_key 不参与真值**——C2 被 supersede 不连带 invalidate 同 key 的其他 Claim；
- 召回时碎片化靠**动态聚合**（runtime composition，按主题/时间/谱系邻近聚类）解决，不落库；
- 二期观察到真实 usage pattern（同一决策多个 Claim 频繁一起召回/展示/裁决）再演进成
  Decision/Group 实体，event_key 可平滑迁移。

### C4. 拆条质量策略：宁可多拆 + 拆条/碰撞分步 + 分布监控

- **宁可多拆不要漏拆**：错误可恢复性不对称——拆粗了想拆细会破坏旧粗结论的用户裁决历史
  （无法自动映射）；拆细了想合并只需加"合并/泛化"边在展示层组装，不破坏各细结论的 confirm 记录；
- **拆条与碰撞判定必须分步**（一步不可能做完：碰撞判定需要拿新结论与库内结论比较，
  库内结论不在拆条 LLM 调用上下文里）：拆条(LLM ①) → 检索候选(embedding，非 LLM) → 碰撞判断
  (LLM ②，N 条新结论批处理，输入=新结论+检索到的候选)；
  **拆条阶段输出不含冲突/支持字段**；
- **质量监控**：拆出条数分布 / 单条长度分布 / 单条引用 span 占原文比例，落尾部才定向抽检；
  反向合成校验（拼接后整体 vs 原文语义覆盖度）查漏拆，逐条比对查编造。

### C5. claim_kind 类型软规则（不用硬上限）

- 统一判据「可独立证伪」覆盖四类，**不做类型级硬粒度上限**（Grok 裁决）；
- 软规则（提取提示级）：fact/constraint 更积极拆；preference 折入 context 防过度泛化；
  **learned-pattern 允许稍长，保留"条件–做法–结果"最小完整结构**（Gemini/Grok 一致，防因果断链）；
- statement 长度参考（工程 heuristic，非硬限制）：**理想 15–80 字，可接受上限约 150 字**，
  极短 <10 字语义完整也接受；超限且仍可拆则优先拆（进监控参考线）。

### C6. 证据引用精度：拆条解决置信度污染，片段引用主要为 UX

- 置信度虚高的根源是 Claim 粗粒度；**拆条后数学污染已切断**（每个原子 Claim 只累加真正支持它的证据）；
- 片段级引用（evidence_quote）对 UX 增益极高（点开证据高亮一句 vs 丢整篇原文），对置信度增益极低；
- **MVP 实现：LLM 拆条时顺带输出 evidence_quote（原文精确子句），存 JSONB，
  服务端字符串匹配定位；不用字符级 offset 坐标**（清洗/tokenizer 差异必错位）；
- 中文证据分块（300-500 字、中文标点分隔符、Markdown 按标题分层）作为二期按需增强。

### C7. 提取成本：不做延迟提升，拆条立即做

- 个人自托管、每天几十条证据规模下**不值得做"候选延迟提升"**（Claude 修正 + doubao 一致）；
- 拆条（单证据内、便宜、高时效）**立即做**；对账/整合保持现有"写路径不等待 + worker 异步"形态；
- 监控端到端延迟与对账比较次数，量变（每天几百条或多用户）再评估；
- "批量整合/演化"是一期之后的价值引擎方向（与 milestone §5 推后一致）。

## 二、实施映射（进 M2.1 P3 实现）

| # | 决策 | 落点 | 变更 |
|---|------|------|------|
| M1 | 拆条：evidence → 0..N 条原子 claim（平行 + event_key） | reconcile_service | `_llm_claim_kind_and_statement` → 拆条调用（LLM ①），输出 claims[]；碰撞判定（LLM ②）批处理 N 条 |
| M2 | claim 加 `event_key` 字段 | schema.sql crystal 段 + init_crystal_db.py | `event_key TEXT NULL`（非实体，无 truth） |
| M3 | 拆条输出带 `evidence_quote` | claim_evidence | 加 `quoted_text TEXT NULL`（或 JSONB），服务端在证据原文字符串匹配定位 |
| M4 | 拆条 prompt 落地（15 条指令 + 反事实测试 + predicate 枚举） | reconcile_service prompt | ChatGPT 十六节指令裁剪落地（R3/R9） |
| M5 | 拆条/碰撞分步（当前已分步） | reconcile_service | 确认分步 + LLM ② 批处理 N 条新结论 |
| M6 | claim_kind 软规则（learned-pattern 保留因果） | 拆条 prompt | 类型感知提示 |
| M7 | 存量 19 条 active 宽 claim 全部清理重建 | migrate/脚本 | 备份 → 清理 → 从 evidence 重新拆条对账（等用户确认） |
| M8 | 质量监控指标 | 验收 | 拆出条数分布 / 单条长度分布 / Blast Radius / Evidence Contamination / Reconstruction Rate |
| M9 | statement 长度参考线 | claim-atomicity 规范 | 15–80 字理想 / 150 字上限（监控参考，非硬限制） |

## 三、与项目内已拍板的兼容性核对（收敛轮）

| 项目内拍板 | 调研结论 | 兼容性 |
|-----------|---------|--------|
| Evidence 不可再生、Claim 派生可重算 | C2：原文属 Evidence，Claim 只放提炼结论 | ✅ 一致，强化了分层边界 |
| Entity/主题 P2 不进核心 | C3：event_key 非实体、无 truth、非关系表 | ✅ 不违反（弱字段） |
| Claim 只存简单断言、适用条件折入句子 | C1/C6：qualifier 折入 statement | ✅ 一致（ChatGPT 折入规则即此） |
| claim_evidence 关系表 role 恒 support | C6：加 quoted_text 不破坏 role 语义 | ✅ 增量 |
| 对账单事务写 | C4：拆条 N 条 + 各自 claim_evidence + 边同事务 | ✅ 事务内批量写 |
| 碰撞判定 LLM 调用（temperature=0） | C4：拆条/碰撞分步 + 批处理 | ✅ 当前已分步，只改批处理 |
| 存量迁移已完成（27 evidence → 20 claim） | M7：存量重建 | ⚠️ 需用户确认（已拍板"全部清理重建"） |
| 个人自托管、单 worker、每天几十条 | C7：不做延迟提升 | ✅ 与规模匹配 |

## 四、调研纪律核验

- 判据 C1（独立生命周期）为**五平台收敛共识**，且与 foundation 已拍板（适用条件折入句子 /
  0..N 拆条 / Claim 可裁决）一致 → 可直接进 ADR；
- C3 event_key、C4 宁可多拆、C6 evidence_quote 为**平台推理 + 项目内裁决**（非文献定论），
  进 ADR 时标注"工程决策，上线后按监控指标验证"；
- 文献支撑点（Dense X Retrieval / FActScore / Zep-Graphiti / TriQua / A-MEM / LeanMem /
  Quadruple Shot / Auto-Dreamer 等）已登记 [08-round-01-conclusions §五](08-round-01-conclusions.md)，
  进设计文档时按需引用；
- **C 类结论（平台推理）需在 P3 实现后以真实数据验证**（Blast Radius / Contamination / Reconstruction
  Rate 三个指标），再确认粒度策略是否成立。

## 五、下一步（衔接 M2.1 P1–P3）

1. **P1 语义定稿**：foundation 回写（原子判据 + event_key + 宁可多拆 + evidence_quote 拍板项）+
   ADR-0020（claim 原子化判据与拆条策略）；
2. **P2 规范 + 设计**：claim-atomicity.md 判据定案回填 + reconciliation-design v2
   （拆条 LLM ① + 碰撞 LLM ② 批处理 + event_key/evidence_quote 落库 + 单事务批量写）；
3. **P3 实现**：拆条 + 存量清理重建（等用户确认）+ 测试（单元/集成/实跑/v5 回归）+ 验收指标。

*状态: 已收敛 · 日期: 2026-08-19*
