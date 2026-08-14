# Round 1 统一理解（复用反馈回收 · 无预设同题）

> 类型: 调研（统一理解） · 调研: 2026-08-14-reuse-feedback-signals
> 执行方式: 五平台（ChatGPT / Claude / Grok / Gemini / doubao）收到**同一开放题**，无候选信号、无预给"采纳"定义、
> 无文献点名。回答原文见各 03-round-01-answers-<platform>.md，不二次概括。
> 纪律: 外部回答是素材不是事实；C 类结论回项目内验证后才可进 ADR / 根目录文档。

## 一、五平台独立收敛的共同结论（无预设条件下出现，可信度高）

本轮最关键产出：**在不给任何候选信号 / 机制 / 文献的前提下**，五平台独立指向同一批结论。说明以下不是题面诱导，
而是多平台各自的本质判断。

| 共同结论 | 证据平台（独立提出） |
|---------|---------------------|
| 问题本质是**归因（credit assignment）**，不是"检测"——能观测的只有下游结果，"某条记忆贡献了多少"是反事实问题 | 全五平台（ChatGPT：ΔSuccess(M,C)；Claude：因果纠缠；Grok：信用分配；Gemini：RL 信用分配；doubao：无法严格因果归因） |
| **放弃单条 0/1 "采纳"标签**，改走"多信号融合 → 连续效用分 + 证据累积" | 全五平台 |
| 信号按**成本/精度分层**组织，高精度（显式反馈/消融）必然稀疏或昂贵，只能做校准/黄金标签，不做主信号 | 全五平台 |
| 开发场景特有的**结果痕迹是最强信号**：代码 diff 采纳、构建/测试结果、命令执行、坑是否复现 | 全五平台（ChatGPT：code diff/test；Claude：坑复现最干净；Grok：代码接受+build/test；Gemini：L1 IDE/L3 CI；doubao：IDE 采纳+运行结果） |
| **显式用户反馈（赞踩/直接管理记忆）精度最高但天然稀疏**，几乎所有产品都验证过采集率过低，不能当主力 | 全五平台（Claude/Windsurf/Cursor 观察；doubao 工程实践；Grok RLHF 经验） |
| **负反馈比正反馈可靠**，且"没用"≠"有害"必须区分 | ChatGPT（useful/irrelevant/stale/wrong/harmful 状态机）；Claude（坑复现、重复陈述是干净负信号）；Gemini（显式否定最高价值）；doubao（反驳强负向、重复查询负向） |
| 记忆要有**状态/生命周期**，而不是一个单调递减的分数（Stale/Superseded/归档/合并） | ChatGPT（状态机）、Claude（superseded）、Gemini（Superseded+归档）、doubao（过期标记+归档）、Grok（保留策略） |
| 反事实/消融是**归因黄金标准，但只能离线抽样做**，用来校准其他弱信号 | 全五平台 |
| **写入端从严**是长期更省力的杠杆（去重、来源可追溯、试用期权重、负反馈优先于隐式正反馈） | Claude、doubao（隐性预防类记忆靠显式确认/规则保留）、ChatGPT（记忆自声明用途） |
| 记忆价值是**条件性的**：Value(M∣Context)，且**延迟效用**存在（本次没用、隔几天才生效） | ChatGPT（Value(M∣Context)、适用场景一等公民）；doubao（跨会话延迟信号）；Grok（长期聚合）；Claude（跨会话存活确认） |
| **"结果差"不能无差别惩罚所有召回记忆**（归因陷阱），要区分"被采纳但结果差"（记忆可疑）vs"未被采纳"（与记忆无关，该查召回策略） | Claude（四象限）、ChatGPT（两学习器）、Grok（utility vs retrieval 分离）、doubao（多记忆混杂） |

## 二、各平台独立提出的核心框架（差异在组织方式，方向同构）

