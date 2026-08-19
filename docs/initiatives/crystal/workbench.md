# Workbench 设计 v1（个人工作台：裁决面 + 洞察面）（草稿）

> 状态: 草稿 · 系统: crystal · 版本: v1 · 最后更新: 2026-08-18
> 关联: [crystal PRD](prd.md)（US-W1~W5 / A6~A8）· [目标模型](foundation.md)（S3 裁决）·
> [里程碑](milestone.md)（M2 前置产物）· [API 契约](api-contract.md)（§2.4 路由）·
> [workbench-vs-debug-roles](../../notes/2026-08-14-workbench-vs-debug-roles.md) · MR-011
> 定位: 本文是 MR-011 的 **产品 + 权限设计**（裁决面 + 洞察面双轨）；API 契约细节见 api-contract §2.4，
> 页面布局为方向性描述（web 是可选管理层，核心能力走 API）。

## 0. 一句话

**个人工作台 = 裁决面（确认/纠错/遗忘/scope 提权审计）+ 洞察面（统计 + 召回行为复盘）双轨一等能力**，
个人 key 只看自己 owner 数据；admin 的 trace/embedding 日志级调试与个人数据**物理隔离**（A11）。

## 1. 背景与目标（承接 MR-011 + workbench-vs-debug-roles）

- MR-011：用户看不到"系统记住了什么"、无法纠正 → 信任闭环缺失（P0）。
- workbench-vs-debug-roles：debug 页 = 系统管理员角色（trace/embedding 日志）；个人工作台 = 个人 key，
  只看自己 container（现为 owner），确认/纠错/遗忘 = confidence 调制的 UI 落点。
- crystal 落地后：**工作台是"写路径"不只是"看"**——confirm/correct/forget = 对账动作的界面形态
  （confirm = +Δ content；correct = 特权 Evidence → supersede；forget = retract 边）。
- **多宿主**：opencode/dsh/hermes 用户不一定开 web → 核心写能力走 API（api-contract §2.4），
  web 工作台只是"可选管理层"，不焊死。

## 2. 角色与权限边界（A6/A11 核心）

| 角色 | 数据范围 | 可做 | 端点前缀 |
|------|---------|------|---------|
| **个人 key**（read/write） | 自己 owner（`owner_id=key_id, owner_type=personal`） | 浏览/确认/纠错/遗忘/scope 提权审计/统计/召回复盘 | `/api/v2/workbench/*` |
| **admin key** | 全量（运维） | trace/embedding 日志级调试、迁移/退役 | `/api/v2/debug/*`、`/api/v2/migrate/*` |
| 其他个人 key | 无（越权 403） | — | — |

- **隔离规则**：workbench 所有端点强制 `WHERE owner_id = current_key_id`；
  `debug/traces`、`debug/embedding-logs` 仅 admin 权限可访问（A11）。
- **不出现"看别人的数据做 debug"**（PRD 隐私最小化）：洞察只用开发者自己的个人数据。

## 3. 裁决面（写侧，US-W1/W2，A3/A6/A7）

### 3.1 四动作（均落谱系边，绝不静默覆盖，v1 #2）

| 动作 | API | 语义 | 谱系落点 | content 影响 |
|------|-----|------|---------|-------------|
| **确认 confirm** | `POST /workbench/claims/{id}/confirm` | 用户认可当前 claim 为真 | 无新边（或记审计） | **+Δ content**（独立正向证据，强度按用户确认档） |
| **纠错 correct** | `POST /workbench/claims/{id}/correct` | 用户给出正确版本 | 新建 `user_correction` Evidence → 对账 **supersede**（特权，不走 LLM） | 新 claim 按网格初值 + 特权档 |
| **遗忘 forget** | `POST /workbench/claims/{id}/forget` | 撤销/清理，无替代者 | `retract` 边（to=NULL） | 该 claim 失活（status=retracted），不删证据 |
| **scope 提权审计 promote-scope** | `POST /workbench/claims/{id}/promote-scope` | 系统建议"项目内知识 → 全局"，用户**事后审计**采纳/拒绝 | 采纳 → `generalizes` 边（claim→无 scope 新 claim） | 新 claim 继承证据 |

