# 最终统一理解（复用反馈回收 · 外部调研收敛）

> 类型: 调研（最终结论） · 调研: 2026-08-14-reuse-feedback-signals
> 执行: round-01（五平台无预设同题）→ round-02（交叉追问，三大分歧收敛，含平台主动修正）→ 收敛轮（回项目内核对代码事实）。
> 纪律: 外部回答是素材不是事实；本文件实施映射已对照 schema.sql / memory_store.py / llm_entity_extraction.py 核对；
> C 类结论需回项目内验证（真实插件流量）后才可进 ADR / 根目录文档。

## 一、调研核心结论（一句话）

**系统缺的不是"更好的记忆评分"，而是"记忆使用后的 outcome 遥测"：把 Memory → Decision → Action → Outcome 建成
可追踪的事件链，先用低成本隐式信号 + 结果痕迹积累证据，再按"证据加权 → 门槛 → 软失效版本链"反哺记忆生命周期；
放弃"单条记忆 0/1 采纳标签"和"精确因果归因"的执念。**

该结论由五平台在**无预设**下独立收敛（round-01），并经 round-02 交叉追问加固——三个分歧点都由提出方自己修正，
证明收敛不是题面附和。

## 二、信号体系最终表述（round-01 + round-02 收敛）

| 信号类别 | 采集方式 | 成本 | 精度 | 定位（收敛后） |
|---------|---------|------|------|--------------|
| 检索/曝光遥测 | retrieval log、注入清单、context snapshot | 极低 | 低 | 证据链起点；只证明"被看到"，不证明"被用" |
| 模型自陈（ref/使用标注） | 生成侧声明用到的记忆 ID | 低 | 低-中（有确认循环风险） | **只做候选筛选/曝光计数，永不单独提权**；须至少一个独立结果层信号才上调置信度 |
| 对话/行为隐式信号 | 重复陈述、反驳/纠正、复制、继续追问、撤销回滚、重复查询 | 低 | 中 | 负信号为主：重复陈述/坑复现/反驳是干净负反馈；"没用上"仅弱负 |
| 开发结果痕迹（最强） | diff 采纳/编辑距离、命令与测试结果、CI 退出码、git commit、坑是否复现 | 低-中 | 高 | 开发助手特有的主力信号；接近真实效用 |
| 用户显式反馈 | 赞踩、直接管理记忆、自然语言确认/纠正 | 低 | 高 | 黄金标签/校准集；天然稀疏，不能做主力；纠正类可直接触发状态变更 |
| 归因诊断 | LLM-as-judge 对照（有/无记忆）、trajectory 分析、should_have_been_used | 中 | 中 | 离线/异步；把结果回传到记忆或检索策略 |
| 反事实/消融 | leave-one-out、抽样 A/B、bandit 式随机屏蔽 | 高 | 最高 | 只做离线校准集（1%~5% 抽样），校准其他弱信号的噪声率 |

### 负反馈与状态设计（round-02 三平台收敛）

- **证据加权**：不同证据强度不同（用户纠正 ≈ −1.0，环境矛盾 ≈ −1.0，一次没用 ≈ 0），Beta-Bernoulli 维护置信度；
  证据带**新鲜度**（时间衰减，decay 按记忆类型差异化）；
- **证据门槛**：单次"没用"永不降权；Stale 需要强负证据（纠正/环境矛盾）；**Harmful 需要因果归因**（M→Decision→Negative Outcome），
  与 Wrong/Stale 三轴分离；冷启动一律 UNKNOWN；
- **软失效 + 版本链**：永不物理硬删除；Full Contradiction → superseded_by；Partial Update → Evolved_To；
  置信度卡点 + 延迟提交（待 2 次印证）；
- **保守衰减 + 人工审计**：缓慢基础衰减 × 证据驱动衰减 + 硬下限；低频记忆负反馈打折；
  自动系统只提假设，人工直接覆盖即时生效（审计日志）。

### 归因粒度（round-02 收敛）

- 归因主体是**一次检索产生的 MemoryGroup（临时集合）**；证据先归组，强信号（显式提及/action 语义匹配/独特信息/消融）才下沉到单条；
- 两层共存：组/主题层管"加载/卸载/归档/冻结"，单条层管"质量治理"；组反馈**永不批量写回**单条分数；
- 提炼粒度在中观（主题/模块）两层架构：实时原子日志 + 异步主题归档（Compress & Synthesize）。

## 三、与项目内机制的映射（收敛轮核对代码事实）

### 已有机制（代码已验证）

