# Round 1 回答：doubao

> 类型: 调研（原始回答归档）
> 调研: 2026-08-12-opencode-compaction-hook
> 说明: 对应 Q1/Q2；原文粘贴，未概括

### doubao

**Q1**

# OpenCode `experimental.session.compacting` 钩子完整梳理（基于官方源码+文档）

> 
> 前置说明：OpenCode 主仓库：[https://github.com/anomalyco/opencode；类型包](https://github.com/anomalyco/opencode%EF%BC%9B%E7%B1%BB%E5%9E%8B%E5%8C%85) `@opencode-ai/plugin` 定义该钩子类型；**`experimental.session.compacting` 是【压缩执行前、调用摘要LLM之前】的扩展点**，用于修改本次压缩的摘要提示词、追加额外上下文，区别于压缩完成后的通知事件 `session.compacted`（只读通知，不可改参数）

## 一、触发时机

### 时序（完整链路）

Agent 一轮交互结束 → 持久化消息 → **Token 预算校验超限** → 进入 compaction 流程 → **先执行 `experimental.session.compacting` 钩子** → 再调用摘要模型生成 summary → 写入摘要消息、标记旧工具输出为已压缩 → 重新组装下一轮上下文

1. **自动触发**：会话消息+工具输出 Token ≥ 模型可用窗口 − 预留缓冲区（默认约20k预留）；仅优先压缩工具输出 Part，普通 user/assistant 文本默认保留，逐级激进降级（工具输出裁剪 → 只保留最后一条用户消息 → 媒体剥离）
2. **手动触发**：用户执行 `/compact` 斜杠命令强制发起压缩，同样会先走本钩子
3. **不会触发**：仅内存临时修剪（prune）、单纯消息追加、普通LLM推理、压缩**完成后**（完成后走 `session.compacted`，不是本钩子）
4. **多次可重入**：一轮会话可多次触发，每次压缩前都会跑一遍该钩子链

> 
> 源码锚点：`packages/opencode/src/session/compaction.ts`，压缩主逻辑、钩子派发入口就在该文件内

## 二、`output.context` / `output.prompt`：含义、区别、优先级

### 类型签名（简化）

```
type ExperimentalSessionCompactingHook = async (
  input: CompactingInput, // { sessionId, messages, tokenStats, model, ... }
  output: CompactingOutput
) => Promise<void>
```

#### 1. `output.prompt`

- 含义：**本次摘要LLM直接使用的系统/指令提示词**，控制“怎么总结历史”
- 行为：**赋值即覆盖**；插件写 `output.prompt = "自定义摘要指令"` 会直接替换原生内置压缩提示词
- 用途：完全改写摘要规则、指定保留字段、强制结构化输出

#### 2. `output.context`

- 含义：**追加到摘要请求里的附加上下文片段数组（string[]）**，**追加、不覆盖原生prompt**
- 行为：`output.context.push(xxx)` 是追加；默认初始为空数组；多个插件push会累积拼接
- 用途：注入项目约束、活跃文件、当前任务、业务规则，**不改动基础摘要模板**

### ✅ 优先级与合并规则（核心）

1. **`output.prompt` 优先级 > `output.context`**
   - 只要任意插件**直接赋值覆盖 `output.prompt`**：原生内置压缩模板失效；`output.context` 仍然生效——**内容追加到这个新prompt后面**
   - 若无任何插件覆盖 `output.prompt`：使用OpenCode原生摘要prompt，所有插件 `output.context` 全部追加在原生prompt之后
2. 一句话记忆：> 
> `prompt = 底座模板（可被覆盖） + 所有context数组拼接`

## 三、多个插件同时注册该钩子：合并/覆盖 & 执行顺序

### 1. 钩子执行顺序（决定性）

插件加载顺序 = 钩子串行执行顺序，加载优先级从先到后：

1. 全局 `opencode.json` NPM插件
2. 项目 `opencode.json` NPM插件
3. 全局插件目录 `~/.config/opencode/plugins/`
4. 项目本地插件目录 `.opencode/plugins/`

> 
> 串行执行、共享同一个 `output` 对象（**引用传递**，不是副本）

### 2. 多插件行为规则

1. **`output.context`：累积追加**
 插件A push → 插件B push → 最终全部保留，按执行先后顺序拼接
2. **`output.prompt`：后写覆盖前写**
 插件A设置 `output.prompt = A` → 后面执行的插件B再赋值 `output.prompt = B` → 最终生效是B；**后执行插件可以抹掉前面插件改的prompt底座**
3. 典型组合案例
   - 插件1：只push context（注入项目规范）
   - 插件2：直接替换output.prompt（改写摘要格式）
    → 最终：使用插件2的prompt底座 + 插件1的context追加内容
4. 无“合并prompt”、无自动diff，就是简单引用可变对象串行修改

## 四、`experimental.` 前缀带来的兼容性风险（重点）

1. **无语义化版本承诺、无弃用预告**
 experimental 系列钩子**不属于稳定公共API**；可以在任意小版本直接删除、改名、修改input/output字段结构、变更触发时序，**不遵循semver**，不会提前发迁移通知
2. 类型包 `@opencode-ai/plugin` 里该类型可能无声变更，不会做向后兼容垫片
3. 行为边界可能调整：例如未来可能修改为 `output.context` 不再自动追加、或调整prompt/context拼接位置、或限制手动覆盖prompt
4. 调试/可观测性弱：错误隔离有限，钩子内抛异常**有可能直接中断本次压缩流程，导致会话直接溢出失败**（不会自动降级回原生压缩逻辑，早期版本无兜底）
5. 官方建议：**仅用于本地/内部实验，不要在生产/团队强制依赖的插件里使用；正式需求尽量用稳定事件 `session.compacted`（仅通知，不可修改压缩参数）**

## 五、官方文档链接 & 关键源码路径

### 官方配置/插件文档入口

[https://opencode.ai/docs/plugins](https://opencode.ai/docs/plugins)
[https://opencode.ai/config.json（Schema，插件声明）](https://opencode.ai/config.json%EF%BC%88Schema%EF%BC%8C%E6%8F%92%E4%BB%B6%E5%A3%B0%E6%98%8E%EF%BC%89)

> 
> 注意：官方主文档对 `experimental.session.compacting` 只做极简清单式标注，**详细行为、合并逻辑、output字段语义没有长文官方文档**，精确规则来自源码 compaction.ts + 类型定义 + 官方示例代码

### 核心源码路径（anomalyco/opencode 仓库）

1. 压缩主流程、钩子派发入口：`packages/opencode/src/session/compaction.ts`（最关键，触发钩子、组装prompt+context、调用摘要LLM）
2. Session 顶层调度：`packages/opencode/src/session/index.ts`
3. Message/Part 数据模型：`packages/opencode/src/session/message-v2.ts`
4. 插件类型定义（`@opencode-ai/plugin`）：`packages/plugin/src/types/hooks.ts`，包含 `experimental.session.compacting` 的 Input / Output TS 类型
5. 稳定后置事件（`session.compacted`，非本钩子）：同目录事件分发

## 六、最简可运行示例（官方示例原版）

```
import type { Plugin } from "@opencode-ai/plugin"
export const CompactionPlugin: Plugin = async () => {
  return {
    "experimental.session.compacting": async (input, output) => {
      // 方案A：追加上下文（推荐，不破坏原生摘要模板）
      output.context.push(`
## 项目约束
- 保留活跃文件：src/main.ts
- 重点跟踪：已完成重构任务
`);

      // 方案B：完全替换压缩prompt（高风险，experimental）
      // output.prompt = "请结构化总结会话，输出Goal/Discoveries/Todo";
    },
  };
};
```

## 七、一句话速记总结

`experimental.session.compacting` = **压缩前、摘要LLM调用前** 的可变钩子；`prompt` 是底座（后写覆盖前）、`context` 是追加片段（全部累积）；多插件串行、共享可变output；experimental意味着随时Breaking Change，生产慎用。

如果你需要，我可以再补充：

- input 对象完整字段清单 + TS接口
- 钩子异常兜底策略、失败降级的源码细节
- 和 `session.compacted`、手动 `/compact` 的完整对比表

**Q2**

# `experimental.compaction.autocontinue` 完整语义（基于 anomalyco/opencode 上游主干、PR#28798 与 `compaction.ts` 源码）

> 
> 一句话定位：**它是【压缩完成后、系统准备注入 synthetic "continue" 伪用户消息之前】的决策钩子**，用来控制：本轮压缩后，Agent 是否自动继续干活，而不是停住等待用户输入。
> 区分：`experimental.session.compacting` = **压缩摘要生成前**；`experimental.compaction.autocontinue` = **压缩已跑完、准备自动续行前**；`session.compacted` = **压缩完成只读通知**。

## 一、触发时机（时序链，非常关键）

完整链路：

1. Token超限 / `/compact` → 进入压缩
2. **`experimental.session.compacting`**（摘要LLM调用前，改prompt/context）
3. LLM生成摘要、替换旧消息、写入会话摘要节点
4. ✅ **触发 `experimental.compaction.autocontinue` 钩子**（就在系统判定“要不要自动注入continue伪消息”这一步）
5. 钩子返回决策 → 系统按决策决定是否插入 synthetic continue 消息，驱动Agent继续
6. 派发只读事件 **`session.compacted`**（通知类，不能改行为）

### 精确触发条件

- 仅在**一轮 compaction 成功落地、会话状态已替换为摘要+保留尾消息**之后、自动续行注入之前执行；
- 自动压缩（`compaction.auto=true`）、手动 `/compact` 都会走到这个钩子；
- **不会在压缩失败、压缩被跳过、普通非压缩回合触发**；
- 串行多插件注册：按插件加载顺序依次执行，**共享同一个output对象**。

> 
> 源码锚点：`packages/opencode/src/session/compaction.ts`，compact流程收尾、准备构建continue synthetic message 的分支内派发此钩子

## 二、`enabled: false` 会产生什么效果

钩子输出契约核心字段：`output.enabled: boolean`（默认**true**，遵从原生策略）

1. **`output.enabled = true`（默认）**：走原生规则；在符合条件时（存在未结束tool调用、任务未自然finish=stop）自动注入 `Continue…` 伪用户消息，Agent自动接着跑，不用人打字。
2. **`output.enabled = false`**：**强制取消本次压缩后的自动续行**，**不再注入 synthetic continue 消息**。
   - 表现：压缩完成、摘要写入后，Agent直接停轮，进入等待用户输入状态；
   - 重点：**它不阻止压缩本身**，只阻止“压缩→自动继续”这个续行动作；压缩流程、摘要生成、`session.compacted` 事件照常跑；
   - 典型用途：防止经典死循环 `overflow → compact → auto-continue → overflow → compact` 风暴、长任务审计、强制人工确认后再继续。

> 
> 注意：这是**按单次压缩实例生效**，不是全局永久关闭autocontinue；下一次新的compaction会重新询问本钩子。

## 三、输入参数 `input` 各字段含义（官方TS契约，`@opencode-ai/plugin` types/hooks.ts）

```
type ExperimentalCompactionAutocontinueHook = async (
  input: ExperimentalCompactionAutocontinueInput,
  output: { enabled: boolean }
) => Promise<void>
```

`input` 关键字段：

- `sessionId`：本次会话ID
- `auto: boolean`：本次压缩是否为**自动压缩**（token阈值触发=true；用户手动`/compact`强制压缩=false）
- `summary`：本次生成的压缩摘要文本
- `tokenStats`：压缩前后token统计（before/after、预留buffer）
- `assistantEndedNaturally: boolean`：核心判断位 —— 压缩前那一轮assistant是否正常finish="stop"、自然结束任务（原生逻辑优先用这个决定要不要自动续行）
- `hasPendingToolCalls: boolean`：压缩前是否存在未完成/待恢复的tool调用（原生自动续行的强条件）

> 
> 插件只读input，**不能修改input**；只能写`output.enabled`布尔值作为决策。

## 四、和 `session.compacted` 事件的关系（高频混淆点）

| 项 | `experimental.compaction.autocontinue`（钩子） | `session.compacted`（事件） |
| --- | --- | --- |
| 类型 | 可决策插件钩子（能改变后续行为） | 只读通知事件，不可修改流程 |
| 时序 | 在session.compacted**之前**执行 | 在autocontinue钩子、决定是否注入continue之后触发 |
| 能力 | 控制：要不要自动续行、注入伪continue消息 | 仅告知外部：本次压缩已经完成，可做日志/外部记忆同步 |
| 副作用 | 能阻断自动续行逻辑 | 监听者无法改变会话内Agent行为 |
| 失败影响 | 钩子抛异常：一般降级为`enabled=true`回退原生策略（不同版本有差异，experimental无强兜底承诺） | 监听异常不影响会话主流程 |

一句话时序记忆：

> 
> 压缩落地 → **autocontinue钩子（决定要不要续）** → 注入/不注入continue伪消息 → **派发 session.compacted 通知**

## 五、多插件同时注册该钩子：合并/覆盖规则

1. 串行执行，共享同一个可变`output`对象；
2. `output.enabled` 是**后写覆盖前写**：
   - 插件A：`output.enabled = true`
   - 插件B（后执行）：`output.enabled = false`
    → 最终生效：`false`（阻断自动续行）
3. 没有“取并/取反/投票”语义，就是简单覆盖；
4. 如果你想实现“任一插件禁止就阻断”，需要自己在插件里叠加判断逻辑（例如读取input+外部状态）。

## 六、`experimental.` 前缀带来的兼容性风险

1. **非稳定API，不遵守semver**：可在小版本直接删除、改名、删除`enabled`字段、变更input结构、调整派发时序，**无提前弃用通知、无迁移垫片**；
2. 契约可变：未来可能扩展output增加其他字段（例如自定义continue消息文本），或直接移除本钩子，改为内置配置开关；
3. 边界行为可能调整：例如未来修改降级策略（钩子抛异常不再回退原生，直接强制禁用autocontinue）；
4. 典型坑：不要在团队强制依赖的生产插件强绑定这个钩子；适合本地实验、长任务风控、防compact风暴。

## 七、官方文档链接 & 源码路径

1. 插件文档主页（仅清单式标注experimental钩子，详细契约在源码+PR）
 [https://opencode.ai/docs/plugins](https://opencode.ai/docs/plugins)
2. 核心源码路径（anomalyco/opencode）
   - 压缩主流程+autocontinue钩子派发：`packages/opencode/src/session/compaction.ts`
   - 插件类型定义：`packages/plugin/src/types/hooks.ts`
   - 关键行为定义PR（修复autocontinue在自然结束任务时误续行）：#28798（本钩子行为基准PR）

## 最简示例

```
import type { Plugin } from "@opencode-ai/plugin"
export const CompactAutoContinuePlugin: Plugin = async () => {
  return {
    "experimental.compaction.autocontinue": async (input, output) => {
      // 场景：如果assistant已经自然结束任务，禁止自动续行，防止无限循环
      if (input.assistantEndedNaturally) {
        output.enabled = false
      }
      // 其他情况保持默认true，允许自动继续
    }
  }
}
```

## 速记三句话

1. `experimental.compaction.autocontinue` = **压缩成功后、注入continue伪消息前的决策点**；
2. `enabled=false` ≠ 不压缩，**只是不让压缩后自动继续，停住等用户**；
3. 在 `session.compacted` 事件**之前**执行；前者可控流程，后者仅通知。

如果你需要，我可以把这4个钩子/事件整理成一张完整生命周期时序总表：`experimental.session.compacting` → `experimental.compaction.autocontinue` → `session.compacted`，并标注各自输入输出、异常兜底、多插件覆盖规则。

**Q3**

**Q4**

**Q5**

**Q6**

**Q7**

**Q8**

