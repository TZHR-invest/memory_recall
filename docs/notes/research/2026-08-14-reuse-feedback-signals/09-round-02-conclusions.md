# Round 2 统一理解（复用反馈回收 · 交叉追问收敛）

> 类型: 调研（统一理解） · 调研: 2026-08-14-reuse-feedback-signals
> 执行方式: 在 round-01 **同一会话**内针对三大分歧交叉追问（ChatGPT/Grok 问分歧 C，Claude 问分歧 B，
> Gemini/doubao 问分歧 A）；追问不点名其他平台表述，只针对该平台自己回答里的薄弱点。回答原文见各
> 05-round-02-answers-<platform>.md，不二次概括。
> 纪律: 外部回答是素材不是事实；C 类结论回项目内验证后才可进 ADR / 根目录文档。

## 一、本轮最重要的现象：主张被各自修正，不是附和

| 平台 | 上一轮主张 | round-02 的修正 | 修正性质 |
|------|-----------|----------------|---------|
| ChatGPT | 五状态机 + 单条 Memory Event Schema | 状态是"证据推导出的 operational state"，**第一等公民是证据不是状态**；主动把单条事件链改成 Task→RetrievalEvent→MemoryGroup→Items 三层 | 主动重构自身方案 |
| Claude | 生成侧自陈是最便宜直接的 uptake 采集 | 自陈**不应单独触发任何提权决策**，只能做候选筛选；它是有确认循环风险的唯一信号类型，必须单独限权 | 主动收窄自身主张 |
| doubao | 用"记忆组"范式替代单条归因 | 纯组级会产生组内腐化、**不可接受**；组级与单条必须两层共存，MVP 阶段组只做过滤不做自动打分 | 主动撤回强主张 |
| Gemini | 冲突检测标记 Superseded | 补齐"**永不物理硬删除** + NLI 四步流水线 + 置信度卡点 + 延迟提交"的安全机制；提炼粒度收敛到主题/模块级两层架构 | 补强自身方案 |
| Grok | 保守衰减 + 人工可审计 | 给出可操作的多维效用向量、分段衰减公式、证据门槛、低频保护与快速恢复通道 | 落地化自身方案 |

三个分歧均有**提出方自己修正**，说明收敛是真实思考而非题面附和。

## 二、分歧 A（归因粒度）：收敛为"两层共存，组控加载、单条管质量"

### 三方的收敛位置

| 平台 | 关键论述 |
|------|---------|
| ChatGPT | 单条归因天然不可靠（redundancy/complementarity/synergy，Shapley 太贵）；事件模型改为 Task→RetrievalEvent→MemoryGroup→Items；**证据天然先属于 Group，只有额外 attribution 证据才下沉到 Item**；Group 是"一次检索的临时集合"不是永久属性；V1 只做 Group→Outcome 归因 + 有条件 Item 归因 + 抽样 Item ablation |
| doubao | 组级会"坏记忆搭便车"（沉默错误随组持续存活）且"局部失效拖累整组"；**组级不能替代单条**；组只决定"要不要加载这组"，单条统计保留在组内；组正向反馈严禁批量给组内记忆加分；MVP = 扁平库 + group_id 过滤 + 组内完整单条闭环 |
| Gemini | 提炼粒度三档（原子/主题/项目），推荐**中观（主题/模块）**两层架构：实时原子日志 + 异步主题归档引擎（Compress & Synthesize）；召回先主题文档补整体、再原子增量补细节 |

### 收敛结论

- 归因主体是**一次检索产生的 MemoryGroup（临时集合）**，不是单条记忆，也不是永久的分组；
- 组/主题层负责"加载/卸载/归档/冻结"（控制候选池），单条层负责"质量治理"（降级/隔离/淘汰）；
- 组级正反馈**永不批量写回**单条分数（credit leakage 禁令）；
- MVP 顺序：先 group_id 过滤 + 单条闭环，再组 UI/全局组，最后才组级自动反馈。

## 三、分歧 B（模型自陈信号）：收敛为"只做候选筛选，永不单独提权"

