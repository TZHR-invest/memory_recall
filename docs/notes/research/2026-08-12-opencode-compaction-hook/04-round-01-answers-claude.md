# Round 1 回答：Claude

> 类型: 调研（原始回答归档）
> 调研: 2026-08-12-opencode-compaction-hook
> 说明: 对应 Q1/Q2；原文粘贴，未概括

### Claude

**Q1**

# `experimental.session.compacting` 插件钩子系统梳理

## 1. 触发时机

该钩子在 opencode 判断会话需要压缩（compaction）时被调用，具体位置在 **`packages/opencode/src/session/compaction.ts`** 的 `SessionCompaction.process()` 流程中：

- 触发点：当 SessionCompaction.process() 运行时，会触发 Plugin.trigger("experimental.session.compacting")（compaction.ts 第 145-151 行），将自定义指令与默认模板合并后再发送给 LLM。
- 语义上：experimental.session.compacting 钩子在 LLM 生成续接摘要（continuation summary）之前触发，用于注入默认压缩提示词遗漏的领域特定上下文。
- 触发条件（上游）：当检测到 token 溢出时，SessionProcessor（processor.ts 第 412 行）会返回 "compact"，从而触发 SessionCompaction.process()（compaction.ts 第 101-229 行）。在此之前系统还会先执行 `SessionCompaction.prune()`（同文件第 55-99 行）标记陈旧工具输出以降低 token 压力，之后才构建 compaction prompt 并触发该钩子。

也就是说，调用链是：**溢出检测 → prune 旧工具调用 → 触发 `experimental.session.compacting` 让插件可修改 prompt/context → 组装最终 prompt → 调用 LLM 生成摘要**。

## 2. `output.context` 与 `output.prompt` 的区别和优先级

两者的语义完全不同，且存在明确的"后者优先、前者被忽略"规则：

- `output.context`：是一个**数组**，用 `.push()` 追加内容，会被拼接进**默认压缩模板**中，不会替换整个 prompt。
- `output.prompt`：是**完整替换**默认压缩提示词的字符串。

官方文档明确给出优先级规则：当设置了 output.prompt 时，它会完全替换默认的压缩提示词，此时 output.context 数组会被忽略。

这一行为在源码层面也能对应上：nextPrompt = compacting.prompt ?? buildPrompt({ previousSummary, context: compacting.context })——即用 `??`（空值合并）判断，只要插件设置了非空的 `prompt`，就直接使用它，`buildPrompt`（内部会用到 `context`）根本不会被调用，`context` 因此被短路忽略。

## 3. 多插件同时注册该钩子的合并/覆盖规则

opencode 的插件钩子机制是**同一个可变 output 对象在多个插件间顺序传递、就地修改**，不是"多个返回值做深度合并"：

- 加载顺序：插件从所有来源加载，所有钩子按顺序执行，加载顺序依次为：全局配置 → 项目配置 → 全局插件目录（~/.config/opencode/plugins/）→ 项目插件目录（.opencode/plugins/）。
- 执行语义：Plugin.trigger 方法会遍历某个钩子名下所有已注册的钩子并依次执行，允许每个钩子就地（in place）修改 output 对象。

由此可以推导出对 `experimental.session.compacting` 具体的合并规则：

| 字段 | 多插件行为 |
|---|---|
| `output.context.push(...)` | **累加合并**：由于是同一个数组的引用，插件 A push 的内容不会被插件 B 覆盖，只要没有插件清空/重写整个数组，最终结果是所有插件依次 push 的内容都会保留，顺序按插件加载顺序排列。 |
| `output.prompt = "..."` | **后写覆盖（last-write-wins）**：如果多个插件都设置了 `output.prompt`，由于是同一个对象字段的赋值，**最后一个执行的插件会覆盖前面插件设置的值**，不存在自动的字符串拼接或提示。 |
| `prompt` 与 `context` 混用时 | 只要**任意一个**插件设置了非空 `output.prompt`，无论其执行顺序在前在后，最终都会走 `compacting.prompt ?? ...` 分支，之前/之后其他插件对 `context` 的 push 都会在生效判断上被忽略（但如果后面还有插件把 `prompt` 置回 `undefined`，则又会回退到 `context` 路径——因为判断是在所有钩子跑完之后一次性做的）。 |

需要特别提醒：这是一种**隐式、脆弱**的合并机制——没有命名空间隔离、没有冲突检测、没有优先级声明字段，完全依赖插件加载顺序这一"隐藏契约"。如果你同时装了两个都会写 `output.prompt` 的插件（比如上文示例中的多智能体压缩模板插件 + 社区的"保留精确细节"压缩插件），实际生效的只有目录加载顺序中较晚的那一个，非常容易在插件组合时产生"某个插件的自定义压缩提示词突然失效"的静默 bug。

