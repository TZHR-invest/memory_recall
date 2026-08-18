# 对账技术设计 v1（Evidence → Claim 写路径）（草稿）

> 状态: 草稿 · 系统: crystal · 版本: v1 · 最后更新: 2026-08-18
> 关联: [目标模型 v1](v1.md)（§两链路 / §置信度与价值信号）· [实体属性文档](entity-attributes.md)（表结构）·
> [里程碑](milestone.md)（M2 前置产物 §4.1）· [API 契约](api-contract.md)（§2.2）· [PRD](prd.md)（US-R1~R4 / A1~A3）
> 定位: 本文是 **对账（写路径）的实现设计**——worker 形态、事务边界、retry、reinforce 计分
> （强度权重表 / 派生折扣分型 / 幂等键）、supersede/correct 流程。
> 读路径（召回）见 [召回技术设计 v1](recall-design.md)。

## 0. 一句话

**Evidence 落库（ms 级，202）→ evidence_processing 状态机 → 对账 worker 异步推进：
定位相关 Claim → 碰撞判定（新事实 / 冗余 reinforce / 冲突 supersede / 用户纠正特权 supersede）→
在单事务内写 Claim + lineage_edge + claim_evidence + status 物化 → 更新 content_confidence（reinforce 计分）。**

## 1. 写路径总览（与 entity-attributes §3 状态机对齐）

```
POST /api/v2/evidence  (202)
   │ ① 落 evidence（append-only，语义不可变）
   │ ② 建 evidence_processing 行: state=pending, current_step='embedding'
   ▼
[异步] 对账 worker（扫描 evidence_processing WHERE state IN (pending,processing,failed)）
   │ ③ embedding 步: 生成向量 → current_step='reconcile'
   │ ④ 对账步: 定位候选 claim → 碰撞判定 → 单事务写
   │ ⑤ 完成: state=done, current_step=NULL
   │ ⑥ 失败: state=failed + last_error{step,message,attempts}
```

- **写接口不等待对账**（v1 #17 写路径可靠性）：客户端同步拿到 202 + evidence_id，后续状态可查。
- **worker 形态**：后台 asyncio 任务（复用 `src/background/scheduler.py` 的调度器 + 自旋 worker），
  不做独立消息队列（v1 #17 拍板"不做队列"）；进程内失败靠重试，跨进程靠 evidence_processing 表状态兜底
  （重启后重新扫描 pending/failed）。

## 2. 对账 worker 设计

### 2.1 扫描与并发

```text
轮询：每 N 秒（默认 5s，可配置）扫描
  SELECT evidence_id FROM evidence_processing
  WHERE processing_state IN ('pending','processing','failed')
    AND updated_at < NOW() - interval '30s'     -- 处理中超时兜底（防死 worker 卡 processing）
  ORDER BY (evidence JOIN observed_at) LIMIT batch_size(默认 50)
```

- **processing 超时兜底**：`updated_at` 超过 30s 未推进视为疑似死锁，重新认领（CAS 更新
  `processing_state='processing' WHERE updated_at < NOW()-30s`）。
- **单 worker 串行 + 批量**：一期单 worker（个人自托管规模），避免同 evidence 并发对账竞争；
  batch 内逐条处理。

### 2.2 事务边界（关键）

> **对账产物单事务提交**（v1 #25 status 物化与写边同事务；entity-attributes §0 原则）。

```text
BEGIN
  1. 写新 Claim（若需）: INSERT claim (id, statement, claim_kind, content_confidence 初值, scope, owner, status='active', embedding)
  2. 写 lineage_edge（若 supersede/generalize/retract）: INSERT lineage_edge (from, to, type, reason)   -- 无触发证据字段
  3. 写 claim_evidence（支持关联）: INSERT (claim_id, evidence_id, role='support')
  4. 写 claim_activity（审计日志）: INSERT (claim_id, action, actor_type, triggered_by_evidence_id, detail)  -- 因果追溯在此
  5. 更新 status 物化: UPDATE claim SET status = 'superseded' WHERE id IN (被取代的旧 claim)   -- 同事务
  6. 更新 content_confidence: 按 reinforce 计分（§4）更新目标 claim
  7. 推进 evidence_processing: state=done
COMMIT
```

- **失败即回滚整事务** → evidence_processing 保持 pending/failed 可重试（幂等重放安全，§5）。
- **不变量①**：新 claim 必须有至少 1 条 claim_evidence（同事务写入，DB 层无强约束，
  应用层保证——SQL CHECK 无法跨表，靠事务原子性）。
- **审计日志同事务**：边不驻留触发证据（2026-08-18 定案），因果追溯（谁/哪条证据/什么动作）
  写 `claim_activity`（entity-attributes §5.1），与边同事务，保证"变更 + 审计"原子。

### 2.3 对账步的碰撞判定（核心逻辑）

