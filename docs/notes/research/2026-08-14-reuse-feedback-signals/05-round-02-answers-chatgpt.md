# round-02 · ChatGPT 回答原文

> 执行日期: 2026-08-14 · 会话: round-01 同一会话内继续追问 · 平台画像: 系统性强、会主动重构自身方案
> 提示词: [04-round-02-prompts.md](04-round-02-prompts.md) ChatGPT 追问块（原文回填，未二次概括）

---

这三个问题其实互相咬合。我上一轮如果再往前推一步，会把之前的“五状态机”稍微改造一下：

状态不应该是第一等公民，证据才是。

Useful / Irrelevant / Stale / Wrong / Harmful 更像是由证据推导出来的 operational state，而不是系统直接观察到的事实。

尤其对于开发 Agent，真正可靠的单位应该是：

Memory × Context × Retrieval Set × Action × Outcome

而不是单独一条 memory。

下面分别回答。

1. 状态转移阈值：我不建议用固定“累计 N 次”

如果直接规定：

negative evidence ≥ 3 → stale
harmful evidence ≥ 2 → harmful

我认为很容易翻车。

因为不同 evidence 的强度差异巨大：

一次用户明确纠正

和

一次 Agent 没用到

显然不能算同样的一票。

所以我建议把证据分成 evidence strength，再做 Bayesian / Beta-Bernoulli 式累计。

1.1 先把 evidence 分级

我会大致这么设计：

Evidence	方向	强度
被召回	中性	0
没被提及	中性	0
被提及	正	0.2
被用于 plan	正	0.4
导致相关 action	正	0.6
action 后测试改善	正	0.8
用户明确表示有用	正	1.0
用户明确纠正	负	-1.0
与当前代码/环境事实冲突	负	-1.0
依据该 memory 导致失败	负	-1.0
依据该 memory 产生错误修改并被回滚	负	-1.2

这些数字不是文献里的标准值，是我的工程建议。

重点不在 0.6 还是 0.7，而在于：

不同观察的证据强度必须不同。

这和推荐系统 / implicit feedback 的经验是一致的：行为信号往往是稠密但有噪声，而显式反馈稀疏但可靠；不能把所有 implicit signal 当成同等强度的 ground truth。
RecSys
+1

1.2 我更推荐维护“置信度”，而不是维护状态

例如：

M123


useful:
  α = 8.4
  β = 1.7


correct:
  α = 12.2
  β = 0.8


harmful:
  α = 0.2
  β = 2.1

于是：

P(useful)
P(correct)
P(harmful)

都是 posterior。

实际实现甚至不需要复杂 Bayesian inference，Beta-Bernoulli 就够 V1：

P(p∣data)=Beta(α,β)

每次事件：

positive → α += evidence_weight
negative → β += evidence_weight
1.3 但我会加一个更重要的东西：Evidence Freshness

因为 memory 有一个典型问题：

5 年前正确，不代表今天正确。

所以：

evidence(t)

最好有时间衰减。

例如：

w
t
	​

=e
−λΔt

于是：

两年前：
"项目用 Node 18"

对今天的 correctness posterior 影响自然逐渐下降。

但是这里又不能对所有 memory 使用统一 decay。

例如：

“这个项目使用 InsightFace buffalo_m”

可能随项目生命周期变化。

而：

“用户喜欢用 TypeScript”

可能应该长期保留。

所以 decay rate 本身也应该是 memory-type dependent。

这和 concept drift / continual learning 中的思路相近：旧证据不能永久具有相同权重，而且显式 drift detector 很容易产生 false alarm，因此实际系统常常采用隐式权重衰减/模型更新。
arXiv

1.4 那到底什么时候从 Useful → Stale？

我的建议不是：

negative evidence ≥ N

而是：

普通 negative evidence

不能直接进入 Stale。

例如：

M123 被召回 20 次
只有 2 次真正用到

这最多说明：

retrieval usefulness questionable

不要碰 memory correctness。

强 negative evidence

例如：

Memory:
项目使用 Node 18


Environment:
Node 24


Agent:
因此使用 Node 18


