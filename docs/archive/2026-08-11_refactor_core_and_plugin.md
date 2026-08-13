> **归档说明（2026-08-12）**：本文是讨论稿，正文多处结论未经核实、不可信任，已拆解为
> `docs/notes/2026-08-12-core-plugin-refactor-discussion.md`（讨论）、
> `docs/notes/2026-08-12-opencode-compaction-hook.md`（源码调研）、
> `docs/notes/2026-08-12-core-plugin-refactor-plan.md`（实施计划）与 ADR-0003~0008。
> 仅作历史参考，不作为实施依据。

# 2026-08-11 核心服务 + OpenCode 插件精简迭代计划

> **文档说明**：本文档记录对 memory_recall 后端服务与 `memory-recall-opencode` 插件的升级迭代 / 精简方向的关键讨论点。用于指导后续重构落地。

---

## 1. 背景与目标

Memory Recall 是一个向后端（FastAPI + PostgreSQL/pgvector 向量搜索 + 知识图谱）提供"跨会话持久记忆"能力的系统。`memory-recall-opencode` 插件是其在 OpenCode 宿主机上的翻译层/代理层，定位于四件事：

1. **显式记忆工具**（`memory-recall`：add/search/profile/list/forget/import-docs/status/retry/help）
2. **上下文自动注入**（chat.message hook：策略化召回 + 去重 + 会话记账）
3. **文档追忆**（document-tracker + file-watcher 增量导入）
4. **会话压缩维护**（compaction：预压缩 / 摘要捕获 / 现场恢复）

本次迭代目标：

- **精简**：消除 hack 式实现，收敛到 opencode 官方提供的机制；
- **升级**：跟进 opencode 最新插件 API（`experimental.session.compacting` 的 `output.prompt`、`experimental.compaction.autocontinue`）；
- **降险**：减少对 opencode 私有存储格式（`~/.opencode/messages|parts`）的直接依赖。

---

## 2. 关键讨论点

### 2.1 插件整体架构认知

插件入口 `src/index.ts` 只暴露 4 个钩子点，三角色分工：

| 钩子 | 能力 | 模块 |
|------|------|------|
| `tool` | 显式记忆工具（9 模式） | `tool.ts` |
| `chat.message` | 每轮消息前上下文自动注入 | `context.ts` + `tracker.ts` + `recall-trigger.ts` |
| `event` | 监听 `message.updated`/`session.idle`/`session.deleted`/`session.compacted` | `events.ts` |
| `experimental.session.compacting` | 压缩前注入项目记忆 / 拍摄现场 | `compaction.ts` |

### 2.2 两套压缩机制 —— 核心争议点

当前存在**两套并行**的压缩路径：

| | 路径 B（正规） | 路径 A（预压缩 / hack） |
|---|---|---|
| 触发者 | opencode 原生 `compaction.auto: true`（默认）或用户 `/compact` | 插件监听 `message.updated`，token 占用率 ≥80%（`compactionThreshold`）主动调 `session.summarize` |
| 干预方式 | `experimental.session.compacting` hook，官方支持 `output.context` 追加与 `output.prompt` **整体替换**摘要 prompt | ① `injectHookMessage` 直接写假 user 消息到 `~/.opencode/messages|parts`；② SDK summarize（该 API **无 prompt 参数**） |
| 记忆注入 | 项目记忆 + AI guidance push 进 `outputData.context` | `createCompactionPrompt` 完整 7 段结构化 prompt 作为假消息 |
| 隐患 | 依赖 `experimental.` 前缀（可能变动） | **依赖 opencode 私有存储格式** + 事件 `tokens` 字段是否持续存在 |

**关键事实**：
- SDK `session.summarize` 不带任何 prompt 参数（仅 providerID/modelID），这是 `injectHookMessage` 文件注入存在的直接原因——插件想让摘要 LLM "看到"结构化 prompt，但 API 不提供通道，于是绕到文件系统。
- 插件插件 pin 的 `@opencode-ai/plugin ^1.3.0`（本机已装 1.15.13），README 中提到与 Oh-My-OpenCode 的压缩恢复冲突——这套压缩恢复功能产生于"压缩后会丢 agent 状态"的旧时代。
- 新版 opencode 已提供 `experimental.compaction.autocontinue` hook（压缩成功后、合成 user 消息前触发）——`recoverAgentConfig` 的诉求已被官方原生化。