```
输入: 新 evidence E（content, source_kind, scope, owner, extraction_type）
1. 定位候选: 向量检索同 owner 下 active claim（top-K=20）+ 同 scope 兜底
   （user_correction 跳过 LLM 定位，直接取"用户指认的 claim"，见 §3.1）
2. 对每个候选 C 判定关系（LLM 结构化判定，temperature=0）:
   - CONFLICT  : E 与 C 矛盾 → 冲突路径（§3.2）
   - REDUNDANT : E 是 C 的近似重复/同源复述 → reinforce 候选（§3.3）
   - SUPPORT   : E 支持/补充 C → reinforce 候选
   - UNRELATED : 无关 → 建新 claim 候选
3. 汇总:
   - 无冲突且无候选 → 建新 claim（statement 从 E 提炼，claim_kind 判定）
   - 有 reinforce 候选 → 追加 claim_evidence + 计分（§4）
   - 有冲突 → 按冲突路径（§3.2）
   - 用户纠正 → 特权 supersede（§3.1）
```

- **LLM 定位 vs 规则定位**：候选定位用向量（规则，无 LLM 成本）；碰撞判定用 LLM（一次调用，结构化 JSON）。
  `user_correction` 例外：用户已指认目标 claim，不 LLM。

## 3. 三条主路径

### 3.1 用户纠正（特权 supersede，US-R3 / A3）

```
POST /workbench/claims/{id}/correct {new_statement}
  → 创建 evidence: source_kind='user_correction', content=new_statement, source_ref={session,message}
  → 对账步: 直接 supersede 指认的 claim（不走 LLM 碰撞）
     1. 新 claim: statement=new_statement, claim_kind=沿用旧 claim（或 LLM 判定）
     2. edge: old --supersedes(reason="用户纠正")--> new
     3. claim_activity: (old, action='superseded_by', actor_type='user', triggered_by_evidence_id=correction_ev, detail={new_claim_id})
     4. claim_evidence: new ← correction_ev（+ 旧 claim 的证据传递？——不传递，新 claim 只引用纠正证据
        + 可选保留旧证据（见下））
     5. status: old→superseded, new→active
```

- **旧证据是否传递**：**不自动传递**（纠正 = 用户否定旧结论的证据基础）；新 claim 只引用
  `user_correction` Evidence。若用户想保留部分旧证据，可在后续 confirm 时补。
  （与 v1 #27"被 superseded 不自动恢复"一致：谱系是历史，不级联。）
- **幂等**：同一会话消息对同一 claim 重复 correct → 幂等键命中（§5），返回既有结果。

### 3.2 冲突（supersede，US-R2 / A3）

```
E 与 active claim C 冲突:
  1. 新 claim C': statement 从 E 提炼（或 E 原文），claim_kind 判定
  2. edge: C --supersedes(reason="新证据冲突: <E 摘要>")--> C'
  3. claim_activity: (C, action='superseded_by', actor_type='system', triggered_by_evidence_id=E, detail={new_claim_id: C'})
  4. claim_evidence: C' ← E
  5. status: C→superseded, C'→active
  6. content: C' 按网格初值（E 的 source_kind × claim_kind）; C 不再计分
```

- **多个候选冲突**：逐个 supersede（每个一条边）；若冲突候选过多（>3），视为"投毒信号"
  （B4 guard 的雏形——一期只记录告警日志 + workbench 假说池可见，不做暂停破坏，B4 归完整项目）。

### 3.3 冗余 reinforce（US-R4 / A3）

```
E 与 active claim C 冗余/支持:
  1. claim_evidence: C ← E（追加关联，role='support'）
  2. content_confidence: 按 §4 reinforce 计分更新（α 累加正向）
  3. 不建新 claim、不建边（无状态变更）
  4. 同源复述闸门: E 与 C 的既有证据同源（source_ref 同一会话/消息链）→ **不计分**（v1 独立性闸门）
```

- **不无限堆积**：reinforce 只追加证据关联 + 计分，claim 行不复制（hermes 冗余教训的 crystal 解法）。

## 4. reinforce 计分（content_confidence 更新，v1 §置信度与价值信号落地）

### 4.1 强度权重表（独立证据 × 强度，M2 细化定案）

| 证据类型 | 强度 w | 判定 | 说明 |
|---------|--------|------|------|
| artifact 验证（测试/构建/退出码通过） | **1.0** | 客观结果 | 最强 |
| 用户另一场合 verbatim 明确陈述 | **0.8** | 原文重复出现 | 独立场合才算 |
| 用户 paraphrase | **0.6** | 意思相同措辞不同 | 独立场合 |
| 用户显式确认（workbench confirm） | **0.5** | 对现有 claim 背书 | 低于 verbatim（非新陈述） |
| agent 提炼 paraphrase | **0.3** | `extraction_type=paraphrase` | 降档防自说自话 |
| agent 推断 inference | **0** | `extraction_type=inference` | 不给分（v1 规则） |
| 仅被召回 / 被使用（report_effect） | **0** | 复用/outcome 独立通道 | **永不喂 content**（v1 #8 三信号独立） |
| 用户纠正（supersede 场景） | 不参与计分 | — | 走特权 supersede，不是 reinforce |

