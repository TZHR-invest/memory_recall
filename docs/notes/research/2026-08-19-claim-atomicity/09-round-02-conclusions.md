# 09 · round-02 统一理解（冲突收敛 + 落地需求）

> 归属: [README](README.md) 调研卡 · 日期: 2026-08-19
> 输入: 五平台 round-02 回答原文（[chatgpt](05-round-02-answers-chatgpt.md) / [claude](05-round-02-answers-claude.md) / [grok](05-round-02-answers-grok.md) / [gemini](05-round-02-answers-gemini.md) / [doubao](05-round-02-answers-doubao.md)）
> 性质: 统一理解是**素材整理**，不是结论；标注事实来源（文献/实践/平台推理），未回项目内验证的不作为实施依据。

## 一、D1 组织层形态 —— 收敛：一期不做 Group 实体，加轻量 event_key 字段

**分歧消失，三方收敛到一个折中方案：**

- **ChatGPT**（原主张 Group/Decision 实体层，round-02 修正）：一期**不做 Group/Decision 实体**，
  加 Claim 上的可选 `event_key` 弱组织字段（非实体、无 truth lifecycle、不可被用户裁决、不参与召回主对象、
  只是"这几个 Claim 从同一次 Evidence/决策表达中一起拆出来"的 extraction grouping hint）；
  **明确边界：event_key 不是 Entity/Topic，不参与真值**（C2 被 supersede 不得连带 invalidate e1 的其他成员）；
  二期观察到真实 usage pattern（同一决策的多个 Claim 频繁一起召回/展示/裁决）再演进成真正的 Decision/Group；
  **给三个可进验收的指标**：Correction Blast Radius / Evidence Contamination / Reconstruction Rate。
- **Grok**（裁决）：选 B——一期不加任何持久化分组，靠谱系边 + scope + 召回时动态聚合（runtime composition）；
  个人自托管几百条结论规模下足够；"受控复合层"（不参与谱系演化、纠正落原子层）**基本等价于 B**；
  若动态聚合频繁失败，再加极轻量只读 `topic_hint` 字符串字段（非外键非关系表）。
- **Claude**（round-02 修正）：用 TriQua 思路——**不拆成互相无引用的 N 条平行结论**，而是
  "简单陈述 → 单 claim；复合决策 → 主 claim + 若干可独立修改的限定符/子属性"的结构化形式；
  分组关系建在数据结构里而不是靠额外谱系边。**注意：这其实挑战了"全拆成平行原子结论"的形态**，
  与 ChatGPT/Grok 的"平行原子 + event_key/动态聚合"有张力（见 D3 的取舍）。

**收敛判向**：ChatGPT（event_key 弱字段）+ Grok（动态聚合）实质兼容——event_key 是"轻量粘合"，
动态聚合是"召回时组装"。Claude 的"主 claim + 子属性"是另一种形态，需要与"平行原子结论"做取舍。
**项目内约束核对**：Entity/主题 P2 不进核心 → event_key 字段或 topic_hint 都不违反（非实体、非关系表）；
Claude 的"主 claim + 子属性"若实现为字段数组/嵌套结构，也不新增实体表，但改变 claim 表形态，成本更高。

## 二、D2 证据引用精度 —— 收敛：拆条本身解决置信度污染；片段级引用主要为 UX，MVP 用"原文子句引用"

- **Gemini**（结构化分析）：置信度增益**极低**——置信度虚高根源是 Claim 粗粒度，拆条后数学污染已切断
  （Claim A 只累加真正支持它的证据）；UX 增益**极高**（点开证据高亮一句话 vs 丢 2383 字原文）。
  **最小代价实现：LLM 拆条时顺带输出"原文子句引用"（evidence_quote，必须是原文精确子串），
  存 JSONB；前端字符串匹配高亮。绝对不要用字符级 offset/span 坐标**（清洗/tokenizer 差异必错位）。
- **doubao**（工程落地）：中文 span 定位坑清单（无空格分词、默认分隔符英文、列表/标题割裂、零宽字符、
  BERT tokenizer 空格痕迹）；**MVP = 分块 + 子句引用 + 字符串匹配三层方案**——证据先按中文语义分块
  （300-500 字、中文标点优先级分隔符、Markdown 先按标题分层），逐块拆条，LLM 输出 `evidence_quotes`
  原文子句（不是数字偏移），系统在 chunk 内字符串匹配定位 span，匹配失败逐级降级
  （exact → fuzzy → chunk → failed）；**可信度计算应基于 span 级引用实际内容，不是 evidence_id 计数**。
  国内产品溯源精度现状：公开最高为段落/chunk 级，很少见子句级成熟产品（做到 span 级有差异化但坑要自己踩）。
  "引用整条证据但只被一句支撑"是 RAG 已知问题，叫 **over-evidencing / 支撑范围膨胀**。
- **项目内约束核对**：一期 claim_evidence 只有 claim_id↔evidence_id；若采用 Gemini MVP（evidence_quote JSONB）
  或 doubao 三层方案（evidence_chunk 表 + claim_evidence 升级），后者要加表，前者只加 JSONB 字段。
  **两者都指向：拆条输出带 evidence_quote，服务端在原文中定位。**

