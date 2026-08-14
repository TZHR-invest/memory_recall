# Round 1 回答：ChatGPT

> 类型: 调研（原始回答归档）
> 调研: 2026-08-14-memory-value-criteria
> 平台: ChatGPT（Q1 判据本体 / Q2 项目内 vs 跨项目 / Q3 价值度量）
> 说明: 原文粘贴，未二次概括

### Q1 / Q2 / Q3

这个问题我建议先做一个重要区分：

“值得保存” ≠ “值得立刻晋升为长期知识”。

现有文献其实没有一个被广泛接受的、可以直接计算出 memory_score > 0.73 的统一理论。比较可靠的做法，是把不同传统里的判据拆开，然后组合成一个面向 Agent 的工程判定模型。

你的价值锚点——

未来还会被需要 × 忘记后会产生重新输入/重新检索/重新推理成本

我认为是一个相当好的产品定义；但需要说明：这是你的产品定义，不是某篇经典文献直接提出的公式。

下面严格区分【原文事实】【推断】【不知道】。

1. 什么样的信息值得保留 / 晋升为可复用知识？

我把相关理论归纳成 10 个判据。

判据	理论/出处	原文事实	能否操作化
未来相关性	Park et al. 2023, Generative Agents	Memory retrieval 综合 relevance、recency、importance	强
重要性 / 显著性	Park et al. 2023	每条 memory 有 importance，并参与 retrieval	强
近期性	Park et al. 2023	retrieval 同时考虑 recency	强，但更适合 retrieval，不适合 retention
反复检索/复用	Roediger & Karpicke 2006/2007	repeated retrieval 能显著增强长期保留	强
可泛化性 / 抽象性	Hu, Long & Wang 2026	抽象 procedural memories 比详细 trajectories 更容易跨任务 transfer	强
可连接 / 可组合性	Luhmann / Zettelkasten	知识单元之间的连接是核心；atomicity促进复用	中-强
原子性 / 单一知识单元	Zettelkasten	一个 note 聚焦一个 knowledge building block / topic	强
证据、可靠性、可重复性	Ackoff 后续扩展 / DIEK；Yao et al. 2019	knowledge 应与 evidence、relevance、robustness、repeatability、reproducibility 联系	中-强
从经验到高层反思/知识	Park et al. 2023	reflection 将 memories synthesis 成 higher-level inferences	强
显性化 / 可表达化	Nonaka 1994	知识通过 tacit ↔ explicit 转化创造和放大	中

下面逐条展开。

1.1 未来相关性：以后解决问题时是否可能需要它？

这是最直接对应你产品目标的判据。

【原文事实】

Park et al. 的 Generative Agents 明确采用：

relevance + recency + importance

来决定哪些 memory 被检索出来。
arXiv

论文的架构不是“把所有历史都永久塞进 context”，而是：

experience → memory stream → retrieval → reflection → planning

而且作者明确指出，长期 Agent 的关键问题之一就是：

retrieve relevant events and interactions over a long period

arXiv

论文：

Park, J. S., O'Brien, J. C., Cai, C. J., Morris, M. R., Liang, P., & Bernstein, M. S. (2023). "Generative Agents: Interactive Simulacra of Human Behavior." UIST 2023.

论文：Generative Agents

【推断】

对你的 Agent：

future_relevance(x)
=
P(x 会帮助未来任务)

应该是最核心的 retention signal 之一。

可以通过：

后续 query 与 memory 的 semantic similarity

memory 被实际 retrieve 的次数

被 retrieve 后是否进入最终 answer/context

被 retrieve 后是否改变了 action

用户是否再次提及相关概念

进行估计。

【不知道】

文献没有给出：

“未来复用概率 > 20% 就应该永久保存”

这种通用阈值。

所以阈值应该由你的产品数据学习，而不是声称来自认知科学。

1.2 重要性 / 显著性
【原文事实】

Generative Agents 不只是 relevance，还给 memory 一个 importance。

论文明确描述 memory retrieval model：

combines relevance, recency, and importance

并将 reflection 建立在这些 memories 之上。
arXiv

因此：

importance ≠ relevance

是一个很重要的设计启发。

比如：

“今天运行 npm install 时用了 12 秒”

可能 relevance 很高，但 importance 很低。

而：

“这个项目决定永远采用 SQLite + sqlite-vec，不考虑 PostgreSQL”

