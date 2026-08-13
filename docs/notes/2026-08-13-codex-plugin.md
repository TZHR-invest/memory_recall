# 2026-08-13: Codex memory recall 插件开发

> 类型: 调研+开发
> 日期: 2026-08-13
> 关联: 插件目录 `apps/api/src/plugins/memory-recall-codex/`

## 背景

用户提出为 Codex 开发 memory recall 插件。仓库已有 opencode（TS/Bun）、
deepseek-tui / hermes（Python MCP stdio）、openclaw 插件，均对接同一后端
（`apps/api`，X-API-Key 认证，user/project 双 tag 隔离）。

## 调研发现

- Codex CLI 0.147 插件体系：`.codex-plugin/plugin.json` 声明 `skills` + `mcpServers`，
  经个人市场（`~/.agents/plugins/marketplace.json`）安装到 `~/.codex/plugins/cache/`；
  插件 `.mcp.json` 的 stdio server 需要显式 `cwd` 字段（相对路径默认按 codex 自身 cwd 解析，会找不到 server.py）。
- 工具命名：MCP server `memory-recall` 的工具在 Codex 中暴露为 `mcp__memory_recall__<tool>`（连字符转下划线）。
- **审批机制**（本次最大坑）：插件 `.mcp.json` 里的 `default_tools_approval_mode` 在 0.147 实测不生效
  （工具级 `tools` 映射也不认 `*` 通配符）；headless `codex exec` 下未配置时工具调用直接 Abort
  （"user cancelled MCP tool call"）。源码确认：
  - `McpServerConfig` 含 `default_tools_approval_mode`（enum: auto/prompt/writes/approve），
    插件解析链路（plugin_config.rs → catalog → McpServerMetadata）理论保留该字段，但实测未生效，疑似 0.147 插件通道 bug；
  - **生效路径**：`~/.codex/config.toml` 的 `[mcp_servers.memory-recall]` 完整定义（Config 层优先级高于 Plugin 层，整条替换），
    加 `default_tools_approval_mode = "approve"` 后工具免审批直通。
- JSONC 注释剥离要字符串感知：naive `//.*$` 正则会把 `http://` 截断（deepseek-tui 的 `_strip_jsonc_comments` 有同款隐患），
  codex server 改为状态机实现。
- 依赖自举：系统 python3 无 mcp 包（PEP 668 阻止 user 级 pip），server.py 启动时自动创建
  `~/.config/codex/memory-recall-venv` 并安装 `mcp<2.0.0`（2.0 移除了 `@app.list_tools()` 装饰器 API）。

## 结论

- 插件已开发完成并端到端验证：`apps/api/src/plugins/memory-recall-codex/`
  （`.codex-plugin/plugin.json` + `.mcp.json` + `server.py` + `skills/memory-recall/SKILL.md` + README）。
- 已安装到本机 Codex（`memory-recall-codex@personal`），15 个工具 + 1 个技能全部生效；
  实测 status/add/search 全链路成功（add → search 相似度 0.68 召回）。
- 本机配置：`~/.codex/config.toml` 的 `[mcp_servers.memory-recall]`（cwd 指向仓库源码，免审批）；
  `~/.config/codex/memory-recall.jsonc`（复用 opencode 的 keyId，user 记忆跨 Agent 共享）。
- 个人市场条目：`~/.agents/plugins/marketplace.json`，源码经 `~/plugins/memory-recall-codex` 软链指向仓库。

## 下一步

- 交互模式下观察审批体验（config.toml 未配置的用户会看到审批提示）；
- 如 codex 后续版本修复插件通道的 approval 字段，可移除 config.toml 里的 server 定义。

## 未决问题

- 插件 `.mcp.json` 的 `default_tools_approval_mode` 未生效的具体原因（codex 0.147 插件加载通道），待上游确认。

---

## 补充调研（同日二次完善）

### 新确认的事实

- 插件 `.mcp.json` 对 codex 0.147 只解析 transport 字段：`disabled_tools`/`enabled_tools` 实测同样不生效（`codex mcp get --json` 显示 null）。
- **MCP server 拿不到工作目录**：运行时探针确认 spawn 环境里 PWD/CODEX_CWD/INIT_CWD/OLDPWD 全部为 None（只有 HOME）。
  → server 端无法感知项目目录，project 范围无法按目录隔离；`[projects."..."]` 级配置也不支持 mcp_servers 覆盖。
- config.toml `[mcp_servers.<name>]` 完整定义会整条覆盖插件注册（Config 层优先级高于 Plugin 层），本机配置因此指向仓库源码（改代码即生效）。

### 本次完善