### 4.2 派生折扣分型（claim→claim 派生）

| 派生链 | 每跳折扣 | 说明 |
|--------|---------|------|
| 常规 claim→claim（generalizes/supersede 继承证据） | **×0.7** | v1 #6 落地，防链式推理自我强化 |
| 决策/推断类派生 | **×0.5**（可更严） | 高层抽象漂移风险大 |
| 偏好类派生 | **×1.0**（不折扣） | 偏好稳定，提炼不易漂移 |

- **折扣应用**：新 claim 从旧 claim 继承证据权重时（generalizes 场景），继承的证据强度 × 折扣
  后才计入新 claim 的 α/β。

### 4.3 计分公式与 Beta 更新

```
score = Σ(独立证据强度 w × 派生折扣) − Σ(矛盾证据强度 w)

Beta 更新（对目标 claim）:
  α += Σ(独立证据强度 × 折扣)      # 正向证据 mass
  β += Σ(矛盾证据强度)             # 负向证据 mass
  content_confidence = α / (α + β)   # Beta 期望，概率语义供展示

初值（建 claim 时）:
  (α₀, β₀) = 网格先验（entity-attributes §7.4: source_kind × claim_kind 的 Beta 参数）
```

- **α+β 上限**（可选，防单 claim 无限累积）：α+β ≤ 100（超出后新证据只小幅移动，工程 heuristic，V2 校准）。
- **负向通道**：矛盾证据（执行失败/用户纠正/代码对不上）→ 触发 supersede（不是加分）；
  contradicts 仲裁后改写 supersede（v1 #23）。计分不成立：冲突 claim 不因"说得多"保持高分。

### 4.4 幂等键（v1 #17 重试防线，entity-attributes §2 修正注）

- **键 = source_ref 会话消息 ID + content 哈希**（如 `sha256(session_id|message_id|content)` 前 32 位）。
- 落库时查 `evidence` 表：同键已有 → 返回既有 evidence_id（202 + accepted=false），不重复落库/不重复对账。
- 幂等键冲突（同键不同 payload）→ 409（api-contract §3.3）。

## 5. 状态机与重试

| 状态 | 含义 | 进入 | 退出 |
|------|------|------|------|
| `pending` | 待处理 | 落库时 | 认领 → processing |
| `processing` | 处理中 | 认领 | 完成 → done；失败 → failed；超时 → 重新认领 |
| `done` | 完成 | 全部步骤成功 | 终态 |
| `failed` | 失败 | 任一步抛错 | 重试（attempts < 3）→ pending；attempts ≥ 3 → 停留 failed + last_error 告警 |

- **重试策略**：指数退避（1s / 5s / 30s），`last_error.attempts` 计数；
  3 次后停留 failed，`GET /evidence/{id}` 可见卡点步骤（US-E2，不静默消失）。
- **current_step 推进**：每步完成更新 `current_step`（embedding → reconcile → NULL）；
  步骤名是数据不是列（entity-attributes §3），加步骤只加字符串。

## 6. 投毒信号（B4 雏形，一期只记录）

- 单条 evidence 触发 >3 条 supersede → 记 `workbench_audit`（type='poison_warning'）+ 日志告警，
  workbench 假说池可见；**不暂停破坏**（B4 guard 归 crystal 完整项目，PRD §4）。

## 7. 验收标准（对应 PRD A1/A2/A3 + US-R*）

- [ ] **A1**：写 evidence → 202 + pending → 对账自动生成/更新 claim；失败卡点可见（failed + last_error.step）。
- [ ] **A2**：对账生成 claim 必带 claim_evidence（不变量①）；evidence 不可变（append-only 无 update/delete 路径）。
- [ ] **A3**：correct 生成 supersede 边 + reason；旧 claim status=superseded 不丢；新 claim 引用纠正证据。
- [ ] **US-R4**：同源复述不 reinforce（独立性闸门生效）；inference 证据不喂分；被使用不喂分。
- [ ] **幂等**：同键重复 POST 不重复落库；对账重试可安全重放（事务原子）。
- [ ] **性能**：写接口 p95 < 50ms（不含对账）；对账单条 < 2s（LLM 碰撞一次）。

## 8. 未决 / 后续

- **LLM 碰撞判定的 prompt 与结构化输出 schema**：实现时定（对账步依赖一次 LLM 调用，temperature=0）。
- **α+β 上限与折扣具体值**：工程 heuristic，上线后 A/B，V2 Beta-Binomial 收敛。
- **claim_kind 判定**（对账时）：规则（从 evidence/旧 claim 继承）vs LLM——一期规则优先，
  迁移映射原样带类型；新 claim 从 E 提炼时 LLM 判定一次。

*状态: 草稿 · 最后更新: 2026-08-18*
