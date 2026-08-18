# ADR-0017: Entity/主题降级为 P2 可选附属，不进核心

> 状态: Accepted
> 日期: 2026-08-14
> 系统: crystal
> 关联: [目标模型 v1](../designs/crystal/v1.md) · [状态有效性 thread](../notes/2026-08-14-agent-memory-state-validity-thread.md) · MR-006 · MR-009

## 背景

状态有效性 thread 的 4 对象模型把 Entity 列为核心对象（Evidence 与 Claim 都挂实体上），其用意是
"跨会话同一件事的绑定"。但原系统的实体图谱（13 种关系）本质目的是"实体关系 → 扩展召回候选 → 精排"，
是一个**提召回率的可选手段**，且价值待验证。另有"主题/category/tags"（内容分类，便于聚焦搜索）。
需要决定：Entity/主题是不是核心底层的一等对象。

## 选项

- A: **Entity 作为核心一等对象**（Evidence/Claim 都挂实体，note 原意）。
- B: **Entity/主题降级为 P2 可选附属**——不进核心，经关系表反挂 Claim，Claim 不主动关联。
- C: **完全不要 Entity/主题**。

## 决策

选 **B**。

- **Entity / entity_network（实体图谱扩展召回）** = P2 可选附属：**关掉它核心照跑**，打开只为提召回率、价值待验证；
  经**关系表反挂 Claim**（Claim 不主动关联 Entity，即核心 Claim 无 `entities[]` 字段）。
- **主题（topic / category / tags）** = P2 衍生能力：对无 scope 或跨项目记忆做"音乐/技术/…"分类，便于聚焦搜索；不做核心场景。
- 二者与 `scope`/`owner` 不同：scope/owner 是核心维度（ADR-0015），Entity/主题是可选附属。

## 理由

- 否决 A：把可选召回扩展能力焊进核心对象，核心被未验证功能耦合；且 MR-009（实体合并靠字符串唯一约束）
  是重型实体图谱的已知坑。
- 否决 C：个人记忆中按主题/实体分类确有其用（聚焦搜索、跨会话绑定），只是现在不确定价值，留作 P2 不砍死。
- B 的关键是**方向性**：核心（Evidence/Claim/Edge + scope/owner）与附属（Entity/主题）分离，
  附属通过关系表从外侧挂上，核心 schema 保持干净、关掉附属也能跑。

## 后果

- 正面：核心底层只含 Evidence / Claim / Lineage Edge（+ scope/owner），简单稳定；实体/主题作为可插拔附属。
- 负面：开实体召回前，"跨会话同一件事的绑定"只能靠语义相似（embedding）而非结构化实体，召回率可能打折扣。
- 跟进：实体召回的价值验证（何时值得开 P2）；关系表（entity_claim）设计留「实体属性文档」。
