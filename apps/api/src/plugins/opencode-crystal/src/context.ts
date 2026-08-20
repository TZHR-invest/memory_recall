import type { ApiClientCrystal } from "./client";
import { getLocale } from "../../_shared/i18n.ts";
import type { SemanticDedupConfig } from "./config";

export function stripPrivateTags(content: string): string {
  return content.replace(/<private>[\s\S]*?<\/private>/g, "");
}
export function isFullyPrivate(content: string): boolean {
  return stripPrivateTags(content).trim().length === 0;
}
export function detectLocale(text: string, setting: string = "auto"): string {
  if (setting !== "auto") return setting;
  const chineseChars = (text.match(/[\u4e00-\u9fff]/g) || []).length;
  const totalChars = text.replace(/\s/g, "").length;
  return chineseChars / totalChars > 0.3 ? "zh_CN" : "en_US";
}
export function getAiGuidance(isZh: boolean): string[] {
  return isZh ? [
    "### 🚨 AI 行为指导（强制执行）","","**【强制规则】收集上下文时，memory-recall 是首选工具**","","### 优先级顺序（从高到低）",
    "1. **检查已注入上下文**（Session Summary、Project Memories、Project Documents）",
    "2. **调用 memory-recall search**（< 1 秒）",
    "3. **最后才使用**：explore/librarian agents、grep、ast_grep、lsp_*、read、glob（30-60 秒）","","### 必须先调用 memory-recall 的场景",
    "- 了解项目架构、技术栈、设计决策","- 查找之前讨论过的功能或问题","- 获取用户偏好、约束、习惯","- 回顾文档内容（README、API 文档等）","- 查询历史会话中的关键信息","- 执行操作前（重启、部署、清理、配置变更）：检查记忆中是否有已有脚本、流程或注意事项","","### 召回策略选择",
    "| 场景 | 参数 | 说明 |","|------|------|------|","| 快速检索 | 默认 | `search(query)` 仅向量搜索 |","| 需要最新信息 | `enableMemoryGraph: true` | 遍历信息演进链 |","| 需要实体关系 | `enableEntityGraph: true` | 遍历实体关系网络 |","| 复杂查询 | 两者都启用 | 完整三层召回 |","","### 记忆关系标注说明",
    "记忆内容后可能带有关系标注，表示该记忆与其他记忆的关系：","- **[更新]**：新版本信息，优先使用此版本，忽略旧版本","- **[补充]**：扩展信息，与源记忆一起形成完整上下文","- **[推断]**：推导信息，置信度较低，需谨慎参考","","### 效率对比","- memory-recall：< 1 秒，命中已有知识","- 代码库探索：30-60 秒，重新扫描代码","","**【核心原则】**：先问记忆，再找代码。记忆里没有，才去探索。","","### 记忆存储规范",
    "- 偏好/约束 → 传 `type: \"preference\"`，后端自动归为 static（永久特征）","- 其他永久特征（姓名、职业、长期规则）→ 传 `isStatic: true`","- 临时信息（会话摘要、最近活动）→ 无需 isStatic，默认 dynamic","- 项目架构/技术决策 → `scope: \"project\"`（默认），用户私密信息 → `scope: \"user\"`","",
  ] : [
    "### 🚨 AI Behavior Guidance (Mandatory)","","**[CORE RULE] memory-recall is the FIRST choice for context gathering**","","### Priority Order (High to Low)",
    "1. **Check injected context** (Session Summary, Project Memories, Project Documents)",
    "2. **Call memory-recall search** (< 1 second)",
    "3. **Last resort**: explore/librarian agents, grep, ast_grep, lsp_*, read, glob (30-60 seconds)","","### When you MUST call memory-recall FIRST",
    "- Understanding project architecture, tech stack, design decisions","- Finding previously discussed features or issues","- Getting user preferences, constraints, habits","- Reviewing documentation (README, API docs, etc.)","- Querying key info from historical sessions","- Before executing operations (restart, deploy, cleanup, config change): check memory for existing scripts, processes, or caveats","","### Recall Strategy Selection",
    "| Scenario | Parameters | Description |","|----------|------------|-------------|","| Quick retrieval | Default | `search(query)` vector search only |","| Need latest info | `enableMemoryGraph: true` | Traverse memory evolution chain |","| Need entity relations | `enableEntityGraph: true` | Traverse entity relation network |","| Complex queries | Enable both | Full three-layer recall |","","### Memory Relation Labels",
    "Memory content may have relation labels indicating relationship with other memories:","- **[updated]**: Newer version - prioritize this, ignore older versions","- **[extended]**: Supplementary info - combine with source memory for complete context","- **[derived]**: Inferred info - lower confidence, use with caution","","### Efficiency Comparison",
    "- memory-recall: < 1 second, hits existing knowledge","- Codebase exploration: 30-60 seconds, re-scans code","","**[CORE PRINCIPLE]**: Ask memory first, then search code. Only explore if memory is empty.","","### Memory Storage Rules",
    "- Preferences/constraints → pass `type: \"preference\"`, backend auto-classifies as static","- Other permanent traits (name, occupation, long-term rules) → pass `isStatic: true`","- Temporary info (session summaries, recent activities) → no isStatic needed, defaults to dynamic","- Project architecture/technical decisions → `scope: \"project\"` (default), user private info → `scope: \"user\"`","",
  ];
}
export function getMemoryNudge(locale: string): string {
  const localeData = getLocale(locale === "zh_CN" ? "zh_CN" : "en_US");
  return localeData.nudge;
}
export interface ContextResult {
  context: string; profileCount: number; projectCount: number; userCount: number;
  chunksCount: number; graphCount: number; entityCount: number; injectedMemoryIds: string[];
}
export async function injectContextFromBackend(
  client: ApiClientCrystal,
  userMessage: string,
  scope: string | null,
  config: {
    injectProfile: boolean; maxProfileItems?: number; maxStaticProfileItems?: number;
    maxProjectMemories?: number; maxMemories: number; maxChunks: number;
    language: string; semanticDedup?: SemanticDedupConfig;
    enableGraphRecall?: boolean; enableEntityRecall?: boolean; graphMaxDepth?: number; graphMaxNodes?: number;
    enableChunksSearch?: boolean; chunksSimilarityThreshold?: number; similarityThreshold?: number; entityChunkThreshold?: number;
    excludeClaimIds?: string[];
  }
): Promise<ContextResult> {
  const res = await client.contextInject(userMessage, scope, { include_explain: false, exclude_claim_ids: config.excludeClaimIds });
  const isZh = config.language === "zh_CN" || (config.language === "auto" && detectLocale(userMessage, "auto") === "zh_CN");
  const lines: string[] = [];
  lines.push(isZh ? "## 用户上下文" : "## User Context");
  lines.push("");
  lines.push(...getAiGuidance(isZh));
  const profile = config.injectProfile ? (res.profile || []) : [];
  const memories = res.memories || [];
  if (profile.length > 0) {
    lines.push(isZh ? "## 用户画像" : "## User Profile");
    for (const p of profile.slice(0, config.maxProfileItems ?? 5)) lines.push(`- ${p.statement}`);
    lines.push("");
  }
  if (memories.length > 0) {
    lines.push(isZh ? "## 相关记忆（Claim）" : "## Relevant Claims");
    for (const m of memories.slice(0, config.maxMemories)) lines.push(`- ${m.statement}`);
    lines.push("");
  }
  const context = lines.length > 5 ? lines.join("\n") : "";
  const injectedIds = [...profile.map(p=>p.claim_id), ...memories.map(m=>m.claim_id)].filter(Boolean) as string[];
  return { context, profileCount: profile.length, projectCount: memories.length, userCount: 0, chunksCount: 0, graphCount: 0, entityCount: 0, injectedMemoryIds: injectedIds };
}
