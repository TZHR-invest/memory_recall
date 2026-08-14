# Memory Recall DSH Plugin (memory-recall-dsh)

为 **DeepSeek Harness (dsh)** 提供长期记忆能力的客户端插件，对标 opencode 插件
`memory-recall-opencode`：工具注册 + 自动召回注入 + 自动捕获，后端为 memory-recall
FastAPI（`apps/api`）。

## 功能

| 能力 | 说明 |
|------|------|
| 记忆工具 | `memory_store` / `memory_search` / `memory_profile` / `memory_list` / `memory_forget` |
| 自动召回 | `agent/pre-step` 时按策略调 `POST /context-inject`，把召回上下文以 `<system-reminder>` 框定消息折入本轮请求 |
| 自动捕获 | `turn/end` 时把该轮 user+assistant 摘要写入长期记忆（`extract` 蒸馏 / `raw` 原文，默认 `extract`） |

### 注入策略（injectionStrategy）

| 策略 | 行为 |
|------|------|
| `once` | 仅会话首次请求注入（含画像 + 记忆 + 文档片段） |
| `smart`（默认） | 首次注入 + 关键词触发（"记得/之前/项目/架构/怎么…"，可配置） |
| `always` | 每轮 step 1 都注入 |

会话内按内容摘要去重：同一轮召回文本不会重复注入。

### 自动捕获（captureMode）

- `extract`（默认）：`POST /extract-memory` 用后端 LLM 蒸馏出值得保存的记忆再逐条落库
  （`type=preference` 自动归为永久特征）；蒸馏无价值或失败时回退 raw；
- `raw`：把摘要原文存为 `conversation` 类型记忆（截断到 `captureMaxChars`）。

捕获为 fire-and-forget + fail-open，绝不阻塞 agent 主流程。注意：后端对语义相似内容
有合并去重（threshold 0.85），重复捕获会自动合并到最新版本，不会堆积。

## 安装

```bash
cd apps/api/src/plugins/dsh
bash install.sh                      # 安装到 web profile（幂等）
bash install.sh --api-key rk_live_xxx   # 把 API Key 写进 profile patch（可选）
bash install.sh --restart            # 安装后重启 dsh web 并验证（会短暂中断 web 服务）
bash install.sh --check              # 只检查状态
bash install.sh --uninstall          # 卸载
```

安装完成（或 `--restart` 重启）后，新会话即生效；**已打开的会话需重启 dsh 才加载插件**。

### 配置

配置写在目标 profile 的 `cordis.patch.yml`（install.sh 自动追加）：

```yaml
- insert:
    - id: memory-recall-dsh
      name: 'memory-recall-dsh'
      config:
        apiKey: 'rk_live_...'        # 也可以不写，运行时读环境变量 MEMORY_RECALL_API_KEY
        baseUrl: 'http://localhost:8000'
```

| 配置项 | 默认 | 说明 |
|--------|------|------|
| `apiKey` | 环境变量 `MEMORY_RECALL_API_KEY` | 后端 API Key（`rk_live_`/`rk_test_`） |
| `baseUrl` | `http://localhost:8000`（环境变量 `MEMORY_RECALL_BASE_URL`） | 后端地址 |
| `keyId` | 启动时 `GET /auth/verify` 自动获取 | 用户 tag（=keyId），一般不用配 |
| `containerTag` | — | 全局容器覆盖（同时用作 user/project tag） |
| `projectTagOverride` | — | 项目 tag 覆盖（默认 `{keyId}_project-<cwd 目录名>`） |
| `autoRecall` / `autoCapture` | `true` / `true` | 开关 |
| `injectionStrategy` | `smart` | `once` / `smart` / `always` |
| `maxMemories` / `maxProfileItems` / `maxStaticProfileItems` | 5 / 5 / 30 | 注入上限 |
| `injectProfile` | `true` | 首次注入是否含用户画像 |
| `enableChunksSearch` / `maxChunks` | `true` / 3 | 文档片段通道 |
| `enableGraphRecall` / `enableEntityRecall` | `true` / `true` | 图谱召回通道 |
| `language` | `auto` | `auto` / `zh_CN` / `en_US` |
| `smartRecallKeywords` | 内置中英文关键词表 | 关键词触发 |
| `captureMode` | `extract` | `extract` / `raw` |
| `captureMinLength` / `captureMaxChars` | 40 / 4000 | 捕获门槛与截断 |
| `requestTimeoutMs` / `writeTimeoutMs` | 30000 / 90000 | 读/写超时（写入含 LLM 提取，实测 25s+） |
| `debug` | `false` | 打印注入明细日志 |

