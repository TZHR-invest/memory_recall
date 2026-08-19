# Workbench 网络视图设计（G5：Claim × Evidence 知识网络可视化）

> 状态: 草稿 · 系统: crystal · 版本: v1 · 最后更新: 2026-08-19
> 关联: [workbench](workbench.md)（洞察面 §4）· [workbench-web-prep](workbench-web-prep.md)（§7 后续项 G5）·
> [api-contract](api-contract.md)（§2.4 路由表 / §3 信封）· [entity-attributes](entity-attributes.md)（schema）· MR-011
> 定位: 洞察面**可视化增强**——纯只读新增端点 + 前端渲染层，不改核心模型、不加表、不碰对账/召回链路。

## 0. 一句话

**网络视图 = 把「我记住了什么」从聚合数字变成可探索的图**：
claim 与 evidence 作为节点（claim 矩形 / evidence 圆点），
`claim_evidence`（支持）与 `lineage_edge`（supersedes/generalizes/contradicts/retract）作为边，
力导向布局渲染 + 点击 claim 直达裁决动作。个人 owner 隔离不变（A11）。

## 1. 背景与动机（承接 MR-011 信任闭环）

- 现有洞察面（workbench §4.1 / `GET /workbench/overview`）只有**聚合 count**：
  看不到"哪条 claim 是被哪条证据支撑的、谁 supersede 了谁、证据链长什么样"。
- 单点详情（`GET /api/v2/claims/{id}`）已含 evidences + lineage，但只能**逐个展开文本**，
  没有全局结构感，无法回答"我的记忆网络整体长什么样、哪里是孤岛、哪里是纠错链"。
- 网络视图是洞察面从"统计"走向"结构叙事"的自然进化：数据侧（claim/evidence/claim_evidence/lineage_edge
  四表）**天然是图**，缺的只是一个聚合读端点 + 一个前端渲染层。

## 2. 数据映射（复用现有模型，零 schema 变更）

| 图元素 | 来源 | 可视化 |
|--------|------|--------|
| Claim 节点 | `crystal.claim` | 圆角矩形；填充色按 `status`；边框虚实按置信（低置信/UNKNOWN 虚线）；scope 以标签显示 |
| Evidence 节点 | `crystal.evidence` | 小圆点（弱化，量大）；颜色按 `source_kind`（`user_correction` 高亮=特权证据）；hover 显示全文 |
| Claim→Evidence 边 | `crystal.claim_evidence` | 细实线（`role=support`） |
| Claim→Claim 边 | `crystal.lineage_edge` | 有向箭头 + 颜色/线型按 `edge_type`：supersedes 红 / generalizes 蓝 / contradicts 橙 / retract 灰虚线 |
| Claim 状态 | `claim.status` | active 实色 / superseded 灰 / disputed 红 / retracted 灰+删除线 |

## 3. 端点设计（api-contract §2.4 增补，纯只读）

### `GET /api/v2/workbench/graph`

权限: read（个人 owner 隔离，A11：`WHERE owner_type/owner_id` 强制）

Query 参数（一期简化，全量拉取；数据量级百~千节点足够，后续按需加分页/聚焦 BFS）：

| 参数 | 类型 | 默认 | 说明 |
|------|------|------|------|
| `with_evidence` | bool | `true` | 是否返回 evidence 节点与 claim_evidence 边（false 时只返回 claim 谱系图，更快） |

Response（信封 `data`）：

```jsonc
{
  "claims": [            // 全部 claim 节点（含非 active：superseded/retracted 是网络叙事的一部分）
    { "claim_id", "statement", "claim_kind", "content_confidence", "scope", "status", "created_at" }
  ],
  "evidences": [         // with_evidence=true 时返回
    { "evidence_id", "content", "source_kind", "scope", "observed_at" }
  ],
  "claim_evidence_edges": [   // claim → evidence 支持边
    { "claim_id", "evidence_id", "role" }
  ],
  "lineage_edges": [     // claim → claim 演变边
    { "edge_id", "from_claim_id", "to_claim_id", "edge_type", "reason", "created_at" }
  ],
  "stats": { "claim_count": n, "evidence_count": n, "claim_evidence_count": n, "lineage_edge_count": n }
}
```

