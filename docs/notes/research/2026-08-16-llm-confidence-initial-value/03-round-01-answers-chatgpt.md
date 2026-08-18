# 03 · round-01 回答 · ChatGPT

> 请把 ChatGPT 的回答**原文整块粘贴**到这里（正文一个字不改、不二次概括）。
> 归属: [README](README.md) · 日期: 2026-08-16

## 回答（原文）

我觉得你们现在的方向基本是对的，但我会把问题再“掰开”一点：

> **“初始可信度”不应该是 LLM 对这条记忆有多自信，而应该是：在没有后续证据时，系统基于“这条信息是怎么产生的”对其真实性做出的先验估计。**

更进一步，我甚至建议：**不要把一个裸的 `confidence = 0.83` 作为记忆的核心状态。**
应该把它拆成：

1. **Provenance / 来源**：这条话是谁、通过什么机制产生的；
2. **Initial prior / 初始先验**：基于来源和证据结构的先验可信度；
3. **Evidence / 后续证据**：用户确认、代码验证、重复出现、被纠正等；
4. **Freshness / 时效性**：这条事实现在是否仍成立；
5. **Posterior / 当前可信度**：综合上述证据后的结果。

这会比“LLM 写入时给一个 0~1 分数”稳健很多。

---

# 一、先指出一个关键问题：你们定义的“可信度”其实混合了两个变量

你们现在定义的是：

> “这条记忆内容为真，且当前仍然成立”的概率。

这里其实至少有两个概率：

[
P(\text{true})
]

和

[
P(\text{still valid now}\mid\text{true})
]

例如：

> “项目使用 SQLite + sqlite-vec。”

如果刚刚从用户口中得到，**真实性可能很高**。

但：

> “项目使用 Python 3.11。”

可能也是用户明确说过的，但半年后它仍然成立的概率就会明显下降。

所以：

[
P(\text{currently valid})
=========================

P(\text{true})\times P(\text{not changed}\mid\text{true})
]

这是我的建议，不是某篇论文直接给出的结论。

**这点非常重要。**

否则你们会发现一个奇怪现象：

> 一条记忆从来没有被证明是错的，所以 confidence 一直 0.95。

但其实它只是**没有被重新验证过**。

---

# 二、我认为“初始置信度”最可靠的来源不是 LLM，而是 Provenance

如果现在让我给这个系统设计 V1，我会把优先级排成：

> **来源类型 > 外部/结构化证据 > 产生过程 > 历史来源可靠性 > LLM 自报 confidence**

也就是说，LLM 自报分数最多只是一个 feature。

例如：

| 来源                              | 我会给的先验 | 理由                       |
| ------------------------------- | -----: | ------------------------ |
| 用户明确说：“记住，我以后都用 pnpm”           |      高 | 用户是第一手来源                 |
| 用户明确纠正：“刚才错了，现在改成 pnpm”         |     很高 | 具有纠错意图                   |
| 系统从用户陈述直接抽取                     |     中高 | 内容来自用户，但多了一层抽取错误         |
| 从代码实际读取到 `packageManager: pnpm` |     很高 | 可验证的一手 artifact          |
| 从 git diff 推断项目决策               |      高 | 有行为证据                    |
| LLM 根据上下文推断                     |     中低 | inference，不是 observation |
| LLM 根据常识猜测                      |      低 | 推测                       |
| 多步 LLM 推理得到                     |     更低 | 推理链可能累计错误                |

这里真正值得借鉴的是 **truth discovery / source reliability** 这一类研究。

Dawid & Skene 1979 的经典工作甚至研究了一个很相似的问题：

> 在没有真实答案的情况下，根据不同“观察者”的历史错误率，反推出真正的答案。

也就是说，**source reliability 本身可以学习**，不一定需要一开始就知道。([OUP Academic][1])

后来的 truth-discovery 工作也是类似思路：同时估计“哪个 claim 更可能是真的”和“哪个 source 更可靠”。([PubMed Central (PMC)][2])