可能当前没有立即 relevance，但 importance 很高。

【推断】

你的系统应该区分至少：

importance
relevance
recency

而不是一个总分。

可以进一步把 importance 拆成：

decision_impact
cost_if_forgotten
future_scope
能否操作化？

可以。

例如：

importance =
    decision_impact
  + user_explicitness
  + downstream_dependency_count

但这是工程设计，不是 Park 原论文中的公式。

1.3 反复被使用：Retrieval / Reuse Frequency

这个判据非常有价值，因为它比“LLM 猜测重要性”可靠。

【原文事实】

Roediger & Karpicke 的经典研究发现：

retrieval practice 本身会增强长期记忆。

2006 年 Psychological Science 的实验发现，延迟测试中，之前进行 retrieval practice 的材料比单纯重复学习有更好的长期保持。
数字对象标识符
+1

2007 年进一步发现：

repeated retrieval during learning is the key to long-term retention

科学直接

论文：

Roediger & Karpicke, 2006

Karpicke & Roediger, 2007

【推断】

虽然这是人类学习研究，不是 Agent memory retention 算法，但可以得到一个很有用的工程启发：

一次被使用只是“可能有用”；多次被成功使用是非常强的价值证据。

所以可以把：

reuse_count

作为长期记忆晋升的重要 signal。

例如：

temporary
    ↓ 被使用 1 次
candidate
    ↓ 被不同任务使用 2~3 次
stable knowledge

注意：

2~3 次不是文献阈值，是产品 heuristic。

1.4 从具体经历 → 抽象知识

这个判据对于你设计 Agent memory，我认为特别重要。

【原文事实】

2026 年的一项研究：

Hu, Long & Wang, "When Continual Learning Moves to Memory: A Study of Experience Reuse in LLM Agents"

研究 LLM agent 的 external memory 如何影响 continual learning。

其核心发现之一是：

abstract procedural memories transfer more reliably than detailed trajectories

也就是说：

抽象后的经验，比原始详细 trajectory 更容易跨任务复用。

arXiv

论文还指出，external memory 并没有消灭 continual-learning 的 stability/plasticity 问题，而是把问题转移到了：

representation + organization + retrieval

arXiv

【推断】

这对你的系统非常关键：

不要简单做：

Conversation
    ↓
Summary
    ↓
Memory

而应该尝试：

experience
   ↓
specific fact
   ↓
pattern / lesson
   ↓
generalizable knowledge

例如：

项目 A：
“sqlite 多线程写入导致 database is locked”

不应该只保存：

项目 A 使用 SQLite，max_workers=4 会锁库

更高价值的知识可能是：

SQLite 在当前写入模式下不适合未经协调的多线程并发写入；
优先使用 WAL + 单写者/写入队列。

后者具有跨项目复用价值。

能否操作化？

可以，而且非常适合做 promotion signal。

可以检测：

project_dependency ↓
environment_dependency ↓
abstraction ↑
transferability ↑
1.5 Reflection：从多个事实产生高阶知识
【原文事实】

Generative Agents 的 reflection 机制，就是：

synthesize memories into higher-level inferences

即从底层 memories 形成 higher-level inference。
arXiv

例如：

Observation 1
Observation 2
Observation 3
       ↓
Reflection
       ↓
Higher-level inference
【推断】

因此可以把：

“是否已经产生了比原始记录更高层次的解释？”

作为 promotion 的判据。

例如：

事实：
MacBook M4 CPU-only


事实：
CLIP embedding 很慢


事实：
80k photos 需要 24~48h


        ↓


知识：
本项目的 embedding pipeline 应支持后台批处理，
并把 GPU acceleration 作为可选 backend。

后者才是“知识”。

1.6 原子性 / 可复用性
【原文事实】

Zettelkasten 的核心原则之一是 atomicity：

一个 note 应尽量表达一个独立的 knowledge building block / topic，同时通过连接与其他 notes 组成网络。
Zettelkasten
+1

Zettelkasten.de 对 atomicity 的解释尤其强调：

atomicity fosters reuse

并认为把不同 concerns 分开，可以提高复用和连接能力。
Zettelkasten

【推断】

对 Agent memory：

一个 memory = 一个可独立复用的 claim / fact / rule / decision

通常比：

整个 session summary

更适合作为长期 memory。

例如不要：

[Session 182]
今天我们讨论了 LensDiary 的数据库、Face Recognition、
Story Detection、SQLite 并发、GPU……

