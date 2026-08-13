# Round 1 回答：Gemini

> 类型: 调研（原始回答归档）
> 调研: 2026-08-12-opencode-compaction-hook
> 说明: 对应 Q1/Q2；原文粘贴，未概括

### Gemini

**Q1**

`experimental.session.compacting` 是 OpenCode 插件系统中用于干预和增强会话上下文压缩（Session Compaction）流程的关键实验性钩子。

---

### 1. 官方文档与关键源码路径

* **官方文档链接**：
* [OpenCode Plugins Guide](https://opencode.ai/docs/plugins/)
* [OpenCode Compaction Docs](https://opencode.ai/v2/docs/compaction)


* **关键源码路径**：
* **钩子调用与压缩主逻辑**：`packages/opencode/src/session/compaction.ts`
* **插件系统与钩子类型定义**：`packages/opencode/src/plugin/`



---

### 2. 触发时机

该钩子在会话需要执行上下文压缩（Compaction）且**即将调用 LLM 生成续接摘要（Continuation Summary）之前**被触发。

触发的具体场景包括：

1. **自动压缩（Auto Compaction）**：系统在发起 Model Request 前进行预检，估算 Token 超过阈值（`estimated tokens > context limit - max(requested output tokens, buffer)`）时。
2. **溢出恢复（Overflow Recovery）**：LLM Provider 返回 context overflow 错误，系统自动尝试一次压缩恢复时。
3. **手动触发**：用户在 TUI 中输入 `/compact` 或 `/summarize` 指令时。

在触发钩子时，OpenCode 会向钩子传入当前会话的上下文参数：

```typescript
input: { sessionID: string }

```

---

### 3. `output.context` 与 `output.prompt` 的区别与优先级

钩子的输出结构如下：

```typescript
output: {
  context: string[];  // 注入的上下文列表
  prompt?: string;    // 自定义的压缩 Prompt
}

```

| 属性 | 数据类型 | 作用与机制 |
| --- | --- | --- |
| **`output.context`** | `string[]` | **追加/补充模式**。用于向默认的 Compaction Prompt 中注入领域特定的上下文（如重要的项目背景、未完成任务的补充说明等），避免默认压缩丢失细节。 |
| **`output.prompt`** | `string`（可选） | **替代/重写模式**。直接替换 OpenCode 默认内置的上下文总结 Prompt Template。 |

#### 优先级与生效逻辑

* **`output.prompt` 拥有最高控制权**：一旦插件设置了 `output.prompt`，OpenCode 将放弃使用默认的压缩提示词模版，转而使用插件提供的 Prompt。
* **`output.context` 的结合规则**：
* 当使用**默认 Prompt** 时，`output.context` 中收集到的文本会被格式化并插入到默认提示词的特定上下文区域中。
* 当设置了 **`output.prompt`（自定义 Prompt）** 时，注入的 `context` 仍会被传给 Prompt 渲染器作为补充变量；但如果自定义 Prompt 未留出对应的上下文占位区域，注入的 `context` 可能会失去作用。



---

### 4. 多个插件同时注册该钩子时的合并/覆盖规则

当多个插件注册了 `experimental.session.compacting` 钩子时，OpenCode 会按照插件的加载顺序（Pipeline 链式调用）依次执行每个插件的钩子，处理规则如下：

1. **`output.context`（合并规则）**：
* **数组拼接（Concatenation）**。所有插件返回的 `context` 字符串数组会被合并累加（`[...pluginAContext, ...pluginBContext]`），确保不同插件注入的领域上下文都能传递给 Prompt。


2. **`output.prompt`（覆盖规则）**：
* **后写胜出（Last-Writer-Wins / Override）**。如果多个插件都返回了非空（非 `undefined`）的 `prompt`，后执行的插件返回的 `prompt` 会直接覆盖先执行插件设置的 `prompt`。



---

### 5. `experimental.` 前缀带来的兼容性风险

带 `experimental.` 前缀说明该钩子处于实验阶段，使用时需关注以下风险：

1. **无 SemVer 保证的 Breaking Changes**：
* 官方可能会在小版本（Minor）甚至补丁版本（Patch）更新中改动参数签名、重命名钩子，或直接废弃。


2. **能力局限性与架构重构风险**：
* 当前钩子仅支持注入文本和替换 Prompt，**无法在压缩期间执行 Tool 调用**（压缩过程中工具集被锁定为 `tools: {}`），因此无法用于修改文件、写入持久化记忆（如 `Memory.md`）等操作。
* 当前钩子**无法阻止/跳过** OpenCode 内置的压缩逻辑（Skip Internal Compaction）。
* 社区已提出关于拆分/扩展该钩子的 Issue（例如提议引入 `experimental.session.pre-compact` 钩子以支持异步工具调用），未来 API 可能会发生较大架构调整。

**Q2**

`experimental.compaction.autocontinue` 是 OpenCode 中专门用来控制上下文压缩（Compaction）完成后，系统是否以及如何“自动无缝续接对话”的拦截控制钩子。

---

### 1. 触发时机

该钩子触发于 **Session 压缩流程结束、新的 Continuation Message（续接消息/摘要）已成功生成并写入会话历史** 的关键时刻。

系统在触发时处于决策点：

> “上一轮长对话已经被压缩为一个摘要节点，我现在是应该**自动发起下一轮 LLM 请求**（无缝恢复刚才被打断的任务），还是**停下来等待用户手动发送指令**？”

钩子会在即将执行自动续接请求之前被同步/异步调用。

---

### 2. 输入参数解析

钩子在被触发时，OpenCode 会传入当前压缩操作的上下文状态：

```typescript
type CompactionAutoContinueInput = {
  sessionID: string;      // 当前会话的唯一标识符
  cause: "auto" | "manual" | "overflow"; // 触发本次上下文压缩的原因
  summary: string;        // 刚刚压缩生成的 Continuation Summary 内容
};

```

* **`sessionID`**：当前运行中的会话 ID，方便插件关联具体的会话上下文或数据库记录。
* **`cause`**：指示引发压缩的源头：
* `"auto"`：Token 达到预警阈值时由系统自动触发的压缩。
* `"overflow"`：模型返回 Context Length Exceeded 错误后恢复触发的压缩。
* `"manual"`：用户通过 `/compact` 或 `/summarize` 命令主动触发的压缩。


* **`summary`**：LLM 生成的总结摘要文本。插件可以分析该文本判断是否包含特定标记（如未完成的任务指示符），以此决定是否允许自动续行。

---

### 3. `enabled: false` 的效果

插件可以通过返回 `{ enabled: false }`（或带有原因的对象）来阻断默认的自动续接行为。

```typescript
// 插件钩子示例
return {
  enabled: false,
  reason: "检测到重大风险，停止自动发送请求"
};

```

**产生的实际效果：**

1. **中断自动请求循环**：OpenCode **不会**自动带上刚才生成的 Summary 重新发起 Model API 请求。
2. **交还控制权给用户**：CLI/TUI/Web 界面将停留在当前的对话界面，用户可以看到压缩完成的通知，但必须**手动敲击回车或输入新的 Prompt** 才能启动下一轮 LLM 交互。
3. **日志/UI 提示**：若插件提供了 `reason`，OpenCode 会在系统日志或 UI 控制台中记录该中断原因，告知用户自动续接已被插件干预拦截。

---

### 4. 它与 `session.compacted` 事件的关系

两者虽然都发生在压缩完成之后，但设计理念与定位完全不同：**一个是决策阻断钩子，一个是纯通知广播事件**。

| 维度 | `experimental.compaction.autocontinue`（Hook） | `session.compacted`（Event/Bus） |
| --- | --- | --- |
| **类型定位** | **插件钩子（Hook）** | **事件总线/订阅广播（Event）** |
| **执行机制** | 阻断式/同步拦截。系统的下一步行为依赖钩子的返回值。 | 非阻塞式（Fire-and-forget）。只读通知，异步广播。 |
| **核心职责** | **决策与控制**：决定压缩后是否继续自动跑 Model Loop。 | **审计与感知**：通知其他模块（如 UI 刷新、指标统计、向量数据库 Index 更新）。 |
| **返回值影响** | 返回 `{ enabled: false }` 会**改变运行流程**（阻止续接）。 | 无返回值（或忽略返回值），**无法改变系统主流程**。 |
| **触发顺序** | 压缩完成后先触发 Hook，计算出是否 Continue。 | 随后触发/广播 `session.compacted` 事件告知全局。 |

`experimental.compaction.autocontinue` 就像是交通信号灯（有权拦截并停下流程），而 `session.compacted` 则是广播电台的通告（仅仅告诉大家“刚才发生了压缩这件事”）。

**Q3**

**Q4**

**Q5**

**Q6**

**Q7**

**Q8**