这和你们的场景其实高度同构：

```text
                 ┌── 用户明确陈述
                 │
                 ├── 用户纠正
                 │
Claim ───────────┼── 代码 / git / config
                 │
                 ├── Agent 推断
                 │
                 └── LLM 提炼

             ↓

        source reliability
             +
        evidence quality
             ↓

       initial prior
```

---

# 三、所以我不会让 LLM 输出 `confidence: 0.87`

至少不会直接这么用。

你们观察到的“LLM 自报 confidence 过度自信”是有充分研究支持的。

例如 Mielke 等人的研究发现，对话模型的语言化 confidence 与实际正确率之间存在明显失配。([MIT Press Direct][3])

而关于 LLM calibration 的经典研究也发现，即使模型自己的 token probability，都不天然等于“答案正确概率”。([MIT Press Direct][4])

不过这里有一个很重要的 nuance：

**不能简单说“LLM confidence 完全没用”。**

Tian 等人在 EMNLP 2023 的研究发现，对经过 RLHF 的模型，直接要求 verbalized confidence，在某些 QA benchmark 上反而比直接使用 token probability 更容易校准，甚至可以明显降低 calibration error。([ACL Anthology][5])

但这是：

> **“经过实验发现某个模型 + 某种 prompt + 某个任务上的 verbalized confidence 有 calibration signal”**

而不是：

> **“LLM 说 90%，所以这个记忆有 90% 概率是真的。”**

最近的研究反而进一步强调了这个区别。2026 年的工作发现，LLM confidence 对 elicitation protocol、conditioning context 等非常敏感；甚至表面上看起来合理的错误答案，也可能获得接近正确答案的 confidence。([arXiv][6])

所以我的判断是：

> **LLM confidence 是一个可利用的弱信号，但绝对不应该是概率的定义。**

---

# 四、最好的办法：让 LLM 输出“证据结构”，而不是“置信概率”

这是我比较强烈推荐的一点。

不要问：

> “你有多确信这条记忆？”

而应该问：

> “这条记忆是从什么证据推导出来的？”

例如：

```json
{
  "claim": "项目使用 pnpm",
  "source_type": "user_explicit",
  "assertion_mode": "direct",
  "evidence": [
    {
      "type": "user_statement",
      "strength": "direct"
    }
  ],
  "inference_required": false,
  "contradiction_detected": false,
  "scope": "project",
  "temporal_scope": "current"
}
```

另一条：

```json
{
  "claim": "项目应该迁移到 pnpm",
  "source_type": "agent_inference",
  "assertion_mode": "recommendation",
  "evidence": [
    {
      "type": "package_json",
      "strength": "indirect"
    }
  ],
  "inference_required": true
}
```

这两个 claim 即使 LLM 都输出：

```text
confidence = 0.95
```

系统也应该完全不同地处理。

---

# 五、我会把初始 confidence 做成一个“先验模型”

一个非常简单的 V1：

[
P_0(m)
======

f(
source,
assertion_type,
evidence,
extraction,
specificity,
temporal_risk
)
]

例如：

```text
P0 =
    source_prior
  × extraction_quality
  × evidence_quality
  × temporal_factor
```

但我更推荐使用 **log-odds / Beta prior**，而不是直接乘几个分数。

---

# 六、甚至可以非常自然地用 Beta 分布

假设一条 memory：

> “项目使用 pnpm。”

不要保存：

```text
confidence = 0.87
```

而保存：

```text
alpha = 8
beta = 1
```

其期望值：

[
E[p] = \frac{\alpha}{\alpha+\beta}=0.889
]

但真正重要的是：

> **你同时保存了“我们对这个判断有多少证据”的概念。**

例如：

### 用户明确说

```text
Beta(8,1)
```

### LLM 自动推断

```text
Beta(3,2)
```

### 代码直接验证

```text
Beta(20,1)
```

