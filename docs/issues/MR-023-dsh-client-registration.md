# MR-023: memory-recall-dsh 浏览器端未注册 —— HARNESS 报 loaded without registering

> 状态: 已解决 · 严重度: P1 · 创建: 2026-08-14 · 解决: 2026-08-14（生成式 classic-script bundle）
> 关联: MR-022（同插件元数据缺陷，本问题为浏览器端形态缺陷）

## 现象

dsh web（3080）能启动、页面 200，但 HARNESS 报：

    Failed to load plugins
    failed to import loader entry 9576afcf (memory-recall-dsh): client-modules:
    bundle /plugins/memory-recall-dsh/client.js?rev=... loaded without
    registering "memory-recall-dsh" via __ModuleLoader__.load

## 根因

dsh 客户端模块系统（dsh-client-modules）在浏览器端用 script 标签按 classic
script 加载每个插件的 client bundle（URL 固定 /plugins/<id>/client.js，内容取自
package.json exports["./client"] 指向的文件），要求 bundle 顶层调用
window.__ModuleLoader__.load({ id, factory }) 注册插件，factory 返回
cordis 插件形状 { name, inject, apply }。memory-recall-dsh 的 client.js 是纯
ESM 库（只 export 类/函数，供服务端 index.js import）：

- 作为 classic script 求值直接 SyntaxError（Unexpected token 'export'）；
- 即使跳过语法错误也没有注册调用 → 报 loaded without registering。

服务端（headless）不加载 browser bundle，所以正常；web profile 必失败。

> 注意：曾误判为 import() 求值并采用"ESM 双模式"（同一文件内加注册块），
> 无头 Chrome 控制台实测（Uncaught SyntaxError: Unexpected token 'export'）
> 推翻该假设——bundle 必须是纯 classic script，不能含 import/export。

## 修复

拆分为"库 + 生成式 bundle"：

- client-lib.js：node ESM 库（原 client.js 内容），index.js 改从它 import；
- build-bundle.mjs：从 client-lib.js 生成 classic-script bundle（剥离 export
  关键字 + 包上 __ModuleLoader__.load 注册壳 + 暴露 { name, inject, apply }）；
- client.js：生成产物，提交进仓库，exports["./client"] 仍指向它；
- install.sh 前置检查补 client-lib.js，重启验证补 bundle curl；
- test/bundle.test.js：产物同步性 + classic script 合法性 + 注册形态 + ESM 库导出。

## 验证

- 21 个测试全绿（新增 4 个 bundle 测试 + 原 17 个集成/单元测试无回归）；
- install.sh --restart 后伺服 bundle 为生成产物（classic script）；
- 无头 Chrome CDP 实测加载 http://127.0.0.1:3080/：模块系统启动
  （__ModuleLoader__/__DSH_MODULES__ 存在）、页面完整渲染、插件相关控制台
  消息为零（修复前稳定复现 SyntaxError + loaded without registering 两条）。

## 备忘

- dsh web 的插件 bundle 就是仓库里的原始文件（无构建步骤，rev 为内容哈希）；
- 新增/修改客户端插件时对照 dsh-lan-access/client.js 的注册形态；
- 浏览器端改动后需刷新 dsh web 页面（响应头 no-cache，正常刷新即取新 bundle）。
- bundle 与库拆开后靠 build-bundle.mjs + 同步测试防漂移，勿手改 client.js。
