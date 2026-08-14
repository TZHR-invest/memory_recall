# round-01 · ChatGPT 回答原文

> 执行日期: 2026-08-14 · 会话: 新会话（无预设同题） · 平台画像: 源码级结论可靠，web/issue 检索强
> 提示词: [02-round-01-prompts.md](02-round-01-prompts.md) 同一开放题

---

我认为这个问题其实问得比“怎么做一个长期记忆模块”更深一层。

如果只把它理解成：

从对话里抽取一些重要信息 → 存进数据库 → 以后 RAG 出来

我会认为方向偏了。

对于一个长期陪伴开发的 AI 助手，真正要解决的是：

如何让系统从连续的开发经历中，逐渐形成一套“以后做事时有用的经验、知识和当前状态”，并且在需要的时候恰当地影响行为。

这和“保存信息”是两个不同的问题。

下面我先给我的核心结论，再拆开讲哪些来自已有研究，哪些是我的综合推理。

一、我认为最核心的判断标准不是“重要”，而是“未来决策价值”

你们现在给出的价值锚点：

一条信息有价值 = 未来还会被需要，且忘记会导致重复成本

我非常认同，而且我会进一步把它改成：

Memory Value ≈ 未来被需要的概率 × 被需要时带来的收益 × 忘记它的代价

也就是：

V(m)=P(future use∣m)×Benefit(m)×Cost
forget
	​

(m)

这是我的综合推理，不是某篇论文直接提出的公式。

它比“importance”更适合开发 Agent。

例如：

信息 A

“今天我们把 foo.py 改成了 bar.py。”

可能当下很重要，但未来价值很低。

因为：

很可能只发生一次

Git 已经记录了

以后不需要 Agent 重新知道这个事实

所以不应该进入长期记忆。

信息 B

“这个项目使用 SQLite，是因为 local-first，不允许依赖云服务。”

价值很高。

因为未来 Agent 很可能再次面临：

“我要不要引入 Supabase？”

这条信息会直接改变决策。

它实际上不是“一个事实”，而是一个：

项目约束 / Design Constraint

信息 C

“InsightFace 的 buffalo_m 在这个项目里效果不错，det_thresh 用 0.5；RetinaFace 太慢。”

价值也很高。

因为它不是简单的：

“我们今天用了 buffalo_m。”

而是：

一个经过实验验证的工程经验。

未来遇到类似问题，可以直接减少搜索、实验和踩坑。

信息 D

“刚才把 SQLite 的 max_workers 从 4 改成了 1。”

单独看价值不高。

但是如果进一步发现：

ThreadPoolExecutor 并发写 SQLite 导致 database is locked；WAL 不能解决这个具体并发模式，因此目前保持单写。

那么这就变成了：

Problem → Context → Failed Approach → Cause → Solution

这是非常好的长期记忆。

所以我会把你们的价值锚点进一步提升为：

长期记忆不是“值得保存的信息”，而是“未来决策时值得重新进入认知过程的信息”。

这是我认为整个设计最重要的一步。

二、因此，“记忆”最好不要和“日志”混在一起

这里有一个非常重要的架构区分：

1. History / Record

“发生过什么？”

例如：

14:32 用户提出使用 SQLite
14:37 Agent 创建 database.py
14:41 测试失败
14:43 修改 connection pool
14:51 测试通过

这是历史记录。

它可以非常完整。

2. State

“现在是什么状态？”

例如：

Project:
  architecture = local-first
  database = SQLite
  vector_index = sqlite-vec
  embedding_model = ViT-B/32
  current_branch = feature/memory
  current_problem = memory extraction

这是状态。

它应该被不断更新，而不是不断 append。

3. Knowledge

“我们现在知道什么？”

例如：

SQLite is preferred because the product must remain local-first.

这是语义知识。

4. Experience

“过去做过类似事情，什么有效，什么没用？”

例如：

When SQLite writes are parallelized through ThreadPoolExecutor,
database locking occurs under the current architecture.
For this workload, single-writer execution is currently safer.

这是经验。

5. Procedure

“下次遇到这个问题应该怎么做？”

例如：