**结论**：预压缩是历史遗留的施工方案，其多数动机现在已被官方 hook 覆盖，应收敛为单一正规路径。**不该整体删除，而应拆开评估。**

### 2.3 预压缩拆解后的删留决策

将预压缩整套拆为五块分别决策：

| 模块 | 性质 | 结论 |
|---|---|---|
| ① 触发决策 `checkAndTriggerCompaction` | 半 hack：依赖事件 `tokens` 字段；与原生 `compaction.auto` 职责重叠；9 道守卫链（30s 冷却 / 防重入 / 5 万 token 门槛 / SDK 查模型真实窗口）维护成本高 | **低频默认关闭或设为可选节奏开关**，价值仅剩"提前压"一个卖点 |
| ② 文件注入 `injectHookMessage` + `createCompactionPrompt` | **纯 hack**：直接写 opencode 内部存储，升级必碎；**已被 hook 的 `output.prompt` 取代** | **删除**。将结构化 prompt 迁移到 `experimental.session.compacting` 的 `output.prompt`，一条路径两来源通吃 |
| ③ 摘要捕获 `handleSummaryMessage` + `waitForSummaryMessage` | 不算 hack：轮询 SDK + 文件兜底，两条路径共用的记忆保鲜能力 | **保留**（可简化，去掉 `summarizedSessions` 双触发标记依赖） |
| ④ 现场恢复 `captureAgentConfig`/`recoverAgentConfig`/`captureTodos`/`restoreTodos` | 半 hack：动态 `import("opencode/session/todo")` 极脆，且新原生机制可能已覆盖 | **先验证后定**：若 `autocontinue` / 新版会话已自动保持 agent 状态，则整体删除；否则仅作兜底 |
| ⑤ 状态清理 `session.deleted` 等 | 正常设计 | 保留 |

**收益预估**：删除 ①+② 后 `compaction.ts` 从约 1044 行砍半；`checkAndTriggerCompaction` 全部守卫链消失；opencode 存储升级不再炸插件。

### 2.4 删除前必须实测的验证点

1. **`experimental.session.compacting` 在插件自己调 summarize 时是否同样触发**——若触发，②删除后"预压缩场景"的摘要质量不受影响；若不触发，删除后该场景退化为默认 prompt 结构。**这是删除前唯一硬性阻塞项。**
2. **opencode 原生 `compaction.auto` 行为**：默认 `true`，上下文满时触发并预留 `reserved` buffer（默认 10000）。需确认其触发阈值是否足够早，避免"满窗再压、摘要调用超窗失败"这个预压缩想解决的痛点复发。
3. **新原生机制是否已保持 agent / todos**：决定 ④ 的完整性。

### 2.5 其它值得保留 / 关注的设计

| 主题 | 要点 |
|---|---|
| 配置分层 | env > 插件 options > JSONC 文件 > 默认值（`config.ts`），自带 JSONC 解析避免正则会误伤 URL |
| 项目隔离 | 按 `keyId` 自动生成 `{keyId}_project-{项目名}` container_tag，多项目零配置隔离 |
| 注入策略 | once / smart（默认）/ always 三态，"smart" 是"从粗暴到克制"的产品路径；`calculateDynamicRecallSize` 让会话越长注入越少 |
| 去重 | 前置哈希精确去重 + 后端 `/context-inject` 语义去重；前后端双实现，后端失败自动降级前端 |
| 异步写入队列 | 写操作入队（<10ms 返回 taskId），指数退避重试；当前为纯内存队列，进程退出丢任务（已知限制） |
| 隐私红线 | `isFullyPrivate` 拒绝存入 + `stripPrivateTags` 净化，保护用户隐私 |
| 知识 vs 会话态 | 会话摘要不再写入记忆库（会污染知识），仅内存缓存（5 分钟过期）——已固化的产品决策 |

---

## 3. 迭代行动计划（建议顺序）

1. **先做验证实验**（对应 2.4 的三个阻塞点），产出结论后再动手代码。
2. **迁移第 1 步**：在 `experimental.session.compacting` 中启用 `output.prompt = createCompactionPrompt(...)`，收敛 7 段结构化摘要 prompt。
3. **删除第 2 步**：移除 `injectHookMessage` 及 `createCompactionPrompt` 的假消息写入路径；连带清理 `injectCompactionContext` 中只服务于该路径的逻辑。
4. **收敛第 3 步**：`checkAndTriggerCompaction` 改写为可选开关（`compactionThreshold` 保留），依赖原生 `compaction.auto` + hook 注入。
5. **评估第 4 步**：确认 `autocontinue` 是否覆盖现场恢复，决定去留。
6. **收尾**：精简 `CompactionState`（`latestSummaries`/`summarizedSessions` 等相关字段）、补充/更新单测（现 9 个测试文件，覆盖注入策略、去重、图谱、队列、压缩），并提升插件 `@opencode-ai/plugin` / `@opencode-ai/sdk` 版本。