这三个虽然平均值可能接近，但证据量完全不同。

这也是 Bayesian updating 非常适合你们这个问题的地方：后续证据可以自然更新 prior。Bayesian 更新本身当然是成熟的统计方法，而不是我为 memory 系统发明的。([科学直接][7])

---

# 七、但这里有一个坑：不要把“被使用”当成“被证明正确”

你们之前提到：

> retrieved → mentioned → used_in_plan → linked_actions → task_success

我认为这个设计非常好。

但这些信号的**证据强度不应该一样**。

例如：

```text
memory retrieved
```

几乎不能说明它是真的。

```text
memory mentioned
```

稍微有一点。

```text
memory used_in_plan
```

说明 Agent 接受了它。

但仍然不能证明事实正确。

```text
memory linked to successful action
```

才开始有较强 evidence。

而：

```text
code execution confirms memory
```

是更强的证据。

所以我会建立：

```text
Evidence Strength

0.00  retrieved
0.05  mentioned
0.10  used_in_reasoning
0.15  used_in_plan
0.25  user implicitly accepts
0.40  successful action consistent
0.70  user explicitly confirms
0.85  independent artifact confirms
0.95  direct deterministic verification
```

**这些数字是我的设计建议，不是文献中的标准值。**

真正上线时应该通过你们自己的历史数据学习。

---

# 八、最有意思的其实是：你们可以学习“来源可靠性”

这是我认为你们系统真正有潜力的地方。

假设系统长期发现：

```text
用户明确陈述
→ 92% 最终被确认

代码 config
→ 99.5% 最终被确认

LLM 自动推断
→ 71%

LLM 从历史上下文推断
→ 63%
```

那么系统根本不需要人工规定：

```text
user = 0.9
llm = 0.7
code = 0.99
```

它可以自己学习。

这和 truth discovery / Dawid-Skene 的思想非常接近：**没有 ground truth 时，也可以利用多个来源之间的行为一致性估计 source reliability。** ([OUP Academic][1])

甚至可以进一步做到：

```text
source reliability
+
claim-type reliability
+
project-specific reliability
+
user-specific reliability
```

例如：

```text
User explicit statements:
    architecture decisions: 0.97
    environment versions: 0.91
    memory of exact filenames: 0.78

LLM extraction:
    preferences: 0.94
    project decisions: 0.88
    inferred architecture: 0.65
```

这就比一个统一的 confidence 强很多。

---

# 九、还有一个非常关键的设计：把“内容可信度”和“来源可信度”分开

我会至少保存：

```text
Memory
├── claim
├── provenance
│   ├── source
│   ├── source_event
│   ├── extraction_method
│   └── evidence_refs
│
├── content_belief
│   ├── alpha
│   └── beta
│
├── freshness
│   ├── last_verified_at
│   ├── volatility
│   └── expires_at
│
└── contradiction_state
```

这样：

> “用户说过 X”

和：

> “X 是真的”

就不会混为一谈。

---

# 十、我甚至建议不要让“confidence”承担所有事情

例如：

> “用户喜欢 dark mode。”

这属于 preference。

> “项目使用 PostgreSQL。”

这是 environment fact。

> “我们决定不用 Redis。”

这是 decision。

> “上次这个 bug 是因为 UTF-16 BOM。”

这是 debugging knowledge。

它们的“正确性机制”其实完全不同。

我会定义：

[
Confidence(m)
=============

P(\text{claim correct}\mid evidence)
]

但再定义一个：

[
Freshness(m)
============

P(\text{claim still applies now}\mid age, volatility, observations)
]

最终：

[
Trust(m)
========

Confidence(m)\times Freshness(m)
]

这个公式是**我的系统设计推理**，不是引用某篇论文。

---

# 十一、这会直接解决“环境事实”的问题

比如：

```text
Python = 3.11
```

写入时：

```text
confidence = 0.99
freshness = 0.99
```

三个月后没有任何验证：

