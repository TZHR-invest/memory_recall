# Crystal 测试策略（草稿）

> 状态: 草稿 · 系统: crystal · 版本: v1 · 最后更新: 2026-08-18
> 关联: [里程碑](milestone.md)（M2 前置产物）· [TESTING.md](../../TESTING.md)（v5 三层分级约定）·
> [API 契约](api-contract.md) · [对账技术设计](reconciliation-design.md) · [召回技术设计](recall-design.md) ·
> [Workbench 设计](workbench.md) · [PRD](prd.md)（能力验收 A1–A11）
> 定位: 本文定 crystal 的 **测试分层、环境、矩阵、验收映射**；测试用例本身是代码（tests/），
> 本文只定策略与清单骨架（DOCUMENTATION_GUIDE §5："测试用例就是代码"）。

## 0. 原则

- **三层分级沿用 v5**（TESTING.md）：单元（mock，任意环境）→ 集成（Postgres + pgvector）→
  实跑（火山引擎，`--ignore`）。
- **每 M 出口验证 = 设计内验收标准逐条回填**（milestone §3.5）：本文的验收矩阵与各 design 的验收节一一对应。
- **命名空间隔离的测试纪律**：crystal 测试数据一律用 `crystal_test_*` 容器/scope，
  **不污染 v5 真实容器**；集成测试沿用 v5 约定"不清理自己测试数据"（人工清理，见 STATUS 测试容器清理史）。
- **LLM 依赖隔离**：对账碰撞判定 / claim_kind 判定 / 提炼是 LLM 调用——单元层全部 mock，
  集成层用固定 prompt 的录制/替身（见 §3），实跑层才真调（`--ignore` 保护）。

## 1. 测试分层

| 层 | 目录（建议） | 环境 | 内容 |
|----|-------------|------|------|
| 单元 | `tests/test_crystal/unit/` | 无 DB / 无 key | 计分公式（Beta 更新/折扣/强度表）、幂等键、碰撞判定逻辑（mock LLM）、scope 校验 helper、分页游标编解码 |
| 集成 | `tests/test_crystal/integration/` | Postgres + pgvector + schema | 写路径端到端（evidence→对账→claim）、召回管道、workbench 动作、迁移幂等 |
| 实跑 | `tests/test_crystal/live/` | 火山引擎（LLM/embedding） | 对账碰撞真实判定、提炼质量抽样（**pytest 收集时 --ignore**） |

## 2. 环境

- 集成层指向临时库：`DATABASE_NAME=memory_recall_test`（TESTING.md 环境注意点，无 TEST_DATABASE_URL）。
- crystal schema 初始化：跑 `init_db.py`（幂等建表，含 crystal schema），**不跑 setup_database.py**（全量清库）。
- **test loop scope 教训**：沿用 `asyncio_default_test_loop_scope = module`；
  crystal 集成测试文件之间避免共享全局 db 单例（MR-024 教训：两个文件不能同跑）——
  策略：crystal 集成测试**单文件独立连接**或**同文件内全部用例**，禁止跨文件共享 fixture。

## 3. LLM 依赖隔离方案

| 调用点 | 单元层 | 集成层 |
|--------|--------|--------|
| 对账碰撞判定（CONFLICT/REDUNDANT/SUPPORT/UNRELATED） | mock 返回固定 JSON | 录制替身：固定输入→固定输出的 prompt 桩（或 mock async client） |
| claim_kind 判定 | mock | 同左（一期规则优先，LLM 仅兜底） |
| statement 提炼 | mock | 同左 |
| embedding（evidence/claim 向量） | 不涉及 | 用规则向量（如 content 哈希的前 N 维）或 mock embedding service |

- **实跑层**：真实 LLM/embedding，抽 20–50 样本做质量观测（提炼准确率、碰撞判定一致性），
  不 gate CI（`--ignore`）。

## 4. 测试矩阵（对应 PRD A1–A11 + 各 design 验收）

