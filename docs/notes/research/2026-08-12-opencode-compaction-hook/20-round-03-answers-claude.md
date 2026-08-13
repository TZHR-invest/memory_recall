# Round 3 回答：Claude

> 类型: 调研（原始回答归档）
> 调研: 2026-08-12-opencode-compaction-hook
> 说明: 对应 R3-2（原生压缩调参）

#### Claude
Good — confirmed exact schema. Now let me look for community discussion/GitHub issues about tuning these values, and check preserveRecentBudget default formula I saw earlier.已通过源码核实这几个字段的确切实现逻辑，并结合社区 issue 中的实践反馈。

## 1. 触发条件的精确公式（源码核实）

`packages/opencode/src/session/overflow.ts`（第 8-19 行）：

```ts
const COMPACTION_BUFFER = 20_000

export function usable(input) {
  const context = input.model.limit.context
  if (context === 0) return 0
  const reserved =
    input.cfg.compaction?.reserved ??
    Math.min(COMPACTION_BUFFER, ProviderTransform.maxOutputTokens(input.model, input.outputTokenMax))
  return input.model.limit.input
    ? Math.max(0, input.model.limit.input - reserved)
    : Math.max(0, context - ProviderTransform.maxOutputTokens(input.model, input.outputTokenMax))
}

export function isOverflow(input) {
  if (input.cfg.compaction?.auto === false) return false
  const count = input.tokens.total || (input+output+cache.read+cache.write)
  return count >= usable(input)
}
```

你说的 `reserved = min(20000, maxOutputTokens)` 是准确的（这是**默认值**，未显式配置 `compaction.reserved` 时生效）；触发条件也准确——**当模型有 `limit.input` 时**是 `usable = limit.input - reserved`，`isOverflow` 判定 `count >= usable`。

有一点需要补充：如果模型**没有**显式的 `limit.input`（很多模型定义里只有 `context`/`output`，没有单独的 `input`），代码走 else 分支 `context - maxOutputTokens(model)`，**这个分支完全不使用 `reserved`**——这是一个已知且尚未修复的 bug：issue #13980 指出，在这个 else 分支下，`config.compaction.reserved` 会被完全忽略，导致用户无法通过调大 reserved 来避免上下文溢出崩溃，这个 bug 影响了像 claude-opus-4.6 这类只定义了 context/output、没有单独定义 input 上限的模型。——如果你调了 `reserved` 却发现某个模型上不生效，先确认该模型的 `limit.input` 是否被定义。

## 2. `tail_turns` / `preserve_recent_tokens` 的默认行为

源码（`compaction.ts` 第 32-33、115-118、228-230 行）：

```ts
const MIN_PRESERVE_RECENT_TOKENS = 2_000
const MAX_PRESERVE_RECENT_TOKENS = 15_000

function preserveRecentBudget(input) {
  return (
    input.cfg.compaction?.preserve_recent_tokens ??
    Math.min(MAX_PRESERVE_RECENT_TOKENS, Math.max(MIN_PRESERVE_RECENT_TOKENS, Math.floor(usable(input) * 0.25)))
  )
}
```

- **`tail_turns` 未设置**（默认）：不限制轮次数量，只受 `preserve_recent_tokens` 的 token 预算约束，从最近往前逐轮塞，塞满预算为止。
- **`preserve_recent_tokens` 未设置**（默认）：预算 = `usable() 的 25%`，但**钳制在 [2000, 15000] token 之间**。
- **关键点**：这个 `[2000, 15000]` 钳制**只在你不显式设置该字段时生效**——一旦你在配置里显式写了 `preserve_recent_tokens`，代码直接用你给的数值，**不会再做任何钳制**，也就是说你可以把它设成 100 这种极端值，系统不会替你兜底。

## 3. 社区实际调参方式与来源

**`compaction.reserved`**：
- 有人（社区文档/评测类文章）实际配置示例：给出的配置示例把 reserved 从默认值调到 30000，用于在自动压缩前预留更充足的 token 缓冲。
- 反模式（已被官方 issue 明确纠正）：issue #27706 明确指出，多名用户把 `compaction.reserved` 误理解为"触发阈值"（认为调大它就能让压缩更早触发），但 schema 注释本身写的是"避免压缩过程本身溢出的安全垫"（"Leaves enough window to avoid overflow during compaction"），语义含糊，容易被误用；该 issue 因此提议新增一个语义明确的独立字段 `compaction.trigger_at`（显式 token 阈值触发器），与 reserved 解耦。
  - **技术事实澄清**：从源码看，`reserved` 客观上确实会通过 `usable = limit.input - reserved` 间接影响触发点（reserved 越大 → usable 越小 → 越早触发压缩），所以"调大 reserved 会更早压缩"这个直觉本身没错，issue 里争议的核心是**语义文档不清晰**，加上前面提到的"部分模型该字段被静默忽略"的 bug，导致用户实际观察到的行为和预期不符。
