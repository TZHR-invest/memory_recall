# Crystal 专项里程碑（北极星 · 目标模型迭代 roadmap）

> 状态: 草稿 · 系统: crystal · 版本: v1 · 最后更新: 2026-08-16
> 关联: [目标模型](foundation.md)（语义裁判）· [crystal PRD](prd.md)（用户故事/能力验收）· [渐进迁移路径](migration-path.md)（Stage A–E 工程阶段）·
> [实体属性文档](entity-attributes.md)（schema 落库）· MR-006 / MR-011 · ISSUES B/C 档
>
> 本文是 crystal 专项的 **capability 视角 roadmap**：覆盖"做什么、交付什么能力、节奏怎么走、明确不做/推后什么"。
> 工程执行阶段一律以 [迁移路径](migration-path.md) 的 Stage A–E 为准（命名空间隔离、不破坏 v5）；
> 本文每个 Milestone 都对应到 Stage，二者用同一只语言。
> 拍板问题（v1 的 B/C 档）在这里按"哪一期做"落到各 Milestone。

## 0. 一句话

**crystal 一期 = 证据采集(P0) + 对账写路径 + 状态查询召回 + 裁决/洞察个人工作台 + 旧数据迁移。**

价值引擎（衰减 / 低置信策略 / 投毒 guard / 每日自省 / 团队多来源）多为"不做或推后"，
用真实数据喂出来后二期再定。北极星是价值公式，但一期先跑通"证据→对账→召回→人可裁决"的骨架闭环。

## 1. 定位与不变项（承接用户会话决策）

- **产品名不变**："Memory Recall" 仍是主品牌；**crystal 只是本次迭代专项代号**（ADR-0018），不对外新命名。
- **洞察面归个人工作台**：理由 (i) 不要基于他人/用户隐私做 debug（用开发者自己的数据）、
  (ii) 未来高级用户可借这里的洞察调整策略配置（策略工作台暂不建设，洞察先行）。
  → 洞察面（统计 + 召回行为复盘）与裁决面**平级**，同属个人工作台（MR-011）。
- **MR-017（注入 cap）仅对 v5 有效，非 crystal 契约**：crystal 重设计 `/api/v2` 与粗排召回逻辑，
  旧的 6/6/4 硬编码与 `maxProjectMemories` 静默丢弃只在 v5 存在；crystal 设计时参考其教训（不静默丢弃）
  但**不作为必须坚持的契约**。
- **Entity / 团队 owner 是 crystal 完整项目的内容，不是一期**（见 §5 不做什么）。

## 2. 能力支柱（crystal 交付的四大块）

| 支柱 | 能力 | 一期? |
|------|------|-------|
| **证据层** | Evidence 采集（P0 add 自报）+ 处理状态机（`evidence_processing`） | ✅ |
| **对账（写路径）** | Evidence → Claim 对账：supersede / reinforce / generalize；用户纠正 = 特权 Evidence | ✅ |
| **状态查询（召回）** | 结构化预过滤(scope+active) → 向量粗排 → 精排(相关×content×复用·outcome)；截断可见 | ✅（精排因子一期简化为相关×content） |
| **个人工作台（MR-011）** | **裁决面**（确认/纠错/遗忘/审计 scope 提权）+ **洞察面**（统计 + 召回行为复盘） | ✅ |

> 遥测（S-pre / P1 复用标注 / outcome）是一期之后才开始喂价值引擎的输入，不进一期核心闭环。

## 3. Milestone 总览

| M | 迁移 Stage | 能力范围 | 出口标准 | 拍板点 |
|---|-----------|---------|---------|--------|
| **M0** | Stage 0 | 命名与规范（ADR-0018 打标） | 已完成 | — |
| **M1** | Stage A | `crystal.*` 建表 + `/api/v2` 骨架 | 空表可写，v5 零影响 | — |
| **M2** | Stage B | 证据采集 + 对账 + 状态查询召回 + **裁决/洞察工作台 v1** | 两链路可用 + 人可裁决 | **B5**（content 初值） |
| **M3** | Stage C | 旧数据迁移（memories→evidence，一次性开发者触发）+ 对账重生成 claim | 迁移幂等可回放 | — |
| **M4** | Stage D | 插件切 `/api/v2`（四端独立） | 插件不再调旧路由 | — |
| **M5** | Stage E | v5 退役（DROP 旧表，单独 commit） | 满足退役标准（连续 N 天无活跃 + 全切 + 用户确认） | — |

> M2 是能力主体；M3–M5 是迁移收尾。价值引擎各支（B3/B4/B6、衰减、复用/outcome）在 M2 之后按需排入 crystal 完整项目，非一期阻塞。

