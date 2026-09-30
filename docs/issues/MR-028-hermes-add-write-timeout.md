# MR-028: hermes 插件 `add` 同步写超时 30s 偏紧（客户端超时但服务端已落库 ⇒ 重试产生重复）

> 状态: **已解决（2026-10-01）** · 严重度: P2 · 发现: 2026-10-01（MR-027 配套改动的真实链路 E2E 中撞到）· 系统: v5 · 关联: [MR-027](MR-027-profile-channel-pollution.md)

## 现象（实测）

用 hermes 运行时解释器直调 `plugins/hermes/server.py::_handle_add` 写入一条记忆：

- `asyncProcess=false`（同步：embedding + LLM 实体提取 + 关系检测）
- 客户端 side：`httpx.ReadTimeout`（`api_request(..., timeout=30.0)`）
- **服务端 side：写入成功** —— DB 里该条已存在（`mem_3ba8c2fc7d474e899875`，container `…_hermes`，`metadata.profile_worthy=false`）

即：**超时 ≠ 未写入**。若调用方（agent）把超时当失败并重试，会产生**重复记忆**（后端 `add` 无语义去重，
同主题多条是已知行为，见 2026-09-2x 的查重铁律记忆）。

## 根因

`_handle_add` 的写请求超时硬编码 `timeout=30.0`；而项目文档明确写着"`POST /memories` 同步含
embedding + LLM 实体提取 + 关系检测，**实测 25s+**"，dsh 插件对此的处置是
`writeTimeoutMs` 默认 **90s**（`docs/PLUGINS.md` §标签约定与后端契约）。

## 影响

- 走 `asyncProcess=false` 的写入（插件默认是 true，故影响面有限）易触发；
- 触发后 agent 常按"失败→重试"处理 ⇒ 重复条目进库 ⇒ 只能靠事后查重/清理。

## 修复（2026-10-01 已实施）

1. **`timeout=30.0` → 90.0**（`plugins/hermes/server.py`，与 dsh 插件 `writeTimeoutMs` 对齐）；
   安全性已核实：MCP 客户端 `read_timeout_seconds` 默认 `None`、hermes 外层工具期限 **420s** ⇒ 90s 不会被上层截断。
2. **同步修正 hermes skill 里那条会致重复的回退建议**（`autonomous-agent-evolution` SKILL.md Step 0c 的 `#588` 条目）：
   原文"ReadTimeout → 改用 asyncProcess=true 重试"对**写类**调用有害（服务端可能已写入）；
   改为"写类超时先 `search` 查重再决定是否重试"，并修正"默认 false"的过时描述（代码默认已是 true）。
3. 测试：`tests/test_hermes_plugin_server.py` 增 `test_write_timeout_is_90s`（8 用例全绿）。

**仍未做**（属另一层，需后端配合）：写请求的幂等键 —— 有了它才能从根上消除"超时重试致重复"。

## 关联

- [PLUGINS.md](../../docs/PLUGINS.md)（写入注意：实测 25s+ / dsh 90s）
- MR-027（同一次改动中发现，画像通道治理）
