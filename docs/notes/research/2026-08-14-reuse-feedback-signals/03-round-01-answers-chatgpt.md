# round-01 · ChatGPT 回答原文

> 执行日期: 2026-08-14 · 会话: 新会话（无预设同题） · 平台画像: 系统性强、会主动重新定义问题
> 提示词: [02-round-01-prompts.md](02-round-01-prompts.md) 同一开放题（原文回填，未二次概括）

---

我认为这个问题非常关键，而且我会先把你们的问题重新定义一下：

不要试图直接判断“这条记忆有没有被采纳”。真正应该估计的是：在某个任务上下文中，这条记忆对最终任务结果产生了多大的增量价值。

“被召回”“被模型看到了”“被模型提到了”“被模型用了”“帮助完成任务”其实是五个不同层次。

这一区分一旦建立起来，整个记忆反馈系统会清晰很多。

1. 我认为最核心的模型：Memory → Retrieval → Use → Outcome

可以把一次记忆生命周期看成：

Memory
  ↓
Retrieved
  ↓
Exposed to Agent
  ↓
Considered
  ↓
Used / Ignored / Rejected
  ↓
Influenced Action
  ↓
Influenced Outcome

而你们真正关心的是最后两步。

例如：

记忆：SQLite 使用 WAL + 单 worker，否则容易 database is locked

这条记忆被召回了。

可能发生：

A. 真正有用

Agent：

“这里 SQLite 有并发写入，我应该避免多个 writer。”

然后修改代码。

测试通过。

这显然是高价值记忆。

B. 被看到但没用

Agent 看到了，但发现当前代码根本没有并发写。

于是完全没用它。

这是召回正确，但当前无用。

C. 被错误使用

Agent 看到：

“SQLite 必须单 worker。”

然后把一个本来可以并发读取的 pipeline 也改成单 worker。

结果性能下降。

这是非常危险的：

记忆被采纳 ≠ 记忆有价值。

D. 记忆没有被显式使用，但实际上帮助了

Agent 看到了：

“之前这个项目用了 WAL。”

之后它自然设计出兼容 WAL 的方案。

Trace 中可能完全没有写：

“我使用了 memory #123。”

但它可能确实产生了影响。

这也是为什么**“模型是否提及 memory”不是最终指标**。

2. 所以我建议你们把“memory usefulness”拆成 4 个指标

我会定义：

U(m,c)=R(m,c)×A(m,c)×V(m,c)×O(m,c)

其中：

R — Retrieval relevance：这条记忆对当前上下文是否相关

A — Adoption：Agent 是否实际采用了它

V — Validity：它是否正确

O — Outcome impact：它是否改善了任务结果

但这里不是简单乘法，工程上我更倾向于把它们作为独立维度保存。

也就是说，一条 memory 不应该只有：

score = 0.87

而应该逐渐形成：

memory #123


retrieval_relevance: 0.91
adoption:           0.72
correctness:        0.96
outcome_impact:     0.61


confidence:
  retrieval: high
  adoption: medium
  correctness: high
  outcome: low

这是我认为你们整个系统最重要的设计方向。

3. 第一层：最便宜的信号——“它被召回后发生了什么”

这层成本极低，我强烈建议全部采集。

Signal 1：是否被引用 / 提及

例如 memory：

[M123]
项目使用 SQLite + sqlite-vec

Agent 后续产生：

“因为项目使用 sqlite-vec，所以这里继续沿用 SQLite……”

那么：

M123 → referenced

这是一个弱正信号。

但不要把它当成“有用”的证明。

因为 LLM 很容易为了合理化而提及上下文。

Signal 2：是否进入 Agent 的 working plan

例如让 agent 内部产生：

Relevant memories:
- M123: SQLite uses sqlite-vec
- M456: previous implementation had database locking


Plan:
1. Keep sqlite-vec
2. Avoid concurrent writers

那么 M456 的 adoption confidence 比单纯“出现在 context 里”高很多。

Signal 3：Memory → Action 对齐

这个信号比“引用”强很多。

例如：

Memory:
"InsightFace buffalo_m is used for face recognition."


↓


Agent action:
load buffalo_m

或者：

Memory:
"SQLite concurrent writers caused database locked."