## 3.5 研发流程（每个 M 的文档门槛）

> crystal 执行遵循 [DOCUMENTATION_GUIDE §5](../../DOCUMENTATION_GUIDE.md#5-一个-feature-的完整文档流) 的
> note → ADR → design v1（含验收标准）→ 实现+测试 → 结果回填。**每个 M 开工前必须先落它的前置产物**，
> 这是"可以动手"的门槛：缺文档不动代码（特殊：M2 的 workbench 设计是 M2 自身的一部分，先于对账/召回开发）。
> 节奏（串行 M0→…→M5）保持 §3 不变，本节只加"每 M 要什么文档"。

| M | 前置产物（开工前必须落定） | 开发内容 | 出口验证（结果回填） |
|---|---------------------------|---------|---------------------|
| M0 | ADR-0018 打标（已完成） | 命名/规范落地 | 已完成 |
| M1 | ~~`entity-attributes.md` 定稿（claim 3 待定项 + claim_usage 落点）~~ **已定稿（2026-08-18）** + ~~**crystal API 契约 v1**~~ **已落稿（[api-contract.md](api-contract.md)，2026-08-18）** | ~~`crystal.*` 建表 + `/api/v2` 骨架~~ **已完成（2026-08-18，见 [STATUS](../../STATUS.md)）**：七表落地（[init_crystal_db.py](../../../apps/api/init_crystal_db.py)）+ 21 路由（证据层真实写入 + 桩）+ `verify_scope_ownership` + 统一信封 | **出口达成**：空表可写（evidence 202+pending+幂等命中）、v5 零影响（回归 402 过）、schema 与 design 一致（集成测试逐字段断言）；crystal 测试 38 全绿 |
| M2 | ~~**workbench (MR-011) 设计 v1**~~ **已落稿（[workbench.md](workbench.md)）** + ~~**对账技术设计 v1**~~ **已落稿（[reconciliation-design.md](reconciliation-design.md)）** + ~~**召回技术设计 v1**~~ **已落稿（[recall-design.md](recall-design.md)）** + ~~**crystal 测试策略**~~ **已落稿（[test-strategy.md](test-strategy.md)）** | ~~证据采集 + 对账 + 状态查询 + 裁决/洞察工作台~~ **已完成（2026-08-19，见 [STATUS](../../STATUS.md)）**：对账 worker + 碰撞判定 + reinforce 计分 + 召回三级管道 + workbench 四动作/洞察面 | **出口达成**：写 evidence→自动对账→召回→工作台裁决闭环可用；explain 截断可见；crystal 测试 73 全绿、v5 回归 402 过、真实链路 E2E 全通（含 correct supersede / forget retract） |
| M3 | **迁移脚本设计 v1**（接口/幂等/断点续传/回放） | 迁移脚本 + 对账重生成 claim | 幂等重放通过；抽样核对 claim 关联 |
| M4 | **插件切换契约**（四端各自接入/回退方案） | 四端切 `/api/v2` | 访问日志无旧路由；回退演练过 |
| M5 | **退役检查单**（备份/可重放/监控确认） | DROP 旧表（单独 commit） | 退役标准满足；可回退 |

> 产品需求层（用户故事 + 能力验收）集中在 [crystal PRD](prd.md)，各 M 的前置产物是其能力的实现化展开。

## 4. M2 详细（一期能力与节奏）

M2 = 目标模型四条支柱的落地 + 裁决/洞察工作台。

### 4.1 写路径（对账）
- `/api/v2/evidence` 上报 → `evidence` 落库（ms 级）→ `evidence_processing` 状态机
  （pending/processing/done/failed + `current_step`）→ 对账生成/更新 `claim` + `lineage_edge`。
- 用户纠正 = `source_kind=user_correction`，对账直接 supersede 现有 claim，不走 LLM 推理（v1 #4）。
- 溯源：`claim_evidence` 关系表（倾向关系表而非数组，收 entity-attributes §7）。
- **reinforce 计分**（v1 §置信度与价值信号）：独立证据 × 强度权重 × 派生折扣 − 负向 → Beta 更新；
  实现细节（强度权重表 / 派生折扣分型 / 幂等键）归对账技术设计 v1。被使用（report_effect）不喂分。

### 4.2 读路径（状态查询）
- 结构化预过滤（scope 匹配 + `status=active`）→ 向量粗排（top-K）→ 精排（相关性 × content × 复用·outcome）。
- **一期精排因子 = 相关性 × content**（复用/outcome 一期恒 0，退化为可运行形态；遥测来了再加）。
- **截断/cap 逻辑与精排分数全部可观测**（承接 MR-017 教训：不静默丢弃，见洞察面）。

### 4.3 裁决面（MR-011 写侧）
- 确认（+Δ content）/ 纠错（= 特权 Evidence → supersede）/ 遗忘（`retract` 边）/ 审计 scope 提权。
- **个人 key + API**：核心写能力走 API（插件也能调，不焊死在 web）；工作台是可选管理层。
- 权限：个人 key 只看自己 owner（个人工作台）；痕量/embedding 日志调试归 admin（承接 workbench-vs-debug-roles）。

### 4.4 洞察面（MR-011 读侧，与裁决平级）
- **统计**：记忆/claim 拓扑、价值信号分布（content 分档、复用/outcome）、source_kind 构成。
- **召回行为复盘**：每次召回像 trace 一样摊开——粗排全部候选、精排每个因子分数、
  截断逻辑（cap 砍了哪几条）、低置信项（**只标注不静默丢弃**，MR-017 教训）。
- **定位**：只用开发者自己的个人数据做洞察；未来高级用户据此调策略（策略工作台暂不建设）。

### 4.5 M2 出口标准
- 闭环可用：写一条 evidence → 自动对账 → 状态查询召回 → 工作台看到/裁决它。
- 洞察面能说明"为什么召回这条、为什么砍掉那条"。
- B5（content 初值）已拍板或已明确挂起规则（见 §6 决策门）。

## 5. 明确不做 / 推后（crystal 一期）

> **范围权威源 = [PRD §4](prd.md)**（用户视角：做什么/不做什么）；本表是**执行映射**
> （各项归入哪个机制/阶段），不重复维护决策清单——范围决策变更只改 PRD §4。

| 项 | 决定（摘要） | 归入 |
|----|-------------|------|
| **B1 衰减曲线** | 不做 DB 留存、预留位置延后启动；只在召回精排按属性现算，初始恒等项 | 推后，发现问题再激活 |
| **B2 低置信召回策略** | 不拍板；先做"召回行为洞察"，看到数据再定策略 | 洞察面承接，策略后置 |
| **B3 提炼/晋升触发** | 一期**显式触发**为主（用户「记住」+ 手动裁决）；稳定后低峰期定时跑「每日自省」 | 每日自省推后 |
| **B4 投毒 guard** | 证据处理流中做 guard：新 evidence 同时破坏大量 claim → 预警 + 暂停破坏 + 裁决页再确认 | crystal 完整项目 |
| **B5 LLM 自报信心初值** | **已定案**（2026-08-16，见 §6） | M1 schema 字段 + 初值档位表落地 |
| **B6 团队多来源加权** | 只影响召回精排，不现在设计 | 推后（团队 owner P1 之后） |
| **C2 / MR-017 注入 cap** | 仅 v5 有效，非 crystal 契约（crystal 重设计粗排） | 当期 v5 收尾 |
| **C3 / MR-009 Entity 合并** | 随 Entity 构建，暂不考虑 | 推后（P2） |
| **团队 owner（P1）** | 个人 owner(P0) 先行 | crystal 完整项目 |

## 6. 决策门 / 待研究

| 门 | 内容 | 状态 |
|----|------|------|
| **B5** | LLM 对内容自报信心不可靠——初值规则 | **已收敛定案（2026-08-16）**：冷启动初值 = source×claim_type 网格弱先验（不含自报）；**用户评审修正：root_observation_id 缓置**（P0 add + P1 report_effect 不产生复述；防线=对账规则 + 幂等键），extraction_type 保留；见 [调研最终结论](../../notes/research/2026-08-16-llm-confidence-initial-value/99-final-conclusions.md)。**实现时落初值档位表（M1 schema）+ extraction_type 字段** |
| **B2 策略** | 低置信召回阈值截断 vs 降权——等洞察面数据后定 | open（后置） |
| **B3 自省** | 每日自省触发形态 + 峰谷定价成本模型 | open（推后） |

## 7. 节奏与验收

- **节奏**：M1→M2→M3→M4→M5 串行；M2 是能力主体、允许最长周期；M3–M5 各一个 commit/
  独立可回退（尤其 M5 退役前备份）。每阶段合入即生效（命名空间隔离不破坏 v5）。
- **验收（方向性，承接 v1 验收标准）**：召回能回答"这条现在还成立吗"+"证据是什么"；
  纠正过时结论不丢、生成带 reason 的 supersede 边、无需人肉改 `is_latest`；可从 Evidence 重派生 claim。

*状态: 草稿 · 最后更新: 2026-08-16*
