# MR-021: codex 插件项目容器探测启动竞态（VSCode 扩展模式偶发 403）

> 状态: 已解决 · 严重度: P1 · 创建: 2026-08-14 · 解决: 见 commit（本文随修复提交）
> 关联: 记忆 mem_6d328cff54074e43ba13（v0.3.0 探测链描述，仍成立，本问题为其补充）

## 现象

- 所有 project 范围 MCP 调用（context-inject / add / search / status）返回 403：
  "Container access denied. Container must start with '085288ba-8eab-439b-b0d4-b92382e0f95d_' or equal '085288ba-8eab-439b-b0d4-b92382e0f95d'."
- 服务本身正常：用正确 container_tag 直接 curl API 可正常读写记忆。

## 根因

codex 插件项目容器探测链（apps/api/src/plugins/memory-recall-codex/config.py）：
显式配置 > 父进程 cwd（codex CLI 模式）> codex 会话 rollout 文件 > 回退 codex-default。

- VSCode 扩展模式下父进程是 "codex ... app-server"，被 _is_codex_cli_parent 有意排除
  （避免把 app-server 当 CLI），只能走 rollout 探测；
- 竞态：MCP server 与会话 rollout 文件几乎同时创建（实测：server 启动 11:03:49 与
  rollout-2026-08-14T11-03-49 同秒）。server 模块导入（_START_TIME）先于 rollout 落盘时，
  文件名时间窗（5 分钟）与 mtime 兜底（10 分钟）都落空 → 回退 codex-default，
  且 PROJECT_TAG 在进程生命周期内冻结；
- API Key（rk_live_...）的 key_id = 085288ba-8eab-439b-b0d4-b92382e0f95d，
  verify_container_ownership 要求 container 等于 key_id 或以 key_id_ 开头；
  codex-default 不满足 → 403。

## 修复

- config.py 新增 ensure_project_tag()：PROJECT_TAG 仍为回退值 codex-default 时，
  首次使用工具惰性重探测（此时 rollout 通常已落盘）；成功后更新全局并幂等返回，
  仍未成功则保持回退值、下次调用再试；
- server.py 的 _tag(scope) 与 status 工具改用 ensure_project_tag()；
- 修复已同步 codex 缓存安装副本；重启 codex 会话（MCP server 重生）后生效。

## 验证

- 模拟启动冻结后调 ensure_project_tag()：返回
  085288ba-8eab-439b-b0d4-b92382e0f95d_project-memory_recall（幂等）；
- curl 实测：正确容器 200、codex-default 403（复现路径一致）。

## 解决记录

（commit 随本文一起提交，见 git log）
