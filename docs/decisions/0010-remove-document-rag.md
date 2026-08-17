# ADR-0010: 文档 RAG 子系统移出核心——文档不再是并行召回语料

> 状态: Accepted
> 日期: 2026-08-13
> 系统: v5
> 关联: ADR-0001（定位收敛）、ADR-0003/0004（注入路径，涉及 chunks 通道）、MR-001/002/003/005/007（随本决策关闭）、MR-019（文档→记忆蒸馏，独立评估）

## 背景

文档子系统是继承自 Supermemory 的完整 RAG 管线：`documents`/`chunks`/`chunk_entities`
三张表；`document_store`/`document_processor`/`document_chunker` + `chunking/` 包
（AST 感知代码分块等 10 个文件）；`/documents*` 五条路由；context-inject 的 chunks
召回通道；三个插件（hermes / deepseek-tui / memory-recall-codex）的 document tools。
入站管线为 chunking → embedding → LLM 摘要/实体，产物留在 chunks，**从不蒸馏为 memories**。

它与记忆系统是并列而非派生关系：两个独立语料库在同一召回入口被混合（hybrid search、
chunks 通道、语义去重的 chunk 分支、注入 cap 的 chunk 计数）。近 20 个 commit 里文档
相关修复密集（URL 去重、HTML 噪音 chunk 注入、实体图谱召回恒 0、状态机细化）；核心
链路每加一个特性（去重/cap/trace/阈值）都要为第四条通道多写一套分支——维护税是乘性的。

使用场景是 coding agent（opencode / deepseek-tui / hermes），agent 自带文件系统读写权；
chunk RAG 解决的是"没有文件系统访问权的 agent 需要知识库检索"的问题，与场景能力重叠。
PROJECT_PLAN 阶段一（文档知识闭环，MR-001~005）实际上在把产品往"文档平台"方向带，
与 ADR-0001 收敛后的定位再次分叉（MR-010 漂移模式复发）。

## 选项

- A: 保留文档系统，按 MR-001~007 继续深度建设（文档知识闭环作为路线图主线）；
- B: 文档 RAG 移出核心：删除文档存储/分块/检索与 chunks 召回通道；文档的角色收敛为
  "记忆的可选入站源"（文档 → LLM 蒸馏 → memories），是否实现由 MR-019 独立评估；
- C: 拆分为独立服务/可选模块，默认关闭，保留代码。

## 决策

选择 **B**：文档 RAG 子系统移出核心产品。`documents`/`chunks`/`chunk_entities` 表、
chunking 管线、`/documents*` 路由、context-inject chunks 通道、hybrid search 与插件
document tools 全部移除；文档对记忆系统的唯一潜在角色收敛为可选入站源，实现与否由
MR-019 另行决策。

## 理由

- **场景重叠**：coding agent 有文件系统，chunk RAG 是冗余替代品；记忆系统应存磁盘上
  没有的蒸馏事实。extract-memory 提示词已确立"代码实现在代码库中，不需要记忆"原则，
  推及文档即"文档在磁盘上，不需要 chunk RAG"；
- **定位一致**：ADR-0001 的教训是讲两个故事导致漂移；文档系统是第二个产品
  （文件同步、版本化、删除传播、失败可观测 = 文档平台），不是记忆系统；
- **价值证据不足**：chunks 通道注入优先级最低、去重时首先被挤掉；历史贡献以故障为主
  （HTML 噪音 chunk 被注入 37 次、实体图谱召回恒 0、URL 去重静默丢更新）；
- **成本**：solo 项目，MR-001~007 是一份文档平台路线图，会持续挤占记忆主线；
  移除后核心链路少一条通道，去重/cap/trace/阈值的 chunk 分支全部消失；
- **退出安全**：缝合线干净（存储、路由、召回通道边界清晰）；git 历史与 docs/archive
  保留全部实现与设计史。若条件变化（agent 无文件系统访问 / 语料量级达到语义检索
  收益线 / 多用户共享知识库），可重新立项，需新 ADR；
- **与蒸馏正交**：文档 → memories 只需要 LLM 提取 + source 溯源字段，不需要
  chunks/RAG；B 不阻塞该方向，反而释放 LLM 预算。

## 后果

- 正面：产品故事单线（对话 → 记忆 → 召回 → 维护）；核心链路少一条通道；LLM 预算从
  chunk 实体提取回归记忆蒸馏；MR-001/002/003/005/007 随本决策关闭，不再排期；
- 负面：失去长文原样召回能力（配置/指南类内容不再以 chunk 原文召回）；存量文档数据
  随实施删除（实施前需确认导出或接受丢失）；依赖 document tools 的工作流失效；
- 跟进：
  - 实施计划（表/代码/路由/插件/测试的删除清单）单独排期，登记 STATUS.md 实施跟踪；
  - MR-019：文档 → 记忆蒸馏是否值得做（触发条件、评估标准），做前按 RESEARCH_GUIDE 调研；
  - PROJECT_PLAN 阶段一改写为记忆主线（本次配套更新）；
  - ADR-0003/0004 正文提及 chunks 通道，历史正文冻结不改，行为变化由本 ADR 声明。

*状态: Accepted · 日期: 2026-08-13*