```text
confidence = 0.99
freshness = 0.72
```

所以：

```text
trust = 0.71
```

如果今天从 `.python-version` 重新看到：

```text
3.11
```

那么：

```text
confidence ↑
freshness ↑
```

而不是简单地：

```text
confidence = 0.99 forever
```

---

# 十二、LLM confidence 如果要保留，我建议这样用

不要：

```text
final_confidence = LLM_confidence
```

而是：

```text
features:
    llm_confidence
    source_type
    evidence_count
    evidence_strength
    inference_depth
    contradiction_count
    claim_type
    temporal_risk
    historical_source_accuracy
```

然后训练一个 calibration model：

[
P(correct)
==========

Calibrator(features)
]

最简单甚至可以先用：

* logistic regression
* isotonic regression
* Platt scaling

这其实和 selective prediction / calibration 文献的思路一致：**模型原始 confidence 并不是最终 probability，需要用 held-out outcomes 做 calibration。** ([ACL Anthology][8])

而且这会非常适合你们。

因为你们天然会产生训练数据：

```text
memory created
       ↓
initial features
       ↓
later evidence
       ↓
最终知道它对/错
       ↓
label
```

这就是一个天然的 calibration dataset。

---

# 十三、所以冷启动其实没有你想象得那么糟

你们现在的困境是：

> 刚创建 memory，没有后续 evidence，怎么办？

我的答案是：

**不要试图解决“我们不知道”的问题。**

冷启动状态应该允许：

```text
confidence = 0.78
evidence_mass = low
```

而不是：

```text
confidence = 0.78
evidence_mass = high
```

更进一步，UI 甚至可以显示：

> **可信度：较高**
>
> 来源：用户明确陈述
> 尚未经过后续验证

而不是：

> **87%**

因为 `87%` 很容易给用户造成“这是一个经过统计验证的客观概率”的错觉。

---

# 十四、我会特别避免一个反模式：人为设定大量精确 prior

比如：

```text
用户确认      = 0.95
用户陈述      = 0.85
LLM 提取      = 0.75
LLM 推断      = 0.60
```

看起来很科学。

实际上很可能是假精确。

如果没有真实历史数据，这些数字本质上是：

> **工程师的主观先验。**

当然可以这么做，但应该明确知道它是 heuristic。

更好的做法是：

```text
Beta(8,1)
Beta(5,1)
Beta(3,2)
Beta(2,2)
```

并且把它解释成：

> **prior strength**

而不是声称：

> “用户明确说的话有 89% 概率是真的。”

---

# 十五、我认为最值得做的其实是“验证事件”

你们现在已经在考虑：

> retrieved / mentioned / used / success

我会再往前一步：

建立一个统一的：

```text
Memory Evidence Event
```

例如：

```text
MemoryCreated
MemoryRetrieved
MemoryMentioned
UserConfirmed
UserCorrected
UserContradicted
CodeVerified
ConfigVerified
GitVerified
ActionSucceeded
ActionFailed
ContradictionDetected
Revalidated
Expired
```

每一个事件都有：

```text
event_type
evidence_strength
independence
timestamp
source
```

尤其是：

### independence

非常重要。

假设：

```text
用户说：项目使用 pnpm
↓
LLM 提炼：项目使用 pnpm
↓
另一个 LLM：项目应该继续使用 pnpm
```

这不是三个 independent evidence。

实际上：

```text
1 个原始 evidence
      ↓
3 次模型复述
```

如果你们把它当三次 positive evidence，confidence 会迅速膨胀。

---

# 十六、所以“跨会话重复出现”也不能简单加分

例如用户连续 10 次说：

> “我们用 pnpm。”

确实是很强的信号。

但是：

```text
session 1: user says pnpm
session 2: LLM retrieves pnpm
session 3: LLM says pnpm
session 4: LLM summarizes pnpm
...
```

不能算 10 次。

真正应该接近：

```text
independent_observations = 1
```

如果：

