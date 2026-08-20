# Crystal 效果评估设计 v1（添加数据 → 召回）

> 状态: 草稿 · 系统: crystal · 版本: v1 · 最后更新: 2026-08-19
> 关联: [召回技术设计](recall-design.md)（explain/trace 契约）· [对账技术设计](reconciliation-design.md)（写路径）·
> [测试策略](test-strategy.md)（三层分级）· [PRD](prd.md)（US-S1/S2 / A4/A5）· [MR-012](../../issues/MR-012-performance-claims.md)（数字失真教训）·
> [调研线索](../../notes/2026-08-14-agent-memory-state-validity-thread.md)（LongMemEval-S / LoCoMo-V2 / BEAM 10M 首次提及）
> 定位: 本文定 **crystal "添加数据 → 召回"效果的量化验证方案**——公共评估集接入、ingest 适配、
> 评测口径、runner 结构、基线建设。**不做**写路径功能设计（见对账设计）与测试用例代码（见测试策略）。

## 0. 一句话

**把公共长期记忆评估集（LongMemEval 首选）的对话历史经 ingest 适配器灌入 crystal，
逐题跑 `/api/v2/search`，用数据集自带标注算证据召回率（Recall@k / MRR），
得到可复现、可对比的效果基线；端到端 QA 准确率作为第二口径后置。**

## 1. 背景与目标

### 1.1 为什么做

- 项目要验证的正是**通用场景**："添加数据 → 召回"（写 evidence → 对账生成 claim → 查询召回）。
  现有验证手段是真实库 E2E 冒烟 + 少量人工抽样，**没有量化基线**，效果好坏说不清、改版无法对比。
- MR-012 的教训：README 里的数字（"召回延迟 < 50ms""50/30/20 加权"）与实测不符，
  已被列为 P2 问题。评估建设要把数字建立在**可复现口径**上。
- crystal 已具备评估所需的观测面：`/api/v2/search` 的 explain 契约（prefilter/candidates/ranked/truncated）
  + `workbench_review` trace 落库——召回过程全程可见，天然适合评估埋点。

### 1.2 公共评估集是否存在（2026-08-19 主源核实）

**存在，且是成熟生态**（HF 可下载、带 ground truth、多家内存系统已用它做横向对比）：