而是：

LensDiary 使用 SQLite + sqlite-vec
LensDiary face embedding 使用 ArcFace 128-d
Story detection 使用 time/GPS/CLIP/person 四类 signal
SQLite 当前写入路径使用单 writer

这样 retrieval 才容易精确命中。

能否操作化？

非常容易。

例如：

atomicity_score =
    1 / number_of_independent_claims

或者更实用：

一个 memory 是否能被一个明确的 query 独立召回并直接使用？

1.7 可靠性 / 稳定性 / 可验证性

这个维度非常容易被 Agent memory 忽略。

【原文事实】

DIKW 的经典来源是：

Russell L. Ackoff, "From Data to Wisdom", 1989

其框架从：

Data
Information
Knowledge
Understanding
Wisdom

逐级抽象。
J-GLOBAL
+1

后续关于这一框架的修订提出：

Data → Information → Evidence → Knowledge

并将：

relevance

robustness

repeatability

reproducibility

作为从 evidence 到 knowledge 的 checkpoint。
PubMed Central (PMC)

【推断】

对 Agent memory，这是一个非常好的 promotion gate：

单次观察
    ↓
事实
    ↓
多次验证
    ↓
稳定知识

例如：

“今天 API 返回 500”

不能自动升级成：

“这个 API 不稳定”

但是：

过去 20 次调用中 8 次失败

就具有更高的 evidence strength。

可操作化？

可以：

evidence_count
source_count
independent_confirmation
contradiction_count
last_verified_at

尤其推荐：

confidence
stability
freshness

分开存。

1.8 “当前正在发生”并不等于“长期值得保存”

这是 cognitive consolidation 能给你的重要启发。

【原文事实】

记忆 consolidation 的经典概念是：

新获得的信息经过一段过程后变得更加稳定、抗干扰。

Nader & Hardt 2009 对 consolidation / reconsolidation 做了综述；Walker et al. 2003 也讨论了 consolidation 的时间过程。
Nature
+1

【推断】

对于 Agent：

raw interaction
        ↓
working / episodic memory
        ↓
repeated exposure / retrieval
        ↓
consolidation
        ↓
semantic / procedural knowledge

这是一个非常合理的产品隐喻。

不要让每条 conversation 都直接进入 permanent memory。

1.9 “用户主动说这是重要的”是一个强 signal
【原文事实】

Tiago Forte 的 Building a Second Brain 主张：

capture only the most important information

并提出围绕：

recurring themes

questions repeatedly returned to

insightful/high-value information

future thinking usefulness

进行 capture。
Forte Labs

他还提出“keep only what resonates”，即用户自己认为与其关注的问题、目标有连接的东西。
Forte Labs

【推断】

对 Agent：

用户明确说：
“记住这个”
“以后所有项目都这样做”
“这是我的默认偏好”
“不要再问我这个”

应该几乎直接进入 candidate / permanent memory。

这属于：

explicit user signal

其权重应该高于 LLM 自己判断。

1.10 知识是否已经“显性化”
【原文事实】

Nonaka 1994 的 SECI 理论把知识创造描述为 tacit / explicit knowledge 之间持续转换，并强调组织对知识进行 articulation / amplification。
PubsOnline

Nonaka, I. (1994), "A Dynamic Theory of Organizational Knowledge Creation", Organization Science 5(1):14–37.

论文：A Dynamic Theory of Organizational Knowledge Creation

【推断】

对于你的系统，一个非常有价值的过程是：

用户/Agent的隐含经验
        ↓
提取
        ↓
显式表达
        ↓
验证
        ↓
可复用知识

比如用户长期说：

“这个东西我不喜欢做得太复杂……”

系统最终可以形成：

Design preference:
Prefer minimal architecture over premature abstraction.

但这里必须注意：

【不知道】

SECI 并没有给 Agent memory 一个“达到什么阈值就应该晋升”的算法。

2. 怎么识别“项目无关、可跨项目复用”的知识？

我认为这是整个系统里最值得单独设计的一层。

关键不是简单做：

project_id == null

而是识别：

这个知识的成立条件，是否依赖当前项目 / 当前环境？

2.1 一个非常实用的判据：Dependency Footprint

我建议给每条 memory 建一个：

dependency_footprint

表示它依赖哪些上下文。

例如：

Knowledge:
“SQLite 多线程写入容易产生 database locked”