```text
user says pnpm
+
package.json says pnpm
+
lockfile = pnpm-lock.yaml
+
CI workflow uses pnpm
```

这才是非常强的多源证据。

这又回到了 truth discovery 的核心思想：**来源和证据之间需要建模，而不是简单计数。** ([PubMed Central (PMC)][2])

---

# 十七、如果让我直接给你们一个 V1，我会这么做

### Memory 写入

LLM **不输出 confidence**，而输出：

```text
claim
claim_type
source_type
assertion_mode
evidence_refs
inference_depth
temporal_scope
volatility
contradiction
```

然后 deterministic scorer 根据 provenance 算：

```text
initial_prior
```

例如：

```text
user_explicit + direct evidence
        → strong prior

user_explicit + ambiguous wording
        → medium-high prior

LLM extraction
        → source prior × extraction reliability

LLM inference
        → lower prior

code/config observation
        → very high prior
```

---

### 后续

所有 interaction 变成 Evidence Event：

```text
+ user confirmation
+ independent artifact confirmation
+ successful action
+ repeated independent observation

- explicit correction
- contradictory artifact
- failed action caused by memory
- stale verification
```

然后更新：

```text
Beta(alpha, beta)
```

---

### 最后

得到：

```text
content_confidence
freshness
evidence_mass
```

而不是一个孤零零的：

```text
confidence = 0.91
```

---

# 十八、再往后，才是“学习器”

当你们积累了几千/几万条 memory 后，就可以训练：

```text
P(correct | features)
```

features 可以包括：

```text
source_type
claim_type
llm_model
llm_confidence
extraction_depth
evidence_strength
number_of_independent_sources
contradiction_count
age
volatility
user_confirmation
code_confirmation
...
```

最终：

```text
raw prior
      ↓
calibration model
      ↓
posterior probability
```

这时候 **LLM confidence 才真正有机会发挥价值**。

它不是概率本身，而是：

> **一个可以被 calibration model 学习利用的 predictive feature。**

这和现代 calibration / selective prediction 的基本思想是吻合的。([ACL Anthology][8])

---

# 十九、关于“LLM 自报 confidence”我的最终评价

我会把它分成三个阶段：

| 阶段             | LLM confidence 的地位  |
| -------------- | ------------------- |
| 冷启动            | **弱信号，可不用**         |
| 有少量历史数据        | **feature，可以校准后使用** |
| 有大量 outcome 数据 | **可以成为模型输入之一**      |

绝对不要：

```text
LLM says 0.9
→ memory confidence = 0.9
```

应该：

```text
LLM says 0.9
+
user explicitly stated
+
direct evidence
+
no contradiction
+
historical reliability of this extraction pipeline
+
claim type
+
temporal risk
↓
calibrator
↓
0.94
```

甚至可能出现：

```text
LLM says 0.99
↓
historically this type of inference is only 65% reliable
↓
posterior = 0.68
```

这才是真正意义上的“让模型的自信接受现实校准”。

---

# 二十、我认为你们真正应该优化的指标，也不是“confidence 准不准”

这是我对你们问题最大的一个重新 framing。

你们最终不是在做：

> **“给 memory 估计一个概率。”**

而是在做：

> **“决定什么时候可以放心把 memory 交给 Agent 使用。”**

所以最终真正应该优化的是：

[
\boxed{
P(\text{memory causes a useful/correct downstream action})
}
]

而不是单纯：

[
P(\text{memory is true})
]

例如：

> “项目以前使用 Redis。”

即使它 99% 为真，如果当前任务是修改 SQLite schema，它可能完全不应该被召回。

反过来：

> “Windows SSH authorized_keys 文件之前因为 UTF-16 BOM 导致 OpenSSH 不识别。”

这条 memory 即使只有 0.85 的 confidence，在当前遇到完全相同的 SSH 问题时，也可能值得召回。

所以我会最终形成三层：