## 4. `experimental.` 前缀带来的兼容性风险

这是这个钩子当前最大的隐患，官方明确将其列为实验性、且已有真实翻车案例：

1. **类型定义缺失导致钩子被静默丢弃**：experimental.chat.system.transform、experimental.session.compacting 这两个钩子并未定义在 @opencode-ai/plugin 的公开类型定义中，Hooks 类型只暴露了 tool、auth、event、config、chat.message、chat.params 等。更严重的是运行时行为：opencode 会静默忽略未知的钩子名——不报错、不警告——导致依赖这些钩子的功能完全失效，例如 memory injection during compaction 永远不会触发。也就是说，**如果你的插件代码写错了 hook 名字，或者当前安装的 opencode 版本还未实现该 hook，插件不会抛异常，只会悄无声息地不生效**，排查成本很高。

2. **官方内部也把它标记为"不稳定、可能变化"**：社区实践中甚至有插件作者主动放弃使用它，理由是：experimental.session.compacting 注入功能被排除的原因是"API 是实验性且不稳定的"，转而用 session.created 重新加载覆盖下一次会话的场景，并计划"等 API 稳定后再重新评估"。

3. **相关基础设施仍在演进中**，例如压缩阈值、压缩模型选择等都还在实验性 flag 阶段（如 `OPENCODE_EXPERIMENTAL_COMPACTION_PRESERVE_PREFIX`、`OPENCODE_EXPERIMENTAL_COMPACTION_PROMPT`），说明整个 compaction 子系统本身仍处于快速迭代期，`experimental.session.compacting` 的输入/输出 schema 未来有变更（甚至是破坏性变更或改名）的可能性较高。

**实践建议**：
- 升级 opencode 版本后，务必手动验证该钩子确实被调用（例如在 hook 内打日志），不要假设"没报错=生效"。
- 不要在生产关键路径上单独依赖它做不可降级的功能；建议同时保留一个非 experimental 的兜底（如 `session.created`/`session.compacted` 事件）。
- 多插件场景下，显式约定"谁负责写 `output.prompt`，谁只写 `output.context`"，避免加载顺序导致的隐式覆盖。

## 5. 官方文档与关键源码索引

**官方文档**
- 插件总览与 Compaction hooks 示例：https://opencode.ai/docs/plugins/（"Compaction hooks" 小节，含 `output.context.push` 与 `output.prompt` 两个完整示例代码）

**关键源码路径**（均在 `anomalyco/opencode` 仓库 `dev` 分支）
- `packages/opencode/src/session/compaction.ts` —— `SessionCompaction.process()`（触发点约第 101-229 行，`Plugin.trigger("experimental.session.compacting")` 调用约第 145-151 行，`prompt ?? buildPrompt(...)` 的优先级判断逻辑）；`SessionCompaction.prune()`（约第 55-99 行）
- `packages/opencode/src/plugin/index.ts` —— `Plugin.trigger` 的钩子遍历/顺序执行/就地修改 output 的实现
- `packages/plugin/src/index.ts` —— `Hooks` 类型定义（**目前官方公开类型未包含 `experimental.session.compacting`，这是风险点之一**）
- `packages/opencode/src/session/processor.ts`（约第 412 行）—— overflow 检测后返回 `"compact"`，触发上游压缩流程
- `packages/opencode/src/plugin/loader.ts` —— 插件加载顺序（全局配置 → 项目配置 → 全局插件目录 → 项目插件目录）的实现

**关联 Issue（第三方问题追踪，非官方文档，仅供交叉验证）**
- vectorize-io/hindsight#2656 —— `experimental.*` 钩子因类型缺失被静默忽略的真实 bug 报告
- anomalyco/opencode#16512 —— 展示了通过 `output.prompt` 完全自定义压缩提示词的实战写法
- anomalyco/opencode#11497 —— compaction 相关实验性 flag（如 `OPENCODE_EXPERIMENTAL_COMPACTION_PROMPT`）

**Q2**

我需要诚实地说明一下检索结果：**`experimental.compaction.autocontinue` 这个钩子名称没有出现在 opencode 官方文档站（opencode.ai/docs/plugins）里**，官方 Compaction hooks 章节只明确记载了 `experimental.session.compacting` 一个钩子（连同 `output.context` / `output.prompt` 用法）。我检索到的关于 `experimental.compaction.autocontinue` 的信息，全部来自**非官方的第三方来源**：

