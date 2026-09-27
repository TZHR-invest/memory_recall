# Memory Recall DSH Plugin (memory-recall-dsh)

为 **DeepSeek Harness (dsh)** 提供长期记忆能力的客户端插件，对标 opencode 插件
`memory-recall-opencode`：工具注册 + 自动召回注入 + 自动捕获，后端为 memory-recall
FastAPI（`apps/api`）。

## 功能

| 能力 | 说明 |
|------|------|
| 记忆工具 | `memory_store`（默认异步，立即返回）/ `memory_search` / `memory_profile` / `memory_list` / `memory_forget` / `memory_update`（版本化修正，ADR-0009） |
| 自动召回 | `agent/pre-step` 时按策略调 `POST /context-inject`，把召回上下文以 `<system-reminder>` 框定消息折入本轮请求 |
| 自动捕获 | `turn/end` 时把该轮 user+assistant 摘要写入长期记忆（`extract` 蒸馏 / `raw` 原文，默认 `extract`） |

### 注入策略（injectionStrategy）

| 策略 | 行为 |
|------|------|
| `once` | 仅会话首次请求注入（含画像 + 记忆 + 文档片段） |
| `smart`（默认） | 首次注入 + 关键词触发（"记得/之前/项目/架构/怎么…"，可配置） |
| `always` | 每轮 step 1 都注入 |

会话内按内容摘要去重：同一轮召回文本不会重复注入。
跨轮次按已注入记忆 ID 去重（per-agent LRU，容量 100）：同一记忆被不同 query
再次召回时由后端 exclude_memory_ids 排除，避免反复注入相同内容。

### 自动捕获（captureMode）

- `extract`（默认）：`POST /extract-memory` 用后端 LLM 蒸馏出值得保存的记忆再逐条落库
  （`type=preference` 自动归为永久特征）。**蒸馏判定"无值得保存"时静默不存**
  （尊重判断，避免临时对话灌入长期记忆）；仅蒸馏接口报错才回退 raw 保全信息；
- `raw`：把摘要原文存为 `conversation` 类型记忆（截断到 `captureMaxChars`）。

捕获为 fire-and-forget + fail-open（写入走 `async_process` 后台完成），绝不阻塞
agent 主流程；**subagent 会话（header.origin="subagent"）不捕获**，避免子任务噪音。
后端对语义相似内容有合并去重（threshold 0.85），重复捕获会自动合并到最新版本。

## 安装

```bash
cd apps/api/src/plugins/dsh
bash install.sh                                      # 安装到 web profile（幂等）
bash install.sh --api-key rk_live_xxx \\               # 把 API Key 写进 profile patch（可选）
  --backend-url http://<你的后端服务器>:8000             # 后端地址（自部署远程服务器，不固定）
# 地址/Key 配置优先级：--backend-url/--api-key 参数 > MEMORY_RECALL_BASE_URL/MEMORY_RECALL_API_KEY
# 环境变量 > 交互询问（仅安装时，输入不回显）
bash install.sh --restart            # 安装后重启 dsh web 并验证（会短暂中断 web 服务）
bash install.sh --check              # 只检查状态
bash install.sh --uninstall          # 卸载
```

安装完成（或 `--restart` 重启）后，新会话即生效；**已打开的会话需重启 dsh 才加载插件**。

### 其他机器安装（一键分发包）

```bash
# 在开发机打包（地址不在打包时写死——后端是各用户自部署的远程服务器）
cd apps/api/src/plugins/dsh
bash package.sh
# 产物: dist/memory-recall-dsh-install.tar.gz（自包含：插件 + 契约预检 + 安装脚本，
#       目标机器无需 clone 仓库、无需 dsh-plugins）

# 目标机器（已装 dsh web）三步安装，后端地址由目标机器安装时配置
scp dist/memory-recall-dsh-install.tar.gz user@目标机:~/
tar xzf memory-recall-dsh-install.tar.gz && cd memory-recall-dsh-install
bash install.sh --api-key rk_live_xxx --backend-url http://<你的后端服务器>:8000
bash install.sh --restart               # 终端执行，冒烟通过才重启
```

