# 09 · round-02 统一理解

> 归属: [README](README.md) · 日期: 2026-08-16
> 输入: ChatGPT / Claude / Grok / doubao 四平台 round-02 回答（`05-round-02-answers-*.md`）
> 本轮性质: 针对 round-01 三个冲突/薄弱点的反馈式追问（各自原会话内，互不点名）

## 一句话

**round-01 的三个冲突点全部收敛：① truth discovery 在单用户单来源场景明确不做（退化边界清晰）；② freshness/R 与 V 分离被独立确认但可工程化兼容我们的拍板；③ 低置信记忆"双池 + 假说标签 + 隐性确认"给出落地形态，且"不静默丢弃"与"不默认注入"被成功解耦。**

## 冲突 #1 收敛：truth discovery 单用户适用性（ChatGPT + Claude）

**两家在"经典 truth discovery 不做"上完全收敛**，且 ChatGPT 主动修正了 round-01 自己的说法：
"在单一用户 + 单会话 + 一次性陈述为主的系统里，truth discovery 不是主模型；它只能在更高层跨大量 memory 的聚合统计上学习一部分。"

### 退化边界的统一画法（两家一致）

| 层级 | 条件 | 能学什么 | 做法 |
|------|------|---------|------|
| Level 0 | 单条 memory，无 corroboration | 不能学习（单条 claim 的 truth 与 source reliability **信息论上不可区分**） | 只能用 prior |
| Level 1 | 大量 memory + 部分 outcome | `P(correct \| source_type)`（跨 claim 学出，非单条学出） | 历史统计 |
| Level 2 | 大量 memory + source × claim_type | `P(correct \| source, claim_type)`——**对 Agent memory 最有意义的一层**（"这个产生机制对这类 claim 多可靠"，而非"用户是不是可靠的人"） | 分组统计 → 校准 |
| Level 3 | 同一 claim 多个独立 observation | 传统 truth discovery（投票估计 claim + source） | **我们场景基本用不上** |

### 直接退化的部分（Claude 明确列出，ChatGPT 同向）

- 迭代式联合估计（EM/优化）：退化图上无信息可迭代，不值得工程复杂度；
- 回声室/依赖来源检测：单来源场景问题不存在；
- 长尾稀疏来源建模：我们来源类型只有两三种，无此问题。

### 可保留的思想（两家各自提出，互不冲突）

- **ChatGPT**：V1 = 规则先验（source_prior + claim_type_prior + extraction_quality + evidence_quality）；V2 = outcome calibration（**Hierarchical Bayesian / Beta-Binomial 优先**，稀疏组合向总体收缩，避免"3 条全对→100%"）；V3 才在真有 corroboration 时启用 claim-level truth discovery。"为 95% 单 observation 的事实引入完整 truth-discovery machinery 是过度设计。"
- **Claude**：把"来源"拆成**陈述来源 ∥ 提炼过程**两个独立维度（有知识融合文献支撑）——单来源场景下一致性能测的是"LLM 提炼引入多少误差"，不是"用户说的客观上是不是真的"；增量式/时序 truth discovery 为"跨会话复现"提供理论框架（每次提及 = 弱观测，**增量更新而非简单计数**）。

## 新增关键发现：证据独立性（ChatGPT，本轮最有价值输出）

这是 round-01 冲突 #3 的深化，且**直接挑战我们"跨 session 稳定复现"的简单用法**：

- **不要把"来源不同"当"独立"**：tool 读 package.json 和 agent 说"根据 package.json 判断"是**同一个证据**（同一 lineage）。
- 核心规则：**只有产生"不可由已有 evidence 机械复制得到的原始观察"才增加独立证据**。
  用户重新说一次 = +1；agent summary / memory retrieval / agent 推理 = 不增加；package.json / CI = 独立观察各 +1。
- **独立 = Distinct Evidence Lineage，不是 Distinct Channel**。
- V1 廉价实现：给每个 evidence 加 `root_observation_id`（根观察 ID），派生物继承之。
  这是"最值得现在就加的字段"——没有它无法区分"10 个真观察" vs "1 个观察被 Agent 传播了 10 次"。
- 可做成三级 independence（0 derivative / 0.3 weak / 0.7 / 1.0 strong），不一定要 bool。
- **最该防范的 failure mode（epistemic feedback loop）**：一次用户陈述 → memory → agent 使用 → agent 总结 → memory 强化 → confidence↑ → 更频繁召回 → 再强化。**系统最终不是"越来越可信"，而是"越来越相信自己过去说过的话"。**
- 可监控指标：Evidence Independence Ratio (EIR) = N_independent / N_observed，长期接近 0.2 说明内部生成在污染证据计数。