dependency:
  technology = SQLite
  concurrency_model = concurrent writers
  project = none
  machine = none

那么它是：

technology-scoped reusable knowledge

而：

“LensDiary 当前用 SQLite + sqlite-vec”

则：

project = LensDiary
technology = SQLite

属于：

project knowledge

2.2 我建议把“项目内 / 跨项目”做成连续谱，而不是二分类

例如：

                    Generality
                        ↑
                        |
      User principle   |   “我喜欢简单架构”
                        |
      Domain knowledge |   “SQLite WAL适合读多写少”
                        |
      Tech knowledge   |   “sqlite-vec支持向量检索”
                        |
      Project pattern  |   “LensDiary用sqlite-vec”
                        |
      Environment      |   “我这台M4 Air没有GPU”
                        |
      Ephemeral        |   “今天这个terminal报错”
                        |
                        +----------------→
                         dependency on context

这比：

project = true/false

有用得多。

2.3 可以操作化成 5 个 dependency signals

我会建议每条 memory 自动计算：

① Project dependency

是否出现：

project name
repository
feature name
ticket
specific architecture

例如：

“LensDiary 的 Story Detection 使用 GPS 40%”

明显 project-specific。

② Environment dependency

是否依赖：

OS
hardware
machine
filesystem
network
installed packages
credentials
deployment topology

例如：

“MacBook M4 Air 上 CLIP 推理很慢”

不是跨项目知识。

但：

“CPU-only 环境下大规模 embedding 应采用 batch + background processing”

可能可以抽象成跨项目知识。

③ Temporal dependency

例如：

“现在 roadmap 是先做 face clustering”

高度 temporal。

而：

“face clustering 应先解决 false merge，再优化 recall”

可能成为 stable engineering principle。

④ Entity dependency

如果 knowledge 必须知道：

LensDiary
OpenCode
某个具体服务器
某个具体客户

才能理解，则 generality 较低。

⑤ Abstraction level

这是最重要的。

比较：

A:
OpenCode session #123 的 context compression 出现问题


B:
LLM agent 的 context compression 需要处理 memory hierarchy


C:
长上下文 agent 应区分 episodic memory 和 reusable semantic memory

B/C 更容易跨项目复用。

2.4 一个非常有价值的信号：Cross-project transfer

2026 年 Hu et al. 的研究恰好给了这个方向较直接的支持：

他们发现，abstract procedural memories 比 detailed trajectories 更容易产生 positive transfer。
arXiv

【推断】

所以你可以定义：

transferability =
    P(memory 在另一个 project/task 中有用)

实际系统里可以观察：

memory A
 ↓
project 1 被使用
 ↓
project 2 被使用
 ↓
project 3 被使用

如果同一个 memory 在多个 project 中被成功 retrieval：

它是极强的跨项目知识证据。

甚至比 LLM classifier 更可靠。

2.5 因此我会设计两个完全不同的 promotion pipeline
Project Memory
raw event
 ↓
project fact
 ↓
project decision
 ↓
project state
 ↓
project history

例如：

LensDiary 使用 InsightFace buffalo_m。
General Knowledge
raw event
 ↓
observation
 ↓
pattern
 ↓
generalized insight
 ↓
cross-project knowledge

例如：

Face recognition pipelines should separate detection,
quality filtering, embedding, and clustering because
errors in early stages propagate nonlinearly downstream.

这两个 pipeline 不应该混为一个“memory extraction”。

3. “重复输入 / 再获取成本”有没有文献里的可操作近似？

这里是我认为最有意思的地方。

简短答案

有相当接近的理论，但没有一个经典研究直接提出你这个完整公式。

你的：

memory value
≈
future reuse probability × cost of forgetting

可以从三个成熟方向得到支持：

Information Foraging

Retrieval / reuse frequency

LLM memory retrieval / task utility

3.1 Information Foraging Theory
【原文事实】

Pirolli & Card 1999 的 Information Foraging Theory 把信息搜索理解成一种“寻找有价值信息”的过程。

核心思想是：

人会调整信息搜索策略，以最大化获得有价值信息的 rate。

ResearchGate

论文：

Pirolli, P., & Card, S. K. (1999). "Information Foraging." Psychological Review, 106(4), 643–675.

【推断】

这几乎可以直接映射到 Agent：

重新获取知识的成本
=
search cost
+ reading cost
+ reasoning cost
+ verification cost