## 三、D3 拆条质量保障 —— 收敛：宁可多拆（错误可恢复性不对称）+ 拆条/碰撞判定必须分步 + 分布监控定向抽检

- **Claude**（核心贡献）：
  - **宁可多拆不要漏拆**，理由是**错误可恢复性的不对称**（这是关键洞察）：拆粗了想拆细 → 旧粗结论的
    用户裁决历史没法自动映射到新细结论（要么作废重来、要么手工建映射）= 真实成本；拆细了想合并 →
    加"合并/泛化"边即可在展示层组装，不需要动底层证据引用、不需要用户重新确认（各细结论确认记录仍有效）。
    **前提：合并操作必须不影响已有 confirm 记录**（设计合并语义时要验证）。
  - **拆条与碰撞判定必须分步**（一步不可能做完）：碰撞判定需要拿新结论去和**已在库里**的结论比较，
    而库内结论不在 LLM 拆条调用时的上下文里 → 拆条(LLM ①) → 检索候选(embedding，非 LLM) →
    碰撞判断(LLM ②，输入=新结论+检索到的候选)。**拆条阶段输出不要包含冲突/支持字段**
    （LLM 没看到存量结论，让它猜冲突是回答没依据的问题，两任务互相拉低质量）。
    **省成本做法：LLM ② 批处理**——一次调用把 N 条新结论连同各自检索到的候选一起传入，输出按 claim_id 索引的数组。
  - **质量校验**：分布监控 + 定向抽检（拆出条数分布/单条长度分布/单条引用 span 占原文比例，
    落在尾部才路由人工复核）；反向合成/往返校验（文献有对应：Quadruple Shot / Knowledge Restoration，
    但**擅长抓精度错误、不擅长抓召回错误**——查漏拆要把 N 条结论拼接后整体与原文做语义覆盖度比较）；
    结构分流（TriQua：先轻量分类"简单陈述 vs 复合决策"，用不同输出 schema）。
- **Gemini**（呼应 Claude 的 TriQua 引用）：learned-pattern 类"复合/因果链"**天然抵抗极度原子化**，
  拆碎导致多层因果推理断链（见 D4）。
- **项目内约束核对**：当前实现是"LLM 一次调用做 claim_kind + statement 提炼"，碰撞判定是另一次调用
  （reconcile_service：`_llm_claim_kind_and_statement` 一次 + `_llm_judge_relations` 一次）——
  **已是分步结构，符合 Claude 的"必须分步"**；M2.1 要做的是把"提炼 1 条"改成"拆条 N 条"，
  碰撞判定输入变为 N 条新结论（批处理形态）。

## 四、D4 claim_kind 类型差异化 —— 分歧：Grok 说不需要硬差异化，Gemini/doubao 说需要类型感知

- **Grok**（裁决：不必要做类型级硬差异化）：四类本质差异在"语义性质与裁决权重"而非"可拆分性"；
  "可独立证伪"判据已足够通用；强行按类型设上限增加提取复杂度、边界案例人为不一致；
  Gemini 的权重/层级字段更适合做召回排序/裁决优先级信号而非粒度控制；
  **统一粒度策略**：默认拆到最小可独立证伪命题；不允许持久化复合结论参与谱系演化；
  **statement 长度参考（经验区间非硬限制）：理想 15–80 字（中文），可接受上限约 150 字，
  极短 <10 字语义完整也接受**；类型软差异仅作提取提示（fact/constraint 更积极拆、preference 少拆、
  learned-pattern 允许稍长保留"条件–做法–结果"最小完整结构）。
- **Gemini**（结构化映射表，类型感知）：fact=极度原子（scope+time 锚定）；constraint=高度原子
  （condition+boundary）；preference=带条件的原子（context 限定，防过度泛化）；
  **learned-pattern=复合/因果链（cause+action+effect），天然抵抗极度原子化，拆碎最致命**
  （把踩坑经验拆成两条独立事实就丢了"因为...所以..."的工程价值）。
- **doubao**（round-01 已提，round-02 未再展开）：按类型差异化粒度上限（事实/约束原子化、
  架构/方案结构化子项）。
- **收敛判向**：Grok 与 Gemini 表面冲突，实质**可兼容**——都承认 learned-pattern 保留
  "条件–做法–结果"最小完整结构（Grok 的"软差异"与 Gemini 的"复合/因果链"一致）；
  分歧只在"是否需要类型级硬规则"（Grok 反对硬上限，Gemini 给类型映射表）。
  **项目内核对**：4 值 claim_kind 中 learned-pattern 确实常含"条件-做法-结果"，机械原子化会丢因果
  → 需要"learned-pattern 允许稍长、保留最小完整结构"这条软规则（Grok/Gemini 一致）；
  fact/constraint 走严格原子；preference 防过度泛化需折入 context。

## 五、D5 提取成本控制 —— 收敛：个人规模下不做"延迟提升"，拆条立即做、对账保持异步全量