| 数据集 | 规模 / 形态 | 覆盖能力 | 与"添加数据→召回"的贴合度 |
|--------|------------|----------|--------------------------|
| **LongMemEval**（ICLR 2025，[GitHub](https://github.com/xiaowu0162/LongMemEval) / [HF](https://huggingface.co/datasets/xiaowu0162/longmemeval-cleaned)） | 500 题 × 5 能力（Information Extraction / Multi-Session Reasoning / Knowledge Updates / Temporal Reasoning / Abstention）；每实例 ~40 会话（S）/ ~500 会话（M）/ oracle 证据会话版 | 个人对话助手长期记忆 | **首选**：自带 `answer_session_ids`（证据会话）与 turn 级 `has_answer` 标注 → **无需端到端 QA 即可算证据召回率**；要求系统"在线解析动态对话→记忆→跨会话后回答"，正是写→召回链路 |
| **LoCoMo**（EMNLP 2023，[paper](https://arxiv.org/abs/2307.06468)） | 10 个跨 184–293 天、每约 27 会话的长对话，~300 题 | 事实召回 / 时间推理 / 多跳 | 中高：时间跨度最真实，适合第二期 |
| **BEAM**（ICLR 2026，[GitHub](https://github.com/mohammadtavakoli78/BEAM) / [HF](https://huggingface.co/datasets/Mohammadta/BEAM)） | 100 对话、2000+ 题、10 能力（含 Knowledge Update / Contradiction Resolution / Preference Following），128K–10M 多尺度 | 超长上下文 + 更新/矛盾语义 | 中：尺度偏大；其 Knowledge Update 类问题与 crystal supersede 链路对口，留第三期 |

备选（BEAM 论文对比表中出现过）：MemBench / PerLTQA / DialSim / MemoryBank——覆盖能力单一，暂不引入。

**现成评测管线参考**：[mem0ai/memory-benchmarks](https://github.com/mem0ai/memory-benchmarks)
把 LoCoMo/LongMemEval/BEAM 统一成 **Ingest → Search → Evaluate** 三阶段开源套件
（支持自托管、`--predict-only` 纯检索模式、top-k cutoff 评估）。**只借鉴其流程设计，
不依赖其代码**（其 Ingest 走 Mem0 的事实抽取，与 crystal 的 evidence/claim 架构不同）。

### 1.3 为什么不再走外部调研

按 [RESEARCH_GUIDE](../../RESEARCH_GUIDE.md) 分类，"有没有公共数据集"是 **S 类（主源可验证）**——
上表已由主源（LongMemEval/BEAM/mem0-benchmarks 的 README）直接确认，无需平台调研。
真正需要社区经验的 C 类问题（对话 benchmark 适配 evidence/claim 架构的坑、口径取舍）留到
**实施遇分歧时**再按调研流程触发（本设计已预置开放问题清单，见 §7）。

## 2. 评测口径（两条，先 A 后 B）

### 2.1 口径 A：证据召回率（主口径，先做）

- **含义**：对每个问题，用问题文本 query 跑 `/api/v2/search`，检查**证据会话对应的 claim
  是否进入 top-k 结果**。LongMemEval 的 `answer_session_ids` / turn 级 `has_answer` 就是
  ground truth（不需要 LLM 判分，便宜、稳定、贴合"召回"语义）。
- **指标**：Recall@k（k=5/10/20，证据 claim 命中 top-k 的比例）、MRR（证据 claim 首次出现位次）、
  按 5 种能力分组的 Recall@10 报表。
- **对齐说明**：LongMemEval 的 turn 是 user/assistant 混合，证据可能在被蒸馏后的 claim statement 里，
  也可能跨 claim。一期实现"证据会话 → 该会话产生的 claims（经 claim_evidence 反查）→ 命中任一即算召回"。
- **可选**：用 explain.ranked 全量（含截断）算 Recall@ALL，评估"候选定位"本身的质量。

### 2.2 口径 B：端到端 QA 准确率（后置）

- **含义**：对每个问题，answerer LLM 基于检索到的 claims 生成答案，judge LLM 与 ground truth 比对打分
  （LongMemEval 官方 `evaluate_qa.py` 就是 gpt-4o 做 autoeval；我们的 answerer/judge 用 doubao，OpenAI 兼容）。
- **成本**：500 题 × 2 次 LLM 调用（answer + judge）≈ 1000+ 次调用；只做子集或留到 P2 之后。
- **与口径 A 的关系**：A 测"系统是否把对的记忆找出来"，B 测"找出来之后是否形成正确答案"。
  A 是纯召回链路，B 混入了 answerer 能力。**一期只做 A**。

## 3. Ingest 适配器（对话 turns → evidence）

对话型评估集需要写一个适配器，把 user/assistant turns 转成 crystal 的 evidence：

```
数据集 JSON（haystack_sessions[]）
  → 逐会话：user/assistant turns 拼接为可蒸馏的文本块
  → POST /api/v2/evidence（source_kind=agent_add，source_ref 记 session_id/turn 范围，
      scope=<eval-scope>，幂等键=sha256(session_id|message_id|content)）
  → 异步对账（现有 worker）→ claim 生成（拆条/碰撞/提炼全复用现有链路）
  → 等待 processing_state=done
```

- **蒸馏粒度问题（开放问题 O1）**：LongMemEval 每个会话有多轮，直接整会话蒸馏会丢证据细节。
  候选：① 每 turn 一条 evidence（最保真，对账/拆条压力大）；② 按会话切块（折中）；
  ③ oracle 模式只灌证据会话（先验证召回链路，再上 full 模式）。
  **一期用 ③ 起步（LongMemEval oracle 文件：只含证据会话，token 量最小、成本最低），
  二期切 full 模式验证真实"在线解析"能力。**
- **owner/scope**：评测专用 API key + 专属 scope（如 `eval_longmemeval`），与真实数据隔离；
  跑完可整 scope 清理（沿用测试容器清理纪律）。
- **knowledge-update 类问题**：full 模式下同一主题新旧证据都会进库，正好验证 supersede 链路
  （旧 claim 被新 evidence 碰撞为 superseded 后不再进 active 召回——A4 状态查询的正确性）。

## 4. 评测 runner 结构

```
apps/api/eval/                     # 独立于 src/，不参与服务运行
├── datasets.py                    # 下载/缓存 LongMemEval（HF resolve URL），解析为统一格式
├── ingest.py                      # §3 适配器：turns → evidence → 等待对账完成
├── search_eval.py                 # 口径 A：逐题 /search → 对齐证据 claims → Recall@k / MRR
├── qa_eval.py                     # 口径 B（后置）：answerer + judge（doubao）
├── report.py                      # 汇总报表：分能力表格 + JSON 结果落盘
└── README.md                      # 使用说明（环境变量、命令、清理）
```

- **执行方式**：独立脚本 `venv/bin/python -m eval.run --dataset longmemeval --subset 50`，
  不并入 pytest（LLM/embedding 真调用、耗时分钟级，属实跑层）；结果 JSON 落
  `eval/results/<date>-<dataset>-<subset>.json`，可 diff 对比改版效果。
- **与测试策略的关系**：`tests/test_crystal/live/` 只做抽样质量观测；**评估 runner 是独立工具**，
  两者不混（评估跑全量数据集，测试跑固定小样本）。
- **重跑一致性**：对账是异步 worker，ingest 后需轮询 `evidence_processing` 全部 done 再开跑；
  幂等键保证重复 ingest 不重复落库（现有机制）。

## 5. 阶段划分（P0 → P3）

| 阶段 | 内容 | 出口 |
|------|------|------|
| **P0（spike，验证可行性）** | LongMemEval oracle 子集 50 题：ingest + 口径 A 跑通，拿到首份 Recall@k 数字 + 适配成本评估 | 50 题结果 + 本设计更新（O1 蒸馏粒度实测定案） |
| **P1（基线建设）** | LongMemEval 全量 500 题（oracle + full 两种模式），分能力报表，结果 JSON 固化为首份基线 | 基线报告 + eval/README |
| **P2（第二口径 + 第二数据集）** | 口径 B 端到端 QA（子集 100 题）；LoCoMo 接入（时间跨度语义） | QA 子集结果 + LoCoMo 基线 |
| **P3（更新语义专项）** | BEAM Knowledge Update / Contradiction Resolution 类子集，验证 supersede/retract 链路正确性 | 更新语义报表 |

- **P0 前置条件**：crystal API 已在跑（真实库或临时库均可，需 VOLC_API_KEY + 火山 embedding）。
- **P0 不做**：不改任何 src/ 代码（纯外部适配器 + 脚本）；若发现召回链路缺陷，另立 MR。

## 6. 与现有文档的衔接

- **explain 契约**（recall-design §4）：口径 A 的 k 截止即 explain.truncated 的分界；
  可选 Recall@ALL 直接消费 explain.candidates。
- **trace 落库**（recall-design §4 G1）：评估跑 search 时 `include_explain=true` 会落
  `workbench_review`——**评测 scope 的 trace 需在跑完后清理**（或 runner 用
  `save_trace=false` 的调用路径，见 §7 O3）。
- **A4 状态查询正确性**（test-strategy 矩阵）：knowledge-update 类问题天然覆盖"superseded 不混入"，
  可作为 A4 的评估级补充（集成测试仍按测试策略走 mock）。
- **MR-012**：README 性能数字后续改用评估与 trace 的实测口径（评估建设完成时回填）。

## 7. 开放问题（实施前逐项收敛，遇分歧按 RESEARCH_GUIDE 触发外部调研）

- **O1 蒸馏粒度**：整会话切块 vs 逐 turn 一条 evidence vs oracle 模式——P0 实测三种的成本/召回差异后定案。
- **O2 英文数据的适配性**：LongMemEval 是英文对话；crystal 的拆条/碰撞 prompt 与 doubao embedding
  主要面向中文。**英文数据集验证的是"架构链路"而非"中文效果"**——若目标含中文效果，需另备中文评估集
  （未见成熟公共中文长期记忆评估集，属空白，P1 后再评估是否自建小集）。
- **O3 trace 污染**：评估 search 是否落 workbench_review——倾向 runner 直连 `search_claims(save_trace=False)`，
  避免污染真实复盘数据；若走 HTTP 则跑完清理评测 scope 的 trace。
- **O4 召回口径的对齐细节**：证据会话→claims 的反查是"证据级"对齐；若 claim 被拆条/合并，
  命中判定需按"同证据来源的任一 claim"放宽——P0 实测后定规则。
- **O5 成本预算**：full 模式 500 题 × 每会话蒸馏（LLM 拆条）+ embedding，量级需 P0 测出
  token 消耗后再定 full 规模（可先 subset 200 题）。

## 8. 验收标准

- [ ] P0：50 题 oracle 模式跑通，输出 Recall@1/5/10 + MRR，适配器代码 + 结果 JSON 入仓；
- [ ] P1：500 题（oracle + full）基线落盘，分能力报表可复现（同环境重跑结果一致）；
- [ ] 评估 runner 不污染真实数据（专用 scope/key，跑完清理）；
- [ ] README 性能/效果数字迁移到评估口径（MR-012 关闭条件之一）。

*状态: 草稿 · 最后更新: 2026-08-19*
