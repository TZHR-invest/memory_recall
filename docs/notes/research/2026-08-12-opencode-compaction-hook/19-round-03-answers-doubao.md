# Round 3 回答：doubao

> 类型: 调研（原始回答归档）
> 调研: 2026-08-12-opencode-compaction-hook
> 说明: 对应 R3-1（生态共存/最佳实践）

#### doubao
# 前置关键结论（先对齐你之前确认的源码规则）
> `nextPrompt = compacting.prompt ?? buildPrompt({ previousSummary, context: compacting.context })`
**只要任意一个插件在 `experimental.session.compacting` 里赋值了 `output.prompt = string`：短路、`buildPrompt` 不执行、**所有插件push进去的 `context` 全部丢弃**。
> 只有**全部插件都不写 `output.prompt`**，所有插件push的 `context` 数组才会被合并传入 `buildPrompt`。
> 多插件执行顺序：**按插件加载顺序串行执行，后执行插件可以覆盖前面插件写的 `output.prompt`；context是数组push、追加合并，不会互相覆盖**（只要没人设置prompt）

> ⚠️ 现状先行说明：**OpenCode（anomalyco/opencode）官方没有维护一个中心化插件注册表**；`experimental.session.compacting` / `experimental.compaction.autocontinue` 属于**实验性钩子**，公开、成熟、带完整源码的压缩增强插件数量很少，**没有成体系的官方名录**；下面列出的是**社区公开可检索、明确注册该组钩子的已知项目**，不含私有/个人未发布脚本。

## 1. 已知注册这两个压缩钩子的项目清单
### ✅ ① Oh-My-OpenCode（yeongyu/Oh-My-OpenCode）
> 最知名的OpenCode增强包，你提到的标杆项目
- 仓库：`https://github.com/yeongyu/Oh-My-OpenCode`
- 钩子注册情况：
  1. `experimental.session.compacting`：✅ 注册
  2. `experimental.compaction.autocontinue`：✅ 注册（用于控制溢出后是否自动发起压缩）
- **核心行为（源码真实写法）：默认只 push `output.context`，不设置 `output.prompt`**
  - 默认策略：追加项目规范、架构约束、重要文件快照、持久化记忆块到压缩上下文，复用原生 `buildPrompt` 模板；
  - 高级模式（可选开关）：**允许用户开启自定义压缩Prompt，一旦开启就会赋值 `output.prompt`，直接抹掉所有其他插件的context**；
- 风险点：如果用户在Oh-My-OpenCode配置里打开 `customCompactionPrompt`，**你的只push context的插件会直接失效，追加内容不会进最终压缩prompt**

### ✅ ② opencode-plugin-smart-compaction（社区独立增强插件，常被作为示例）
> 掘金/社区教程里最常引用的纯压缩增强插件，也是很多自定义脚本的样板
- 仓库：`https://github.com/opencode-plugins/opencode-plugin-smart-compaction`
- 钩子注册：`experimental.session.compacting` ✅；`experimental.compaction.autocontinue` ✅
- **默认行为：仅 push context，不设置 prompt**
  用途：追加token预算标记、关键路径白名单、禁止压缩的文件列表、会话元信息；
  极少场景才会替换prompt（仅大模型摘要质量专项调优分支）

### ✅ ③ 社区教程示例插件（掘金等文章里的最小demo）
> 掘金《OpenCode实验钩子实战》系列里的极简compacting示例，大量用户直接复制复用
- 无独立NPM包，以gist/代码片段分发
- 典型代码范式：
```ts
export default {
  hooks: {
    "experimental.session.compacting": async (input, output) => {
      output.context.push("【附加约束：xxx】");
    }
  }
}
```
- 行为：**只push context、永远不写output.prompt**；是最安全、最常见的第三方插件写法

### ❌ 补充：热门但**不注册这两个压缩钩子**的知名插件（避坑）
- `opencode-plugin-loop`：只做定时任务调度，**完全不碰compacting/autocontinue**，和压缩链路无关；
- OpenSpec / opsx系列：规划归档类插件，不注册compacting钩子；
- 官方内置逻辑：**框架本身不是插件，内置压缩逻辑在compaction.ts，不属于插件钩子体系**

## 2. 两类插件的倾向总结
1. **绝大多数社区compaction增强插件（Oh-My-OpenCode默认版、smart-compaction、教程demo）：只push context，不碰output.prompt**
    - 设计意图：做**附加信息注入**，兼容原生压缩模板、兼容其他同类型插件共存
2. **少数高级/定制分支：会设置output.prompt（全量替换压缩摘要指令）**
    - 一旦启用 → **全局短路规则生效，所有其他插件push的context全部丢失**（包括你的）

## 3. 你的插件「只push context」共存：已知冲突 + 最佳实践
### 🚨 已知核心冲突（只有一类致命冲突）
> **只要环境里有任意插件（含Oh-My-OpenCode开启customCompactionPrompt）执行 `output.prompt = "自定义摘要指令"` → 你的context直接被忽略、不会拼进最终prompt**
> 次要冲突：多插件同时push context只会**顺序追加数组**，本身不会覆盖，内容会全部保留；但token上限问题可能导致部分上下文被模型截断（不是钩子机制层面的覆盖，是LLM窗口限制）

### ✅ 共存最佳实践（按优先级）
1. **前置检测防御（强推荐，代码可直接写）**
    在你的 `experimental.session.compacting` 钩子开头，**先检测是否已有别的插件写入了 `output.prompt`**：
    ```ts
    "experimental.session.compacting": async (input, output) => {
      if (output.prompt !== undefined) {
        // 已有插件接管完整prompt，直接return，不要静默失效；可打warning日志
        console.warn("[your-plugin] compaction prompt already overridden by another plugin, skip context append");
        return;
      }
      output.context.push(/*你的内容*/);
    }
    ```
2. **文档显式声明兼容性**
    > 本插件仅追加context、依赖原生buildPrompt；**若同时启用任何设置output.prompt的压缩插件/开关，本插件附加上下文会失效**（尤其提醒Oh-My-OpenCode用户不要开启customCompactionPrompt）
3. **不要自己兜底写prompt**：你的定位是附加上下文，一旦你也赋值prompt，直接破坏所有同类context型插件
4. **autocontinue钩子共存提示**：`experimental.compaction.autocontinue` 输出只有`enabled`，多插件串行执行时**后执行插件的enabled会覆盖前面**；如果你要和Oh-My-OpenCode共存，注意autocontinue的执行顺序冲突（它会控制是否自动触发压缩）

### 📌 一句话风险口诀
> **Context是累加池，Prompt是断路器；只要有人写Prompt，全部Context直接丢。**

## 4. 补充：源码锚点（和你前面核对的compaction.ts保持一致）
文件：`packages/opencode/src/session/compaction.ts`（dev分支 anomalyco/opencode）
1. 触发插件钩子：收集所有插件返回的 `compacting: {context: string[], prompt?: string}`
2. 合并规则：所有插件的context push合并；prompt取**最后一个非undefined值**
3. 短路求值行：`nextPrompt = compacting.prompt ?? buildPrompt({ previousSummary, context: compacting.context })`

如果你需要，我可以直接给一份**可放进插件README的兼容性声明文本** + 完整防御型钩子样板（同时包含compacting+autocontinue）。