---

## 4. 附：本次讨论时的工程观察（备忘）

- 插件事件字段取法不一致（`properties.sessionID` vs `properties.info.sessionID`），说明是按真实事件样本调试出来的，**脆弱但实用**，重构时注意保留兼容。
- 全文"每步带 fallback"的设计哲学（轮询摘要失败 → 读文件；SDK 查窗口失败 → 200K；todo 恢复失败 → 静默跳过）是**弱依赖 = 高可用 + 低保证**的取舍主轴，精简时不要破坏这条原则。

## 5. 附：context-inject 接口与插件注入链路认知纪要

> 本节为围绕 `context-inject` 接口设计及其与插件交互的讨论纪要，补充 2.5 中"去重"一行的完整上下文。

### 5.1 接口设计认知（`POST /context-inject`）

- **定位**：后端一站式聚合器——画像 / 向量 / 记忆图谱 / 实体图谱 / 文档 chunk 五路召回 + 语义去重 + 格式化全部在后端完成，插件一次调用拿全部，避免多次往返。
- **输入三要素**：
  - 容器：`user_tag` / `project_tag`（新版双容器）或 `container_tag`（旧版兼容，自动回退到 API Key 的 container_tag）；
  - `query`：可为空（纯画像注入）；
  - `config`：17 个可调参数分四组——数量上限（profile/memories/chunks）、图谱 depth/nodes、相似度阈值、去重与语言。
- **输出三部分**：`context`（给 LLM 读的 Markdown，按 画像→项目记忆→用户记忆→文档 分区，中英自动检测，空结果返回 `""`）；`sources`（给程序读的结构化引用，含 id 供插件记账）；`stats`（去重统计）。`include_trace` 时附召回链路明细。
- **行为要点**：
  - 两种模式由请求体自动分派（`inject_with_tags` / `inject`），容器越权 403；
  - 图谱扩展只在语义命中后触发，总量硬上限 `max_memories * 2`；
  - `inject_profile` 默认 `false`——插件只在首次注入时开画像，是刻意的 token 节省策略；
  - 每环节独立 try/except，互不拖垮；语义去重按 `SOURCE_PRIORITY` 保留（profile 最高）。

### 5.2 插件注入链路

- 挂 `chat.message` hook，把 `synthetic` 的 text part **unshift 到用户消息头部**，LLM 首轮即见记忆；
- `injectionStrategy`：once / smart（默认）/ always；首次注入大配额 + 画像，增量注入收窄（`smartRecall.maxAdditionalMemories` + `dynamicRecallSize` 随会话增长递减）；
- `injectedMemoryIds` 记账，避免同会话重复注入同一条记忆；
- `useBackendDedup` 开关选择实现：后端模式 `injectContextFromBackend`（一次调 `/context-inject`）vs 前端模式 `injectContext`（自己串 `/profile`+`/search`+`/documents/search`+`/graph`+`/embed`）。

### 5.3 降级语义修正（重要认知）

- **前端模式并不独立于后端**：仍打同一 `baseUrl` 的普通端点，后端整体宕机时两种模式同样失效。
- 真实保护范围：
  1. `/context-inject` **单端点故障**（一步抛 500 全链路失败；前端模式逐端点 try/except，局部挂仍能注入其余来源）；
  2. **超时**：聚合端点内多次串行 embedding + 图谱遍历，易撞 30s 超时；前端模式每次调用更轻且带客户端 embedding cache；
  3. **绕过后端图谱遍历逻辑 bug**（前端拿 `/graph` 数据在客户端 `traverseFromSeeds`）。
- **真正的韧性在别处**：`index.ts` 外层 catch——注入失败仅记日志、不注入、对话照常。记忆注入是 best-effort 的"锦上添花"，**失败不阻塞主流程**才是生存底线。

---

*创建日期：2026-08-11 · 状态：讨论稿，待验证点确认后进入实施*