1. `config.py` 拆分：jsonc 剥离 + 配置加载独立成无依赖模块（可单测）；server.py 改为 import，消除模块级 bootstrap 副作用。
2. 单元测试 `tests/test_codex_plugin_config.py`（11 用例）：URL 不被注释剥离误伤（回归）、注释/尾逗号/转义处理、配置优先级、坏文件回退。
3. `status` 增强：显示 user/project 双范围记忆与文档统计。
4. bootstrap 加 flock 并发锁（POSIX），防多会话首次启动并发建 venv。
5. SKILL.md 增强：scope 语义说明（user 跨项目 / project 当前共池）、记忆维护（update 版本化 / forget 软删除 / extract-memory 沉淀）、项目初始化导入 README/AGENTS.md/docs。
6. README 补「已知限制」与「测试」章节。

### 验证

- 11 个单测全绿；真实 Codex 会话调用 status 返回双范围统计（用户 61 记忆 / 55 文档）。

## 补充调研（同日三次完善）：会话开头漏注入的根治

### 背景

用户复盘发现：新会话开头未调用 context_inject（"执行疏忽"）。排查确认插件加载正常
（技能 + 15 个 MCP 工具均在会话内，codex mcp get 显示 enabled），漏注入是模型侧
未按技能优先级执行，而非加载故障。

### 事实

- 全局 AGENTS.md（~/.codex/AGENTS.md）存在但为 0 字节（空占位）——Codex 全局常驻指令机制未被使用。
- 技能 SKILL.md 的规则是"被动触发"（需模型先识别任务匹配再执行）；
  全局 AGENTS.md 是"主动在场"（每轮上下文都有），可靠性更高。
- developers.openai.com 对 curl 返回 403，未能确认 Codex 是否存在
  session-start 自动执行工具的官方机制（据所知无公开配置）。

### 决策

在 ~/.codex/AGENTS.md 写入强制规则：新会话动手前先 context_inject
（injectProfile: true, maxMemories: 8）；工具不可用先确认加载不静默跳过；
会话结束前 add 沉淀。纯元问题豁免第 1 条。

### 下一步

- 观察后续新会话是否稳定先注入（验证 AGENTS.md 规则的实际约束力）。
- 如官方文档可访问，复核 session-start 钩子是否存在。

---

## 二轮 review（同日第三次完善）

### 修复/改进

1. **工具 schema 数字参数加范围约束**（对照后端 Field 校验）：limit 1-100、maxMemories 1-20、maxChunks 1-10、threshold 0-1、图谱 depth 1-5 / nodes 1-20，模型直接可见，避免 422。
2. **修复错误工具描述**：`maxMemories`"设为 0 可跳过"→ 后端 ge=1 会 422（hermes 继承来的错误）。
3. **配置死字段激活**：config 的 max_memories/max_chunks/similarity_threshold 此前未被 server 使用，现作为 search/hybrid/context-inject 的默认值。
4. **status 后端宕机误报 bug**：`_count` 吞异常导致后端全挂时仍显示"✅ 正常运行"；改为记忆查询 strict（失败即报不可用），文档计数宽松（?）。由新增测试发现。
5. **status 显示配置来源**（配置文件/默认值/+环境变量），不再硬编码路径。
6. README：修正"个人市场无需 marketplace add"、cwd 路径按本机调整的说明、自举免安装提示。
7. SKILL.md：extract_memory 参数示例、存储前先 search 查重。
8. **新增 handler 级测试** test_codex_plugin_server.py（mock api_request，8 用例，无 mcp 环境自动 skip），测试环境为插件自举 venv（装了 pytest + pytest-asyncio）。

### 验证

- 19 个测试全绿（config 11 + server 8）；真实 Codex 会话 status 返回双范围统计 + 配置来源。

## 补充调研（同日四次完善）：codex 插件 project_tag 与真实数据不匹配

### 背景

用户指出"本项目已有 project 记忆但 context_inject 没召回"。核对数据库实锤：

- memories 表 container_tag 分布：_project-memory_recall 83 条 / 42 篇文档；
  codex 插件配置的 _project-codex 在库中 0 条（空池）。
- 根因：opencode 插件能感知 cwd，按 {keyId}_project-<目录名> 动态生成 project_tag；
  codex 插件 MCP server 拿不到工作目录（已知限制），jsonc 配置写死 _project-codex，
  导致 codex 会话 project 范围恒空、看不到 opencode/hermes 沉淀的既有项目记忆。

### 修复

- ~/.config/codex/memory-recall.jsonc 的 project_tag 改为
  _project-memory_recall；MCP server 启动时加载配置，重启会话生效。
- 验证：直接调 POST /context-inject（新 tag）召回 6 条项目记忆 + 3 chunks
  （stats: total 20 → after_dedup 18, project_memories 6）。
- README 已知限制/故障排查补两条：project_tag 需手动指到目标项目；
  status 项目 0/0 时先查数据库 container_tag 核对。

### 教训