- 一个第三方仓库（JuliusBrussee/caveman）的 issue 里，作者罗列了他们所理解的 opencode Hooks 接口支持的钩子名单，其中包含 experimental.chat.system.transform、experimental.chat.messages.transform、experimental.session.compacting、experimental.compaction.autocontinue，但这是第三方对 opencode 插件 API 的**转述**，不是 opencode 官方文档或源码。
- 一个社区插件 token-optimizer 在其 README 的钩子用途表中写着：experimental.compaction.autocontinue 用于"压缩后重置信号、刷新质量评分"，但这只是**该插件自己的使用说明**，同样不是 opencode 官方对该钩子输入/输出 schema 的定义。

也就是说，我**没有找到官方文档或 opencode 主仓库源码里对 `experimental.compaction.autocontinue` 的权威定义**（对比上一轮 `experimental.session.compacting`，我能直接定位到 `compaction.ts` 里 `Plugin.trigger` 的具体行号和字段语义；但这个钩子我找不到对应的源码引用）。如果我在这里编出"输入参数分别是 xxx、`enabled: false` 会如何如何"，那是在编造，不能这样做。

**我能负责任地告诉你的是与它高度相关、且确实有源码依据的底层机制**，这大概率就是这个 hook 名字背后想暴露的能力：

- opencode 的自动续接（auto-continue）逻辑在 SessionCompaction.process() 里由 result === "continue" && input.auto 这个条件控制：当条件成立时，会注入一条合成的 "Continue if you have next steps..." 用户消息，从而让 agent 在压缩完成后自动接着干活，而不是停下来等你手动敲 "continue"。
- 这个 input.auto 标志目前来自更上游的调用，例如 /session/:sessionID/summarize 接口；有一个已合并的改动把这个 auto 参数暴露给了插件——之前它在 summarize 接口里被硬编码为 false，导致插件调用 client.session.summarize() 时无法开启压缩后自动续接；改动后插件可以显式传 auto: true 来启用"压缩后自动续接"。
- 该行为存在已知边界问题：当 assistant 已经自然结束当前轮次（finish === "stop"）时，compaction.ts 目前仍会无条件注入这条合成续接消息，被社区标记为会导致无限循环的 bug，正确行为应该是只在 finish === "tool-calls"/"unknown"（也就是模型还在工具调用中途）时才注入续接消息</cite。

所以，如果 `experimental.compaction.autocontinue` 这个钩子确实存在于某个版本的 opencode 中，从命名和上下文推断，它很可能是用来让插件**拦截/覆盖**上面这个"是否注入合成 continue 消息"的判断逻辑（对应你问的 `enabled: false`——大概率语义是"插件显式让本次压缩后不要自动续接，交还控制权给用户"），但我**没有可验证的源码或官方文档能确认**输入参数的具体字段名、`enabled` 是否就是唯一字段、以及它和 `session.compacted` 事件之间的触发先后顺序。

**关于它和 `session.compacted` 事件的关系**，同样只能给出有依据的部分：官方文档中 `session.compacted` 被列为标准 Session Events 之一（`session.created`、`session.compacted`、`session.deleted`、`session.diff`、`session.error`、`session.idle`、`session.status`、`session.updated`），是通过通用的 `event` 钩子订阅的**事件通知**（只读、发生在压缩完成之后，用于告知外部"这次压缩已结束"）；而 `experimental.session.compacting`（以及推测中的 `autocontinue`）是**压缩过程中/前后可修改行为**的干预点。二者若共存，合理的顺序应是：`experimental.session.compacting`（压缩前，可改 prompt）→ 实际生成摘要 →（可能存在的）`experimental.compaction.autocontinue`（决定是否自动续接）→ `session.compacted` 事件广播（压缩已完成，仅通知）。但这个顺序是我基于机制的合理推断，不是我能直接引用到的源码结论。

**建议你验证的方式**：直接在你本地的 opencode 安装目录里跑

```bash
grep -rn "compaction.autocontinue\|autocontinue" node_modules/@opencode-ai/plugin/dist/*.d.ts packages/plugin/src/index.ts 2>/dev/null
```

或者查看你当前 opencode 版本对应的 `@opencode-ai/plugin` 类型定义文件，看这个钩子是否真的在你的版本里被类型化导出——结合上一轮讨论过的"`experimental.` 前缀钩子可能未在类型里声明、未声明则会被静默丢弃"的风险，这一步核实比我这边继续检索更可靠。

**Q3**

**Q4**

**Q5**

**Q6**

**Q7**

**Q8**