Build:
ERROR: requires Node >= 22

这是：

contradiction = strong

可以直接：

M123.status = SUSPECT_STALE

甚至暂时 suppress。

用户明确纠正

例如：

“这个已经不对了，我们两个月前已经改掉了。”

这应该是最高等级之一：

status → STALE

不需要等 10 次证据。

因为这里不是统计推断，而是直接观测 ground truth。

1.5 Harmful 应该比 Stale 更谨慎

我现在会把上一轮的五状态稍微修正：

Useful
Irrelevant
Stale
Wrong
Harmful

实际上：

Harmful 不是 Wrong 的一个普通子类。

它意味着：

Memory→Decision→Negative Outcome

也就是说需要一定程度的 causal attribution。

例如：

M123:
不要使用 async


Agent:
因为 M123，删除 async


Test:
失败


Agent:
revert

这个才有资格叫：

Harmful

而：

M123 是错的

只是：

Wrong

我甚至会建议：

WRONG:
事实不正确


STALE:
过去正确，现在不再适用


HARMFUL:
被错误采用后产生负面后果

这是三个不同维度。

1.6 冷启动：宁愿“不知道”，不要误判

这里我特别赞成你提的：

“证据稀疏怎么办？”

答案是：

增加 Unknown / Uncertain

而不是强行五分类。

实际上：

Useful
Irrelevant
Stale
Wrong
Harmful

上面应该再有：

          ┌────────────┐
          │  UNKNOWN   │
          └────────────┘

一条新 memory：

retrieval = 1
use = 0

正确状态不是：

Irrelevant

而是：

Unknown
confidence = 0.31

这对冷启动非常重要。

2. 怎么分开“retrieval policy 错”还是“memory 内容错”？

这是三个问题里我认为最重要的一个。

我给你一个非常实用的判定框架：

不要根据“这次没用”判断。

要观察 memory 在“应该使用它的 context”中的表现。

2.1 先区分两个概率

你真正要学习的是：

P(Useful∣M,C)

和：

P(Retrieve∣M,C)

第一个属于：

Memory Content

第二个属于：

Retrieval Policy

举个例子

Memory：

“SQLite 多 writer 曾经导致 database locked。”

当前 context：

“修改 SQLite ingestion pipeline。”

这时：

P(Useful | M,C) 很高

如果 retrieval 没把它召回：

retrieval policy 有问题

但如果：

Context:
修改 CSS button

没用到 SQLite memory：

不能说明 memory 有问题

甚至：

retrieval system 根本不应该召回它。

2.2 一个非常实用的自动判定规则：找“机会窗口”

我会定义：

Memory Applicability Window

即：

Memory M
什么时候本来就应该有机会发挥作用？

例如：

M:
"SQLite 多 writer 会 database locked"


Applicability:
- 修改 SQLite 写入
- 修改 worker concurrency
- ingestion pipeline
- database transaction

如果：

context ∈ applicability

那么没用到 M 才具有负反馈意义。

如果：

context ∉ applicability

那么：

ignore = neutral
2.3 这个 applicability 不需要人工维护

可以让模型在 memory 创建时自动生成：

JSON
{
  "memory": "SQLite 多 writer 曾导致 database locked",
  "applies_when": [
    "SQLite concurrency",
    "worker count",
    "database writes",
    "ingestion pipeline"
  ],
  "does_not_apply_when": [
    "frontend CSS",
    "read-only query"
  ]
}

但我不会完全相信它。

随着 trajectory 收集：

actual useful contexts

再反过来修正：

applies_when

这实际上形成了：

Memory 的“使用条件”也是可以学习的。

2.4 最强的自动判定方法：相似 Context 对照

假设 M123：

SQLite locking memory

历史上出现：

Context A:
修改 SQLite worker
→ M123 retrieved
→ used
→ success


Context B:
修改 SQLite worker
→ M123 retrieved
→ ignored
→ success


Context C:
修改 SQLite worker
→ M123 NOT retrieved
→ failed

这时候：

C 很像 retrieval failure

因为：

same type of context
M123 missing
→ outcome worse
B 不足以证明 memory 无用

因为：