- status 显示"项目范围 0/0"不能直接采信为"没有记忆"——要先核对 project_tag
  是否与真实数据所在 tag 一致（本次正是配置空池误导）。
- codex 插件多项目场景：改 tag 后所有 project 操作进同一池；后续增强方向
  是 server.py 支持按调用传 project_tag 覆盖（默认用配置值）。

## 补充调研（同日五次完善）：project_tag 自动化生成

### 背景

用户要求 codex 插件像 opencode 一样自动生成 project_tag。先查证 opencode 机制：
不是用 git——opencode 运行时把 input.directory（当前工作目录）传给插件，
getProjectTag 取 path.basename(directory) 生成 {keyId}_project-<目录名>。

codex 无对等机制：MCP server 是 spawn 的 stdio 进程，环境变量仅 HOME/PATH 等
（实测 /proc/<pid>/environ），父进程链为 codex app-server ← VSCode server，
cwd 全是 home 目录，VSCode Remote 扩展模式下拿不到项目目录。

### 实现（config.py）

- detect_project_tag(user_tag, fallback)：读 /proc/<ppid>/cmdline 判定父进程
   是否为 codex CLI（含 "codex" 且不含 "app-server"）；是则取 /proc/<ppid>/cwd
   basename 生成 {user_tag}_project-<目录名>；否则（VSCode 模式/不可读/home 等）回退。
- load_config：project_tag 为空/auto/默认占位时自动探测；显式配置永远优先。
- jsonc 支持 "project_tag": "auto"；当前本机 jsonc 仍显式写 _project-memory_recall
   （VSCode 模式必需，不受影响）。
- 新增 6 个单测（CLI 生成/app-server 回退/home 回退/异常回退/显式优先），
   共 25 个测试全绿。实测 CLI 模式生成结果与 opencode 一致：
   085288ba-..._project-memory_recall（跨 Agent 共享同一 project 池）。

### 遗留

- VSCode 扩展模式（当前运行方式）无法自动生成，必须显式配置 project_tag；
   除非 codex 在 MCP 请求中下发 thread cwd（VSCode 扩展有 turnCwds 概念，
   是否传到 stdio server 待探针确认）。
- 注意 apply_patch 写入含 \x00 的补丁会把转义变真实 NUL 字节，
  测试/源码里避免字面 \x00（本日踩坑：config.py 的 replace("\x00"," ") 被破坏）。

## 补充调研（同日六次完善）：git 兜底 + 父进程链排查

用户追问「还有没有别的方法（比如 git）」。实测三条路：

1. **VSCode 祖先链**：code-server cmdline 无 workspace 参数（仅 connection-token/
   socket），environ 只有 VSCODE_AGENT_FOLDER——远程 server 侧不知道工作区路径，此路不通。
2. **git**：server cwd 固定为插件目录，git rev-parse --show-toplevel 稳定返回
   插件所在仓库（本机即 memory_recall）——可行但只能覆盖插件所在仓库。
3. MCP 请求是否下发 thread cwd：VSCode 扩展有 turnCwds 概念，但未探针确认，待办。

实现：config.py 探测链改为 父进程 cwd（CLI）> git 仓库根（VSCode 模式兜底）> fallback；
显式配置永远优先。新增 2 个单测（git 生成/git 失败回退），共 27 个测试全绿。
真实环境验证：VSCode 模式 + git 兜底生成 k1_project-memory_recall，与 opencode 一致。

## 补充调研（同日七次完善）：rollout 会话记录定位 cwd（回答「codex 怎么知道自己在哪个项目」）

用户追问 codex 自身如何感知项目。侦查发现：codex 把每个会话的 cwd 写进
~/.codex/sessions/YYYY/MM/DD/rollout-<时间戳>-<thread_id>.jsonl 首行 session_meta
（实测 52 处 cwd 字段，本机全部为 memory_recall 项目）。

关键对应关系：MCP server 由 codex 在会话创建时拉起，进程启动时间与 rollout
文件名时间戳同秒（617843@10:33:59 ↔ rollout-10-33-35；633823@10:59:46 ↔ rollout-10-59-47）。
实现 _detect_from_rollout：扫描 ~/.codex/sessions，按文件名时间戳与进程启动时间
（模块导入时刻 time.time()）取差最小且 <300s 的 rollout，读 session_meta.cwd 生成 tag。
真实数据验证：两个 server 实例均正确匹配 _project-memory_recall；重启超窗回退 git。
新增 4 个单测（最近匹配/超窗拒绝/坏 cwd 拒绝/坏文件拒绝），共 31 个测试全绿。

最终探测链：显式配置 > 父进程 cwd（CLI）> rollout session_meta（VSCode）> git 仓库根 > 默认值。
VSCode 模式已真正自动化，仅多项目场景（不同目录的仓库）仍需显式配置。