所以：

一个 memory 如果能够避免一次昂贵的信息搜索，它的价值就很高。

例如：

忘记：
“项目为什么选择 SQLite？”


重新获取：
搜索 Git history
→ 找 PR
→ 找设计讨论
→ 阅读 20 分钟
→ 重新推理

那么这个 memory 的 value 很高。

而：

忘记：
“某个临时变量叫 foo”

几乎没有 retrieval cost。

3.2 你的“重复输入成本”可以进一步拆成 Cost of Re-acquisition

我建议产品里不要只记录：

reuse_count

而是记录：

reacquisition_cost

可以粗略定义：

C_reacquire
=
C_user_input
+
C_search
+
C_read
+
C_reason
+
C_verify

例如：

Memory	忘记后的成本
用户喜欢 dark mode	重新问一句
项目使用什么数据库	查 repo
为什么选择 SQLite	查 Git history + 重新分析
某个复杂 bug 的 root cause	重新实验
3.3 Reuse Frequency 是最容易落地的 proxy
【原文事实】

知识管理研究中，knowledge reuse frequency 确实被作为可观测变量研究。比如相关组织知识研究会把：

knowledge reuse frequency

knowledge reuse lag

作为时间维度变量。
MagTech

另外，Agent memory 的近期研究也开始直接研究 experience reuse 和 transfer。
arXiv

【推断】

所以你的系统完全可以直接统计：

reuse_count
reuse_count_7d
reuse_count_30d
reuse_count_cross_project
reuse_success_rate

其中：

cross_project_reuse_count

尤其重要。

3.4 Future citation probability

这个概念虽然不是一个统一的经典 memory metric，但可以自然定义：

P(reuse | future task)

实际系统可以用历史行为估计。

例如：

P(reuse)
=
# future queries successfully using memory
/
# eligible future queries

实际在线系统里可以做得更简单：

retrieved
   ↓
actually used
   ↓
helped answer/action

形成：

retrieval_rate
usage_rate
utility_rate
3.5 最重要的一个指标：Miss Cost

我甚至认为：

“忘记它会多花多少钱？”

比：

“它重要不重要？”

更适合你的产品。

定义：

miss_cost(x)
=
expected_cost_if_memory_is_absent

例如：

memory:
“用户明确要求所有项目优先 local-first”


miss_cost:
高

因为每次新项目都可能重新问。

3.6 可以得到一个非常实用的 Memory Value 模型

注意：

下面这个公式是我的工程推断，不是某篇论文提出的公式。

我建议：

Memory Value


= P(reuse)
× Cost(reacquisition)
× Transferability
× Reliability
× Stability

然后扣掉：

Maintenance Cost
+
Wrong Memory Risk
+
Retrieval Cost

即：

V(memory)
=
P(reuse)
× C(reacquire)
× T
× R
× S
-
C(maintain)
-
C(false_memory)
-
C(retrieval)

这比单纯：

importance_score

强很多。

4. 最后，把整个问题压缩成一个 Memory Promotion Framework

如果让我给这个 Agent memory 系统设计第一版，我不会让 LLM 直接决定：

“保存 / 不保存”。

而是做 三级 memory lifecycle：

                    ┌──────────────┐
                    │   Interaction │
                    └──────┬───────┘
                           ↓
                  ┌─────────────────┐
                  │ Episodic Memory │
                  │  原始经历/事实   │
                  └────────┬────────┘
                           ↓
                 consolidation signals
                           ↓
          ┌────────────────┴────────────────┐
          ↓                                 ↓
   Project Knowledge                 General Knowledge
          ↓                                 ↓
   project fact/decision          reusable pattern/principle
          ↓                                 ↓
          └──────────────┬──────────────────┘
                         ↓
                   Long-term Memory

然后每个 candidate memory 至少有这些字段：

content


scope:
  project
  domain
  user
  environment
  global


dependency_footprint:
  project
  environment
  technology
  person
  time


importance
relevance
recency


reuse_count
cross_project_reuse_count


estimated_reacquisition_cost


confidence
evidence_count
stability


abstraction_level
transferability


last_used_at
last_verified_at
5. 我认为最值得采用的 Promotion 判据

最终可以浓缩成 7 个问题：

P1. 未来还可能用吗？
Future Relevance

来源：Park et al. 2023。
arXiv