same context
M123 retrieved
→ ignored
→ still success

所以：

“没使用”只是弱 negative evidence。

2.5 最理想的训练数据其实是这种
Context cluster #42


              M123 retrieved    M123 absent
--------------------------------------------
Task A             success          fail
Task B             success          success
Task C             success          fail
Task D             fail             success

你会发现：

M123:
probably useful

但：

retrieval policy:
should retrieve M123 in context cluster #42

可以独立学习。

这就是为什么我认为：

Memory quality 和 retrieval policy 必须有两个独立的 posterior。

2.6 不依赖人工，能不能做？

可以，而且我认为 V1 就应该做。

建立一个自动 evaluator：

Task
Context
Retrieved memories
Agent trajectory
Outcome

让 evaluator 输出：

JSON
{
  "memory_id": "M123",


  "applicable": true,
  "adopted": false,
  "should_have_been_used": true,


  "content_correct": true,
  "retrieval_failure": false,
  "memory_failure": false,


  "confidence": 0.78
}

这里尤其重要的是：

should_have_been_used

它不是：

“Agent 有没有用？”

而是：

“在这个 context 中，一个理想 Agent 是否应该利用它？”

这两个完全不同。

3. 但第三个问题其实推翻了“单 memory event”

你问：

整组 memory 一起注入，单条 attribution 会不会崩？

会。

而且我认为这不是小问题，是设计 Memory Event Schema 时必须解决的问题。

3.1 为什么单条 attribution 天然不可靠？

例如一次 retrieval：

[M1, M2, M3, M4, M5]

全部一起注入。

Agent 最后：

修改 worker count

你说：

M3 caused this

凭什么？

可能：

M1 提供事实
M2 提供背景
M3 提供具体方案
M4 只是重复 M3
M5 完全没用

甚至：

M2 + M3

必须一起出现才有意义。

这就是典型的：

redundancy / complementarity / synergy

RAG attribution 的研究也正面遇到这个问题：单文档 attribution 很难处理 retrieved documents 之间的冗余、互补和协同；Shapley-style attribution 虽然理论上更合理，但计算成本很高。
arXiv

而近期研究也发现，即使回答能够被“grounded”，仍可能出现 attribution 错配问题，所以“有引用”本身不能证明某个具体 source 真正承担了因果作用。
arXiv

3.2 所以我建议增加 Group 层

最终 schema 我会设计成：

Task
 └── RetrievalEvent
       └── MemoryGroup
             ├── Memory M1
             ├── Memory M2
             ├── Memory M3
             └── Memory M4
                    ↓
                  Agent
                    ↓
                  Actions
                    ↓
                 Outcome

注意：

Group 不是 Memory 的永久属性。

它是：

一次 retrieval / injection 产生的临时集合。

3.3 也就是说 Memory 和 MemoryGroup 是两个完全不同的对象
Memory

长期实体：

M123
content
created_at
validity
confidence
MemoryGroup

一次使用事件：

G789


query:
"SQLite worker concurrency"


memories:
[M123, M456, M891]


injection:
system_context


token_budget:
1200


rank:
M123 > M456 > M891

然后：

G789
 ↓
Agent trajectory
 ↓
Outcome

这样就能保留：

group-level evidence

3.4 我甚至建议 Event Schema 变成三层

不是：

MemoryEvent

而是：

Task
  ↓
Memory Retrieval Event
  ↓
Memory Group
  ↓
Memory Items

具体：

JSON
{
  "task_id": "T42",


  "retrieval_event_id": "R17",


  "query": "...",


  "group": {
    "id": "G9",
    "memories": [
      {
        "memory_id": "M1",
        "rank": 1,
        "score": 0.91
      },
      {
        "memory_id": "M2",
        "rank": 2,
        "score": 0.86
      },
      {
        "memory_id": "M3",
        "rank": 3,
        "score": 0.79
      }
    ]
  },


  "outcome": {
    "success": true
  }
}

然后后处理再生成：

Group usefulness = strong evidence
M1 usefulness     = weak evidence
M2 usefulness     = weak evidence
M3 usefulness     = weak evidence