## 依赖契约

- 运行时只 import：`@deepseek-ai/schemastery`（Config 校验）、`@deepseek-ai/dsh-llm`
  （`createUserMessage`）、`@deepseek-ai/dsh-tools`（`defineTool`）；
- 声明 `inject: ["agents", "tools"]`，由宿主 dsh 组合提供；
- **无构建步骤**：纯 ESM JavaScript，install.sh 直接复制到
  `~/.dsh/profiles/node_modules/memory-recall-dsh/`（loader 解析目录），
  与 `~/.dsh/plugins/dsh-lan-access` 同一安装机制。

## 标签约定（与 opencode / codex 插件一致）

- `userTag = keyId`（跨项目）；
- `projectTag = {keyId}_project-<cwd 目录名>`（项目隔离），每个 agent 按会话 cwd 推导；
- 后端契约：`X-API-Key` 头 + `GET /auth/verify` → keyId；统一召回 `POST /context-inject`。

## 开发与测试

```bash
# 依赖解析：把 node_modules 链到 dsh 的 profile node_modules（仓库内已被 gitignore）
ln -sfn ~/.dsh/profiles/node_modules node_modules

# 运行测试（单元 + 集成；集成用例连真实后端，缺 API Key 时自动跳过）
node --test
```

测试覆盖：配置解析/边界夹取/标签推导/语言检测/关键词触发；5 个工具端到端
（store→search→profile→forget）；自动召回（smart 关键词触发、once 首次注入、
摘要去重、后端不可达 fail-open）；自动捕获（turn 落库 + 无回复不落库）。

## 客户端 bundle 生成（MR-023）

dsh web 用 script 标签按 classic script 加载插件 bundle：不能含 import/export
（否则直接 SyntaxError），且必须顶层调用 window.__ModuleLoader__.load
注册插件形状 { name, inject, apply }。因此：

- client-lib.js —— node（服务端）ESM 库，index.js 从它 import；
- client.js —— 浏览器端 bundle，由 build-bundle.mjs 从 client-lib.js 生成
  （剥离 export + 包上注册壳），产物提交进仓库；
- 改 client-lib.js 后执行 node build-bundle.mjs 重新生成（test/bundle.test.js
  会校验产物同步，不同步测试即失败）；
- 安装/重启：bash install.sh --restart。

## 开发检查清单（防崩，MR-022/MR-023 教训固化）

**任何改动 → 安装 → 激活前，按顺序过一遍：**

1. **契约预检**（必做，防 dsh 启动即崩）：
   ```bash
   node preflight.mjs .
   ```
   检查 `dsh.client.platform` 为非空字符串（web profile 只接受 `"web"`）、
   `exports["./client"]` 存在且指向 bundle、bundle 为 classic script（无顶层
   import/export + 含 `__ModuleLoader__.load` 注册）。`install.sh` 的前置检查已内置
   该预检，未通过会拒绝安装（MR-022 事故：platform 缺失 → 插件树组合失败 → dsh 启动即退出）。

2. **改了库文件后重新生成 bundle**（`client.js` 是生成物，勿手改）：
   ```bash
   node build-bundle.mjs
   ```

3. **全量测试**：`node --test`（21 例全绿）。

4. **安装**：`bash install.sh --check`（先只查不装）→ `bash install.sh`。

5. **激活**：在**终端**里执行 `bash install.sh --restart`（或手动重启 dsh web）。
   ⚠️ **绝不在 agent（dsh 会话）内部重启宿主 dsh web 进程**——agent 就跑在
   dsh web 里，重启等于杀掉自己；且 dsh web 无守护进程托管，崩溃后无人拉起
   （2026-08-14 事故：GUI 挂机约 3 小时，靠手动重启恢复）。

6. **验证**：页面 200；`/plugins/<id>/client.js` 返回 200；boot 日志无
   `client-modules:` 报错；新会话里自动召回注入出现。

## 已知限制 / 后续

- 压缩（compaction）时未注入记忆摘要（opencode 插件有 compaction 注入，后续可对标）；
- 无客户端 UI（web 侧记忆浏览/纠错属于 MR-011 产品闭环，见 docs/ISSUES.md）；
- 文档导入（import-docs）未移植（文档 RAG 已按 ADR-0010 移出核心，不移植是正确方向）。