| # | 能力 | 关键用例（骨架） | 层 |
|---|------|----------------|----|
| A1 | 证据采集 | 写 evidence 202+pending；异步对账生成 claim；失败卡点可见（failed+last_error.step） | 集成 |
| A2 | 结论溯源 | claim 必有 claim_evidence（不变量①）；evidence 不可变（无 update/delete 路径）；反查 evidence→claims | 集成 |
| A3 | 纠正闭环 | correct → supersede 边 + reason；旧 claim superseded 不丢；新 claim 引用纠正证据 | 集成 |
| A4 | 状态查询 | 只返回 active+scope 匹配；superseded 不混入；scope=NULL 全局可见 | 集成 |
| A5 | 召回可解释 | explain 含粗排全貌/精排分数/truncated/low_confidence；默认 false 零开销 | 集成 |
| A6 | 裁决面 | confirm 加 confidence；forget → retract；越权 403（他人 owner） | 集成 |
| A7 | 审计面 | promote-scope 建议/采纳/拒绝留痕（workbench_audit） | 集成 |
| A8 | 洞察面 | overview 统计只含个人 owner；reviews trace 展开与 explain 一致 | 集成 |
| A9 | 迁移 | 幂等重放（跑两次结果一致）；断点续传（中断后从断点继续）；抽样核对 claim 关联 | 集成 |
| A10 | 切换/退役 | 访问日志无旧路由（人工核对脚本）；回退演练（摘路由后 v5 正常） | 集成/手动 |
| A11 | 权限隔离 | workbench 越权 403；debug/traces 仅 admin；个人 review 无他人数据 | 集成 |
| — | reinforce 计分 | 强度权重表逐档验证（artifact 1.0 / verbatim 0.8 / inference 0）；同源复述不 reinforce；被使用不喂分；派生折扣 0.7/0.5/1.0 | 单元 |
| — | 幂等 | 同键重复 POST 不重复落库；对账重试可安全重放 | 集成 |
| — | B5 初值 | 网格档位表逐格验证（source×claim_kind → α/β）；inference 降档 ×0.7；UNKNOWN 不入表 | 单元 |

## 5. 每 M 的测试出口

| M | 测试出口（里程碑 §3.5 回填） |
|---|------------------------------|
| M1 | schema 与 design 一致（建表 SQL 对照 entity-attributes 逐字段断言）；/api/v2 骨架路由鉴权 401/403/200 冒烟 |
| M2 | 上表 A1–A8 + reinforce/幂等用例全绿；集成层真库跑通"写 evidence→对账→召回→工作台裁决"闭环 |
| M3 | A9 迁移用例（幂等重放 + 抽样核对）；M1/M2 回归全绿 |
| M4 | A10 切换核对脚本 + 回退演练记录 |
| M5 | 退役检查单（备份可重放验证 + 监控确认） |

## 6. 命令

```bash
cd apps/api
# crystal 单元（无 DB / 无 key）
venv/bin/python -m pytest tests/test_crystal/unit -q -x
# crystal 集成（需 Postgres + pgvector + init_db.py 建 crystal schema）
venv/bin/python -m pytest tests/test_crystal/integration -q -x \
  --ignore=tests/test_crystal/live
# crystal 实跑（需 VOLC_API_KEY；CI 不跑）
venv/bin/python -m pytest tests/test_crystal/live -q -x
```

## 7. 未决 / 后续

- **碰撞判定测试替身的录制方式**：实现时定（prompt 桩 vs mock async client）。
- **迁移抽样核对样本量**：A9 细化时定（建议 ≥5% 或 ≥100 条）。
- **性能基准**：写接口 p95 < 50ms、粗排 p95 < 100ms（对账/召回设计验收）——性能测试文件
  沿用 v5 `test_performance.py` 模式，单独跑（`--ignore` 默认）。
- **效果量化评估**（不属于测试层，见 [evaluation-design.md](evaluation-design.md)）：公共评估集
  （LongMemEval 等）接入 + 口径 A 证据召回率（Recall@k/MRR），独立 runner `apps/api/eval/`，
  不并入 pytest；A4 状态查询正确性可用 knowledge-update 类问题做评估级补充。

*状态: 草稿 · 最后更新: 2026-08-18*