| 平台 | 核心框架 | 信号分层 | 自标出处 |
|------|---------|---------|---------|
| ChatGPT | 问题重新定义为"估计记忆在 context 下对任务结果的**增量贡献**"；U(m,c)=R×A×V×O 四维；三级信号（L1 隐式遥测 → L2 LLM 归因 → L3 反事实）；记忆自声明用途（When useful / Expected consequence / Evidence）；两个学习器（内容 vs 检索策略） | 引用/plan/action/code diff/tool/test/用户纠正/任务成功 信号表（20 行） | MemCon 2026、MemToolAgent、memory survey、Joachims click bias（附 arXiv 链接） |
| Claude | 归因问题而非检测问题；**uptake 与 outcome 拆成两轴**的四象限表；信号分显式/隐式/模型自评三类；"坑是否复现"是最干净的负反馈；跨会话"持续未被推翻"=累积正反馈 | 显式（赞踩/纠正/重复陈述）→ 隐式（diff 采纳/命令/测试/坑复现/回滚）→ 模型自评（向量相似度/Reflexion） | HiMPO/Mem-T/ICA（2026 arXiv 预印本，未验证顶会）、Park et al. 2023、When to Forget 预印本、Reflexion |
| Grok | 效用信号而非采纳标签；多粒度多时间尺度；5 类信号；**信用分配 + 主动巩固 + 闭环共演化**（检索策略与记忆库价值共同更新）；特别警告**错误的负反馈会加速遗忘低频但有用的记忆** | 显式反馈（黄金标签）→ 任务/会话结果 → 隐式行为（diff 接受率/反驳/投入度）→ 模型内部诊断（LLM-as-judge 对照）→ 长期聚合 | 多篇 2025–2026 arXiv/OpenReview agent memory 工作；行为信号为工程推理/跨领域迁移 |
| Gemini | RL 信用分配问题；**放弃单次精准归因**，转向多维隐式信号 + 异步巩固；L1/L2/L3 信号矩阵；实时效用分（Score=α·Recency+β·Importance+γ·Utility）+ 异步冲突检测（L2 纠错触发 Superseded） | L1 代码/IDE（diff 采纳+编辑距离、LSP 诊断、Git commit）→ L2 对话（显式否定、Retry/Undo）→ L3 任务工程（终端/CI 退出码=终极真理） | Park et al. 2023、MemGPT、Zep/Mem0 事实失效；IDE/LSP/Git 信号网为工程推演 |
| doubao | 9 个信号分四类（LLM 侧 / 显式 / 隐式行为 / 跨会话延迟）；元数据统计表 + 证据加权 + 时间衰减 + 检索重排；明确列出**四个易踩坑错误方案**；额外提出**"记忆组"范式**（组级开关、组级反馈，降低单条归因压力） | ref 标记 → 后向归因 → 消融（离线）→ 整体赞踩 → 直接管理记忆 → 会话行为（复制/反驳/重复查询）→ IDE 采纳+运行 → 跨会话累积统计 | RAGTruth 2024、LangGraph 文档、Cursor/Copilot 公开博客、Retrieval-Augmented LM ablation；其余为综合推理 |

## 三、关键分歧点（round-02 追问轮候选）

### 分歧 A：归因粒度——单条记忆级 vs 记忆组级

doubao 明确质疑单条归因范式，提出"记忆组"（按项目/主题/版本分组、整组开关、组级反馈）；
其余四平台默认按单条记忆建事件链 / 统计表。若组级成立，"Memory Event Schema + 单条 credit assignment"
的整个架构要改写；若组级不成立，需要说清楚"组内坏记忆怎么被掩盖"。

### 分歧 B：模型自陈（ref 标记 / 使用标注 / 记忆自声明用途）的可信度与定位

ChatGPT 建议记忆"自声明用途"（When useful / Expected consequence / Evidence）并把 mentioned / used_in_plan
写进 V1 事件链；Claude 建议生成侧自陈"用到了记忆 ID"作为最便宜的 uptake 采集；doubao 给出 ref 标记的
三类漏洞（幻觉 ref / 隐性使用丢失 / 内化不引用）并降级为"低-中"信号。分歧在于：自陈到底算主信号还是只算
粗筛，以及"隐性使用"（看到但没写 ref、实际影响了推理）怎么补。

### 分歧 C：负反馈与归因陷阱的落地防护

三平台都识别了"结果差 → 无差别降权"的归因陷阱，但给出的防护不同：Claude 用 uptake×outcome 四象限；
ChatGPT 用 useful/irrelevant/stale/wrong/harmful 五状态 + 证据累积（一次没用不降权）；Grok 警告错误的负反馈
会加速遗忘低频但有用的记忆，主张保守衰减 + 人工可审计。分歧在：状态机 vs 四象限 vs 保守衰减，哪个更适合
"开发助手 + 已有 contradiction 检测"的存量系统。

## 四、与本项目现状的直接相关点（回项目内验证用，非结论）

- 本系统已有 detect_contradiction（矛盾→降级）+ 显式 update 建版本链 + is_latest 语义，与
  分歧 C 的"负反馈优先"、"Superseded/版本化"直接咬合（Claude 四象限、Gemini L2 纠错触发 Superseded、
  doubao 过期标记）。
- 本系统检索路径（context-inject + semantic_dedup）目前无任何 usage/outcome 遥测，缺的正是 ChatGPT 说的
  "Memory → Decision → Action → Outcome 可追踪链路"。
- v2 结论"判据 = 复用机会×有效性×影响−维护/遗忘成本"与 round-01 的"增量贡献 ΔSuccess(M,C)"同构，
  但 round-01 明确补上了 v2 的缺口：**怎么观测**（信号体系 + 归因），且提醒"召回分高 ≠ 记忆好"。
