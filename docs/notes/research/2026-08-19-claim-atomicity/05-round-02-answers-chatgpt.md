# 05 · round-02 回答 · ChatGPT

> 归属: [README](README.md) 调研卡 · 状态: **待回填** · 日期: 2026-08-19
> 提示词: [04-round-02-prompts.md §ChatGPT](04-round-02-prompts.md)（组织层形态 / 拆条指令落地版）
> 纪律: 回答原文整段回填，**不二次概括、不改正文、不删链接**。

<!-- 将 ChatGPT 的回答原文粘贴到下面（保留其原有格式与链接） -->

## 回答原文

我会把一期方案再收紧一点：**不增加真正的 Group/Decision 实体，也不要试图用谱系边承担“同一事件里的兄弟关系”。**

可以用一个很轻的 **`group_key` / `event_key`** 作为 Claim 上的可选元数据。它不是实体、不是知识节点、没有 truth lifecycle，只是告诉系统：

> “这些 Claim 是从同一次 Evidence / 同一个决策表达中一起拆出来的。”

这样既不违反你们“Entity/Topic P2、不进核心 schema”的拍板，又能给二期留下演进钩子。

---

# 一、问题 1：一期到底要不要 Group/Decision？

## 我的建议

### 一期：不做 Group/Decision 实体

核心 schema 保持：

```text
Evidence
   ↓
Claim
   ├── scope
   ├── status
   ├── provenance
   ├── lineage
   └── optional event_key
```

其中：

```text
event_key
```

只是一个**弱组织字段**。

它：

* 不参与 Claim 真值判断
* 不参与 Claim 唯一性
* 不产生独立 Evidence
* 不拥有自己的状态
* 不允许用户单独确认/纠正/遗忘
* 不作为召回的主要对象

它只是：

> **co-occurrence / extraction grouping hint**

所以它不是 Entity/Topic，也不是实体网络。

---

## 为什么我不建议一期做真正的 Decision Group？

因为你们现在真正需要解决的是：

> **拆条以后，每条 Claim 能不能独立维护。**

而不是：

> **系统能不能理解“这四条属于同一个决策”。**

后者是 retrieval / presentation 问题，前者是 truth model 问题。

如果现在引入：

```text
Decision
  ├── Claim
  ├── Claim
  └── Claim
```

马上会产生一堆一期其实不需要解决的问题：

* Decision 自己有没有状态？
* Decision 是否可以 supersede？
* Decision 能不能被用户确认？
* Decision 被纠正时影响哪些 Claim？
* Decision 有没有 Evidence？
* Decision 和 Topic 什么区别？
* Decision 和 Project State 什么区别？

这很容易把你们带进“知识图谱一期化”的坑。

**目前没有必要。**

---

# 二、但只靠谱系 + scope，不能完全解决碎片化

这里我会修正 round-01 的一个地方。

如果只有：

```text
Claim
  ├── scope
  ├── supersedes
  ├── contradicts
  └── generalizes
```

那么**可以解决 truth lifecycle**，但解决不了：

> “这几个 Claim 原来是同一次决策表达中的几个组成部分。”

例如：

```text
C1: RSS 聚合方案倾向 Miniflux
C2: 初期最多 20 个信息源
C3: 信息源分五类
C4: 采用四阶段路线
```

它们可能完全没有 lineage：

```text
C1 ─╳─ C2
C2 ─╳─ C3
C3 ─╳─ C4
```

但它们又明显属于一次决策/规划事件。

所以如果完全没有 grouping 信息，未来想恢复这个整体，只能：

* 依靠 Evidence 再反查；
* 或依靠语义相似性重新聚类。

这两个都不够稳定。

---

# 三、因此我推荐一个非常轻的 V1：`event_key`

例如一次 Evidence：

> “我们这期先用 Miniflux，最多接 20 个源，源分五类，整个项目分四阶段推进。”

LLM 输出：

```json
{
  "claims": [
    {
      "id": "c1",
      "statement": "本项目当前阶段的 RSS 聚合方案倾向采用 Miniflux。",
      "claim_kind": "decision",
      "event_key": "e1"
    },
    {
      "id": "c2",
      "statement": "本项目初期的信息源数量上限为 20 个。",
      "claim_kind": "constraint",
      "event_key": "e1"
    },
    {
      "id": "c3",
      "statement": "本项目的信息源规划分为五类。",
      "claim_kind": "plan",
      "event_key": "e1"
    },
    {
      "id": "c4",
      "statement": "本项目采用四阶段路线推进。",
      "claim_kind": "plan",
      "event_key": "e1"
    }
  ]
}
```