↓


Agent action:
change max_workers=4 → max_workers=1

这时候可以形成：

memory → decision → tool/action

这是非常有价值的 attribution signal。

4. 对开发 Agent 来说，你们拥有一个其他 Memory 系统没有的巨大优势

就是：

代码 Agent 的环境是可观测的。

这是我认为你们应该重点利用的地方。

普通 ChatGPT memory 很难判断：

“用户今天为什么回答得更好？”

但 coding agent 可以观察：

memory
 ↓
code change
 ↓
test
 ↓
build
 ↓
runtime
 ↓
git diff
 ↓
user acceptance

因此 coding agent 的 memory feedback 可以比普通个人助手精确得多。

5. Signal 4：Memory → Code Diff

这是我认为你们第一版就应该做的。

例如：

Memory #123


"项目使用 max_workers=1，因为 SQLite 曾出现 database is locked"

之后：

Diff
- ThreadPoolExecutor(max_workers=4)
+ ThreadPoolExecutor(max_workers=1)

系统可以通过 LLM / AST / semantic diff 判断：

这个修改与 memory #123 高度相关。

于是：

M123
  ↓
retrieved
  ↓
influenced code change

可以记：

JSON
{
  "memory_id": "123",
  "action": "code_change",
  "confidence": 0.87
}

这比让 Agent 自己说：

“我使用了 M123”

可靠得多。

6. Signal 5：Memory → Tool Action

代码 Agent 里还有很多非常好的信号。

例如 memory：

“这个项目使用 Python 3.12，不要用 Python 3.13，因为某依赖不兼容。”

然后 agent：

python --version
uv run python ...

或者：

修改 pyproject.toml

这些都可以建立 attribution。

同理：

Memory
 ↓
npm package version
 ↓
install
 ↓
build
 ↓
test
7. Signal 6：Memory → Test Outcome

这是比“用了”更重要的一级。

例如：

M123:
SQLite concurrent writes → database locked

Agent 因此修改代码。

然后：

pytest

从：

17 failed

变成：

0 failed

那么你们就获得了一个很强的：

Outcome-correlated usefulness signal

可以记录：

M123
retrieved = 1
used = 1
related_action = 1
test_improvement = +17

这已经非常接近真正的“价值”。

8. Signal 7：用户是否纠正了它

这个信号极其重要。

例如 memory：

“用户偏好使用 React。”

Agent：

“我们继续用 React。”

用户：

“不是，这个项目已经改成 Vue 了。”

那么：

M123 → explicit negative feedback

这是非常强的负信号。

甚至应该触发：

memory status:
  stale / contradicted

而不是仅仅：

score -= 0.1

因为这是内容正确性问题。

9. 我特别建议区分两种负反馈

这是很多 memory 系统容易混淆的地方。

“没用”

和

“有害”

完全不是一回事。

例如：

Memory A:
用户喜欢使用 pytest

今天没用到。

这是：

irrelevant

不是坏记忆。

而：

Memory B:
项目使用 Node 18

实际项目已经升级 Node 24。

Agent 根据这个记忆操作失败。

这是：

stale / false

应该强烈降权甚至废弃。

所以 memory 至少应该有：

useful
irrelevant
stale
wrong
harmful

而不是一个 usefulness score。

10. 最重要的信号：任务最终是否成功

最终还是要回到：

这个 memory 有没有增加 task success 的概率？

例如：

Task:
修复 sqlite locking 问题


Memory M123:
之前 sqlite locking 的解决方案

有 memory：

修复成功

没有 memory：

修复失败

那么才真正证明：

M123→TaskSuccess
11. 但这里出现一个非常重要的问题：相关 ≠ 因果

这是整个问题最难的地方。

假设：

召回 M123
↓
任务成功

不能说明：

M123 导致任务成功

因为 Agent 可能根本不需要它。

所以如果你们真的想知道：

“memory 到底有没有帮忙？”

最终需要某种反事实 / ablation。

12. 我认为最有价值的机制：Memory Ablation

例如一个任务：

Task #923

正常运行：

Memories:
M123
M456
M789

最终：

success

系统可以偶尔做：

shadow replay

或者：

A:
with M123


B:
without M123

比较：