When modifying SQLite concurrency:
1. Enable WAL.
2. Avoid concurrent writers.
3. Benchmark with max_workers=1 first.
4. Only introduce a writer queue if throughput becomes a bottleneck.

这是程序性知识 / skill。

这其实与认知科学和 Agent memory 研究中的区分非常接近：

episodic memory

semantic memory

procedural memory

CoALA 就明确把 language agent 的 memory 设计成模块化的认知架构。
arXiv
+1

而近年的 Agent memory survey 也基本在往这个方向收敛。
ACL Anthology
+1

所以我会强烈建议：

不要设计一个叫 long_term_memory 的桶，把所有东西扔进去。

至少从语义上，要区分：

History
State
Knowledge
Experience
Procedure

底层是不是五张表倒不是重点。

三、而且我认为“什么值得记住”不能只在写入时决定

这是我认为很多 Memory 系统容易犯的错误。

传统思路：

conversation
    ↓
LLM 判断重要性
    ↓
important → memory
    ↓
vector DB

我认为这还不够。

因为：

信息的价值不是静态的，而是随时间和上下文变化的。

举个开发场景。

今天：

“项目使用 Python 3.12。”

可能没什么特别。

三个月后：

“我们准备升级到 Python 3.13。”

这时候原来的信息突然变得重要。

甚至后来：

“Python 3.13 导致某个依赖不兼容。”

那么：

Python 3.12
      ↓
upgrade attempt
      ↓
dependency failure
      ↓
current compatibility constraint

整个知识结构发生了变化。

因此 Memory 应该允许：

remember → retrieve → revise → consolidate → supersede → forget

而不是：

write once → retrieve forever

这也是最近研究开始明显强调的问题。

2026 年 ACL 的一篇 Agent Memory survey 直接把发展路线概括成：

Storage → Reflection → Experience

即：

保存轨迹

对轨迹反思、清洗

从轨迹中形成可迁移的 Experience

ACL Anthology
+1

我觉得这个框架非常适合你们。

四、所以我会把“记忆形成”设计成一个生命周期

不是：

聊天
 ↓
Memory

而是：

                  ┌──────────────┐
                  │   Raw Event  │
                  └──────┬───────┘
                         │
                         ▼
                 Candidate Memory
                         │
             ┌───────────┴───────────┐
             │                       │
          不值得                    值得
             │                       │
             ▼                       ▼
          History               Consolidation
                                     │
                    ┌────────────────┼────────────────┐
                    ▼                ▼                ▼
                  State           Knowledge        Experience
                    │                │                │
                    └────────────────┼────────────────┘
                                     ▼
                              Retrieval / Use
                                     │
                                     ▼
                              New Evidence
                                     │
                                     ▼
                              Update / Conflict
                                     │
                                     ▼
                              Supersede / Merge

这是我自己的系统设计推理。

其中最关键的其实不是“Candidate Memory”。

而是：

Consolidation（巩固）

五、我甚至不建议 Agent 每次都直接“写 Memory”

更好的机制可能是：

第一层：什么都记录

开发过程天然已经有很多东西：

user messages

assistant messages

tool calls

command outputs

git diff

test results

errors

files changed

decisions

environment information

这些都可以作为：

episodic log

它不需要特别聪明。

第二层：周期性做 Memory Consolidation

比如：

一个 task 完成

一个 issue 解决

一个 session 结束

一个 milestone 完成

项目发生重大架构变化

触发 consolidation。

Agent 回头问：

这一段经历里，有什么东西未来值得保留？

然后形成更高级的 memory。

例如从：

用户：
我们不要 Redis。


Agent：
为什么？


用户：
因为这是 local-first app。


Agent：
好的。


...


Agent：
Redis 会导致部署复杂。


...

最终不要记：

“用户说不要 Redis。”

而应该形成：

Architecture constraint: The project is local-first and should avoid infrastructure dependencies that require a server-side deployment.

然后附带：

evidence:
  session_123
  decision_456


scope:
  project


confidence:
  high


status:
  active

这样未来才真正可用。

六、我特别建议你们引入一个概念：Evidence

这是我认为开发 Agent Memory 和普通聊天机器人 Memory 最大的区别之一。

每一条重要记忆最好都有证据来源。

