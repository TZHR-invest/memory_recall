# Workbench Web 开发准备 v1（个人工作台前端）

> 状态: 草稿（**页面 v1 已实现，2026-08-19**）· 系统: crystal · 版本: v1 · 最后更新: 2026-08-19
> 关联: [crystal PRD](prd.md)（US-W1~W5 / A6~A8）· [workbench 设计 v1](workbench.md)（产品+权限）
> · [API 契约](api-contract.md)（§2.4 路由 / §4 骨架）· [web 现状](../../../web/)（dashboard.html / debug.html）
> 定位: 本文是 workbench **web 页面开发启动前的准备文档**——范围边界、页面规格、与后端契约的差距清单、
> 任务分解、验收映射。代码开发前先读本文。

## 0. 一句话

**web 工作台 = 现有 v5 dashboard/debug 之外的 crystal 专属页面（`web/crystal/workbench.html`）**，消费现成 `/api/v2/workbench/*` 与
`/api/v2/claims/*` 接口，一期做「裁决面 + 洞察面」最小闭环（只读洞察 + 确认/纠错/遗忘 + 提权审计），
页面是可选管理层，核心能力仍走 API（多宿主不焊死 web）。

## 1. 需求来源（PRD 支柱四，US-W1~W5）

| 用户故事 | 需求 | 对应验收 |
|---------|------|---------|
| US-W1 | 裁决面·浏览/确认/纠错/遗忘（只看自己 owner） | A6 |
| US-W2 | 审计面·scope 提权建议可见 + 采纳/拒绝留痕 | A7 |
| US-W4 | 洞察面·统计（拓扑/价值分布/source_kind/处理健康） | A8 |
| US-W5 | 洞察面·召回复盘（trace 摊开：粗排/精排/截断/低置信） | A5 / A8 |
| （US-W3） | owner 审批面依赖团队 owner P1 → **一期不做**，页面置灰/隐藏 | — |

- **不静默丢弃**（PRD §1）：截断/排除项必须对用户可见 → 洞察面 trace 展示是硬需求。
- **隐私最小化**（PRD §1 / A11）：页面只用当前 key 的 owner 数据；admin debug 日志不混入。
- **多宿主**（PRD §1）：裁决四动作可纯 API 调用，web 只是同一 API 的消费界面。

## 2. 页面路径与命名（2026-08-19 拍板）

**路径：`web/crystal/workbench.html`**（crystal 专属子目录，与 v5 旧页面 dashboard.html / debug.html 物理隔离）。

| 决策点 | 结论 | 理由 |
|--------|------|------|
| 前缀用 `crystal` 而非 `v6` | **crystal** | ADR-0018 已否掉纯版本号方案（v6 与产品 v5.2.x 撞车）；后端路由是 `/api/v2`（非 v6），crystal 前缀与 ADR/文档/schema（`crystal.*`）/路由全链路命名体系一致 |
| 子目录 `web/crystal/` 而非文件名前缀 | **子目录** | crystal 后续大概率多页（evidence 浏览/迁移状态/复盘页），子目录可扩展、天然归类 |
| 页面内区分 | 标题/头部标注 "crystal 工作台" + 与 v5 页面不同主色调 | 区分成为产品语义而非文件名巧合 |
| 导航互通 | dashboard/debug/workbench 三页互相链接，各标注所属系统 | 用户不迷路 |
| 启动方式 | `python3 -m http.server 3000` 对子目录零成本 | 无需改 web/start.sh |

## 3. 范围（In / Out）

### 一期 In（本页面交付）

1. **裁决面**：claim 列表（"我记住了什么"，active 优先 + 状态/类型/scope 过滤）
   - 确认 confirm（+Δcontent）
   - 纠错 correct（弹窗输入正确版本 + reason）
   - 遗忘 forget（reason）
   - 谱系查看：点开 claim 详情（证据 + 出/入边 + 使用统计）
2. **审计面**：scope 提权建议列表（promotion）+ 采纳/拒绝
3. **洞察面**：overview 统计卡片（4 组指标）+ 假说池（低置信列表）
4. **召回复盘**：search 实验面板（带 include_explain）摊开粗排/精排/截断/低置信
   （直接消费 `POST /api/v2/search` 的 explain，不依赖 review 落库）