success probability
time
tokens
tests
tool calls
quality

得到：

Impact(M123)≈P(success∣M123)−P(success∣¬M123)

这才是真正意义上的：

memory 的增量价值。

13. 但是不应该每次都做 ablation

成本太高。

我会设计成三级：

Level 1 — Implicit telemetry

100% 收集：

retrieved
referenced
action-linked
test-linked
user-corrected

成本：

几乎为 0

精度：

低～中

Level 2 — LLM attribution

对完成后的 trajectory 做一次分析：

哪些 memories 实际影响了决策？
哪些被忽略？
哪些导致了错误？

例如：

M123: strong positive
M456: irrelevant
M789: potentially harmful

成本：

低～中

精度：

中

但注意：

LLM judge 仍然只是另一个模型的解释，不是因果证据。

Level 3 — Counterfactual / A-B

只对：

高价值 memory

高不确定性 memory

新 memory

争议 memory

做：

with memory
vs
without memory

成本：

高

精度：

最高

我会把它当作校准系统，而不是日常主路径。

14. 还有一个非常漂亮的办法：让 Memory 自己“声明用途”

我比较推荐这个设计。

Memory 不只是：

SQLite 曾经 database locked

而是：

Memory:
SQLite 曾经因为多个 writer 导致 database locked。


When useful:
- 修改 SQLite 并发代码
- 增加并发 worker
- 调整数据库写入策略


Expected consequence:
- 避免 database locked


Evidence:
- 2026-07-xx incident #42

于是 memory retrieval 以后：

memory
 ↓
expected use
 ↓
actual action
 ↓
expected consequence
 ↓
actual consequence

就可以形成一个非常漂亮的闭环。

这其实已经不是传统的“知识库”了。

更像：

Experience → Prediction → Action → Outcome → Learning

15. 这也是我认为你们应该从“Memory Store”升级到“Memory Learning System”

很多 memory 产品基本是：

conversation
 ↓
extract memory
 ↓
vector DB
 ↓
retrieve
 ↓
prompt

这是一个单向管道：

Write → Read

你们现在遇到的问题，本质上是在要求：

Write
 ↓
Retrieve
 ↓
Use
 ↓
Act
 ↓
Observe outcome
 ↓
Evaluate memory
 ↓
Update memory
 ↓
Retrieve differently next time

也就是：

Memory 必须形成闭环，而不是一个被动数据库。

最近的一些工作其实也开始明确往这个方向走。例如 2026 年的 MemCon 将 memory management 建模成一个在线决策过程，根据任务反馈学习“什么时候取、取什么、取多少、什么时候 consolidation / forgetting”；论文报告只用任务级反馈也能学习 retrieval/management policy。
arXiv

MemToolAgent 也明确使用环境反馈和用户反馈，把错误执行反思成可以长期保存的 critique。
arXiv

这和你们现在碰到的问题其实高度一致。

16. 一个非常重要的启发：不要追求“绝对 usefulness”

信息检索领域几十年来其实已经遇到过类似问题：

用户点了搜索结果，是否说明结果相关？

答案是：

有信息，但有偏差。

Joachims 等人的研究发现，click 是有用的隐式 relevance feedback，但存在明显 bias；相对偏好通常比“绝对相关性”判断更可靠。
Penn State
+1

这对你们非常有启发。

不要问：

M123 usefulness = 0.73？

而应该更多问：

在相似任务中，M123 是否比 M456 更值得召回？

也就是说：

M123>M456

往往比：

M123=0.73

更容易可靠地学习。

17. 所以我会给每条 Memory 建立“经验统计”

例如：

Memory #123


content:
SQLite concurrent writers caused database locked


retrievals:
37


relevant:
29


ignored:
8


adopted:
21


successful_after_use:
18


harmful:
1


explicit_negative:
0


contradicted:
0


avg_task_success_delta:
+0.18


similar_tasks:
14


confidence:
0.91

再进一步：

contexts where useful:
- SQLite write concurrency
- ingestion pipeline
- batch processing


contexts where useless:
- read-only queries
- migration scripts

这比单纯 embedding + importance score 强很多。

18. 更进一步：Memory 的价值其实是“条件性的”