数据库里甚至不需要：

```text
decision table
group table
topic table
```

只需要 Claim 有：

```text
event_key nullable
```

即可。

---

# 四、`event_key` 和 Entity/Topic 是本质不同的

这个边界我建议你们明确写进设计文档。

| 东西             | 生命周期    | 是否有真值 | 是否可被用户裁决 | 一期 |
| -------------- | ------- | ----: | -------: | -: |
| Evidence       | 永久      |     否 |        否 |  ✅ |
| Claim          | 独立      |     是 |        是 |  ✅ |
| lineage        | 随 Claim |  表达演变 |       间接 |  ✅ |
| event_key      | 辅助      |     否 |        否 |  ✅ |
| Entity/Topic   | 长期      |    可能 |      TBD |  ❌ |
| Decision Group | 独立对象    |   TBD |      TBD |  ❌ |
| Summary        | 派生      |     否 |        否 |  ❌ |

所以：

> **event_key 是“这几个东西一起出现过”的事实，而不是“它们属于某个实体”。**

这个区别非常重要。

---

# 五、二期怎么演进？

我建议自然演进成：

```text
V1

Evidence
   ↓
Claim ── event_key
```

↓

```text
V2

Evidence
   ↓
Claim
   ↓
Decision / Plan / Architecture / Topic
```

而且 V1 的：

```text
event_key = e1
```

未来完全可以迁移成：

```text
group_id = G123
```

甚至：

```text
G123
type = decision
```

所以**现在完全没必要为了未来设计实体表**。

---

# 六、一个重要的原则：event_key 不能参与 truth

例如：

```text
C1 ── event_key=e1
C2 ── event_key=e1
C3 ── event_key=e1
```

后来：

```text
C2 superseded by C5
```

不能导致：

```text
e1 invalid
C1 invalid
C3 invalid
```

`event_key` 只是：

> “历史上它们一起产生/表达。”

不是：

> “它们在逻辑上互相依赖。”

这能防止 grouping 偷偷变成新的 truth structure。

---

# 七、问题 2：我建议的 V1 JSON Schema

我会把 LLM 输出控制得相当简单。

**不要让模型输出数据库最终 schema。**

LLM 只负责：

> Evidence → 候选 Claim + claim 间的局部关系 + grouping hint

数据库层再负责：

> ID、状态、provenance、lineage persistence、时间戳等。

推荐：

```json
{
  "claims": [
    {
      "id": "c1",
      "statement": "...",
      "claim_kind": "fact",
      "event_key": "e1",
      "relations": []
    }
  ]
}
```