### 一期 Out（明确不做）

| 项 | 理由 |
|----|------|
| 召回复盘历史列表（`reviews` type=recall / `reviews/{trace_id}`） | 后端 `workbench_review` 表未落地（见 §4 差距 G1），trace 落库 501 桩 |
| owner 审批面（US-W3） | 依赖团队 owner P1，PRD §4 推后 |
| 策略工作台（高级用户调配置） | PRD §4 明确暂不建设 |
| admin debug 页（trace/embedding 日志） | 归 debug.html 角色，A11 隔离，不在本页 |
| 价值引擎遥测展示（reuse/outcome 计数） | 一期恒 0，overview 可占位显示 |

## 4. 页面规格（方向性，最终以实现为准）

```
web/crystal/workbench.html（crystal 工作台，个人 key 登录）
├── 头部：API key / API base 输入（复用 dashboard.html 模式）+ 保存
├── 导航：裁决面 | 审计面 | 洞察面 | 召回复盘（tab 切换，单文件）
│
├── 裁决面
│   ├── 过滤栏：status（active/superseded/disputed/retracted）· claim_kind · scope
│   ├── claim 列表（GET /api/v2/workbench/claims）
│   │   ├── 每行：statement + claim_kind 徽标 + content_confidence 条 + status + scope
│   │   ├── 动作：确认 / 纠错（弹窗输入 new_statement + reason）/ 遗忘（确认弹窗 + reason）
│   │   └── 展开：详情（GET /api/v2/claims/{id}：证据列表 / 谱系出·入边 / usage）
│   └── 动作结果 toast + 列表刷新
│
├── 审计面
│   ├── 提权建议列表（GET /api/v2/workbench/reviews?type=promotion）
│   └── 每条：claim statement + 建议时间 + 采纳 / 拒绝（弹窗填 reason）
│
├── 洞察面
│   ├── 统计卡片（GET /api/v2/workbench/overview）
│   │   ├── 拓扑：claim 按 status 计数 · 谱系边按类型 · evidence 关联数
│   │   ├── 价值分布：content_confidence 分档（unknown/low/mid/high）柱状图
│   │   ├── source_kind 构成：evidence 按 source_kind 计数
│   │   └── 处理健康：evidence_processing 状态分布
│   └── 假说池（GET /api/v2/workbench/reviews?type=low_confidence）
│       └── 低置信 claim 列表（<0.4 或 UNKNOWN），可确认升级（复用 confirm）
│
└── 召回复盘
    ├── 输入：query + scope（可选）+ limit
    └── 结果（POST /api/v2/search include_explain=true）
        ├── results：精排返回 + 每项 scores（relevance/content/final）
        └── explain 摊开：
            ├── prefilter（scope_matched/active/passed）
            ├── candidates（粗排全貌 + rank）
            ├── truncated（截断项 + reason，不静默丢弃）
            └── low_confidence 标注
```

- **技术形态**：单文件静态 HTML + 原生 JS（对齐 web/dashboard.html 既有模式），无构建步骤，
  `python3 -m http.server 3000` 即可服务（web/start.sh）。
- **鉴权**：复用 dashboard.html 的 `X-API-Key` header + localStorage 存储模式（LS_KEY / LS_BASE）。
- **只读优先**：加载即拉 overview + claims；写动作（confirm/correct/forget/promote）单独触发 + 确认弹窗。

## 5. 后端契约差距清单（开发前置，按需补齐）

> 以下为 web 开发会触达的后端现状核对结果（2026-08-19，M3 完成态）。