这是我认为你们之前做长期记忆价值公式时特别值得注意的一点。

不是：

Value(M)

而应该是：

Value(M∣Context)

例如：

“项目使用 SQLite”

这个记忆本身可能价值一般。

但：

Context:
正在设计数据库

价值很高。

而：

Context:
正在写前端 CSS

价值接近 0。

所以真正应该学习的是：

P(Useful∣Memory,Context)

而不是：

P(Useful∣Memory)

这也是为什么我认为memory 的“适用场景”应该成为一等公民。

19. 对你们的开发助手，我会特别采集这张表
信号	采集方式	成本	可信度
被召回	retrieval log	极低	★
被模型看到	context log	极低	★
被提及	trace / LLM	低	★★
被加入 plan	agent trace	低	★★★
对应代码修改	diff + semantic match	低	★★★★
对应 tool action	tool trace	低	★★★★
对应测试变化	test telemetry	低	★★★★
用户接受/修改	conversation + diff	低	★★★★
用户明确纠正	explicit feedback	极低	★★★★★
任务成功	environment	低	★★★★
memory 导致错误	trajectory analysis	中	★★★★
LLM attribution	post-hoc judge	中	★★★
A/B	replay	高	★★★★★
counterfactual	controlled execution	很高	★★★★★
20. 但我不会让用户频繁点击 👍 / 👎

这是一个很容易走偏的地方。

传统系统喜欢：

“这条记忆有用吗？👍 👎”

但开发 Agent 的使用频率太高。

如果每次：

Memory recalled:
[👍 有用] [👎 没用]

很快就会变成 UX 噪声。

信息检索研究也长期发现，显式 relevance feedback 虽然清晰，但用户通常不愿意持续承担额外反馈成本；implicit feedback 的优势正是可以在不增加交互负担的情况下大量采集。
科学直通车
+1

所以我建议：

80–95% 反馈自动采集，只有高价值/高不确定性节点主动问用户。

比如：

“你刚刚说之前那个方案已经失效了，要不要更新长期记忆？”

这个问题就非常值得问。

21. 我甚至会设计一种“Memory Failure Detector”

这可能比 usefulness scorer 更重要。

每次 Agent 失败后：

Task failed
 ↓
inspect retrieved memories
 ↓
有没有 memory 与错误决策相关？

例如：

M123:
Node 18


Agent:
使用 Node 18


Build:
requires Node >= 22

那么：

M123
→ retrieved
→ adopted
→ contradicted by environment
→ caused failure

这是一个非常强的 negative learning event。

可以自动触发：

M123.status = stale

甚至：

M123:
superseded_by = M456

于是长期记忆不是：

越来越多

而是：

不断进化
22. 我会把 Memory 状态机设计成这样
                ┌─────────────┐
                │   Candidate │
                └──────┬──────┘
                       ↓
                  Retrieved
                       ↓
              ┌────────┴────────┐
              ↓                 ↓
           Useful            Irrelevant
              ↓
          Reused
              ↓
       Outcome observed
          ↙        ↘
      Positive     Negative
         ↓            ↓
    Strengthen     Investigate
                       ↓
               ┌───────┴───────┐
               ↓               ↓
             Stale           Harmful
               ↓               ↓
            Degrade          Suppress

但有一个特别重要的设计：

不要因为一次没用就降低 memory。

必须做 Bayesian / evidence accumulation 式更新。

23. 我甚至不会直接更新 score，而会更新“证据”

例如：

M123


positive evidence: 17
negative evidence: 2
contradiction: 0
unknown: 31

然后：

P(useful∣evidence)

逐渐变化。

这样可以避免：

今天没用到一次
↓
score 0.9 → 0.3

这种灾难。

24. 另外一个很关键的问题：你们实际上需要两个学习器

这是我比较强的判断。

Learner A：Memory Content Learner

回答：

这条 memory 本身是不是好东西？

学习：

correctness
staleness
specificity
generality
Learner B：Retrieval Policy Learner

回答：

当前情况下该不该把它拿出来？

学习：

context → memory

这两个千万不要混在一起。

例如：

“项目使用 Python 3.12”

是一条非常好的 memory。

但用户正在写 React CSS 时把它召回：

retrieval policy 错了。