- 全量单次返回（无分页）：一期数据量（个位数~百位 claim）下最简；
  后续若大 owner 再升级为 `focus={claim_id}&depth=2` 聚焦子图 + 游标。
- 非 active claim **保留返回**（不是只画 active）：supersede/retract 链正是网络视图最有价值的叙事
  （"这条被纠正过"），前端用样式弱化而非过滤。
- `retract` 边 `to_claim_id=NULL` 的：作为"终点"边返回，前端画成指向空（灰虚线+叉）。

### 错误

- 越权他人数据 → 404（与现有端点一致，不泄露存在性）。
- 无效参数（with_evidence 非 bool）→ 422（FastAPI 默认）。

## 4. 前端渲染（web/crystal/workbench.html 新增第 5 tab「🕸️ 网络视图」）

### 4.1 布局：SVG 力导向（零依赖，~120 行手写）

- 不引入 D3/Cytoscape（页面是无构建链单 HTML，保持零依赖；数据量级下自绘足够）。
- 力导向：斥力（节点间）+ 弹簧（边连接）+ 中心引力，迭代 ~150 轮收敛；
  SVG `<line>` 边 + `<rect>/<circle>` 节点 + `<text>` 标签，`<g>` 分组 + CSS class 控制样式。
- 渲染挂在固定 viewBox（如 1400×900），容器内自适应缩放。

### 4.2 交互

| 交互 | 行为 |
|------|------|
| 拖拽节点 | 固定该节点位置（其余继续受力，释放后可拖动再固定/取消） |
| hover evidence | tooltip 显示 evidence 全文 + source_kind + scope |
| 点击 claim | 高亮该节点 + 其 1 跳邻居（证据/谱系），右侧/下方面板显示详情 + 复用裁决动作按钮 |
| 点击裁决动作 | 复用现有 modal（`openCorrect` / `openForget` / `doConfirm` / `openPromote`），动作后刷新图 |
| 图例 | 固定角落：status 色 / edge_type 线型 / evidence 形状说明 |
| 缩放平移 | 一期可选：wheel 缩放 + 拖空白平移（简单 transform 实现） |

### 4.3 动作联动

- 网络视图内 confirm/correct/forget/promote 全部复用裁决面既有函数 → 网络视图是**可选管理层**的增强入口，
  不是新写路径（多宿主原则不变，workbench §1）。

## 5. 验收标准

- [ ] `GET /api/v2/workbench/graph` 返回本人 owner 全部 claim/evidence/边（含非 active），他人数据不可见（404）。
- [ ] 前端第 5 tab 渲染网络：claim 矩形 + evidence 圆点 + 两种边，图例清晰。
- [ ] 点击 claim → 高亮邻居 + 详情面板；confirm/correct/forget 动作可触发且图随后刷新。
- [ ] 空 owner（无数据）→ 图区显示空态引导，不白屏。
- [ ] 集成测试覆盖：聚合正确性 / owner 隔离 / with_evidence=false 只返回谱系。

## 6. 不做（边界）

- **不做跨 claim 语义关联**（P2 实体网络，foundation §P2 待建文档）：本视图只画**已有结构边**，
  不新增"相似度连线"等派生边。
- **不做自动布局服务端计算**：布局是纯前端展示逻辑，后端只给数据（保持后端薄）。
- **不做建议池（G2）联动**：网络视图不承担"系统主动出建议"职责（G2 归后续项）。
- **不做分页/聚焦 BFS**（一期全量）：大 owner（>1k 节点）时再升级。

## 7. 后续项

1. **聚焦子图**：`graph?focus={claim_id}&depth=2` BFS 展开，避免大图全量渲染。
2. **证据折叠**：默认只显示 claim 谱系，evidence 按需展开（`with_evidence=false` 已是雏形）。
3. **时间轴动画**：按 created_at 播放 claim/边的出现顺序（"记忆如何演化"）。

*状态: 草稿 · 最后更新: 2026-08-19*
