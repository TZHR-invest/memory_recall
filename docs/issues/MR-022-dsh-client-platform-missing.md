# MR-022: memory-recall-dsh 缺 dsh.client.platform 导致 dsh web 启动崩溃

> 状态: 已解决 · 严重度: P1 · 创建: 2026-08-14 · 解决: 2026-08-14（package.json 补 platform/export）
> 关联: commit a79962f（新增 memory-recall-dsh 插件，本问题为其元数据缺陷）

## 现象

- dsh web（http://192.168.0.206:3080）无法访问，3080 端口无监听（connection refused）；
- /tmp/dsh-web.log 显示启动即崩溃：
  `Error: dsh: plugin tree failed to load: ... client-modules: memory-recall-dsh dsh.client.platform must be a string`；
- 进程无 systemd/cron/pm2 托管（手动 npx 启动），崩溃后无人拉起。

## 根因

dsh 客户端模块加载器（@deepseek-ai/dsh-client-modules 的 parseDshClient/resolveMeta）要求：

1. package.json 的 `dsh.client.platform` 必须是字符串（web profile 只接受 `"web"`），缺失即抛错；
2. platform 通过后还要求 `exports["./client"]` 存在（client bundle 路径）。

memory-recall-dsh 的 package.json 只声明了 `dsh.client.inject`，platform 缺失、
exports 也没有 "./client"（对比正常工作的 dsh-lan-access 两个字段都有）。
单个 client 包组合失败 → 整个插件树加载失败 → dsh 进程启动即退出。

## 修复

`apps/api/src/plugins/dsh/package.json` 补两个字段：

```json
"exports": { ".": "./index.js", "./client": "./client.js", "./package.json": "./package.json" },
"dsh": { "client": { "inject": [], "platform": "web" } }
```

然后 `bash install.sh --restart` 同步留档副本与运行副本并重启 dsh web。

## 验证

- 127.0.0.1:3080 与 192.168.0.206:3080 均 200；
- /plugins/dsh-lan-access/client.js 与 /plugins/memory-recall-dsh/client.js 均 200；
- 日志末尾为成功启动行 "dsh web: http://127.0.0.1:3080 (LAN: ...)"，无新报错。

## 备忘

- dsh 无守护进程托管，手动拉起后终端/崩溃都会让它消失；如需常驻建议后续补 systemd user unit。
- 插件新增/修改后必须跑 install.sh（或至少核对加载器要求：platform 字符串 + exports["./client"]）。