不能因此把 memory 本身降权。

这也是 2026 年 MemCon 工作很值得关注的地方：它强调 memory management 本身是 context-dependent policy，而不是固定 heuristic。
arXiv

25. 如果让我给你们设计 V1，我反而不会做复杂的“Memory Usefulness Model”

我会做一个非常务实的闭环：

             ┌─────────────┐
             │   Memory DB  │
             └──────┬──────┘
                    │
                 retrieve
                    ↓
             ┌─────────────┐
             │    Agent     │
             └──────┬──────┘
                    │
          ┌─────────┼─────────┐
          ↓         ↓         ↓
       plan      tool       code
          │         │         │
          └─────────┼─────────┘
                    ↓
                 outcome
                    ↓
             ┌─────────────┐
             │  Evaluator   │
             └──────┬──────┘
                    ↓
              memory events
                    ↓
             Memory Manager
              ↙          ↘
          strengthen    weaken

每一次 retrieval 只记录：

JSON
{
  "memory_id": "M123",
  "task_id": "T456",
  "retrieved": true,
  "mentioned": true,
  "used_in_plan": true,
  "linked_actions": ["A17"],
  "linked_changes": ["D42"],
  "task_success": true
}

然后再让一个 evaluator 异步判断：

M123:
  relevance: high
  adoption: high
  contribution: probable
  correctness: high
  harm: none

先把事件链建立起来。

不要一开始就追求一个神奇的：

memory_quality = 0.873
26. 我认为最终最漂亮的目标是“Memory Credit Assignment”

如果再往前推一步，你们真正需要解决的问题其实很像强化学习里的：

Credit Assignment

最终任务成功：

Task Success

到底应该把多少 credit 分给：

memory #12
memory #37
tool #4
planning decision #8
retrieval query #2

也就是说：

TaskOutcome→Action→Decision→Memory

做反向 credit assignment。

这比传统 RAG 的：

“检索准确率是多少？”

高了一个层次。

27. 所以我对这个问题的最终判断

我会把你们现在的问题概括成一句话：

Memory 系统真正缺的不是“更好的记忆评分”，而是“记忆使用后的 outcome telemetry”。

传统 memory：

write → retrieve

你们需要：

write
 ↓
retrieve
 ↓
attribute
 ↓
act
 ↓
observe
 ↓
evaluate
 ↓
update
 ↓
retrieve better

其中最值得优先投入的不是“模型判断这条记忆有多重要”，而是建立：

Memory → Decision → Action → Outcome 的可追踪链路。

然后按照成本从低到高：

retrieval telemetry

引用 / plan telemetry

memory → action attribution

memory → code diff / test attribution

用户纠正 / 接受

LLM trajectory evaluator

少量 A/B / ablation

最终学习 retrieval policy + memory lifecycle

最后一个我认为很重要的观点

你们最初的问题是：

“系统怎么知道一条记忆有没有被采纳、有没有用？”

我认为这个问题其实稍微问偏了一点。

更准确的问题应该是：

“系统如何估计一条 memory 在某个 context 下，对未来任务 outcome 的增量贡献？”

因为：

被召回 ≠ 被采用

被采用 ≠ 有用

有用 ≠ 正确

任务成功 ≠ memory 有贡献

而真正有价值的是：

ΔSuccess(M,C)=P(Success∣M,C)−P(Success∣¬M,C)
	​


当然，实际系统无法每次计算这个 counterfactual，所以才需要前面那一整套从廉价 implicit signals → trajectory attribution → selective ablation的信号体系。

这也解释了为什么我会把你们的长期记忆系统看成一个在线学习系统，而不是一个 RAG 数据库。

而且从近期研究看，这个方向正在逐渐出现：memory survey 已经明确把 agent memory 描述成 write–manage–read loop，并把 continual consolidation、causal retrieval、trustworthy reflection、learned forgetting 列为核心开放问题；MemCon 则进一步直接把 memory management 建模为带任务反馈的在线控制问题。
arXiv
+1

**如果你们现在正在设计产品，我最建议下一步直接把“Memory Event Schema + Memory Credit Assignment”设计出来。**这会比继续讨论“重要性公式”更容易落到真正可实现的系统上。
