# MR-023: memory-recall-dsh 浏览器端未注册 —— HARNESS 报 loaded without registering

> 状态: 已解决 · 严重度: P1 · 创建: 2026-08-14 · 解决: 2026-08-14（client.js 双模式 + 注册块）
> 关联: MR-022（同插件元数据缺陷，本问题为浏览器端形态缺陷）

## 现象

dsh web（3080）能启动、页面 200，但 HARNESS 报：

    Failed to load plugins
    failed to import loader entry 9576afcf (memory-recall-dsh): client-modules:
    bundle /plugins/memory-recall-dsh/client.js?rev=... loaded without
    registering "memory-recall-dsh" via __ModuleLoader__.load

## 根因

dsh 客户端模块系统（dsh-client-modules）在浏览器端 import() 每个插件的 client
bundle，要求 bundle 在顶层调用 window.__ModuleLoader__.load({ id, factory })
注册插件，factory 返回 cordis 插件形状 { name, inject, apply }（无 apply 或
未注册都会使该入口加载失败）。memory-recall-dsh 的 client.js 是纯 ESM 库
（只 export 类/函数，供服务端 index.js import），从未注册——服务端（headless）
正常，web profile 的浏览器端加载必失败。

## 修复

client.js 改为双模式：

- 底部加浏览器注册块：typeof window !== "undefined" 且有
  window.__ModuleLoader__ 时，load({ id: "memory-recall-dsh", factory })，
  factory 返回 { name, inject, apply } + 顺带暴露 MemoryRecallClient 等；
- node 环境无 window 自动跳过，底部 export 保持不变，index.js 照常 import。

## 验证

- node --check 语法 OK；node ESM 导入导出三件套正常；
- 浏览器模拟（globalThis.window 装假 __ModuleLoader__ 后 import 该文件）：
  恰好注册 1 次、id 正确、插件形状 name/inject/apply 合法；
- install.sh --restart 同步并重启后，伺服 bundle 含 __ModuleLoader__.load，
  页面 200、日志无新报错。

## 备忘

- dsh web 的插件 bundle 就是仓库里的原始文件（无构建步骤，rev 为内容哈希）；
- 新增/修改客户端插件时对照 dsh-lan-access/client.js 的注册形态；
- 浏览器端改动后需刷新 dsh web 页面（响应头 no-cache，正常刷新即取新 bundle）。