要求：Node.js 18.17+；dsh web 已初始化；memory-recall 后端可达；
headless 冒烟需 headless profile（首次 `dsh --profile headless "1"` 自动初始化）。

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
| `minRecallQueryLength` | 5 | 查询长度闸门，**只约束非首轮**（<5 字的非首轮查询不触发召回，挡住 "嗯"/"ok" 白跑一次语义检索）；首轮无条件注入、画像随首轮下发，不受长度限制（2026-09-28 修：此前闸门排在首轮判定之前，"继续"/"test" 这类 ≤4 字开场会连画像一起丢） |
| `captureMode` | `extract` | `extract` / `raw` |
| `captureMinLength` / `captureMaxChars` | 100 / 4000 | 捕获门槛与截断（2026-08-16 门槛 40→100 抑制短轮碎片） |
| `captureMinIntervalMs` | 600000 | 捕获节流：两次蒸馏最小间隔（ms，0=关闭）；窗口内摘要累计到下轮，信息不丢（2026-08-16） |
| `requestTimeoutMs` / `writeTimeoutMs` | 30000 / 90000 | 读/写超时（写入含 LLM 提取，实测 25s+） |
| `injectTimeoutMs` | 3000 | 自动召回注入预算：超过则跳过本轮注入（模型请求关键路径不被拖慢） |
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
node --test            # 需要 node ≥18：本机系统 node 是 v12，用 nvm 的 node 执行
MR_TEST_BASE_URL=http://<后端>:8000 node --test   # 后端不在本机时
```

测试覆盖：配置解析/边界夹取/标签推导/语言检测/关键词触发；6 个工具端到端
（store→update 版本链→search→profile→forget）；自动召回（smart 关键词触发、
once 首次注入、首轮短查询仍注入、非首轮长度闸门、跨轮去重、后端不可达 fail-open）；
摘要去重 source 形态兼容（v3/v4）；自动捕获（turn 落库 + 无回复不落库 + 节流）；
bundle 生成产物同步性 + classic-script 合法性 + `__ModuleLoader__.load` 注册形态。

⚠️ 测试里有联网用例（连真实后端、部分单条 >25s），且默认 `baseUrl` 是
`http://localhost:8000`——后端不在本机时用 `MR_TEST_BASE_URL` 指向真实地址，
否则整组用例假失败；且**不要**把用例的容器目录写死复用（后端对高相似内容会合并
去重，旧内容会让"刚写入的 marker"断言假失败），按 `xxx-<Date.now()>` 每轮独立。

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

3. **全量测试**：`node --test`（29 例全绿；其中联网用例约 60s）。

4. **安装**：`bash install.sh --check`（先只查不装）→ `bash install.sh`。

5. **冒烟试启动**（防"启动即崩"）：`bash install.sh --smoke` 在隔离的 headless
   profile 里真实 boot 一次插件组合（约 10-30 秒），插件契约/加载有问题会在
   boot 阶段崩溃并被判定中止（退出码 1），正式 web 完全不受影响。
6. **激活**：**绝不在 agent（dsh 会话）内部重启宿主 dsh web 进程** —— agent 就跑在
   dsh web 里，重启等于杀掉自己（2026-08-14 事故：GUI 挂机约 3 小时）。当前 dsh web
   由 **systemd 用户单元**托管（`dsh.service`，`Restart=always`），在**终端**里执行：
   ```bash
   systemctl --user restart dsh.service
   ```
   ⚠️ **systemd 托管下不要用 `bash install.sh --restart`**（2026-09-28 实测）：该单元的
   ExecStart 是相对路径 `node ./lib/bin.js web --trusted-host …`，脚本里 5 个
   `pkill -f` 模式（`dsh web` / `node_modules/.bin/dsh web` / `npm exec …` /
   `sh -c dsh web` / `@deepseek-ai/dsh/lib/bin.js web`）**没有一个匹配它**（逐条子串
   验证过），于是旧进程杀不掉，脚本又 `setsid nohup` 起一个竞争进程抢 3080。
   （`--smoke` 在 MR-025 之后已能正确定位 dsh：`command -v dsh` 优先，覆盖 nvm/npm
   全局安装与 npx 缓存两种形态。）
   手动冒烟与回滚：
   ```bash
   MEMORY_RECALL_API_KEY=<key> dsh --profile headless "1"    # 隔离 headless 试启动
   bash install.sh --uninstall && systemctl --user restart dsh.service   # 回滚
   ```

7. **验证**：页面 200；`/plugins/<id>/client.js` 返回 200；boot 日志无
   `client-modules:` 报错；新会话里自动召回注入出现。

## 已知限制 / 后续

- 压缩（compaction）时未注入记忆摘要（opencode 插件有 compaction 注入，后续可对标）；
- 无客户端 UI（web 侧记忆浏览/纠错属于 MR-011 产品闭环，见 docs/ISSUES.md）；
- 文档导入（import-docs）未移植（文档 RAG 已按 ADR-0010 移出核心，不移植是正确方向）。