| # | 差距 | 现状 | 对 web 的影响 | 建议 |
|---|------|------|--------------|------|
| G1 | **`workbench_review` 表未落地** | schema.sql 只有 `claim_activity`/`migration_state`；`GET /reviews` type=recall 返回空、`reviews/{trace_id}` 501 桩 | 召回复盘**历史**无法回看；只能现场 search 摊开 explain | **一期 web 不做历史复盘**，用 search 实验面板替代；表 + 落库归后续（见 §6 后续项） |
| G2 | `GET /workbench/reviews?type=promotion` 返回的是**已发生的审计记录**（claim_activity），非"待审计建议池" | 实现返回 action=promoted_scope 的 activity 列表 | 审计面展示的是"历史决策"而非"待办建议" | web 一期按"历史审计记录"展示（标签区分 adopt/reject）；**建议池的产生逻辑（系统主动出建议）未实现**，归后续 |
| G3 | 裁决端点错误码统一为 `{code,message,data}` 信封 | 已实现（ok_response / CrystalAPIError） | 页面 fetch 需解信封取 `data` | 前端封装统一 `unwrap()` 函数 |
| G4 | `GET /api/v2/workbench/claims` 无游标分页（limit 上限 200） | 实现为 LIMIT 直取 | 大 owner 数据量时列表截断 | 一期够用（个人数据量小）；后续按 api-contract §5 游标化 |
| G5 | claim 详情 `GET /api/v2/claims/{id}` 已含证据/谱系/usage | 已实现（recall_service.get_claim_detail） | 详情展开数据齐备 | 无缺口 |
| G6 | confirm 无 body；correct 需 `new_statement`+可选 `reason`/`source_ref`；forget 需 `reason`；promote-scope 需 `action` | 已实现（workbench.py CorrectRequest 等） | 前端表单字段明确 | 无缺口 |

**结论**：web 一期可用的后端面 = 裁决四动作 + overview + claims 列表 + promotion 审计记录 + 低置信假说池 +
search explain。**缺口只影响「召回复盘历史」与「提权建议池」两个非一期能力**，不阻塞最小闭环。

## 6. 任务分解（建议顺序）

> **2026-08-19：Phase 0–4 已全部实现**，落点 `web/crystal/workbench.html`（单文件，四个 tab）。
> **Phase 5 联调已完成**（真实库 + 个人 key，见下）；待办：无。

### Phase 0：骨架与共享基建（✅ 已实现）
- [x] P0-1 新建 `web/crystal/workbench.html`（单文件，crystal 冷绿主色调，与 v5 灰蓝区分）
- [x] P0-2 基建：API base/key 输入 + localStorage 持久化 + `X-API-Key` header
- [x] P0-3 基建：统一信封解包 `api()`（抛错带后端 message）+ toast + 错误展示
- [x] P0-4 dashboard.html / debug.html 导航加 crystal 工作台入口（互相可达）

### Phase 1：洞察面（✅ 已实现）
- [x] P1-1 `GET /overview` 四组统计卡片 + 价值分布柱状图（CSS bar）
- [x] P1-2 `GET /reviews?type=low_confidence` 假说池列表（可确认升级 → 复用 confirm 动作）
- [x] P1-3 空态/加载态/错误态处理

### Phase 2：裁决面（✅ 已实现）
- [x] P2-1 `GET /workbench/claims` 列表 + 过滤栏（status/claim_kind/scope）
- [x] P2-2 claim 详情展开（`GET /api/v2/claims/{id}`：证据/谱系/usage）
- [x] P2-3 confirm 动作（+Δcontent）+ 结果反馈（读取返回 content_confidence）
- [x] P2-4 correct 弹窗（new_statement + reason）→ 调 correct
- [x] P2-5 forget 确认弹窗（reason）→ 调 forget（读取返回 status）
- [x] P2-6 动作后列表刷新 + 详情谱系可查

### Phase 3：审计面（✅ 已实现）
- [x] P3-1 `GET /reviews?type=promotion` 历史审计记录列表（adopt/reject 标签）
- [x] P3-2 promote-scope 采纳/拒绝（action + reason）——针对 scope 非空且 active 的 claim

### Phase 4：召回复盘（✅ 已实现）
- [x] P4-1 search 实验面板（query/scope/limit + include_explain=true）
- [x] P4-2 explain 摊开渲染：prefilter / candidates / truncated / low_confidence

