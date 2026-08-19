# 08 · round-01 统一理解（共识 / 冲突 / 待补）

> 归属: [README](README.md) 调研卡 · 日期: 2026-08-19
> 输入: 五平台回答原文（[chatgpt](03-round-01-answers-chatgpt.md) / [claude](03-round-01-answers-claude.md) / [grok](03-round-01-answers-grok.md) / [gemini](03-round-01-answers-gemini.md) / [doubao](03-round-01-answers-doubao.md)）
> 性质: 统一理解是**素材整理**，不是结论；标注事实来源（文献/实践/平台推理），未回项目内验证的不作为实施依据。

## 一、五平台高度共识（可直接作为判据基础）

**共识 1：粒度不由字数/长度决定，由「独立生命周期 / 可证伪单元」决定。**
全部平台一致。ChatGPT 提「四独立」测试（独立检索 / 独立纠正 / 独立失效 / 独立证据）；Claude 提「独立可证伪性测试」（粒度 = 谱系边能独立作用的粒度，由"工作台的裁决动作在哪个单位上生效"决定）；Gemini 提四判据（真值原子性 / 生命周期易变性 / 召回内聚性 / 裁决边界）；Grok / doubao 提「可独立证伪的最小有意义命题」。**本质收敛到同一判据：两个部分未来是否可能被分别裁决（一个纠正/失效、另一个仍成立）→ 是则拆。**

**共识 2：整篇文档 / 长原文照抄不是"粗结论"，是"分层错误"。**
全部平台一致：2383 字架构文档**根本不是 Claim，应该是 Evidence**。ChatGPT："零条结论、一份证据被误标成了结论"；Claude："原文照抄不产生理解增量，违背'结论可重算'"。结论 = 系统对证据的理解产物，必须是从证据提炼出的可证伪判断。

**共识 3：拆细的代价真实存在，但解药不是"把 Claim 做粗"。**
代价清单（五平台叠加）：存储/检索/关系/一致性/提取成本爆炸（ChatGPT）、单条结论不可读（Claude/Weaviate）、对账 O(N²)→O(16N²)（Claude 推理）、召回"只见树木不见森林"（Claude/Grok/Gemini）、UI 信息过载（Gemini）、碎片化缺上下文（doubao）。**解药共识：原子存储 + 聚合消费——写入时拆细，召回/展示时按需聚合，不新增粗 Claim。**

**共识 4：需要 Claim 之上的「组织/视图」层解决碎片化。**
ChatGPT：Group/Decision/Summary（"原子性和可理解性不要由同一个对象承担"）；Claude：co-derived-from 分组边；Grok：受控复合层（复合结论内部保持原子引用）；Gemini：复合结论/主题树 + 图邻域展开；doubao：召回时聚合视图。**分歧在实现形态**（见冲突 1）。

**共识 5：证据支持关系必须精确，不能模糊共享。**
ChatGPT："Evidence 可以共享，但 support relationship 不能模糊共享"——多条不同主题证据被同一宽 Claim 吸收 = provenance bug（正是我们观察到的置信度虚高）；doubao：证据引用应精确到片段（offset/span），"引用整条证据"与"引用其中几句话"可信度完全不同。

**共识 6：原子性 = 系统生命周期性质，不是语言学性质。**
ChatGPT（"atomicity 不是语言学性质"）/ Gemini（"粗与细标尺误导，应该用原子性衡量，类比 3NF"）/ doubao（"不是固定阈值问题，是按证据性质选择最小充分表示"）。过度机械拆分（一句话一个 Claim、一个主谓宾一个 Claim）是错误方向（ChatGPT 引 TriQua：atomicity 与 context preservation 有张力，必要上下文用 qualifiers 保留）。

## 二、主要分歧 / 决策点（round-02 追问对象）

| # | 分歧点 | 各方立场 | 为什么是决策点 |
|---|--------|---------|---------------|
| D1 | **组织层实现形态** | ChatGPT：Group/Decision/Summary 实体层（derived view）；doubao/Gemini：召回时动态聚合视图（只读计算，不落库）；Claude：谱系边加 co-derived-from 类型 | 影响 schema 与召回实现；foundation 已拍板「Entity/主题 = P2 不进核心」，加实体层与此冲突 |
| D2 | **证据引用精度** | doubao：精确到片段 span；当前实现只到 evidence_id | 影响 claim_evidence schema；决定置信度虚高问题修到什么程度 |
| D3 | **拆条质量保障** | FActScore（Min et al.）：原子事实判定必须"无争议"；TriQua：annotator 对合取/条件/上下文拆分存在明显分歧；Claude 未直接给方案 | 我们依赖 LLM 拆条，拆分本身不稳定，需要校验机制 |
| D4 | **是否按 claim_kind 差异化粒度** | doubao：按类型设不同粒度上限（事实/约束原子化、架构/方案结构化子项）；Gemini：加权重/层级字段；LeanMem：三类异构表示 | 我们已有 4 值 claim_kind（fact/preference/constraint/learned-pattern），是否映射差异化策略 |
| D5 | **提取成本控制** | Claude：候选原子结论先轻量挂 evidence 下，复用命中/高风险才提升为正式 Claim（延迟提升）；当前实现 evidence 落库立即全量对账提炼 | 影响对账 worker 流程与写路径可靠性 |