| 调研结论 | 项目内已有落点 | 差距 |
|---------|---------------|------|
| 软失效 + 版本链，不硬删 | 显式 update 建版本链（version+1、root_memory_id、is_latest=false、updates 关系）；get_version_history 读取真实历史 | 语义一致；缺"Partial Update / Evolved_To"的显式区分（当前靠 updates 关系 + 新版本） |
| 冲突检测 → 降级 | detect_contradiction（LLM 判断 is_contradiction）+ 矛盾→updates + _mark_not_latest 降级 | 已有（NLI 判定范式与 Gemini 建议同构）；无置信度卡点/延迟提交 |
| 生命周期/过期 | is_latest / valid_from / valid_until / is_forgotten / forget_after | 已有 |
| 冷启动低置信 | confidence 字段存在 | 无 UNKNOWN/uncertain 状态语义；confidence 由写入时设定，无证据累积更新 |
| 检索事件留痕 | recall_traces（query/channels/dedup/final 注入清单） | **有"曝光"但无"使用/结果"**——recall_traces 到注入为止，不记录后续是否被采纳、任务结果 |

### 缺口（调研结论指向、项目内尚缺；均为 C 类，待真实流量验证后进 ADR）

| 缺口 | 调研依据 | 建议落点（待 ADR/实施） |
|------|---------|----------------------|
| **使用/结果遥测缺失（最优先，本次调研核心）** | ChatGPT（outcome telemetry 缺位）、Claude（开发结果痕迹）、Gemini（L3 测试/CI）、doubao（IDE 采纳+运行） | 召回事件 → 注入 → 后续信号回写：memories 加 usage/evidence 元数据（reuse_count、last_reused_at、正负证据计数），recall_traces 之后接"采纳/结果"记录；当前 schema 无任何此类字段（api_keys 的 last_used_at/usage_count 是认证用途，不是记忆用途） |
| 证据加权与状态机 | ChatGPT（evidence strength + Beta 置信度 + UNKNOWN）、Grok（多维效用向量） | memories 加状态/证据字段：evidence JSONB（正负加权事件）、status（unknown/active/stale/superseded）；confidence 改为证据推导而非写入时一次性 |
| 组/主题层 | ChatGPT（MemoryGroup 临时集合）、doubao（group_id 过滤 + 两层共存）、Gemini（主题归档） | 轻量起步：memories 加 group_id/主题标签 + 检索按组过滤；组级自动反馈后置 |
| 延迟反馈回填 | doubao（跨会话延迟效用）、Claude（跨会话存活）、Grok（长期聚合） | 会话结束/离线任务把 outcome 回填到本次召回组 |
| 人工审计接口 | Grok（完整档案/直接覆盖/审计日志） | 产品层（依赖 MR-011 知识浏览/纠错闭环）；自动降级留审计记录 |

## 四、分阶段实施建议（顺序即优先级）

| 阶段 | 内容 | 依赖 |
|------|------|------|
| 0（调研后立项） | 定义 Memory Event Schema（Task→RetrievalEvent→MemoryGroup→Items→Outcome）与证据加权表 | 本项目调研 99 结论 + v2 99 结论 |
| 1（遥测先行） | 插件侧埋点：注入清单回传 + 会话内"引用/plan/action/测试"信号 + 用户纠正事件；后端写入 evidence 元数据 | codex/opencode/dsh/hermes 插件 |
| 2（负反馈闭环） | 用现有 detect_contradiction + 显式 update 建立证据驱动的降级路径：强负证据→stale/superseded，加置信度卡点与延迟提交 | schema 加 evidence/status 字段 |
| 3（组层） | group_id/主题过滤 + 检索候选池收窄（doubao MVP 方案） | schema 加 group_id |
| 4（校准） | 离线 leave-one-out 抽样 + LLM 归因诊断，估计自陈信号噪声率、校准证据权重 | 插件信号积累 |

## 五、与 v2 调研的关系（本调研补上了什么）

- v2 结论："判据 = 复用机会×有效性×影响−维护/遗忘成本"，并指出**最大缺口是复用反馈回收**（P 因子最难估）。
- 本调研（Q2）就是围绕该缺口的深入：v2 回答的是"值不值得记"（判据/生命周期），Q2 回答的是"怎么观测到被用了"
  （信号体系 + 归因 + 反馈闭环）——两个问题是两个学科（价值判断 vs 反馈工程），Q2 补上了 v2 只点到的 HOW。
- Q2 对 v2 的一个关键修正提醒：**召回分高 ≠ 记忆好**（Claude/Gemini/doubao 独立强调），检索相关性不能当效用；
  且"没用"≠"有害"（ChatGPT 状态机），负反馈必须区分，避免把"没被召回/没用上"误判成记忆内容问题。

## 六、待回项目内验证项（C 类，进 ADR 前必须）

1. 插件实际能观测到的信号面（每端插件能拿到什么：最终输出？工具调用？用户动作？）——决定哪些信号根本采不到；
2. 开发结果痕迹在真实会话中的覆盖率（diff/测试/命令事件在对话型会话中的占比）；
3. 自陈 ref 信号在当前模型（doubao）上的真实噪声率（小样本实测）；
4. detect_contradiction 当前误判率与延迟提交的收益（对照 Gemini 的置信度卡点建议）。