例如：

Memory:
SQLite is used because the application is local-first.


Type:
architecture_constraint


Scope:
project


Status:
active


Confidence:
0.96


Evidence:
  conversation: abc123
  decision: xyz456
  file: docs/architecture.md


Created:
2026-08-14


Last confirmed:
2026-08-14

为什么重要？

因为 LLM Memory 最大的问题之一不是：

“记不住。”

而是：

记错了以后还一直相信自己。

2026 年的 memory 研究也开始明确关注这一点：单纯保存 raw trajectories 会把成功、错误、幻觉和无效尝试一起保存下来，因此需要 reflection / evaluation 来清洗。
Preprints
+1

所以我会要求：

Memory = Claim + Provenance + Confidence + Scope + Temporal Status

而不是：

Memory = 一段 embedding。

七、尤其要区分“事实”和“推论”

例如：

Fact
SQLite is currently used.
User decision
User explicitly decided to remain on SQLite.
Agent inference
The reason appears to be local-first architecture.
Experience
SQLite is sufficient for the current single-user workload.

这四个东西的可信度完全不同。

如果系统把它们全部写成：

“SQLite is preferred because it is sufficient for single-user local-first workload.”

其实已经开始产生记忆幻觉了。

所以我会让 memory object 里显式保存：

source_type:
  user_assertion
  tool_observation
  artifact
  agent_inference
  experiment


confidence:
  ...


evidence:
  ...

这部分是我的设计推理，但我认为对于开发 Agent 非常关键。

八、另外，“重要性”本身不是一个好的长期筛选指标

Generative Agents 是这里非常经典的早期工作。

它把 memory retrieval 做成：

Recency + Importance + Relevance

即最近性、重要性、相关性。
数字对象标识符
+1

这是很好的起点。

但对于开发助手，我会认为：

Importance ≠ Long-term value

例如：

生产环境挂了

Importance：

★★★★★

但它可能只是一次性的。

而：

这个 API 的 rate limit 是 100/min，而且官方文档没有写清楚。

Importance：

★★★

Long-term value：

★★★★★

所以我会把：

importance

改成：

future utility

甚至进一步拆成：

reuse probability
impact if reused
forgetting cost
stability
transferability
九、我会用“未来任务”而不是“当前内容”来判断 Memory

这是我认为你们可以做得比很多 Memory 产品更好的地方。

不要问：

“这句话重要吗？”

而问：

“未来什么任务会需要这条信息？”

比如：

Memory:
项目使用 local-first 架构。


Potential future tasks:
- 添加数据库
- 增加同步功能
- 选择 SaaS
- 部署方案设计
- 选择第三方 API

于是 Memory 的价值变得可计算。

甚至可以反过来：

一条 Memory 如果找不到任何合理的 future task，它就很可能不值得长期保存。

这是我的推理。

十、因此，最好的 Memory 不是“知识库”，而是“未来任务的先验”

这一点我特别想强调。

普通知识库：

“我知道很多东西。”

优秀的开发 Agent Memory：

“我知道这个用户 / 这个项目过去做过什么，以及这些过去经历会如何改变我现在应该怎么做。”

这两个系统的目标完全不同。

例如用户问：

“帮我加一个缓存。”

普通 RAG：

搜索：
cache
redis
sqlite
python
...

Memory-aware Agent：

Project constraints:
  local-first
  single-user


Previous experience:
  Redis was rejected because it adds infrastructure.


Current architecture:
  SQLite


Therefore:
  first consider SQLite-based cache / filesystem cache
  before introducing Redis.

这才是真正的“记忆”。

十一、所以 Retrieval 也不能只是 Semantic Search

这是第二个大坑。

很多系统：

memory
 ↓
embedding
 ↓
vector DB
 ↓
cosine similarity

然后宣布：

“我们有长期记忆了。”

其实没有。

因为：

保存什么和什么时候取出来是两个问题。

例如记忆：

“项目必须 local-first。”

用户问：

“我们可以用 Redis 吗？”

语义相似度可能并不高。

但它应该被召回。

所以 retrieval 至少应该同时考虑：

semantic relevance
+
task relevance
+
scope
+
state validity
+
recency
+
confidence
+
dependency / relationship