## 冲突 #2 收敛：freshness 独立维度（Grok）

- **双标量模型**：R = Source/Extraction Reliability（写入时定、缓慢修正）+ V = Current Validity（随证据/时间动态更新）。
- **V 的驱动信号按优先级**：① 显式 supersession/矛盾（最高，冲突即 V→0.05–0.15，保留历史）；② 访问强化（V←V+α(1−V)，α≈0.08–0.12）；③ 时间衰减（usage-reinforced 指数衰减，half-life 按类型：偏好/决策 60–180 天、踩坑 30–90 天、临时 7–21 天）；④ 被动观察（文件/配置变更 → 下调并标记待复查）。
- **召回合成**：`sim × R^β × V^γ`（β≈0.6–0.8, γ≈0.7–1.0），乘法保证"高可靠但已失效"或"仍有效但来源极差"不挤进 top-k；V<0.15 默认不注入除非显式查历史。
- **自报信心冷启动建议完全忽略**；若保留：同来源桶内独立排序、幅度 ≤±0.03、用 `extraction_type ∈ {verbatim, paraphrase, inference}` 门控（inference 直接置 0），防止复述虚高进入置信。
- 声明：bi-temporal 与 Ebbinghaus 衰减是广泛实践；具体数值/公式为工程推理，建议上线后 A/B 调参。

**与我们拍板的兼容性分析（收敛轮判断）**：Grok 的 V 维度概念上独立，但**驱动信号全是我们已有/已规划的**——
supersession（已定谱系边）、访问/复用强化（已定 claim_usage）、时间衰减（B1 已定"召回时现算、不落 DB"）。
**不需要新增 valid_from/valid_to 字段**（时间失效继续由谱系边承载；V 的时效分量在召回精排时按类型 + 时间现算）；
工程上把 V 吸收进"召回精排的 freshness/validity 因子"即可，与 B1 完全自洽。**采纳其概念分离，不采纳其字段落库。**

## 冲突 #3 收敛：低置信不静默丢弃 + 草稿确认时机（doubao）

- **关键解耦**：`"低置信不静默丢弃" = 用户有权审计/看见/修正`；`≠ 任何记忆都有权静默参与模型推理`。两个目标可以分开满足。
- **推荐双池模型（主召回池 ∥ 假说/草稿池）**：inferred/低置信记忆默认不参与自动召回注入，但永久存储、可检索、可审计、可确认升级；风险根源不是"存在库中"而是"不经感知混入 prompt 影响推理输出"。
- 单池 + 大 topK 的坑：TopK 开大→上下文膨胀；收小→"名义存在、实际捞不出"= **事实上的静默丢弃**，违背原则。
- 折中形态：假说可在极强相关时带【假说记忆｜待用户验证】标签后置注入 + LLM 强指令"仅参考、不作确定性前提"。**这与我们 v1"低置信只降权不静默丢弃 + 洞察面可查"同向，且给了具体工程形态。**
- **确认时机（绝不打断核心流）**：触发 = 假说被召回命中 + 用户处于轻负载间隙（非写码/调试/排错）+ 冷却节流（单会话 ≤1 次、单记忆 N 天一次）。**优先隐性确认**（多次命中 + 用户沿用不反驳 → 缓慢上调），显性提问做兜底；次选纯面板集中审核（零干扰）；严禁在攻坚编码时插问。
- 草稿生命周期：写入假说池（draft:true + 24h 冷却）→ 命中时隐性累计 → 满足条件轻量询问 → 是=晋升 / 否=失效+修正记忆 / 稍后=延长冷却 → 达上限永久留假说池仅面板可查。

**与我们的兼容性判断**：我们 v1 是全量 claim 存 claim 表（无物理双池），工程上用 `status/confidence 分档 + 召回预过滤 + 洞察面可按"含假说"检索` 即可模拟双池，无需两套索引；doubao 的交互节奏（轻行内提示、非模态、冷却节流、隐性优先）可直接进 MR-011 洞察/裁决面的交互设计。

## 本轮新确认的三条"直接可采纳"结论（无需再追问）

1. **自报信心在冷启动阶段完全忽略**（Grok 强结论 + doubao"垃圾过滤器" + ChatGPT 修正后弱化）——但仍保留为 V2 校准的潜在 feature（各家一致）。
2. **中性先验 + Beta-Binomial 分层收缩**是 V2 校准的推荐形态（ChatGPT 首选 + Claude 同向）。
3. **source × claim_type 分层统计**是"来源可靠性"最终的落地形态（两家一致），比单一 source reliability 更有意义。

*状态: 完成 · 日期: 2026-08-16*