完整 JSON Schema：

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "object",
  "additionalProperties": false,
  "required": ["claims"],
  "properties": {
    "claims": {
      "type": "array",
      "items": {
        "$ref": "#/$defs/claim"
      }
    }
  },
  "$defs": {
    "claim": {
      "type": "object",
      "additionalProperties": false,
      "required": [
        "id",
        "statement",
        "claim_kind",
        "event_key",
        "relations"
      ],
      "properties": {
        "id": {
          "type": "string",
          "pattern": "^c[0-9]+$"
        },
        "statement": {
          "type": "string",
          "minLength": 1
        },
        "claim_kind": {
          "type": "string",
          "enum": [
            "fact",
            "preference",
            "decision",
            "constraint",
            "plan",
            "goal",
            "rationale",
            "state",
            "observation"
          ]
        },
        "event_key": {
          "type": ["string", "null"],
          "pattern": "^e[0-9]+$"
        },
        "relations": {
          "type": "array",
          "items": {
            "$ref": "#/$defs/relation"
          }
        }
      }
    },
    "relation": {
      "type": "object",
      "additionalProperties": false,
      "required": [
        "type",
        "target"
      ],
      "properties": {
        "type": {
          "type": "string",
          "enum": [
            "rationale_for",
            "condition_for",
            "depends_on",
            "qualifies",
            "supports"
          ]
        },
        "target": {
          "type": "string",
          "pattern": "^c[0-9]+$"
        }
      }
    }
  }
}
```

不过这里我有一个建议：

**V1 不要把 `relations` 做得太丰富。**

实际上第一版最重要的可能只有：

```text
rationale_for
condition_for
depends_on
```

`supports` 容易和 Evidence → Claim 的 support 混淆。

因为你们已经有：

```text
Evidence → supports → Claim
```

所以不要再让：

```text
Claim → supports → Claim
```

变成同一种关系。

---

# 八、Claim Kind 我建议不要定义太多

你们可能会想做：

```text
fact
preference
decision
constraint
plan
goal
rationale
state
observation
...
```

这可以，但我建议内部语义上把它们分成三大类：

### 描述类

```text
fact
state
preference
```

例如：

> 用户偏好 CLI。

---

### 行动/规划类

```text
decision
constraint
plan
goal
```

例如：

> 初期最多 20 个源。

---

### 解释类

```text
rationale
```

例如：

> 选择 SQLite 是因为不希望引入数据库运维。

其中 `rationale` 有一个特殊规则：

> **如果一句话表达“因为 A，所以 B”，A 和 B 可以是两个 Claim，但必须保留 `rationale_for` 关系。**

而不是机械拆成：

```text
C1: 因为
C2: local-first
C3: SQLite
C4: 运维
```

---

# 九、共同 scope / 时间 / 条件：不要机械变成独立 Claim

这是拆条里非常容易翻车的地方。

例如原文：

> “第一阶段最多接 20 个信息源。”

不要拆：

```text
C1: 第一阶段
C2: 信息源最多 20 个
```

正确：

```json
{
  "statement": "第一阶段的信息源数量上限为 20 个。",
  "claim_kind": "constraint"
}
```

也就是说：

> **qualifier 如果是理解该 Claim 所必需的，就折进 statement。**

---

## 再比如：

> “目前我们只在开发环境使用 SQLite。”

应该：

```text
当前开发环境使用 SQLite 作为数据库。
```

而不是：

```text
C1: 使用 SQLite
C2: 当前
C3: 开发环境
```

---

## 再比如：

> “如果后续超过 1 万个源，再考虑 PostgreSQL。”

这是一个非常典型的条件 Claim：

```text
{
  "statement": "当信息源数量超过 1 万个时，再考虑迁移到 PostgreSQL。",
  "claim_kind": "plan"
}
```

而不是：

```text
C1: 信息源超过 1 万
C2: 使用 PostgreSQL
```

因为：

> “超过 1 万”在这里不是一个独立事实，而是触发条件。

---

# 十、我建议给 statement 加一个非常硬的规则

> **每一条 Claim 必须脱离原 Evidence 后仍然能够被人正确理解。**

例如不要：

```text
“这个也先不做。”
```

因为脱离上下文不知道“这个”是什么。

应该生成：

```text
“本项目当前阶段暂不实现 XX 功能。”
```

同理：

```text
“20 个就够了。”
```

不能直接成为 Claim。

应该：

```text
“本项目初期最多接入 20 个信息源。”
```

这个规则非常重要。

---

# 十一、但不要为了 self-contained 而重复整个上下文

这里又有一个平衡。

错误：

> “在当前项目、当前开发阶段、当前 RSS 聚合模块、当前第一阶段的开发计划中，信息源数量上限为 20 个……”

太重。

更好的：

> **“初期信息源数量上限为 20 个。”**

然后依赖已有的：

```text
Evidence
scope
project_id
```

所以规则应该是：

> **自洽，但不自我膨胀。**

---

# 十二、如何防止“拆不干净”

这个问题我建议直接在 prompt 里加入一个：

> **Predicate Enumeration Test**

要求模型在生成 Claim 前，先在内部判断：

> 当前 Evidence 是否表达了多个可以独立改变真值的 predicate？

例如：

> “我们用 Miniflux，20 个源，五类，四阶段。”

模型应该识别：

```text
采用什么？
数量上限？
分类方式？
实施路线？
```

四个 predicate。

然后分别生成。

---

## 一个非常实用的 prompt 规则

可以直接写：

> **如果一句话中出现多个“主体-关系-对象”组合，并且其中任意一个对象未来可以被单独修改、否定、过期或查询，则必须拆成多个 Claim。**

例如：

```text
Miniflux
+
20
+
五类
+
四阶段
```

全部独立。

---

# 十三、如何防止“过度拆分”

再加一个反向规则：

> **不要因为句子中存在多个名词、条件、原因或修饰语就机械拆分；只有当拆出的部分可以脱离其他部分独立拥有真值状态时才拆。**

例如：

> “选择 SQLite 是因为项目强调 local-first。”

不要变成四条。

而是：

```text
C1:
项目选择 SQLite 作为本地数据库。