Generative Agents 用 relevance/recency/importance 是很好的早期启发；CoALA 则进一步把 memory 操作作为认知架构的一部分。
数字对象标识符
+1

近年的 A-MEM 甚至开始尝试让 Memory 自己形成链接、更新上下文和关系，而不是一个孤立的 vector chunk。
NIPS论文集

十二、我认为“关系”对于开发项目尤其重要

因为项目天然是一个 graph。

例如：

Constraint
   │
   ├── motivates ──> Decision
   │                    │
   │                    └── implemented by ──> Code
   │
   ├── caused ─────> Rejection
   │
   └── tested by ──> Experiment

例如：

local-first
    ↓
avoid Redis
    ↓
SQLite
    ↓
SQLite concurrent writes
    ↓
database locked
    ↓
single writer

如果只把这些分别做 embedding：

memory1
memory2
memory3
memory4
memory5

系统以后很难知道：

为什么当初选择 SQLite？

而 graph / links 能保留：

原因 → 决策 → 实施 → 结果

A-MEM 的方向其实就是在探索这种动态链接和 memory evolution。
NIPS论文集

但我要强调：

我不认为你们现在就应该上 Knowledge Graph。

逻辑关系比 Graph Database 更重要。

SQLite + relation table 完全可能先做出来。

十三、我会把 Memory 分成三个“尺度”

这是一个比较偏我自己的设计。

Project Memory

只对当前项目有效。

例如：

Architecture
Constraints
Current decisions
Current roadmap
Known bugs
Current environment
User Memory

跨项目有效。

例如：

User prefers local-first solutions.
User tends to use CLI tools.
User prefers open-source solutions.
User dislikes cloud dependency.

当然，这类信息要非常谨慎，因为容易侵犯用户感受。

General Experience

甚至不绑定用户。

例如：

SQLite concurrent writes can cause locking.
InsightFace buffalo_m offers a useful speed/accuracy tradeoff.
Certain ffmpeg filters are expensive at high resolution.

它实际上变成：

Agent 自己积累的工程经验。

这三个层级非常重要：

User
  ↑
Project
  ↑
Task
  ↑
Episode

以及：

Episode
   ↓ abstraction
Project Knowledge
   ↓ abstraction
General Experience

这正好对应最近研究从 Storage → Reflection → Experience 的演化方向。
ACL Anthology

十四、一个特别重要的原则：不要过度压缩原始经历

这里可能和很多“Memory 产品”的直觉相反。

我会建议：

原始轨迹可以便宜地保存，但不要把它当作长期 Memory。

例如：

Raw:
session / tool call / git diff / terminal output

保留。

然后：

Derived:
decision
experience
constraint
procedure

作为长期 Memory。

原因是：

压缩后的 Memory 会丢失证据。

未来如果 Memory 错了，可以回溯原始轨迹重新解释。

因此：

Raw Event
    ↓
Derived Memory
    ↓
Evidence → Raw Event

形成可逆链路。

这实际上非常像数据系统里的：

source of truth vs materialized view

我认为这是非常适合 Agent Memory 的工程类比。

十五、我甚至会把“记忆”理解成一种 Materialized View

这是我自己的一个比较强的设计观点。

真正的数据：

Conversation
Tool Calls
Files
Git
Tests
Issues
User Decisions

是：

source of truth

Memory 是：

面向未来任务的 materialized knowledge

因此：

Raw history
      ↓
Extraction
      ↓
Consolidation
      ↓
Memory
      ↓
Retrieval
      ↓
Agent action

而当事实变化：

new evidence
      ↓
invalidate / update
      ↓
memory

这比：

“Memory DB 是系统事实来源”

安全得多。

十六、这也意味着 Memory 必须允许“过期”

比如：

Python = 3.12

后来：

Python = 3.13

不要：

memory += new fact

否则系统同时记住：

Python 3.12
Python 3.13

然后 RAG 随机召回。

应该变成：

Python 3.12
    ↓
superseded by
    ↓
Python 3.13

所以 Memory object 至少需要：

status:
  active
  superseded
  deprecated
  uncertain
  archived

这点在工程 Agent 中尤其重要。

