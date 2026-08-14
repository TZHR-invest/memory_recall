# _dsh-common — dsh 插件通用基础设施

> 状态: ACTIVE · 2026-08-14
>
> 供 `apps/api/src/plugins/` 下所有 dsh（DeepSeek Harness）客户端插件复用的
> 防崩基础设施，沉淀自 2026-08-14 事故（MR-022/MR-023：manifest 契约缺失 +
> classic-script bundle 形态错误导致 dsh 启动即崩、GUI 挂机约 3 小时）。

## 目录内容

| 文件 | 用途 |
|------|------|
| `preflight.mjs` | **契约预检**：`node preflight.mjs <插件目录>`，校验 `dsh.client.platform` 非空字符串（web 只接受 `"web"`）、`exports["./client"]` 存在且指向 bundle、bundle 无顶层 import/export + 含 `__ModuleLoader__.load` 注册 + 包名一致。退出码 0/1。 |
| `install-template.sh` | **通用安装器模板**：`--plugin <名> --src <目录> [--profile] [--api-key] [--check|--smoke|--restart|--uninstall]`，内置契约预检 + headless 试启动冒烟 + 幂等 patch 接线 + 卸载回滚。 |

## 新 dsh 插件开发流程（防崩五步）

1. **脚手架**：复制 `install-template.sh` 到插件目录（作为 `install.sh`），
   或直接以 `bash ../_dsh-common/install-template.sh --plugin <名> --src <插件目录> ...`
   方式调用（推荐，模板升级自动生效）。
2. **契约预检**：`node _dsh-common/preflight.mjs <插件目录>`（install.sh 前置已内置）。
   关键规则（MR-022/023）：
   - `package.json` 里若声明 `dsh.client`，`platform` 必须是字符串（web 只接受 `"web"`）
     且 `exports["./client"]` 必须存在 —— 缺失 → 插件树组合失败 → **dsh 启动即崩**；
   - 浏览器端 bundle 由 dsh web 按 **classic script**（script 标签）加载：
     不能含顶层 `import/export`，必须顶层 `window.__ModuleLoader__.load({ id, factory })`
     注册 `{ name, inject, apply }`；
   - bundle 是生成物就配 `build-bundle.mjs` 生成并提交，勿手改。
3. **全量测试**：`node --test`（bundle 同步性/形态测试防漂移）。
4. **冒烟 + 激活**（在**终端**执行，严禁在 agent 会话内部重启宿主 dsh）：
   `bash install.sh --smoke`（隔离 headless 试启动，exit 1 = 插件问题）
   → `bash install.sh --restart`（冒烟通过才重启正式服务，插件问题自动中止）。
5. **回滚**：`bash install.sh --uninstall` + 重启 dsh。

## 与 memory-recall-dsh 的关系

`apps/api/src/plugins/dsh/install.sh` 是本模板的实例化（早期版本，含插件特有逻辑）；
`preflight.mjs` 已抽到本目录并共享。**新插件优先用模板**；模板升级时如需要
可以把 memory-recall-dsh 的 install.sh 迁移到模板调用方式（低优先）。
