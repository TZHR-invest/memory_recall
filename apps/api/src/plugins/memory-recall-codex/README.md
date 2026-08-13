# Memory Recall Codex 插件

> 状态: ACTIVE · 版本: 0.1.0 · 最后更新: 2026-08-13

为 [Codex](https://openai.com/codex/) 提供跨会话持久记忆，对接 Memory Recall 后端
（`apps/api`，PostgreSQL + pgvector + 火山引擎 doubao embedding）。

与仓库内其他插件共享同一份记忆数据：

| 插件 | 目录 | 形态 |
|---|---|---|
| opencode | `../opencode/` | TS/Bun 插件（功能最完整） |
| deepseek-tui | `../deepseek-tui/` | Python MCP stdio server |
| hermes | `../hermes/` | Python MCP stdio server |
| **codex（本插件）** | `../memory-recall-codex/` | **Codex 插件（skills + MCP stdio server）** |

## 组成

- **MCP server**（`server.py`）：通过 MCP 协议暴露 15 个记忆工具（add / search /
  profile / context-inject / update / forget / import-docs 等），实现与 hermes 插件
  完全一致的工具面，配置方式与 deepseek-tui 一致。
- **Skill**（`skills/memory-recall/SKILL.md`）：指导 Codex 在任务开始前召回相关记忆、
  任务结束后沉淀关键信息。
- **Manifest**（`.codex-plugin/plugin.json`）：Codex 插件市场入口，声明 skills 与
  MCP server。

## 安装

前置条件：Memory Recall 后端已启动（`uvicorn main:app --port 8000`），且本机
`python3` 可运行 MCP server（见下方"依赖"）。

```bash
# 1. 注册个人市场（本机已配置）
# 个人市场（~/.agents/plugins/marketplace.json）由 Codex 隐式发现，无需 marketplace add；
# 只需把本插件目录放到 ~/plugins/memory-recall-codex（或软链过去）

# 2. 安装插件
codex plugin add memory-recall-codex@personal

# 3. 新开一个 Codex 会话即可生效
```

> 本仓库开发环境已把插件注册到个人市场（`~/.agents/plugins/marketplace.json`，
> 源码经 `~/plugins/memory-recall-codex` 软链指向本目录），直接执行第 2 步即可。

## 依赖

```bash
pip install -r requirements.txt   # mcp + httpx
```

> 也可以什么都不装：server.py 首次启动会自动创建 `~/.config/codex/memory-recall-venv` 并安装依赖。

## 免审批配置（推荐）

插件自带的 MCP server 注册后，工具调用默认需要 Codex 审批（交互模式点一下即可，
headless `codex exec` 会被自动取消）。在 `~/.codex/config.toml` 追加以下配置，
memory 工具免审批直接可用，且 MCP server 直接跑仓库源码（改代码即时生效，无需重装）：

```toml
[mcp_servers.memory-recall]
command = "python3"
args = ["server.py"]
cwd = "/home/wbaifan/.openclaw/workspace-ai_tui/projects/memory_recall/apps/api/src/plugins/memory-recall-codex"
default_tools_approval_mode = "approve"
```

> 说明：`approval_mode` 可选 `auto`（非破坏性工具免审批）/ `approve`（全部免审批）/
> `prompt`（默认，每次都问）。memory 工具无破坏性标注，两者效果一致。
>
> `cwd` 填你本机插件源码目录（本仓库开发环境用上面的路径）；也可以指向
> `codex plugin add` 输出的安装缓存目录（`~/.codex/plugins/cache/personal/memory-recall-codex/<版本>/`），
> 但指向源码目录的好处是改代码即时生效、无需重装。
## 配置

配置优先级：**环境变量 > `~/.config/codex/memory-recall.jsonc` > 默认值**。

推荐使用配置文件（复制 `config.jsonc.example` 到
`~/.config/codex/memory-recall.jsonc` 并填写）：

```jsonc
{
  "base_url": "http://localhost:8000",
  "api_key": "rk_live_...",
  "user_tag": "your-key-id",
  "project_tag": "auto"   // 或留空；显式写值则永远优先
}
```

或使用环境变量（`MEMORY_RECALL_BASE_URL` / `MEMORY_RECALL_API_KEY` /
`MEMORY_RECALL_USER_TAG` / `MEMORY_RECALL_PROJECT_TAG`）。

> `user_tag` 建议与 opencode 插件共用同一个 keyId，实现跨 Agent 的 user 记忆共享；
> `project_tag` 遵循 `{keyId}_project-<dirName>` 约定。
>
> **project_tag 自动化**：设为 `"auto"`（或留空）时，server 启动会探测会话工作目录——
> codex CLI（`codex exec` / 终端运行）按父进程 cwd 自动生成
> `{keyId}_project-<目录名>`（与 opencode 的 input.directory 行为一致）；
> VSCode 扩展从 codex 会话记录（~/.codex/sessions/**/rollout-*.jsonl 的
> session_meta.cwd，按 server 启动时间匹配最近会话，5 分钟时间窗；长会话重启
> 场景按文件 mtime 兜底，10 分钟窗）自动生成；隐藏目录（如 .codex）同样生成
> 独立容器。探测失败回退共享容器 codex-default，绝不写入插件自身仓库。
> 显式配置 project_tag 永远优先。
>
> 配置含 API key，建议 `chmod 600 ~/.config/codex/memory-recall.jsonc`。
> `project_tag` 遵循 `{keyId}_project-<dirName>` 约定。

## 使用

安装后技能自动生效：Codex 在任务开始时调用 `context-inject` 召回相关记忆，任务
结束时用 `add` 沉淀关键信息。也可直接用 MCP 工具：

- `context-inject` — 统一召回（画像+记忆+文档+知识图谱）
- `search` / `hybrid-search` — 语义搜索
- `add` / `update` / `forget` — 记忆生命周期
- `status` — 检查后端连通性

## 开发迭代

插件源码在本仓库，改动后：

```bash
python3 /home/wbaifan/.codex/skills/.system/plugin-creator/scripts/update_plugin_cachebuster.py \
  /home/wbaifan/.openclaw/workspace-ai_tui/projects/memory_recall/apps/api/src/plugins/memory-recall-codex
codex plugin add memory-recall-codex@personal   # 重装
# 新开会话生效
```

## 故障排查

- `status` 工具报"未配置 API Key" → 检查 `~/.config/codex/memory-recall.jsonc` 或环境变量
- 工具报"无法连接" → 确认后端已启动且 `base_url` 正确
- 修改配置后不生效 → 重启 Codex 会话（MCP server 随会话启动）
- status 显示项目范围 0 记忆/0 文档但项目明明有记忆 → project_tag 与真实数据
  所在 tag 不匹配（查数据库 memories/documents 表的 container_tag 核对），
  修改 jsonc 的 project_tag 指向目标项目 tag。

## 已知限制（codex 0.147）

- 插件 `.mcp.json` 只支持 transport 字段（command/args/env/cwd）；策略字段
  （`default_tools_approval_mode`、`disabled_tools`）实测不生效，免审批配置必须走 config.toml（见上）。
- **config.toml 层的策略字段生效**（与插件层不同）：`default_tools_approval_mode`
  免审批、`disabled_tools` 禁用工具（本机已用 config.toml 禁用 delete_doc，
  `codex mcp get` 实测生效）。插件 .mcp.json 里的同名字段才是死的。
- MCP server 无法直接感知工作目录（spawn 时无 PWD/CODEX_CWD），但会从父进程
  cwd（CLI）或 codex 会话 rollout（VSCode）自动探测项目目录生成 project 容器；
  需要更细隔离时可在内容里标注项目名（如 `【项目X】...`）。
  **project_tag 自动探测链**：父进程 cwd（codex CLI）> codex 会话 rollout
  （~/.codex/sessions session_meta.cwd，启动时间 5 分钟窗 + mtime 10 分钟窗，
  VSCode 模式可用）> 回退共享容器 codex-default。隐藏目录（如 .codex）也会
  生成独立容器；探测失败绝不写入插件自身仓库（避免污染）。多项目隔离请显式
  配置 project_tag（显式配置永远优先）。
- `project` 级配置（`[projects."..."]`）不支持 mcp_servers 覆盖。
- Windows 上首次自举建 venv 无文件锁（fcntl 仅 POSIX），多会话并发首次启动可能冲突；
  若出现"依赖自举失败"，删除 `~/.config/codex/memory-recall-venv` 后重试即可。

## 测试

```bash
# config.py 纯函数单测（jsonc 剥离 / 配置优先级），无需后端与 mcp 包
cd apps/api && python3 -m pytest tests/test_codex_plugin_config.py -q
```

```bash
# 真实链路集成测试（需本机后端 + ~/.config/codex/memory-recall.jsonc；不可达自动跳过）
~/.config/codex/memory-recall-venv/bin/python -m pytest tests/test_codex_plugin_integration.py -q
```