## 三、项目内已确认判断的对照（收敛轮输入，非结论）

- 「一条 evidence 只产一条 claim」与 foundation「0..N」相悖 → 平台全部支持拆条，方向确认；
- 「statement 未体现的证据 reinforce 进来抬高置信度」→ 平台确认这是 provenance bug（共识 5），
  且给出两个量化指标：**Correction Blast Radius**（修正爆炸半径，ChatGPT）与 **Evidence Contamination**（证据污染比例，ChatGPT）——可进验收标准；
- 「裁决只能整条 supersede 连带误杀」→ 平台确认这是粒度过粗最典型症状（ChatGPT 最强拆分信号 = 独立纠正）。

## 四、平台标注的「自己推理 / 不确定」部分（回项目内验证前不信）

- ChatGPT 明确标注：MIC（Minimum Independent Claim）、Blast Radius、Evidence Contamination、Summary=derived view 是**综合设计推理**，非论文现成结论；
- Claude 明确标注：独立可证伪性测试、非文档测试、co-derived-from 分组边、延迟提升、按主体分桶降对账成本均为**推理**，无直接文献；
- doubao 明确标注：结论类型粒度表、证据片段引用、聚合视图、部分取代为**推理**；
- Claude 诚实声明：无文献给出"结论多少字/token"的量化阈值；Dense X Retrieval 的"100-200 词≈10 命题"是英文维基语料经验，中文项目语境换算关系未知；
- doubao 未决：谱系边 DAG 长期可维护性（深度/宽度增长、20 层谱系链查询性能）无成熟方案，建议压力测试。

## 五、文献/实践出处清单（外部素材，非项目结论）

| 出处 | 平台引用 | 相关点 |
|------|---------|--------|
| Dense X Retrieval（EMNLP 2024, Chen et al.） | Claude | 命题粒度检索；自足性/最小性/语境化三标准；句子边界≠语义边界 |
| FActScore（EMNLP 2023, Min et al.） | Claude/Grok | atomic fact 定义；互不重叠/判定无争议假设；合取命题失良定义 |
| Zep / Graphiti（arXiv:2501.13956） | Claude/ChatGPT | 事实=图边+时间有效区间；冲突检测限定实体对；一条事实=一个谓词作用于实体 |
| ATOM（EACL 2026 findings） | ChatGPT | 拆分为 minimal self-contained atomic facts，抽取完整性与稳定性提升 |
| TriQua（arXiv:2608.05228） | ChatGPT | 复杂事实需保留 qualifiers/context，不能为 atomicity 丢上下文 |
| Dissecting Atomic Facts（arXiv:2509.01460） | ChatGPT/Claude | 原子性定义模糊，annotator 拆分分歧 |
| Mem0（token-efficient memory） | ChatGPT/Grok | 独立可检索 atomic memories；token-efficient retrieval |
| LeanMem（arXiv 2026-08, 合工大） | doubao | 三类异构记忆表示（profile/event/record）；统一摘要=最大准确率下降 |
| A-MEM（arXiv:2502.12110） | doubao | 原子记忆卡片+双向关联边+动态进化（Zettelkasten） |
| AtomicRAG | Grok | 原子级存储+查询分解避免粗单元稀释 |
| Truth Maintenance System（1979） | ChatGPT | belief 记录 justification，assumptions 变化时依赖式修正 |
| Claude Code 记忆设计（第三方分析） | doubao | 索引行（150 字符/200 行）+ 按需加载 + Auto Dream |
| Weaviate chunking 指南 / 分块实证研究 | Claude | 自足性判据；极细分块丢答案；非单调下游曲线 |
| AI21 多分辨率索引 | Claude | 无普适最优粒度，查询依赖，多尺度索引+RRF |

## 六、round-02 追问分配（见 [04-round-02-prompts.md](04-round-02-prompts.md)）

针对 D1–D5 五个决策点，按平台画像与"谁提出谁深化"分配（每平台 2 个聚焦追问），
背景附上项目内约束（foundation 已拍板项），让平台在真实约束下给方案而非泛泛而谈。

*状态: 进行中 · 日期: 2026-08-19*