```text
                ┌──────────────┐
                │ Truth        │
                │ 内容可信度    │
                └──────┬───────┘
                       │
                ┌──────▼───────┐
                │ Freshness    │
                │ 当前有效性    │
                └──────┬───────┘
                       │
                ┌──────▼───────┐
                │ Utility      │
                │ 对当前任务有用 │
                └──────────────┘
```

然后：

```text
Memory Retrieval Score
=
Truth
× Freshness
× Relevance
× Expected Benefit
```

这比单纯追求一个“完美 confidence”更接近你们这个产品真正的目标。

---

## 最后给一个我认为最重要的结论

**你们现在不应该花太多精力研究“LLM 到底应该输出 0.73 还是 0.81”。**

真正值得投资的是：

> **把 memory 从“一个带分数的文本”，变成“一个带 provenance + evidence history + temporal validity 的 claim”。**

初始阶段：

```text
provenance → prior
```

成长阶段：

```text
evidence → posterior
```

规模起来以后：

```text
historical outcomes → learn source reliability
```

最终：

```text
truth × freshness × relevance
→ retrieval / action policy
```

而 LLM confidence：

```text
                  ┌→ 不作为真概率
LLM confidence ──┤
                  └→ 作为一个待校准的弱 feature
```

我认为这条路线比“LLM 自评 + Bayesian 累加”还要再前进一步：**Bayesian 的核心对象应该是 evidence，而不是 confidence 分数。**

另外，我查到的文献里，**“LLM verbalized confidence 应该如何直接用于长期记忆系统”目前没有看到一个已经成熟、被广泛验证的标准方案**。上面的 memory-specific 架构主要是我把 calibration、truth discovery、provenance 和你们的 Agent memory 场景综合后的设计推理，而不是声称“已有论文已经证明了这个方案”。这一点我建议你们在内部设计文档里也明确标注。

[1]: https://academic.oup.com/jrsssc/article/28/1/20/6953573?utm_source=chatgpt.com "Maximum Likelihood Estimation of Observer Error-Rates Using the EM Algorithm | Journal of the Royal Statistical Society Series C: Applied Statistics | Oxford Academic"
[2]: https://pmc.ncbi.nlm.nih.gov/articles/PMC4688015/?utm_source=chatgpt.com "Modeling Truth Existence in Truth Discovery - PMC"
[3]: https://direct.mit.edu/tacl/article/doi/10.1162/tacl_a_00494/112606/Reducing-Conversational-Agents-Overconfidence?utm_source=chatgpt.com "Reducing Conversational Agents’ Overconfidence Through Linguistic Calibration | Transactions of the Association for Computational Linguistics | MIT Press"
[4]: https://direct.mit.edu/tacl/article/doi/10.1162/tacl_a_00407/107277/How-Can-We-Know-When-Language-Models-Know-On-the?utm_source=chatgpt.com "How Can We Know When Language Models Know? On the Calibration of Language Models for Question Answering | Transactions of the Association for Computational Linguistics | MIT Press"
[5]: https://aclanthology.org/2023.emnlp-main.330/?utm_source=chatgpt.com "Just Ask for Calibration: Strategies for Eliciting Calibrated Confidence Scores from Language Models Fine-Tuned with Human Feedback - ACL Anthology"
[6]: https://arxiv.org/abs/2605.27752?utm_source=chatgpt.com "Asking Is Not Enough: Protocol Sensitivity in LLM Confidence Calibration"
[7]: https://www.sciencedirect.com/science/article/pii/S0378375810002703?utm_source=chatgpt.com "On Bayesian learning from Bernoulli observations - ScienceDirect"
[8]: https://aclanthology.org/2023.findings-eacl.150/?utm_source=chatgpt.com "Selective-LAMA: Selective Prediction for Confidence-Aware Evaluation of Language Models - ACL Anthology"


## 备注

（粘贴人可记录：平台访问时间 / 会话标题 / 其他观察，选填。）

*状态: 已回填*