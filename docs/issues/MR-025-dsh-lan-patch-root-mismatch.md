# MR-025: dsh web 局域网 403 —— 补丁打在错误副本（npm 全局安装 vs npx 缓存）

> 状态: 已解决 · 严重度: P1 · 创建: 2026-08-18

## 问题

dsh web 局域网访问 `/api/settings.describe` 报 HTTP 403（回环正常）。

根因：**dsh 实为 npm 全局安装**（systemd ExecStart=`~/.npm-global/bin/dsh web`，rc.7），
而 `reapply-lan-patches.sh` / `install.sh` 的 ROOT 定位只扫 `~/.npm/_npx` 缓存副本（rc.6），
补丁全打在**错误副本**上——运行副本缺特权围栏放行 / 设置持久化 / webserver 令牌门卫三层补丁。

## 处置

1. **手工对全局副本补三层**（备份 `.bak-20260818`）+ 重启 dsh 服务；
2. **修正两个脚本的 ROOT 定位**：运行进程 cwd（readlink /proc/PID/cwd）→ npm root -g 内嵌
   node_modules → npx 缓存，以 `dsh-client-connection` 存在为准；
3. **DSH_BIN 解析**：`command -v dsh`（npm 全局）优先，其次 ROOT/node_modules/.bin/dsh（npx 布局）；
4. **pkill 宽匹配**：匹配实际 cmdline。

本仓库内存入 install.sh 的修复；reapply-lan-patches.sh 属 dsh-plugins 基础设施仓库
（packages/dsh-lan-access/），另行同步。

## 验证

- LAN + 令牌 settings.describe 415（等同回环）；
- LAN 无令牌 401（令牌门卫生效）；
- 页面 200 / 401；
- `--check` 五层全绿。

## 解决记录

- commit: 本次提交（install.sh ROOT/DSH_BIN 定位修复 + 文档）
- 2026-08-18 完成