P2. 忘掉它，重新获取贵吗？
Reacquisition Cost

来源：Information Foraging 理论提供理论基础。
ResearchGate

P3. 它是否已经被重复使用？
Reuse Frequency

来源：retrieval practice / knowledge reuse literature。
科学直接
+1

P4. 它能否脱离原项目成立？
Transferability

近期 Agent continual-learning 研究尤其支持这一点：抽象经验比具体 trajectory 更容易 transfer。
arXiv

P5. 它是否已经从“事实”变成“知识”？
Observation
   ↓
Pattern
   ↓
Generalized insight

来源：Park reflection + DIKW/knowledge-creation tradition。
arXiv
+1

P6. 它是否可靠、稳定、可验证？
Evidence
Confidence
Stability

DIKW 的后续 evidence-oriented 工作尤其强调 relevance、robustness、repeatability、reproducibility。
PubMed Central (PMC)

P7. 它是否是一个独立、可复用的知识单元？
Atomicity

来源：Zettelkasten。
Zettelkasten
+1

6. 一个我认为特别重要的结论

你的产品价值锚点其实可以进一步修正成：

Memory 的价值不是“信息本身有多重要”，而是“保存它能为未来决策/行动节省多少成本”。

也就是：

                ┌─ future reuse probability
                │
Memory Value ───┼─ reacquisition cost
                │
                ├─ transferability
                │
                └─ reliability

而这意味着：

“项目现状”本身也可以是非常高价值的 memory。

例如：

“当前 LensDiary 的 Story Detection 经常产生 incoherent stories。”

它并不跨项目，但价值可能非常高，因为：

P(reuse in this project) ≈ 很高
C(reacquire) ≈ 高

所以：

跨项目性不是 memory value 的必要条件。

它只是决定：

memory scope / promotion destination

而不是决定：

是否值得记住

这是我认为这套系统最应该抓住的一个设计原则。

7. 哪些地方目前应该明确标成“未知”

为了避免把理论包装成“科学已经证明”，以下几件事我建议在产品设计文档里明确写成【不知道】：

没有公认的 memory promotion 阈值
例如 reuse_count >= 3 并不是认知科学结论。

没有公认的 Agent memory value 公式
P(reuse) × reacquisition_cost 是非常合理的工程模型，但不是经典理论中的标准公式。

没有证据证明“跨项目 = 更有价值”。
它只意味着更高的 transferability；一个高度 project-specific 的 memory 也可能极其有价值。

没有证据证明 LLM 自己判断 importance 比行为信号更可靠。
相反，近期工作已经开始发现 write-time salience 与 future query utility 之间存在错位问题；2026 年 MemSIF 明确把这种现象称为 Delayed Utility Manifestation，并采用 recurring query demand 来支持 memory promotion。
arXiv

consolidation 不能直接等价于“LLM summary”。
人类记忆 consolidation 是神经生物学过程；把它映射成 Agent 的 summarize/promote，是架构类比，而非已经验证的等价机制。
Nature
+1

如果把它进一步变成产品规则

我会采用：

                 RAW / EPISODIC
                       │
                       ▼
              ┌────────────────┐
              │ Candidate Fact │
              └───────┬────────┘
                      │
        ┌─────────────┼─────────────┐
        ↓             ↓             ↓
   Future Use     Miss Cost     Reliability
        │             │             │
        └─────────────┼─────────────┘
                      ↓
                 PROMOTION
                      │
          ┌───────────┴───────────┐
          ↓                       ↓
   PROJECT MEMORY          REUSABLE KNOWLEDGE
          │                       │
   当前项目继续使用          跨项目复用

而且不要在第一次出现时就要求 LLM 判断它是不是“长期知识”。

更好的设计是：

先低成本捕获 → 通过后续行为获得证据 → 再 consolidation → 再 promotion。

这其实同时吸收了 Generative Agents 的 reflection、认知科学里的 consolidation、Zettelkasten 的 atomicity、Forte 的 selective capture，以及近期 LLM memory 对“future utility / experience reuse”的研究。
arXiv
+4
arXiv
+4
Nature
+4

如果只让我选一个最核心的产品指标，我会选：

Expected Avoided Reacquisition Cost（预期避免的再次获取成本）

因为它最直接对应你定义的产品价值，而且最终可以通过真实的 agent 行为数据不断校准，而不是依赖一个“看起来很聪明”的 LLM importance classifier。