### Phase 5：收尾（✅ 已完成，2026-08-19）
- [x] P5-1 与后端联调（真实库，个人 key）——**详见 §6.1 联调记录**
- [x] P5-2 越权场景验证（无效 key → 401；个人 key 访问 debug → 403；scope 伪装 → 403）
- [x] P5-3 更新 docs/STATUS.md + 本文状态

### 6.1 联调记录（2026-08-19，真实库 + rk_live key）

**前置动作**：API 容器重启（原进程 08-13 启动，crystal /api/v2 路由未加载；`./restart.sh restart` 后 21 条 v2 路由生效，v5.2.3 服务正常）。

| 验证项 | 结果 | 备注 |
|--------|------|------|
| overview 统计 | ✅ | 15 active claim / 22 evidence / 25 关联 / 全 high 置信 / agent_add 22 / done 22 |
| claims 列表 | ✅ | 15 条，字段齐全（claim_id/statement/kind/conf/scope/status/created_at） |
| claim 详情 | ✅ | 证据 + 谱系 + usage 全返回 |
| search + explain | ✅ | prefilter/candidates/truncated/low_confidence 结构确认 |
| **confirm** | ✅ | conf 0.8 → 0.82（+Δ content 强度 0.5 档） |
| **correct** | ✅ | user_correction 证据 + 旧 claim superseded + 新 claim active（conf 0.8571 特权档）+ supersedes 边 + 证据继承 |
| **forget** | ✅ | status → retracted + retract 边 to=NULL |
| **promote-scope reject** | ✅ | 审计记录落库（decision:reject + reason），原 claim 不受影响 |
| 权限隔离 A11 | ✅ | 无效 key 401 / 无 key 401 / 个人 key 访问 debug 403 / scope uuid 前缀伪装 403 |
| 现场恢复 | ✅ | 联调产生的 superseded/retracted 链保留（设计产物），correct 重建 active 手电 claim |

**联调发现并修复**：
- explain.prefilter 实际字段为 `{owner_id, scope, scope_matched, active_only}`（页面原读 `active`/`passed`）→ 已修正
- explain.candidates 实际字段为 `{claim_id, relevance, rank}`（页面原读 `raw_score`）→ 已修正
- search results 补展示 reuse 分（价值引擎信号可见）

**注意事项**：claim_id 为完整 32 位串，测试脚本截断会导致 404（页面用完整 id，不受影响）。

## 7. 后续项（不在本开发范围，记录备查）

1. **G1 补全**：`workbench_review` 表（schema.sql crystal 段）+ 召回 trace 落库 + `reviews?type=recall` / `reviews/{trace_id}` 真实化——workbench 设计 §5 已定义表结构，落库点在 recall_service 或 search 端点。
2. **提权建议池（G2）**：系统主动出建议（workbench §3.2 候选池判据：召回命中高 + 无 scope 冲突 + 已 confirm），一期只有用户手动 promote-scope。
3. **列表游标分页（G4）**：按 api-contract §5 游标化 claims 列表。
4. **owner 审批面（US-W3）**：团队 owner P1 后再做。

## 8. 验收映射（对应 PRD / workbench 设计）

| # | 验收 | 本页面落点 |
|---|------|-----------|
| A6 | 裁决面：个人 key 只看自己数据；确认/纠错/遗忘生效可追溯 | Phase 2（列表 owner 过滤 + 动作 + 详情谱系可查） |
| A7 | 审计面：scope 提权建议可见、采纳/拒绝留痕 | Phase 3（promotion 记录 + adopt/reject） |
| A8 | 洞察面：统计 + 召回复盘可用，只用个人数据 | Phase 1 + Phase 4（overview + search explain） |
| A5 | 召回可解释：粗排全貌 + 精排分数 + 截断项，无静默丢弃 | Phase 4（explain 摊开） |
| A11 | 权限隔离：admin debug 与个人数据不混 | 页面只调 `/api/v2/workbench/*` 与 `/api/v2/claims/*`，不触 debug 端点 |
| 多宿主 | 裁决四动作均可纯 API 调用 | 页面只是 API 消费端，不新增后端能力 |

*状态: 草稿 · 最后更新: 2026-08-19*