C2:
项目强调 local-first。

C2 --rationale_for--> C1
```

这样：

* 两个 Claim 独立；
* 原因关系仍然存在。

---

# 十四、我甚至建议加入“最小反事实测试”

这是我认为最适合你们系统的拆条判断。

对候选 Claim 问：

> **如果只把这句话中的一个部分改掉，其他部分是否仍然可以保持为真？**

例如：

> “Miniflux，最多 20 个源。”

反事实：

> “Miniflux，最多 30 个源。”

其他部分依然成立。

→ **必须拆。**

---

再看：

> “因为 local-first，所以选择 SQLite。”

改成：

> “因为 local-first，所以选择 PostgreSQL。”

这里：

* 原因和选择之间有逻辑关系；
* 但“local-first”本身仍然可以独立成为 Claim；
* “选择 SQLite”也可以独立成为 Claim。

所以：

```text
C1 local-first
C2 SQLite
R(C1,C2)=rationale_for
```

---

再看：

> “第一阶段最多 20 个源。”

如果改成：

> “第一阶段最多 30 个源。”

“第一阶段”与“20”不能分别作为两个事实存在。

所以：

```text
C1 = 第一阶段最多 20 个源
```

而不是两个 Claim。

这就是 qualifier 与 independent claim 的边界。

---

# 十五、`event_key` 怎么生成？

我建议**不要让模型生成真正的 UUID**。

因为 temperature=0 下完全没有必要把 token 浪费在 UUID 上。

只需要：

```text
e1
e2
e3
```

表示：

> 本次 Evidence 中的第几个事件组。

例如：

```json
{
  "claims": [
    {
      "id": "c1",
      "statement": "本项目当前阶段倾向采用 Miniflux 作为 RSS 聚合方案。",
      "claim_kind": "decision",
      "event_key": "e1",
      "relations": []
    },
    {
      "id": "c2",
      "statement": "初期信息源数量上限为 20 个。",
      "claim_kind": "constraint",
      "event_key": "e1",
      "relations": []
    },
    {
      "id": "c3",
      "statement": "用户偏好使用 CLI 工具。",
      "claim_kind": "preference",
      "event_key": "e2",
      "relations": []
    }
  ]
}
```

然后服务端把：

```text
e1
```

映射成：

```text
extraction_id + e1
```

即可。

---

# 十六、我建议你们最终采用的 V1 Prompt 核心指令

下面这个我认为已经可以直接拿去做 extraction agent 的 system/developer instruction。

> ### Claim 拆分规则
>
> 1. 将输入 Evidence 拆分为**最小的、语义自洽且可以独立拥有真值状态的 Claim**。
>
> 2. 判断拆分粒度时，不以句子长度、字数或语法结构为标准，而以**独立生命周期**为标准。
>
> 3. 如果两个信息未来可能被独立查询、独立纠正、独立失效、独立取代，或者由不同 Evidence 独立支持，则必须拆成不同 Claim。
>
> 4. 如果一句话包含多个可以独立改变真值的事实、偏好、决策、约束、计划或状态，应拆成多个 Claim。
>
> 5. 对每个 Claim 做“反事实修改测试”：如果只修改其中一部分，其他部分仍然可以保持为真，则应拆分。
>
> 6. 不要机械拆分原因、条件、范围、时间、主体等必要上下文。若这些信息不能独立拥有真值，而是限定 Claim 的适用范围，则将其自然地折入 `statement`。
>
> 7. 如果一个 Claim 表达“因为 A，所以 B”，可以将 A 和 B 分别表示为独立 Claim，并使用 `rationale_for` 表达 A 与 B 的关系；不得为了原子化而丢失因果关系。
>
> 8. 如果一个条件只是 Claim 的触发条件或适用范围，应保留在 statement 中。例如“当信息源超过 1 万个时考虑迁移 PostgreSQL”应作为一个完整 Claim，而不是拆成条件和行动两个无关系的 Claim。
>
> 9. 每个 Claim 的 `statement` 必须脱离原 Evidence 后仍能被正确理解，不得使用无法解析的“这个”“那个”“我们现在”“上面”等指代。
>
> 10. `statement` 应保持简洁，只补充理解该 Claim 所必需的上下文，不要把整个 Evidence 或项目背景复制进 Claim。
>
> 11. 同一次 Evidence 中由同一个决策、计划、方案或讨论事件产生的多个 Claim，使用相同的 `event_key`；`event_key` 只是组织提示，不代表它们具有共同真值，也不产生依赖关系。
>
> 12. 不要因为多个 Claim 具有相同 `event_key` 而建立 `depends_on` 关系。只有语义上存在真实依赖、因果、条件或理由关系时才建立 relation。
>
> 13. 不要把整个文档、长段落或多个独立决策原文复制为一个 Claim。原文属于 Evidence；Claim 只保存可独立维护的结论。
>
> 14. 不要为了追求最短 Claim 而产生无法单独解释、无法独立判断真值的碎片。
>
> 15. 输出的每个 Claim 必须能够明确回答：“这条 Claim 本身到底声称了什么？”

---

# 十七、我会再加一个“隐含检查”，但不一定输出

由于你们是：

> 一次 LLM 调用 + temperature=0

我反而不建议让模型输出一堆 reasoning/checklist。

可以在 prompt 中要求它内部完成：

```text
Evidence
  ↓