十七、我认为“忘记”其实和“记住”同等重要

一个系统如果：

什么都记住

最终并不聪明。

因为：

memory volume ↑
retrieval noise ↑
contradictions ↑
context cost ↑
false recall ↑

所以真正成熟的 Memory System 应该有：

forgetting policy

例如：

永久保留

用户明确的长期偏好

核心项目约束

高价值工程经验

关键架构决策

状态性保留

当前技术栈

当前 roadmap

当前 deployment 状态

会被更新。

暂时保留

当前 debugging context

最近的失败尝试

原始日志

长期归档，但默认不参与 retrieval。

十八、所以我会给每条 Memory 一个“生命周期”

例如：

Memory
├── content
├── type
├── scope
├── status
├── confidence
├── evidence
├── created_at
├── last_confirmed_at
├── last_used_at
├── usage_count
├── supersedes
├── related_memories
└── expected_future_tasks

其中 expected_future_tasks 是我比较推荐你们实验的字段。

例如：

Memory:
"Project is local-first."


Expected future tasks:
  architecture decisions
  infrastructure selection
  deployment
  data storage

它会直接帮助 retrieval。

十九、真正应该优化的指标也不是“Memory Recall”

这里我认为产品设计最容易走偏。

不要只测：

“用户说过的东西，Agent 能不能记住？”

这是一个很容易把产品推向“什么都记住”的指标。

真正应该测的是：

Memory Utility

例如：

用户第二次遇到同一个问题时，Agent 是否避免了第一次的错误？

Redundant Input Reduction

用户是否需要再次解释已经告诉过 Agent 的事情？

Decision Quality

Memory 是否让 Agent 做出了更好的工程决策？

Retrieval Precision

召回的 Memory 是否真的应该进入当前 context？

Staleness Error

Agent 是否因为旧 Memory 做出了错误决策？

Memory Cost

为了得到这些收益，付出了多少 token / latency / storage？

我甚至会定义一个非常简单的最终指标：

Memory ROI=
记忆产生 + 存储 + 检索 + 错误成本
因为记忆而节省的未来成本
	​


这同样是我的综合推理，而不是论文里的标准指标。

二十、因此我会把你们整个系统设计成一个“闭环”

我认为最终比较理想的是：

                  ┌──────────────┐
                  │   Interaction │
                  └───────┬──────┘
                          ↓
                   Episodic History
                          ↓
                   Memory Candidates
                          ↓
                    Consolidation
                          ↓
        ┌─────────────────┼─────────────────┐
        ↓                 ↓                 ↓
      State            Knowledge         Experience
        │                 │                 │
        └─────────────────┼─────────────────┘
                          ↓
                      Memory Store
                          ↓
                  Task-aware Retrieval
                          ↓
                     Agent Context
                          ↓
                      Agent Action
                          ↓
                Outcome / Feedback
                          ↓
                   Memory Update
                          ↓
                 Consolidate again

这就不再是一个：

“Memory Feature”

而是：

Learning Loop

二十一、这也是我对你们最初问题最大的修正

你问的是：

哪些信息值得长期沉淀？

我会说：

这个问题本身有一点点问偏了。

更好的问题应该是：

哪些经历应该被转化成未来可复用的认知资产？

因为：

Information

和：

Reusable knowledge

不是同一个东西。

比如：

“昨天用了 3 小时解决 X 问题。”

这是信息。

而：

“X 问题在这种架构下通常由 Y 导致，优先检查 Z。”

这是经验。

后者才是真正的 Memory。

二十二、如果让我现在给你们定一个最小可行架构

我反而不会一开始搞很复杂。

第一版我会只做 4 类 Memory：

类型	示例	生命周期
Constraint	项目必须 local-first	长期
Decision	为什么选择 SQLite	长期，可能被 supersede
State	当前使用 Python 3.13	动态更新
Experience	某方案失败以及为什么失败	长期

然后保留完整：

Episode / History

作为证据源。

Memory 写入

不是：

每句话抽取 memory。

而是：

事件发生
 ↓
判断是否可能影响未来任务
 ↓
candidate
 ↓
task/session/milestone结束时 consolidation
 ↓