- **Claude**（修正 round-01 建议）：文献里的成熟模式是"**抽取本身写入时就做（便宜），
  延后的是去重/合并/图重构这类真正贵的整理工作**"（Letta sleep-time compute / 生产系统偏好
  on-write 抽取 + on-read 推理）；round-01 说的"候选轻量挂证据下延迟提升"实质是"延后抽取本身"，
  是更少见、成熟度更低的模式。**结论：个人自托管、单 worker、每天几十条证据规模下不值得做延迟提升**，
  先按现状（写路径不等待 + worker 异步全量拆条对账），靠分布监控 + 端到端延迟/对账比较次数指标后置优化；
  若未来多用户/团队场景再评估。
- **doubao**（工程形态，与 Claude 收敛）：**拆条和整合/演化是两件事，不应绑定**——
  拆条（单证据内、低 LLM 调用、高时效）**立即做**；整合/演化（跨证据、高成本、低时效）**批量做**
  （触发：未整合 ≥10 条 OR 距上次 ≥2 小时 OR 空闲且 ≥3 条；召回缺口= pending 结论立即可召回、
  可信度 ×0.8、UI 标"待整合"；整合按主题聚类逐簇 5-10 条处理）。引用 Auto-Dreamer 双通道
  （Fast Online Acquisition + Slow Offline Consolidation）、Google Always-On Memory（30min 定时）、
  LeanMem 缓冲区、dream-memory 门控（min_sessions=3 AND min_hours=1.0）。
- **收敛判向**：Claude 与 doubao 一致——**拆条立即做**（当前 worker 异步全量已是这个形态，不需改）；
  doubao 的"整合批量做"是一期之后的价值引擎方向（当前对账就是每次 evidence 全量对账，
  O(n²) 在个人规模下不构成瓶颈，与 Claude 判断一致）。
  **项目内核对**：当前对账 worker 每条 evidence 独立异步对账 = 拆条立即做 ✅；"批量整合"涉及
  对账流程重构，属于二期/完整项目（与 milestone §5"价值引擎推后"一致）。

## 六、round-02 新增的落地需求（进 99-final 实施映射候选）

| # | 需求 | 来源 | 形态 |
|---|------|------|------|
| R1 | Claim 加 `event_key` 弱组织字段（非实体、无 truth、不可裁决） | ChatGPT | schema 增量：claim.event_key TEXT NULL |
| R2 | 拆条输出带 `evidence_quote`（原文子句引用） | Gemini / doubao | claim_evidence 加 quoted_text / JSONB（或 evidence_chunk 表） |
| R3 | 拆条 prompt 含"反事实修改测试"+"Predicate Enumeration Test" | ChatGPT | prompt 指令（隐含检查，不输出） |
| R4 | 拆条阶段不输出冲突/支持字段，碰撞判定独立 LLM 调用（批处理 N 条） | Claude | 流程（当前已分步，改批处理） |
| R5 | 宁可多拆（错误可恢复性不对称），合并走"泛化/合并"边不破坏 confirm 记录 | Claude | 粒度策略 + 合并语义设计 |
| R6 | 拆条质量监控：拆出条数分布/单条长度分布 + 定向抽检 | Claude | 监控指标（可进验收） |
| R7 | learned-pattern 保留"条件–做法–结果"最小完整结构（不机械原子化） | Gemini / Grok | claim_kind 软规则 |
| R8 | 拆条输出 JSON schema：claims[] {id, statement, claim_kind, event_key, relations[]} | ChatGPT | 落地版 schema（V1 裁剪：relations 只留 rationale_for/condition_for/depends_on） |
| R9 | statement 自足性硬规则（脱离 Evidence 仍可理解；"自洽但不自我膨胀"） | ChatGPT | prompt 指令 |
| R10 | 验收指标：Correction Blast Radius / Evidence Contamination / Reconstruction Rate | ChatGPT | 验收标准 |
| R11 | 证据分块（中文 300-500 字、中文标点分隔符、Markdown 按标题分层） | doubao | 仅当采用 chunk 级引用时 |

## 七、round-02 后仍未收敛 / 需项目内裁决的点

1. **原子形态 vs 主 claim+子属性**（Claude TriQua 方案 vs ChatGPT/Grok 平行原子）：
   影响 claim 表形态。项目内判断：平行原子 + event_key 与现有 claim 表结构兼容（每行一个 statement），
   主 claim+子属性需嵌套/数组结构，改表成本高 → 倾向平行原子；learned-pattern 用"允许稍长 statement"
   保留因果（R7）而不引入嵌套结构。**收敛轮核对。**
2. **evidence_quote 是否需要 evidence_chunk 表**（Gemini JSONB 最小版 vs doubao 三层分块）：
   一期倾向 Gemini 最小版（JSONB 存 quoted_text + 服务端字符串匹配），evidence_chunk 表二期按需。
   **收敛轮核对。**
3. **event_key 生成**：ChatGPT 建议 LLM 输出 e1/e2 序号（不浪费 token 在 UUID），服务端映射
   extraction_id + e1。可落地。
4. **statement 长度参考**（Grok：理想 15-80 字、上限 150 字）——工程 heuristic，进 claim-atomicity 规范
   作为监控参考线而非硬限制。

*状态: 进行中 · 日期: 2026-08-19*