- **correct 的特殊性**：correct 不是直接改 claim，而是**创建特权 Evidence**（`source_kind=user_correction`）
  再走对账——保证"用户说了算"同时 Evidence 不可再生地基完整（v1 #4）。
- **confirm 的强度档**：确认 = 用户对现有 claim 的背书，计分按"用户显式确认"档（对账技术设计 v1 强度权重表），
  低于"另一场合 verbatim 明确陈述"（0.8）但高于 agent 提炼（0.3）——待对账设计细化。
- **forget 后恢复**：被 superseded/retracted 的 claim 不自动恢复；用户可再 correct 显式重建（v1 #27）。

### 3.2 scope 提权建议（US-W2 / A7）

- **建议产生**（系统主动）：对账/召回技术设计 v1 定判据（S1 质变：去上下文后仍为真且可复用，
  v1 #18）——一期简化为"召回命中高 + 无 scope 冲突 + 用户 confirm 过"的候选池，先出建议不自动提。
- **审计流**：建议列表（`GET /workbench/reviews?type=promotion`）→ 用户采纳/拒绝
  （`POST /workbench/claims/{id}/promote-scope {action: adopt|reject, reason?}`）→ 留审计痕迹
  （建议、决策、reason、时间——记 `workbench_audit` 表，见 §5）。

### 3.3 低置信"假说池"（调研 #10 落地，US-W5 补充）

- `content_confidence < 阈值` 或 `UNKNOWN` 的 claim 进"假说池"视图（`GET /workbench/reviews?type=low_confidence`）：
  **永久存储、可检索、可审计、可确认升级**（confirm 后脱离低置信）；默认不参与注入
  （与"不静默丢弃"解耦：可查可见，只是不默认注入）。
- 阈值：`content_confidence < 0.4` 或 NULL（UNKNOWN）→ 低置信；具体值随对账设计定案，先 0.4 起步。

## 4. 洞察面（读侧，US-W4/W5，A8）

> 与裁决面**平级**的一等能力（milestone §1）；只统计个人 owner 数据。

### 4.1 统计（`GET /workbench/overview`）

| 组 | 指标 | 来源 |
|----|------|------|
| 拓扑 | claim 总数（active/superseded/disputed/retracted）、谱系边数（按 edge_type）、claim_evidence 关联数 | claim/lineage_edge/claim_evidence |
| 价值信号分布 | content_confidence 分档（<0.4/0.4–0.7/>0.7/NULL）、复用/outcome 计数（一期恒 0） | claim + claim_usage |
| source_kind 构成 | evidence 按 source_kind 计数、extraction_type 构成 | evidence |
| 处理健康 | evidence_processing 状态分布（pending/processing/done/failed + 卡点步骤 topN） | evidence_processing |

### 4.2 召回行为复盘（`GET /workbench/reviews` + `GET /workbench/reviews/{trace_id}`）

- 每次召回像 trace 一样摊开（US-W5 / A5）：
  1. **粗排全部候选**（prefilter 命中 + 向量分）；
  2. **精排每个因子分数**（relevance / content / reuse·outcome，一期 reuse 恒 0）；
  3. **截断/排除项**：cap 砍了哪几条、为什么（不静默丢弃，MR-017 教训）；
  4. **低置信标注**：只标注不静默丢弃。
- **trace 契约**：与召回技术设计 v1 的 `explain` 结构一致（api-contract §4.2），
  workbench 只是把 explain 落库可回看（`workbench_review` 表，见 §5）。
  **✅ 已实现（2026-08-19，G1）**：`workbench_review` 表落地 + 落库 + reviews 端点真实化。
- **与 debug 的边界**：workbench/reviews 只含**个人召回行为**（自己 owner 的查询/注入）；
  `debug/traces` 是 admin 的全量运维 trace（embedding 日志、所有 key 的调用）——两者数据源可以同表，
  **权限层隔离**（A11）。