形成 Constraint / Decision / State / Experience
Memory 读取

不是：

embedding search

而是：

当前 Task
 ↓
识别需要哪些认知类型
 ↓
Project State
 ↓
Relevant Constraints
 ↓
Relevant Decisions
 ↓
Relevant Experiences
 ↓
必要时才取 Raw Episode

这其实很像：

先查“我现在是什么状态和规则”，再查“过去有什么经验”，最后才查“当时具体发生了什么”。

二十三、我认为一个优秀 Memory 最终应该长这样

不是：

“2026-08-14 用户讨论过 SQLite。”

而应该是：

SQLite 是当前项目的数据库，因为项目要求 local-first、single-user，并且不希望引入外部基础设施。

然后：

Type:
  Constraint + Decision


Scope:
  Project: LensDiary


Status:
  Active


Confidence:
  High


Why:
  local-first architecture


Evidence:
  Decision #42
  Session #183


Related:
  Redis rejection
  SQLite concurrency issue


Potentially useful for:
  database changes
  deployment decisions
  infrastructure choices

这时候它才真的成为 Agent 的“长期记忆”。

二十四、最后说一下现有研究给我的总体判断

如果把目前这个领域粗略地画成一条线，我会认为：

第一阶段：Storage

把过去存起来。

MemGPT / 早期 long-context memory 系统很典型。MemGPT 的核心思想就是把 context 当 RAM、外部 memory 当 disk，并建立 core / recall / archival 等不同层级。
MemGPT
+1

第二阶段：Retrieval

从过去找相关东西。

Generative Agents 的：

recency + relevance + importance

是非常经典的代表。
数字对象标识符

第三阶段：Reflection

不只是保存过去，而是从过去总结。

Generative Agents 已经明确包含这一层：从大量 observation 产生 higher-level reflection。
数字对象标识符

第四阶段：Consolidation / Experience

把多次经历变成可以迁移的经验。

这正是 2026 年 ACL 那篇 survey 提出的：

Storage → Reflection → Experience

路线。
ACL Anthology

A-MEM 则进一步探索：

memory 自己组织、连接、更新。

NIPS论文集

Mem0 则从工程落地角度强调：

extraction + consolidation + retrieval

并报告了在长期对话 benchmark 上相对于多种 baseline 的收益。需要注意，这些结果主要来自其论文自己的 benchmark，不能直接等同于“已经证明是通用最优架构”。
arXiv

我的最终判断

如果让我用一句话定义你们应该做的东西：

不是一个“帮 Agent 记住更多东西”的 Memory System，而是一个“把开发过程中的经历逐渐转化成未来可用认知资产”的 Experience System。

它的核心链条应该是：

经历
 ↓
筛选
 ↓
抽象
 ↓
验证
 ↓
结构化
 ↓
关联
 ↓
在未来任务中召回
 ↓
被实际使用
 ↓
根据结果修正

而判断一条信息是否值得留下，最本质的标准不是：

“它重要吗？”

甚至也不只是：

“以后会不会用？”

而是：

“如果未来某个任务再次出现，这条信息能不能改变 Agent 的行为，使它少走一次弯路、少问用户一次问题、少做一次实验、少犯一次错误，或者做出更好的决策？”

如果答案是 yes，它就有 Memory Value。

反过来：

一个信息即使非常“重要”，但未来只需要通过 Git、代码、文档或原始历史重新获得，那么它未必应该成为长期认知。

这是我认为最值得作为整个产品设计 North Star 的区别。

出处边界说明：上面关于 episodic/semantic/procedural、memory stream、recency/relevance/importance、reflection、MemGPT、CoALA、A-MEM、Storage→Reflection→Experience 等，尽量对应了具体论文/研究；关于“未来决策价值”“Memory 是 materialized view”“expected future tasks”“Memory ROI”以及我给出的五类/四类开发 Memory 架构，主要是我基于这些研究、软件工程经验和你描述的 Agent 场景做的综合推理，不是某篇文献的原话。对于这个领域目前是否已经存在一个被广泛验证的、能够准确计算“某条信息长期价值”的统一公式，我不知道有这样的成熟答案；就目前研究来看，这仍然是开放问题。