- **反模式（"reserved 太大导致过早压缩"）**：确实存在——reserved 设得越大，`usable` 越小，压缩触发得越早越频繁，会明显增加压缩调用次数和 token 成本（每次压缩本身也要消耗一次 LLM 调用）。issue #11314 反映了相反方向的问题：多个模型（如 Gemini）的表现在上下文使用到 30% 左右就已开始质量下降，但当时的默认压缩阈值要到 75%（786k token）才触发，导致用户在压缩生效前已经经历了响应变慢、幻觉增多、代码质量下降等问题，这类用户的诉求正是把阈值提前（即变相调大等效 reserved），说明"调多大"本质上要看模型的实际质量衰减曲线，不存在放之四海而皆准的固定值。
- **反模式（"reserved 太小导致快满才压"）**：这也是默认值 `min(20000, maxOutputTokens)` 在超大上下文模型（如 1M context 的 Opus）上暴露的问题——20000 相对 1M 是很小的比例（2%），所以默认配置下大窗口模型会"几乎顶满才触发"，这正是 issue #27706 想解决的场景（SigNoz 可观测性数据显示 200K token 阈值的跨越是"静默且昂贵的"，即触发得太晚，用户毫无察觉地花费了大量 token 直到系统才反应过来）。

**`tail_turns`**：
- 社区在追求"更激进/更省钱的压缩"场景下，常把它设得很小：issue #27706 给出的配置示例里把 tail_turns 设为 2，配合更早的触发阈值一起使用，用于让压缩更频繁、每次保留的原文轮次更少。
- 反模式：`tail_turns` 设得过小（如 1）容易在多步骤任务（比如连续的文件编辑、测试-修复循环）中把还在进行中的上下文切掉，导致 agent "失忆式"重复劳动——这属于官方文档里反复强调的"压缩是有损的，别设置得过于激进"的范畴，官方 V2 文档明确说明 compaction 是有损操作（lossy），虽然不会删除底层持久化的历史消息，但活跃上下文里的细节会丢失，"保留更多的 keep.tokens 能保留更多近期细节，但会留给未来工作的空间更少"，这条 trade-off 逻辑同样适用于 V1 的 `tail_turns`/`preserve_recent_tokens`。

**`preserve_recent_tokens`**：
- 目前没有找到社区就这个字段单独给出的"推荐数值"讨论帖，多数人依赖默认的 25%（钳制在 2000-15000）即可；调大它（如设到 20000+，突破默认上限钳制）通常是为了在压缩后仍能让 agent 精确记得"最近几个文件改了什么"，代价是压缩后上下文占用仍然偏高、省不下多少 token。
- 反模式：显式设一个很小的数值（几百 token）——如前面源码分析所述，这会**绕开系统默认的 2000 下限保护**，导致压缩后几乎没有保留任何逐字原文，模型只能依赖摘要，容易丢失最近的精确技术细节（文件名、报错信息等），这正好呼应 issue #16512 里反映的普遍抱怨："压缩后 AI 会重复问已经回答过的问题，忘记用户的约束条件，丢失调试状态"，该 issue 明确指向的是压缩提示词/保留内容不够精确的问题。

## 4. 来源汇总

| 来源 | 类型 | 内容 |
|---|---|---|
| `github.com/anomalyco/opencode` `dev` 分支 `packages/opencode/src/session/overflow.ts` | 官方源码 | `usable()` / `isOverflow()` 精确公式 |
| `github.com/anomalyco/opencode` `dev` 分支 `packages/opencode/src/session/compaction.ts` | 官方源码 | `preserveRecentBudget()`、`tail_turns` 使用位置 |
| `github.com/anomalyco/opencode` `dev` 分支 `packages/core/src/v1/config/config.ts`（约第 149-167 行） | 官方源码（config schema） | `compaction.{auto,prune,tail_turns,preserve_recent_tokens,reserved}` 字段定义与官方描述文案 |
| GitHub Issue #27706（anomalyco/opencode） | 社区反馈 + 官方回应 | `reserved` 语义误解、`trigger_at` 提案、大窗口模型"快满才压"问题 |
| GitHub Issue #13980（anomalyco/opencode） | 已知 bug 报告 | 无 `limit.input` 时 `reserved` 被忽略 |
| GitHub Issue #11314（anomalyco/opencode） | 社区反馈 | 不同模型质量衰减曲线远早于默认压缩阈值的实测证据 |
| GitHub Issue #16512（anomalyco/opencode） | 社区反馈 | 压缩后细节丢失的具体投诉，间接支持"别把 preserve_recent_tokens 设太小"的建议 |
| `opencode.ai/v2/docs/compaction`、`opencode.ai/v2/docs/config` | 官方文档（**注意是 V2**） | V2 把这套参数重命名为 `compaction.keep.tokens` / `compaction.buffer`，语义与 V1 的 `preserve_recent_tokens` / `reserved` 基本对应，但**字段名和默认值都变了**，升级到 V2 时不能直接照搬 V1 的配置键名 |

⚠️ 提醒一点：官方文档站已经出现了 **V1（当前 `dev` 分支源码用的字段名）** 与 **V2（`opencode.ai/v2/docs`）** 两套 compaction 配置 schema 并存的情况，字段名不一致（`reserved`→`buffer`，`preserve_recent_tokens`→`keep.tokens`，且 `tail_turns` 在 V2 文档里未出现）。你在查文档或抄社区配置示例时，务必先确认对方使用的是 V1 还是 V2，否则直接套用会导致配置字段不生效（未知字段通常被 schema 校验静默忽略或报错，视校验严格程度而定）。