这是一个非常重要的原则：

证据天然首先属于 Group，只有在有额外 attribution 证据时，才下沉到 Item。

3.5 这会让你们的 Bayesian 更新更合理

比如：

G1:
[M1,M2,M3]
→ success


G2:
[M1,M2,M3]
→ success


G3:
[M1,M2,M3]
→ success

你只能说：

P(group useful) ↑

而不能说：

P(M1 useful) ↑↑
P(M2 useful) ↑↑
P(M3 useful) ↑↑

否则就是典型的：

credit leakage

把 group 的 credit 平摊给所有成员。

3.6 那什么时候才把 Group credit 分给 Memory？

我会设置几个自动 attribution signal。

Signal A：Explicit mention

Agent：

“根据之前关于 SQLite locking 的记录……”

→ 对应 M123。

强度高。

Signal B：Action semantic match

Memory：

max_workers=1

Action：

Diff
- max_workers=4
+ max_workers=1

→ M123。

强度高。

Signal C：独特信息

Group：

M1: SQLite uses WAL
M2: previous lock issue was caused by writers
M3: project uses Python

Agent：

“这里应该避免多个 writer。”

明显更可能来自 M2。

Signal D：Counterfactual

这是最强的：

Group:
[M1,M2,M3]


remove M2
→ task fails


remove M1
→ task succeeds


remove M3
→ task succeeds

那么：

M2 = high causal credit
3.7 V1 不需要真的做 Shapley

虽然理论上：

ϕ
i
	​

=
S
∑
	​

n!
∣S∣!(n−∣S∣−1)!
	​

[U(S∪i)−U(S)]

可以计算每个 memory 的 marginal contribution。

但在 Agent 中：

太贵。

而且 LLM outcome 本身还有 stochasticity。

我建议 V1 只做：

Group-level attribution

100%：

retrieval group → outcome
Item-level attribution

只在有明显证据时：

explicit mention
semantic action match
contradiction
user correction
Item ablation

只对：

high-value memory
uncertain memory
frequently retrieved memory

抽样做。

这已经足够形成非常有价值的数据。

4. 这三个问题合起来，我会把 V1 Schema 改成这样

上一轮我给你的：

retrieved
mentioned
used_in_plan
linked_actions
task_success

还是太扁平。

我现在会改成：

Task
│
├── Context snapshot
│
├── RetrievalEvent #1
│     │
│     └── MemoryGroup
│           ├── M1
│           ├── M2
│           └── M3
│
├── RetrievalEvent #2
│     │
│     └── MemoryGroup
│           ├── M4
│           └── M5
│
├── Agent decisions
│
├── Actions / diffs / tests
│
└── Outcome

然后每一层承担不同职责：

层	主要回答
Task	最终成功了吗？
RetrievalEvent	为什么/什么时候召回？
Group	这一批 memory 整体有没有帮助？
Memory Item	哪一条可能贡献/错误？
Action	实际做了什么？
Outcome	结果怎样？
5. 我会特别增加一个字段：counterfactual_status

例如：

M123
counterfactual_status:
  unknown

以后经过 ablation：

M123
counterfactual_status:
  positive

或者：

M123
counterfactual_status:
  neutral

甚至：

M123
counterfactual_status:
  harmful

这样你们的数据里会天然区分：

observational evidence

和：

causal evidence

这一点我认为非常重要。

6. 最终我会把“Memory 状态机”改成“两个 posterior + 一个 lifecycle”

这是我对上一轮方案最大的修正。

不要：

Memory
 ↓
Useful / Stale / Harmful

而是：

                  Memory
                    │
        ┌───────────┴───────────┐
        ↓                       ↓
 Content posterior       Retrieval posterior
        │                       │
 correctness              P(useful | context)
 staleness                P(retrieve | context)
 harmfulness
        │                       │
        └───────────┬───────────┘
                    ↓
               Lifecycle
                    │
       active / uncertain / stale /
       suppressed / superseded

这样三个问题就全部被解耦了：

“它是不是好记忆？”

→ Content posterior

“这次为什么没用？”

→ Retrieval posterior + applicability