候选 predicate 枚举
  ↓
反事实修改测试
  ↓
qualifier 判断
  ↓
因果/条件关系判断
  ↓
最终 claims
```

但 JSON 只输出最终结果。

这样 token 成本低很多，也更容易让输出稳定。

---

# 十八、最终我建议一期 Schema 就控制在这个复杂度

如果让我现在真的给你们 V1 定稿，我甚至会进一步砍掉东西：

```json
{
  "claims": [
    {
      "id": "c1",
      "statement": "...",
      "claim_kind": "constraint",
      "event_key": "e1",
      "relations": [
        {
          "type": "rationale_for",
          "target": "c2"
        }
      ]
    }
  ]
}
```

数据库侧：

```text
Claim
├── id
├── evidence_ids
├── statement
├── claim_kind
├── event_key       nullable
├── status
├── scope
├── valid_from
├── valid_to
└── lineage
```

其中：

### 核心

```text
statement
evidence_ids
status
lineage
```

### V1 辅助

```text
claim_kind
scope
event_key
relations
```

### 暂时不要

```text
Entity
Topic
Decision entity
Group table
Summary entity
Knowledge graph
```

---

## 最后，我会这样收敛你们两个问题

### 一期最小可行

```text
                    Evidence
                       │
                ┌──────┴──────┐
                ▼             ▼
              Claim          Claim
                │             │
           event_key=e1   event_key=e1
                │             │
                └──────┬──────┘
                       │
                 lineage / relations
```

**不增加 Group 实体。**

`event_key` 只是把拆开的 Claim 重新“轻量地粘在一起”，但不参与 truth。

### 二期

当你们真实观察到：

> “用户经常需要把同一个决策的 5 个 Claim 一起召回/一起展示/一起裁决”

再把：

```text
event_key=e1
```

演化成真正的：

```text
Decision / Plan / Architecture Group
```

而且这是**从真实 usage pattern 推出来的 schema 演进**，而不是提前设计知识图谱。

---

我认为这个路线还有一个很重要的好处：**你们可以用 V1 的真实数据验证“到底需要多粗的 Claim”，而不是现在就凭直觉规定粒度。**

后面特别值得统计三个指标：

1. **Correction Blast Radius**：一次纠正影响了多少本不该受影响的语义；
2. **Evidence Contamination**：一个 Claim 的 support evidence 中，有多少其实只支持其中一部分；
3. **Reconstruction Rate**：只依赖 Claim + `event_key`，能否恢复用户原本表达的一个完整决策/计划。

如果这三个指标都健康，你们基本就找到了合适的 Claim 粒度；如果 Reconstruction Rate 低，再考虑二期真正的 Decision/Group，而不是一开始就把组织层塞进核心 schema。
