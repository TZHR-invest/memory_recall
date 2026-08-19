# 对账技术设计 v2（Evidence → Claim 写路径）（M2.1 拆条升级）

> 状态: 草稿 · 系统: crystal · 版本: v2 · 最后更新: 2026-08-19
> 关联: [目标模型](foundation.md)（§两链路 / §置信度与价值信号，已拍板 #36–39）· [实体属性文档](entity-attributes.md)（表结构）·
> [里程碑](milestone.md)（M2/M2.1）· [API 契约](api-contract.md)（§2.2）· [PRD](prd.md)（US-R1~R4 / A1~A3）·
> [Claim 原子化规范](claim-atomicity.md)（M2.1 判据/双上限）· [ADR-0020](../../decisions/0020-claim-atomicity.md)（决策）
> 定位: 本文是 **对账（写路径）的实现设计**——worker 形态、事务边界、retry、reinforce 计分
> （强度权重表 / 派生折扣分型 / 幂等键）、supersede/correct 流程。
> 读路径（召回）见 [召回技术设计 v1](recall-design.md)。

> **v2 变更（2026-08-19，M2.1）**：对账步从「提炼 1 条 claim」升级为「拆条 N 条原子 claim」——
> LLM ① 拆条（输出 claims[] + event_key + evidence_quote）→ 检索候选 → LLM ② 碰撞判定批处理 N 条；
> 超上限 evidence 默认隔离留存 workbench。细节见 [§2.4 拆条（M2.1 新增）](#24-拆条m21-新增)。

## 0. 一句话

**Evidence 落库（ms 级，202）→ evidence_processing 状态机 → 对账 worker 异步推进：
拆条（LLM ①）→ 定位相关 Claim → 碰撞判定（LLM ②，批处理）→
在单事务内写 N 条 Claim + lineage_edge + claim_evidence + status 物化 → 更新 content_confidence（reinforce 计分）。**

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
  WHERE processing_state IN ('pending','failed')
     OR (processing_state = 'processing' AND updated_at < NOW() - interval '30s')
  ORDER BY updated_at ASC LIMIT batch_size(默认 50) FOR UPDATE SKIP LOCKED
```

> **2026-08-19 M2 实现拍板（pending 立即认领）**：原设计把 pending/processing/failed 统一加
> `updated_at < NOW()-30s` 条件，导致新写入的 pending evidence 要等 30s 才被处理（扫描空转）。
> 落地改为：**pending/failed 立即认领**（无时间条件），**仅 processing 用 30s 超时兜底**
> （防死 worker 卡 processing）；`FOR UPDATE SKIP LOCKED` 防多 worker 抢同一批。

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
1. 定位候选: 向量检索同 owner 下 active claim（top-K=20），scope 语义与召回预过滤一致
   （请求 scope 时匹配 claim.scope==scope 或 scope IS NULL 全局；请求 scope=NULL 只匹配全局；
   2026-08-19 M2 落地确认——避免跨 scope 知识误 reinforce/supersede）
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

### 2.4 拆条（M2.1 新增，v2）

> 依据: [Claim 原子化规范](claim-atomicity.md) §3 / [ADR-0020](../../decisions/0020-claim-atomicity.md)。
> 对账步从「提炼 1 条」升级为「拆条 N 条原子 claim」。

**双上限前置检查（§4.2）**——进入拆条前先判：

```
IF length(evidence.content) > 1500 字  OR  预期拆出 > 15 条
  → 不自动拆条/不对账
  → evidence_processing 保持 pending（或标记隔离）
  → 留存 workbench「待裁决」视图（人工决定：手动拆分/概括/忽略/删除）
  → 人工放行后才走正常对账
ELSE
  → 正常拆条流程
```

**拆条流程（分步，LLM ① → 检索 → LLM ②）**：

```
LLM ① 拆条（一次调用，temperature=0）
  输入: evidence.content + scope + 拆条指令（claim-atomicity §3 判据 + 15 条核心指令）
  输出: {
    "claims": [
      {"id": "c1", "statement": "...", "claim_kind": "...", "event_key": "e1",
       "evidence_quote": "原文子句", "relations": []},
      ...
    ]
  }
  - 不含冲突/支持字段（LLM 没看到存量结论，不猜）
  - event_key: 模型输出 e1/e2 序号（不浪费 token 在 UUID），服务端映射 extraction_id+e1
  - evidence_quote: 原文精确子句，服务端在原文字符串匹配定位（不存字符 offset）

检索候选（embedding，非 LLM）
  对每条新 claim 向量检索同 owner active claim top-K（scope 语义与召回预过滤一致）

LLM ② 碰撞判定（批处理，一次调用）
  输入: N 条新 claim + 各自检索到的候选（按 claim_id 索引）
  输出: [{"claim_id": "c1", "judgment": "CONFLICT|REDUNDANT|SUPPORT|UNRELATED", "target_claim_id": ...}]
  - 批处理省成本（N 条一次传入，不逐条调）
```

**单事务写（N 条批量，§2.2 事务边界扩展）**：

```
BEGIN
  对每条新 claim:
    1. INSERT claim (statement, claim_kind, content_confidence 初值, scope, owner, status='active',
                     embedding, event_key, created_at)
    2. INSERT claim_evidence (claim_id, evidence_id, role='support', quoted_text=evidence_quote)
    3. INSERT claim_activity（审计）
  冲突路径: 逐条 supersede（每条一条边 + status 物化）
  reinforce: 同主题证据追加关联 + 计分（claim-atomicity §4）
  推进 evidence_processing: state=done
COMMIT
```

**约束**：
- **不变量①**：每条新 claim 必须有 ≥1 条 claim_evidence（同事务，应用层保证）；
- **event_key 不参与真值**：同一 event_key 的成员被 supersede 不连带失效其他成员；
- **拆条阶段输出不含冲突/支持字段**；LLM ② 只对检索到的候选做判断；
- **超上限隔离不丢数据**：evidence 原文保留，`evidence_processing` 可见"待裁决"状态（MR-017 不静默丢弃）。

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

> **2026-08-19 M2 实现拍板（期望直接移动，α/β 不落库）**：§4.3 的 α/β 是内部状态，
> 但 schema 只物化 `content_confidence`（Beta 期望）。落地实现：**不在 schema 加 α/β 两列**，
> 直接在期望上按证据强度移动——
> `reinforce_score(current_conf, weight, discount)`：
>   - `current_conf == NULL`（UNKNOWN）→ 初值 = `weight × discount`（单证据期望）
>   - 有值 → `conf += (1 - conf) × (weight × discount) × 0.2`（向 1 移动，单条 reinforce
>     移动上限 20%，防单证据虚高；V2 Beta-Binomial 校准）
> 效果等价于 α/β 更新（正向证据单调增、inference/被使用零权重不移动、NULL 可初始化），
> 且避免 schema 演进。强度权重表 §4.1 原样实现；`extraction_type=inference` 证据权重恒 0
> （不给分，v1 规则）。

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

## 7. 验收标准（对应 PRD A1/A2/A3 + US-R*，v2 加拆条）

- [ ] **A1**：写 evidence → 202 + pending → 对账自动生成/更新 claim；失败卡点可见（failed + last_error.step）。
- [ ] **A2**：对账生成 claim 必带 claim_evidence（不变量①）；evidence 不可变（append-only 无 update/delete 路径）。
- [ ] **A3**：correct 生成 supersede 边 + reason；旧 claim status=superseded 不丢；新 claim 引用纠正证据。
- [ ] **US-R4**：同源复述不 reinforce（独立性闸门生效）；inference 证据不喂分；被使用不喂分。
- [ ] **幂等**：同键重复 POST 不重复落库；对账重试可安全重放（事务原子）。
- [ ] **性能**：写接口 p95 < 50ms（不含对账）；对账单条 < 2s（LLM 碰撞一次）。
- [ ] **拆条（M2.1）**：含多独立结论 evidence → 产出 N 条原子 claim（各自 claim_kind/claim_evidence/event_key/quote，单事务）；拆条阶段输出不含冲突/支持字段；LLM ② 批处理 N 条一次判断。
- [ ] **双上限隔离（M2.1）**：超 1500 字 / 超 15 条 → 不自动拆条、evidence 保留、workbench 待裁决可见（不静默丢弃）。

## 8. 未决 / 后续

- **拆条 LLM ① 的 prompt 与结构化输出 schema**：实现时定（claim-atomicity §3 判据 + 15 条核心指令落地，
  输出 claims[] {id, statement, claim_kind, event_key, evidence_quote, relations}）；
- **LLM ② 碰撞批处理的 prompt 与输出 schema**：按 claim_id 索引的判断数组（v2 新增，批处理形态）；
- **双上限阈值**（1500 字 / 15 条）：工程初值，按 workbench 裁决数据调整；
- **α+β 上限与折扣具体值**：工程 heuristic，上线后 A/B，V2 Beta-Binomial 收敛；
- **claim_kind 判定**（对账时）：规则（从 evidence/旧 claim 继承）vs LLM——一期规则优先，
  迁移映射原样带类型；新 claim 从 E 提炼时 LLM 判定一次。

*状态: 草稿 · 版本: v2 · 最后更新: 2026-08-19*