“这一组 memory 到底有没有帮助？”

→ Group-level outcome

“某一条到底贡献了多少？”

→ Item attribution / ablation

7. 如果让我定具体 V1 规则，我会这么做

非常具体地说：

新 memory
status = uncertain

不因为一次 retrieval/no-use 改状态。

每次 retrieval

记录：

RetrievalEvent
  └── MemoryGroup
        └── Items
每个 Task 结束

自动产生：

group_relevance
group_outcome

这是最可靠的第一层反馈。

Item 只有出现以下情况才更新较强 evidence
+ explicit mention
+ plan dependency
+ action semantic match
+ test/outcome correlation


- explicit correction
- environment contradiction
- caused failed action
- reverted change
只有 strong evidence 才允许：
uncertain → stale
uncertain → wrong
uncertain → harmful

而：

retrieved but unused

永远不直接触发 stale/wrong/harmful。

最多：

retrieval_usefulness ↓
Group-level success 不直接给所有 Item 加分

这是我现在认为最重要的一条：

Group success = group evidence，而不是 item evidence。

否则你们的数据很快会出现：

一个 20 条 memory 的 context
→ task success
→ 20 条 memory 全部 usefulness +1

半年后整个 memory store 都会变成“看起来很好”。

8. 一个更深的结论

这其实把你们的问题从：

“Memory 是否有用？”

变成了一个很典型的：

Partial observability + credit assignment + selection bias

问题。

你看不到：

Agent 内部到底用了哪条 memory

所以是 partial observability。

多条 memory 一起注入：

M1 + M2 + M3 → outcome

所以是 credit assignment。

而只有被 retrieval 的 memory 才有机会表现：

retrieved → observed outcome

所以又存在 selection bias。

因此：

“一次被召回但没用”不能直接当 negative label。

这和推荐系统里“没点击 ≠ 不相关”是同一个结构性问题；implicit feedback 天生存在 presentation / selection bias。
SIGWEB
+1

而你们真正有价值的地方是：coding agent 有大量可观测的 downstream action 和 test outcome，所以比普通推荐系统更有机会做 attribution。

近期的 MemCon 工作甚至直接把 memory management 建模成 contextual online policy，并用 task-level binary feedback 学习 retrieval / consolidation / forgetting policy；它报告无需额外 LLM call 也能用 contextual bandit 学到 adaptive memory policy。
arXiv
 这其实非常支持你们把“内容质量”和“检索策略”拆开，而不是继续用一个 memory score 解决所有问题。

如果只让我给一个最终架构，我会选这个
                         ┌──────────────────┐
                         │   Memory Store   │
                         └────────┬─────────┘
                                  │
                              retrieval
                                  ↓
                         ┌──────────────────┐
                         │ Retrieval Event  │
                         └────────┬─────────┘
                                  │
                         ┌──────────────────┐
                         │   Memory Group   │
                         │ M1 M2 M3 M4 M5  │
                         └────────┬─────────┘
                                  │
                                  ↓
                              Agent
                                  │
                   ┌──────────────┼──────────────┐
                   ↓              ↓              ↓
                 Plan           Action          Diff
                   │              │              │
                   └──────────────┼──────────────┘
                                  ↓
                             Tests / Outcome
                                  │
                                  ↓
                         ┌──────────────────┐
                         │    Evaluator     │
                         └────────┬─────────┘
                                  │
               ┌──────────────────┼──────────────────┐
               ↓                  ↓                  ↓
        Group evidence      Item attribution    Retrieval evidence
               │                  │                  │
               ↓                  ↓                  ↓

V1 真正应该存的不是一个 usefulness_score，而是一串可重新解释的 evidence。

因为今天你认为：

“没有使用 = negative”

明天你可能发现：

“原来这是 retrieval policy 的问题。”

如果你存的是：

score = -0.3

这次错误判断基本无法恢复。

但如果你存的是：

retrieved = true
mentioned = false
applicable = uncertain
group_success = true
item_attribution = unknown

以后模型升级了，你仍然可以重新解释历史事件。

这点我认为是整个系统设计里最值得提前做对的地方。