## 5. 数据落点（新增表，M2）

| 表 | 用途 | 字段（骨架） |
|----|------|-------------|
| `claim_activity` | **变更审计日志**（承接 lineage_edge 触发证据职责 + workbench 审计动作；entity-attributes §5.1） | `id, claim_id, action(superseded_by/generalized_to/confirmed/retracted/promoted_scope/poison_warning), actor_type(system/user/admin), actor_id, triggered_by_evidence_id, detail, created_at` |
| `workbench_review` | 召回复盘 trace 落库（个人可回看） | `id, owner_id, scope, query, source(search/context_inject), trace_json(explain 结构), created_at` |

> 两表都是**运维/审计辅助**，非核心模型（Evidence/Claim/Edge 之外）。`claim_activity` 已随 M2 建；
> **`workbench_review` 已随 G1 落地（2026-08-19）**（schema.sql §12.8 + init_crystal_db.py 增量段），
> 落库点在 recall_service.save_recall_trace（/search、/context-inject include_explain=true 时）。
> **`claim_activity` 与原 `workbench_audit` 合并为同一张表**（2026-08-18 定案，v1 #35）：
> 对账自动变更（superseded_by/generalized_to）、用户裁决（confirmed/retracted/promoted_scope）、
> 投毒告警（poison_warning）统一落这一张 append-only 审计日志；scope 提权"建议"本身记
> `action=promoted_scope, detail={suggested:true}`，采纳/拒绝记 `detail={decision:adopt|reject}`。

## 6. 页面布局（方向性，web 是可选管理层）

```
个人工作台（/workbench，个人 key 登录）
├── 裁决面
│   ├── 我记住了什么（claim 列表：active 优先，可点开证据/谱系）
│   │   ├── 确认 / 纠错（弹窗输入正确版本）/ 遗忘
│   ├── 待审计：scope 提权建议（采纳/拒绝 + reason）
│   └── 假说池（低置信，可确认升级）
└── 洞察面
    ├── 统计（拓扑 / 价值分布 / source_kind 构成 / 处理健康）
    └── 召回复盘（trace 列表 → 展开：粗排全貌 / 精排分数 / 截断项 / 低置信标注）
```

- 一期只做**只读洞察 + 纠错/遗忘**最小闭环（workbench-vs-debug-roles 分两档：先最小闭环，确认队列下一档）。

## 7. 验收标准（对应 PRD A6/A7/A8 + US-W*）

- [ ] **US-W1 / A6**：个人 key 登录看到自己 owner 的 claim；confirm/correct/forget 生效且可追溯（谱系边可查）。
- [ ] **US-W2 / A7**：scope 提权建议可见、采纳/拒绝留痕（workbench_audit）；拒绝不影响原 claim。
- [ ] **US-W3**：owner 提权（审批面）一期**不开放**（依赖团队 owner P1），页面置灰/隐藏。
- [ ] **US-W4 / A8**：overview 统计可用，只统计个人 owner 数据。
- [ ] **US-W5 / A5**：reviews 每次召回摊开粗排/精排/截断/低置信；`explain` 结构与召回设计一致。
- [ ] **A11**：workbench 端点越权 403；debug/traces 仅 admin 可访问；个人 review 不含他人数据。
- [ ] **多宿主**：裁决四动作均可纯 API 调用（插件可调），web 仅消费同一 API。

## 8. 未决 / 后续

- **confirm 强度档具体值**：归对账技术设计 v1 强度权重表（本设计只定语义"确认 = 正向独立证据"）。
- **scope 提权建议判据**：归召回/对账设计（§3.2 一期简化为候选池）。
- **确认队列（写前把关）**：workbench-vs-debug-roles 的"下一档"（写前 confirm 队列），一期不做。
- **团队 owner（P1）**：owner 提权审批面 + 团队视图随 P1。

*状态: 草稿 · 最后更新: 2026-08-18*