| 问题 | Claude round-02 的答案 |
|------|----------------------|
| 偏差方向 | 两种失效分开处理：假阳性（说了用、没真用；context 与参数知识重合导致的 unfaithfulness）vs 假阴性（真用了、没写 ref） |
| 校准 | 小比例（1%~5%）leave-one-out 消融做校准集（ContextCite / AttriBoT / RAGONITE 思路）→ 混淆矩阵估计噪声率，按记忆类型分层；全量用便宜文本比对粗筛，抽样消融精校，用精校结果修正粗筛的系统偏差；历史日志对比"自陈用/没用"两组的结果分布做零成本 sanity check |
| 权重 | 自陈不单独触发提权，只做曝光计数；唯一有**确认循环风险**的信号，必须单独限权（约 0.05~0.1 vs 结果确认正反馈 1.0，且设天花板）；"自陈没用"比"自陈有用"可信（无否认动机），但只用来调检索范围、不删记忆 |
| 隐性使用 | 条目级全覆盖做不到；缓解：低门槛 touched_memory_ids、自托管模型的 attention 线索（只当线索）、对"自陈没用"抽样 leave-one-out、bandit 式随机屏蔽做统计补偿（规模大了再上） |

### 收敛结论

- 自陈信号（ref/使用标注）= **候选筛选 + 曝光计数**，是证据链的起点不是终点；
- 置信度上调必须至少有一个**独立的结果层信号**（未被纠正/代码被采纳/坑未复现）；
- 隐性使用通过"小比例消融抽样 + 统计补偿"覆盖，不追求单条全覆盖。

## 四、分歧 C（负反馈与归因陷阱）：收敛为"证据加权 + 证据门槛 + 保守衰减 + 冷启动 UNKNOWN"

| 平台 | 贡献 |
|------|------|
| ChatGPT | evidence strength 分级表（提及 0.2 → plan 0.4 → action 0.6 → 测试改善 0.8 → 用户确认 1.0；纠正/环境矛盾/导致失败 −1.0~−1.2）；Beta-Bernoulli 维护置信度而非状态；**证据新鲜度**（时间衰减，decay 按记忆类型）；只有强负证据（用户纠正/环境矛盾）才触发 Stale；**Harmful 需要因果归因**（M→Decision→Negative Outcome），与 Wrong/Stale 三轴分离；冷启动 = UNKNOWN，不强分五类；retrieved-but-unused 永不触发 stale/wrong/harmful |
| Grok | 低频有用 vs 过时未揭穿的区分信号（冲突一致性/条件触发匹配/恢复重现价值/外部变化代理/负反馈稀疏性）；多维效用向量；**分段双时间尺度衰减**（缓慢基础衰减 × 证据驱动衰减，带硬下限）+ 低频保护（低频负反馈打折 0.3~0.5）+ 快速恢复通道 + 人工可审计接口（完整档案/证据明细/直接覆盖/审计日志/影响预览） |
| Gemini | 误判成本不对称（假阳性删错 >> 假阴性并存）→ **永不物理硬删除**；NLI 四步流水线（结构化抽取→候选检索→NLI 分类 Contradiction/Partial_Update/Entailment/Neutral→版本链更新 superseded_by / Evolved_To）；置信度 >0.85 才软失效；延迟提交（待失效到被 2 次以上印证才正式更新） |

### 收敛结论

- 负反馈必须**加权 + 门槛**，单次"没用"永远不降权（弱证据只调检索，不碰内容状态）；
- 过时/矛盾处理 = **软失效 + 版本链**（superseded_by / Evolved_To / Partial_Update），永不物理删除；
- 冷启动与新记忆 = **UNKNOWN/uncertain 态** + 试用期保护，避免证据稀疏期误判；
- 人工可审计是必要组件：自动系统提假设，人做最终仲裁，直接覆盖即时生效。

## 五、三分歧收敛后的统一机制草图（供 99 引用）

```text
Task ──┬── Context snapshot
       ├── RetrievalEvent(s) ── MemoryGroup (临时集合) ── Items
       ├── Agent decisions / Actions / diffs / tests
       └── Outcome ──▶ 证据写入（加权，先归 Group 再按强信号下沉 Item）

记忆侧：Content posterior（correctness/staleness/harmfulness）∥ Retrieval posterior（P(useful|M,C)）
        ──▶ Lifecycle：unknown / active / uncertain / stale / suppressed / superseded

负反馈：证据加权 → 门槛 → 软失效版本链（不硬删）＋ 保守衰减 ＋ 人工审计覆盖
```

