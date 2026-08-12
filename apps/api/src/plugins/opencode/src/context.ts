import type { ApiClient, Profile, SearchResult, Memory, ChunkSearchResult, GraphNode, GraphEdge, GraphResponse, ContextInjectConfig, ContextInjectResponse } from "./client";
import { getAllKeywords, getLocale, type Locale } from "./i18n";
import {
  semanticDeduplicate,
  createDeduplicableItem,
  type DedupSource,
  type DeduplicableItem,
} from "./semantic-dedup";
import type { SemanticDedupConfig } from "./config";

const keywordPattern = new RegExp(getAllKeywords().join("|"), "i");

export function computeContentHash(content: string): string {
  return Bun.hash(content).toString(16).padStart(16, "0");
}

export interface CrossScopeDedupResult {
  staticFacts: string[];
  dynamicFacts: string[];
  dedupedProjectMemories: Memory[];
  dedupedUserMemories: (SearchResult | ExpandedMemory)[];
  dedupedChunks: ChunkSearchResult[];
  dedupStats: {
    projectMemoriesFiltered: number;
    userMemoriesFiltered: number;
    chunksFiltered: number;
    semanticStats?: {
      total: number;
      removed: number;
      bySource: Record<DedupSource, { kept: number; removed: number }>;
    };
  };
}

export function deduplicateAcrossScopes(
  profile: Profile | null,
  projectMemories: Memory[],
  userMemories: (SearchResult | ExpandedMemory)[] = [],
  chunks: ChunkSearchResult[] = []
): CrossScopeDedupResult {
  const userContentHashes = new Set<string>();
  
  const staticFacts = profile?.static || [];
  const dynamicFacts = profile?.dynamic || [];
  
  staticFacts.forEach(fact => userContentHashes.add(computeContentHash(fact)));
  dynamicFacts.forEach(fact => userContentHashes.add(computeContentHash(fact)));
  
  const dedupedProjectMemories = projectMemories.filter(m => {
    const hash = computeContentHash(m.content);
    return !userContentHashes.has(hash);
  });

  const profileHashes = new Set([
    ...staticFacts.map(computeContentHash),
    ...dynamicFacts.map(computeContentHash),
  ]);
  const projectMemoryHashes = new Set(
    dedupedProjectMemories.map((m) => computeContentHash(m.content))
  );
  const allHashes = new Set([...profileHashes, ...projectMemoryHashes]);

  const dedupedUserMemories = userMemories.filter((m) => {
    const hash = computeContentHash(m.content);
    return !allHashes.has(hash);
  });

  const userMemoryHashes = new Set(
    dedupedUserMemories.map((m) => computeContentHash(m.content))
  );
  const allHashesWithUser = new Set([...allHashes, ...userMemoryHashes]);

  const dedupedChunks = chunks.filter((c) => {
    const hash = computeContentHash(c.content);
    return !allHashesWithUser.has(hash);
  });
  
  return {
    staticFacts,
    dynamicFacts,
    dedupedProjectMemories,
    dedupedUserMemories,
    dedupedChunks,
    dedupStats: {
      projectMemoriesFiltered: projectMemories.length - dedupedProjectMemories.length,
      userMemoriesFiltered: userMemories.length - dedupedUserMemories.length,
      chunksFiltered: chunks.length - dedupedChunks.length,
    },
  };
}

export async function deduplicateWithSemanticLayer(
  client: ApiClient,
  profile: Profile | null,
  projectMemories: Memory[],
  userMemories: (SearchResult | ExpandedMemory)[],
  chunks: ChunkSearchResult[],
  config: SemanticDedupConfig
): Promise<CrossScopeDedupResult> {
  const hashResult = deduplicateAcrossScopes(
    profile,
    projectMemories,
    userMemories,
    chunks
  );

  if (!config.enabled) {
    return hashResult;
  }

  const items: DeduplicableItem[] = [];

  hashResult.staticFacts.forEach((fact) => {
    items.push(createDeduplicableItem(fact, "profile"));
  });
  hashResult.dynamicFacts.forEach((fact) => {
    items.push(createDeduplicableItem(fact, "profile"));
  });
  hashResult.dedupedProjectMemories.forEach((m) => {
    items.push(createDeduplicableItem(m.content, "projectMemory", m.id));
  });
  hashResult.dedupedUserMemories.forEach((m) => {
    items.push(createDeduplicableItem(m.content, "userMemory", m.id));
  });
  hashResult.dedupedChunks.forEach((c) => {
    items.push(createDeduplicableItem(c.content, "chunk", c.id));
  });

  try {
    const semanticResult = await semanticDeduplicate(
      client,
      items,
      config.threshold,
      config.maxBatchSize
    );

    const semanticItems = semanticResult.items;

    const staticFacts: string[] = [];
    const dynamicFacts: string[] = [];
    const dedupedProjectMemories: Memory[] = [];
    const dedupedUserMemories: (SearchResult | ExpandedMemory)[] = [];
    const dedupedChunks: ChunkSearchResult[] = [];

    const originalStaticFacts = hashResult.staticFacts;
    const originalDynamicFacts = hashResult.dynamicFacts;

    for (const item of semanticItems) {
      if (item.source === "profile") {
        if (originalStaticFacts.includes(item.content)) {
          staticFacts.push(item.content);
        } else if (originalDynamicFacts.includes(item.content)) {
          dynamicFacts.push(item.content);
        }
      } else if (item.source === "projectMemory") {
        const original = hashResult.dedupedProjectMemories.find(
          (m) => m.content === item.content
        );
        if (original) {
          dedupedProjectMemories.push(original);
        }
      } else if (item.source === "userMemory") {
        const original = hashResult.dedupedUserMemories.find(
          (m) => m.content === item.content
        );
        if (original) {
          dedupedUserMemories.push(original);
        }
      } else if (item.source === "chunk") {
        const original = hashResult.dedupedChunks.find(
          (c) => c.content === item.content
        );
        if (original) {
          dedupedChunks.push(original);
        }
      }
    }

    return {
      staticFacts,
      dynamicFacts,
      dedupedProjectMemories,
      dedupedUserMemories,
      dedupedChunks,
      dedupStats: {
        projectMemoriesFiltered:
          projectMemories.length - dedupedProjectMemories.length,
        userMemoriesFiltered:
          userMemories.length - dedupedUserMemories.length,
        chunksFiltered: chunks.length - dedupedChunks.length,
        semanticStats: semanticResult.stats,
      },
    };
  } catch (error) {
    console.warn("Semantic deduplication failed, falling back to hash-only:", error);
    return hashResult;
  }
}

export const RELATION_WEIGHTS: Record<string, number> = {
  updates: 1.0,
  extends: 0.7,
  derives: 0.5,
};

export const ENTITY_WEIGHTS: Record<string, number> = {
  person: 1.0,
  organization: 0.9,
  location: 0.8,
  preference: 0.7,
  time: 0.5,
};

export interface ExpandedMemory extends SearchResult {
  source: "vector" | "relation" | "entity" | "vector+entity";
  depth: number;
  relationType?: "updates" | "extends" | "derives";
  matchedEntities?: Record<string, string[]>;
}

export interface EntityMatch {
  type: string;
  values: string[];
}

export function detectMemoryKeyword(text: string): boolean {
  const textWithoutCode = removeCodeBlocks(text);
  return keywordPattern.test(textWithoutCode);
}

function removeCodeBlocks(text: string): string {
  return text
    .replace(/```[\s\S]*?```/g, "")
    .replace(/`[^`]+`/g, "");
}

export function stripPrivateTags(content: string): string {
  return content.replace(/<private>[\s\S]*?<\/private>/g, "");
}

export function isFullyPrivate(content: string): boolean {
  const stripped = stripPrivateTags(content).trim();
  return stripped.length === 0;
}

export function detectLocale(text: string, setting: string = "auto"): string {
  if (setting !== "auto") {
    return setting;
  }
  const chineseChars = (text.match(/[\u4e00-\u9fff]/g) || []).length;
  const totalChars = text.replace(/\s/g, "").length;
  return chineseChars / totalChars > 0.3 ? "zh_CN" : "en_US";
}

export function traverseFromSeeds(
  seeds: SearchResult[],
  edges: GraphEdge[],
  nodes: GraphNode[],
  maxDepth: number,
  maxNodes: number
): ExpandedMemory[] {
  const visited = new Set<string>();
  const results: ExpandedMemory[] = [];
  const nodeMap = new Map<string, GraphNode>();
  
  nodes.forEach(n => nodeMap.set(n.id, n));
  
  for (const seed of seeds) {
    visited.add(seed.id);
  }
  
  const queue: { id: string; depth: number; relationType?: "updates" | "extends" | "derives"; confidence: number }[] = 
    seeds.map(s => ({ id: s.id, depth: 0, confidence: s.similarity }));
  
  while (queue.length > 0 && results.length < maxNodes) {
    const current = queue.shift()!;
    
    if (current.depth > 0) {
      const node = nodeMap.get(current.id);
      if (node && !visited.has(current.id)) {
        visited.add(current.id);
        results.push({
          id: current.id,
          content: node.content,
          similarity: current.confidence,
          source: "relation",
          depth: current.depth,
          relationType: current.relationType,
        });
      }
    }
    
    if (current.depth < maxDepth) {
      for (const edge of edges) {
        let nextId: string | null = null;
        let relationType: "updates" | "extends" | "derives" | undefined;
        
        if (edge.source === current.id && !visited.has(edge.target)) {
          nextId = edge.target;
          relationType = edge.type;
        } else if (edge.target === current.id && edge.type === "updates" && !visited.has(edge.source)) {
          nextId = edge.source;
          relationType = edge.type;
        }
        
        if (nextId && relationType) {
          const weight = RELATION_WEIGHTS[relationType] || 0.5;
          queue.push({
            id: nextId,
            depth: current.depth + 1,
            relationType,
            confidence: edge.confidence * weight,
          });
        }
      }
    }
  }
  
  return results.slice(0, maxNodes);
}

export function calculateRelationScore(edge: GraphEdge): number {
  const weight = RELATION_WEIGHTS[edge.type] || 0.5;
  return edge.confidence * weight;
}

const ENTITY_PATTERNS: { type: string; patterns: RegExp[] }[] = [
  {
    type: "person",
    patterns: [
      /和([^\s，。！？]+)见面/g,
      /跟([^\s，。！？]+)一起/g,
      /和([^\s，。！？]+)一起/g,
      /叫([^\s，。！？]+)/g,
    ],
  },
  {
    type: "organization",
    patterns: [
      /在([^\s，。！？]+公司)/g,
      /在([^\s，。！？]+工作)/g,
      /就职于([^\s，。！？]+)/g,
      /加入([^\s，。！？]+公司)/g,
    ],
  },
  {
    type: "location",
    patterns: [
      /住在([^\s，。！？]+)/g,
      /在([^\s，。！？市省区县]+[市省区县])/g,
      /来自([^\s，。！？]+)/g,
    ],
  },
];

export function extractEntitiesFromQuery(query: string): EntityMatch[] {
  const results: EntityMatch[] = [];
  
  for (const { type, patterns } of ENTITY_PATTERNS) {
    const values = new Set<string>();
    for (const pattern of patterns) {
      const matches = query.matchAll(pattern);
      for (const match of matches) {
        if (match[1] && match[1].length >= 2 && match[1].length <= 20) {
          values.add(match[1]);
        }
      }
    }
    if (values.size > 0) {
      results.push({ type, values: Array.from(values) });
    }
  }
  
  return results;
}

export function findBySharedEntities(
  nodes: GraphNode[],
  queryEntities: EntityMatch[],
  maxNodes: number
): ExpandedMemory[] {
  if (queryEntities.length === 0) return [];
  
  const results: ExpandedMemory[] = [];
  const queryEntityMap = new Map<string, Set<string>>();
  
  for (const entity of queryEntities) {
    queryEntityMap.set(entity.type, new Set(entity.values));
  }
  
  for (const node of nodes) {
    if (!node.entities) continue;
    
    const matchedEntities: Record<string, string[]> = {};
    let matchScore = 0;
    
    for (const [entityType, entityValues] of Object.entries(node.entities)) {
      const queryValues = queryEntityMap.get(entityType);
      if (!queryValues) continue;
      
      const shared = (entityValues as string[]).filter(v => queryValues.has(v));
      if (shared.length > 0) {
        matchedEntities[entityType] = shared;
        const weight = ENTITY_WEIGHTS[entityType] || 0.5;
        matchScore += weight * (shared.length / Math.max(entityValues.length, 1));
      }
    }
    
    if (Object.keys(matchedEntities).length > 0) {
      results.push({
        id: node.id,
        content: node.content,
        similarity: Math.min(1, matchScore),
        source: "entity",
        depth: 0,
        matchedEntities,
      });
    }
  }
  
  return results
    .sort((a, b) => b.similarity - a.similarity)
    .slice(0, maxNodes);
}

export function calculateEntityMatchScore(
  node: GraphNode,
  queryEntities: EntityMatch[]
): number {
  if (!node.entities || queryEntities.length === 0) return 0;
  
  let totalScore = 0;
  const queryEntityMap = new Map<string, Set<string>>();
  
  for (const entity of queryEntities) {
    queryEntityMap.set(entity.type, new Set(entity.values));
  }
  
  for (const [entityType, entityValues] of Object.entries(node.entities)) {
    const queryValues = queryEntityMap.get(entityType);
    if (!queryValues) continue;
    
    const shared = (entityValues as string[]).filter(v => queryValues.has(v));
    if (shared.length > 0) {
      const weight = ENTITY_WEIGHTS[entityType] || 0.5;
      totalScore += weight * (shared.length / Math.max((entityValues as string[]).length, 1));
    }
  }
  
  return Math.min(1, totalScore);
}

export function mergeAndDedupe(
  vectorResults: SearchResult[],
  relationResults: ExpandedMemory[],
  entityResults: ExpandedMemory[]
): ExpandedMemory[] {
  const memoryMap = new Map<string, ExpandedMemory>();
  
  for (const m of vectorResults) {
    memoryMap.set(m.id, {
      ...m,
      source: "vector",
      depth: 0,
      similarity: m.similarity,
    });
  }
  
  for (const m of relationResults) {
    const existing = memoryMap.get(m.id);
    if (existing) {
      existing.similarity = existing.similarity * 0.5 + m.similarity * 0.3;
    } else {
      memoryMap.set(m.id, m);
    }
  }
  
  for (const m of entityResults) {
    const existing = memoryMap.get(m.id);
    if (existing) {
      existing.similarity = existing.similarity * 0.7 + m.similarity * 0.2;
      existing.matchedEntities = m.matchedEntities;
      existing.source = "vector+entity";
    } else {
      memoryMap.set(m.id, m);
    }
  }
  
  return Array.from(memoryMap.values())
    .sort((a, b) => b.similarity - a.similarity);
}

export interface ContextOptions {
  profile: Profile | null;
  projectMemories: Memory[];
  userMemories: (SearchResult | ExpandedMemory)[];
  projectChunks: ChunkSearchResult[];
  locale: string;
  maxProfileItems: number;
  maxStaticProfileItems: number;
  maxProjectItems: number;
  maxUserItems: number;
  maxChunksItems: number;
  dedupedResult?: CrossScopeDedupResult;
}

function formatMemoryLine(m: SearchResult | ExpandedMemory): string {
  if ("source" in m) {
    const expanded = m as ExpandedMemory;
    if (expanded.source === "relation" && expanded.relationType) {
      return `- [via ${expanded.relationType}] ${m.content}`;
    }
    if (expanded.source === "entity" && expanded.matchedEntities) {
      const entityTypes = Object.keys(expanded.matchedEntities);
      return `- [entity: ${entityTypes.join(", ")}] ${m.content}`;
    }
    if (expanded.source === "vector+entity" && expanded.matchedEntities) {
      const entityTypes = Object.keys(expanded.matchedEntities);
      const similarity = Math.round(m.similarity * 100);
      return `- [${similarity}%, entity: ${entityTypes.join(", ")}] ${m.content}`;
    }
  }
  const similarity = Math.round(m.similarity * 100);
  return `- [${similarity}%] ${m.content}`;
}

export function getAiGuidance(isZh: boolean): string[] {
  return isZh 
    ? [
        "### 🚨 AI 行为指导（强制执行）",
        "",
        "**【强制规则】收集上下文时，memory-recall 是首选工具**",
        "",
        "### 优先级顺序（从高到低）",
        "1. **检查已注入上下文**（Session Summary、Project Memories、Project Documents）",
        "2. **调用 memory-recall search**（< 1 秒）",
        "3. **最后才使用**：explore/librarian agents、grep、ast_grep、lsp_*、read、glob（30-60 秒）",
        "",
        "### 必须先调用 memory-recall 的场景",
        "- 了解项目架构、技术栈、设计决策",
        "- 查找之前讨论过的功能或问题",
        "- 获取用户偏好、约束、习惯",
        "- 回顾文档内容（README、API 文档等）",
        "- 查询历史会话中的关键信息",
        "- 执行操作前（重启、部署、清理、配置变更）：检查记忆中是否有已有脚本、流程或注意事项",
        "",
        "### 召回策略选择",
        "| 场景 | 参数 | 说明 |",
        "|------|------|------|",
        "| 快速检索 | 默认 | `search(query)` 仅向量搜索 |",
        "| 需要最新信息 | `enableMemoryGraph: true` | 遍历信息演进链 |",
        "| 需要实体关系 | `enableEntityGraph: true` | 遍历实体关系网络 |",
        "| 复杂查询 | 两者都启用 | 完整三层召回 |",
        "",
        "### 记忆关系标注说明",
        "记忆内容后可能带有关系标注，表示该记忆与其他记忆的关系：",
        "- **[更新]**：新版本信息，优先使用此版本，忽略旧版本",
        "- **[补充]**：扩展信息，与源记忆一起形成完整上下文",
        "- **[推断]**：推导信息，置信度较低，需谨慎参考",
        "",
        "### 效率对比",
        "- memory-recall：< 1 秒，命中已有知识",
        "- 代码库探索：30-60 秒，重新扫描代码",
        "",
        "**【核心原则】**：先问记忆，再找代码。记忆里没有，才去探索。",
        "",
        "### 记忆存储规范",
        "- 偏好/约束 → 传 `type: \"preference\"`，后端自动归为 static（永久特征）",
        "- 其他永久特征（姓名、职业、长期规则）→ 传 `isStatic: true`",
        "- 临时信息（会话摘要、最近活动）→ 无需 isStatic，默认 dynamic",
        "- 项目架构/技术决策 → `scope: \"project\"`（默认），用户私密信息 → `scope: \"user\"`",
        "",
      ]
    : [
        "### 🚨 AI Behavior Guidance (Mandatory)",
        "",
        "**[CORE RULE] memory-recall is the FIRST choice for context gathering**",
        "",
        "### Priority Order (High to Low)",
        "1. **Check injected context** (Session Summary, Project Memories, Project Documents)",
        "2. **Call memory-recall search** (< 1 second)",
        "3. **Last resort**: explore/librarian agents, grep, ast_grep, lsp_*, read, glob (30-60 seconds)",
        "",
        "### When you MUST call memory-recall FIRST",
        "- Understanding project architecture, tech stack, design decisions",
        "- Finding previously discussed features or issues",
        "- Getting user preferences, constraints, habits",
        "- Reviewing documentation (README, API docs, etc.)",
        "- Querying key info from historical sessions",
        "- Before executing operations (restart, deploy, cleanup, config change): check memory for existing scripts, processes, or caveats",
        "",
        "### Recall Strategy Selection",
        "| Scenario | Parameters | Description |",
        "|----------|------------|-------------|",
        "| Quick retrieval | Default | `search(query)` vector search only |",
        "| Need latest info | `enableMemoryGraph: true` | Traverse memory evolution chain |",
        "| Need entity relations | `enableEntityGraph: true` | Traverse entity relation network |",
        "| Complex queries | Enable both | Full three-layer recall |",
        "",
        "### Memory Relation Labels",
        "Memory content may have relation labels indicating relationship with other memories:",
        "- **[updated]**: Newer version - prioritize this, ignore older versions",
        "- **[extended]**: Supplementary info - combine with source memory for complete context",
        "- **[derived]**: Inferred info - lower confidence, use with caution",
        "",
        "### Efficiency Comparison",
        "- memory-recall: < 1 second, hits existing knowledge",
        "- Codebase exploration: 30-60 seconds, re-scans code",
        "",
        "**[CORE PRINCIPLE]**: Ask memory first, then search code. Only explore if memory is empty.",
        "",
        "### Memory Storage Rules",
        "- Preferences/constraints → pass `type: \"preference\"`, backend auto-classifies as static",
        "- Other permanent traits (name, occupation, long-term rules) → pass `isStatic: true`",
        "- Temporary info (session summaries, recent activities) → no isStatic needed, defaults to dynamic",
        "- Project architecture/technical decisions → `scope: \"project\"` (default), user private info → `scope: \"user\"`",
        "",
      ];
}

export function formatContext(options: ContextOptions): string {
  const { profile, projectMemories, userMemories, projectChunks, locale, maxProfileItems, maxStaticProfileItems, maxProjectItems, maxUserItems, maxChunksItems, dedupedResult } = options;
  
  const isZh = locale === "zh_CN";
  const lines: string[] = [];

  const sectionTitle = isZh ? "## 用户上下文" : "## User Context";
  lines.push(sectionTitle);
  lines.push("");

  lines.push(...getAiGuidance(isZh));

  let staticFacts: string[];
  let dynamicFacts: string[];
  let dedupedProjectMemories: Memory[];
  let dedupedUserMemories: (SearchResult | ExpandedMemory)[];
  let dedupedChunks: ChunkSearchResult[];

  if (dedupedResult) {
    staticFacts = dedupedResult.staticFacts;
    dynamicFacts = dedupedResult.dynamicFacts;
    dedupedProjectMemories = dedupedResult.dedupedProjectMemories;
    dedupedUserMemories = dedupedResult.dedupedUserMemories;
    dedupedChunks = dedupedResult.dedupedChunks;
  } else {
    const deduped = deduplicateAcrossScopes(profile, projectMemories, userMemories, projectChunks);
    staticFacts = deduped.staticFacts;
    dynamicFacts = deduped.dynamicFacts;
    dedupedProjectMemories = deduped.dedupedProjectMemories;
    dedupedUserMemories = deduped.dedupedUserMemories;
    dedupedChunks = deduped.dedupedChunks;
  }

  if (staticFacts.length > 0) {
    const staticTitle = isZh ? "### 永久特征" : "### Static Facts";
    lines.push(staticTitle);
    staticFacts.slice(0, maxStaticProfileItems).forEach((fact) => lines.push("- " + fact));
    lines.push("");
  }

  if (dynamicFacts.length > 0) {
    const dynamicTitle = isZh ? "### 最近活动" : "### Recent Activities";
    lines.push(dynamicTitle);
    dynamicFacts.slice(0, maxProfileItems).forEach((fact) => lines.push("- " + fact));
    lines.push("");
  }

  if (dedupedProjectMemories.length > 0) {
    const projectTitle = isZh ? "### 项目记忆" : "### Project Memories";
    lines.push(projectTitle);
    dedupedProjectMemories.slice(0, maxProjectItems).forEach((m) => {
      lines.push("- " + m.content);
    });
    lines.push("");
  }

  if (dedupedChunks.length > 0) {
    const chunksTitle = isZh ? "### 项目文档" : "### Project Documents";
    lines.push(chunksTitle);
    dedupedChunks.slice(0, maxChunksItems).forEach((c) => {
      const similarity = Math.round(c.similarity * 100);
      const docTitle = c.document_title || "Document";
      lines.push(`- [${docTitle}: ${similarity}%] ${c.content}`);
    });
    lines.push("");
  }

  if (dedupedUserMemories.length > 0) {
    const userTitle = isZh ? "### 相关记忆" : "### Related Memories";
    lines.push(userTitle);
    dedupedUserMemories.slice(0, maxUserItems).forEach((m) => {
      lines.push(formatMemoryLine(m));
    });
    lines.push("");
  }

  if (lines.length <= 3) {
    return "";
  }

  return lines.join("\n");
}

export function getMemoryNudge(locale: string): string {
  const localeData = getLocale(locale === "zh_CN" ? "zh_CN" : "en_US");
  return localeData.nudge;
}

export interface ContextResult {
  context: string;
  profileCount: number;
  projectCount: number;
  userCount: number;
  chunksCount: number;
  graphCount: number;
  entityCount: number;
  injectedMemoryIds: string[];
}

export async function injectContext(
  client: ApiClient,
  userMessage: string,
  userTag: string,
  projectTag: string,
  config: {
    injectProfile: boolean;
    maxProfileItems: number;
    maxStaticProfileItems: number;
    maxProjectMemories: number;
    maxMemories: number;
    language: string;
    enableChunksSearch: boolean;
    maxChunks: number;
    chunksSimilarityThreshold: number;
    chunksDocTypes: string[];
    enableGraphRecall: boolean;
    enableEntityRecall: boolean;
    graphMaxDepth: number;
    graphMaxNodes: number;
    semanticDedup?: SemanticDedupConfig;
  }
): Promise<ContextResult> {
  const locale = detectLocale(userMessage, config.language);
  let profile: Profile | null = null;
  if (config.injectProfile) {
    try {
      const response = await client.getProfile(
        userTag,
        userMessage,
        config.maxStaticProfileItems,
        config.maxProfileItems
      );
      profile = response.profile;
    } catch {}
  }

  let projectMemories: Memory[] = [];
  let userMemories: SearchResult[] = [];
  let projectChunks: ChunkSearchResult[] = [];
  let graphMemories: ExpandedMemory[] = [];
  let entityMemories: ExpandedMemory[] = [];
  
  try {
    projectMemories = await client.listMemories(projectTag, config.maxProjectMemories);
    projectMemories = projectMemories.filter(m => 
      !m.content.startsWith("[Session Summary]") && 
      !m.content.startsWith("[会话摘要]")
    );
  } catch {}

  try {
    userMemories = await client.search(userMessage, userTag, config.maxMemories);
  } catch {}

  if (config.enableChunksSearch) {
    try {
      const docTypes = config.chunksDocTypes.length > 0 ? config.chunksDocTypes : undefined;
      projectChunks = await client.searchChunks(
        userMessage,
        projectTag,
        config.maxChunks,
        config.chunksSimilarityThreshold,
        docTypes
      );
    } catch {}
  }

  if (config.enableGraphRecall && userMemories.length > 0) {
    try {
      const graph = await client.getGraph(userTag, { limit: 100 });
      
      if (graph.nodes.length > 0) {
        graphMemories = traverseFromSeeds(
          userMemories,
          graph.edges,
          graph.nodes,
          config.graphMaxDepth,
          config.graphMaxNodes
        );
      }
      
      if (config.enableEntityRecall) {
        const queryEntities = extractEntitiesFromQuery(userMessage);
        if (queryEntities.length > 0) {
          entityMemories = findBySharedEntities(
            graph.nodes,
            queryEntities,
            config.graphMaxNodes
          );
        }
      }
    } catch {}
  }

  const mergedMemories = mergeAndDedupe(userMemories, graphMemories, entityMemories);

  let dedupedResult: CrossScopeDedupResult | undefined;
  
  if (config.semanticDedup?.enabled) {
    try {
      dedupedResult = await deduplicateWithSemanticLayer(
        client,
        profile,
        projectMemories,
        mergedMemories,
        projectChunks,
        config.semanticDedup
      );
    } catch (error) {
      console.warn("Semantic deduplication failed, falling back to hash-only:", error);
    }
  }

  const profileCount = profile 
    ? Math.min(profile.static.length, config.maxStaticProfileItems) + Math.min(profile.dynamic.length, config.maxProfileItems)
    : 0;
  const projectCount = Math.min(projectMemories.length, config.maxProjectMemories);
  const userCount = Math.min(mergedMemories.length, config.maxMemories);
  const chunksCount = Math.min(projectChunks.length, config.maxChunks);
  const graphCount = graphMemories.length;
  const entityCount = entityMemories.length;

  const context = formatContext({
    profile,
    projectMemories,
    userMemories: mergedMemories,
    projectChunks,
    locale,
    maxProfileItems: config.maxProfileItems,
    maxStaticProfileItems: config.maxStaticProfileItems,
    maxProjectItems: config.maxProjectMemories,
    maxUserItems: config.maxMemories,
    maxChunksItems: config.maxChunks,
    dedupedResult,
  });

  const injectedMemoryIds: string[] = [
    ...projectMemories.slice(0, config.maxProjectMemories).map(m => m.id),
    ...mergedMemories.slice(0, config.maxMemories).map(m => m.id),
  ];

  return {
    context,
    profileCount,
    projectCount,
    userCount,
    chunksCount,
    graphCount,
    entityCount,
    injectedMemoryIds,
  };
}

export async function injectContextFromBackend(
  client: ApiClient,
  userMessage: string,
  userTag: string,
  projectTag: string,
  config: {
    injectProfile: boolean;
    maxProfileItems: number;
    maxStaticProfileItems: number;
    maxProjectMemories: number;
    maxMemories: number;
    maxChunks: number;
    language: string;
    semanticDedup?: SemanticDedupConfig;
    enableGraphRecall?: boolean;
    enableEntityRecall?: boolean;
    graphMaxDepth?: number;
    graphMaxNodes?: number;
    enableChunksSearch?: boolean;
    chunksSimilarityThreshold?: number;
    similarityThreshold?: number;
    entityChunkThreshold?: number;
    chunksDocTypes?: string[];
  }
): Promise<ContextResult> {
  const apiConfig: ContextInjectConfig = {
    inject_profile: config.injectProfile,
    max_profile_items: config.maxProfileItems,
    max_static_profile_items: config.maxStaticProfileItems,
    max_memories: config.maxMemories,
    max_chunks: config.maxChunks,
    enable_semantic_dedup: config.semanticDedup?.enabled ?? true,
    dedup_threshold: config.semanticDedup?.threshold ?? 0.85,
    enable_memory_graph: config.enableGraphRecall ?? false,
    memory_graph_depth: config.graphMaxDepth ?? 2,
    memory_graph_nodes: config.graphMaxNodes ?? 5,
    enable_entity_graph: config.enableEntityRecall ?? false,
    entity_graph_depth: config.graphMaxDepth ?? 2,
    entity_graph_nodes: config.graphMaxNodes ?? 5,
    language: config.language === "auto" ? "auto" : (config.language === "zh_CN" ? "zh_CN" : "en_US"),
    enable_chunks_search: config.enableChunksSearch ?? true,
    chunks_similarity_threshold: config.chunksSimilarityThreshold ?? 0.45,
    memory_similarity_threshold: config.similarityThreshold,
    entity_chunk_threshold: config.entityChunkThreshold,
  };

  try {
    const response = await client.injectContext(userTag, projectTag, userMessage, apiConfig);

    const isZh = config.language === "zh_CN" || 
      (config.language === "auto" && detectLocale(userMessage, "auto") === "zh_CN");
    
    const lines: string[] = [];
    lines.push(isZh ? "## 用户上下文" : "## User Context");
    lines.push("");
    
    lines.push(...getAiGuidance(isZh));

    if (response.context) {
      lines.push(response.context);
    }

    const context = lines.length > 3 ? lines.join("\n") : "";

    const projectMemoriesCount = response.stats.project_memories_count ?? 
      (response.stats.memories_count - (response.stats.user_memories_count ?? 0));

    return {
      context,
      profileCount: response.stats.profile_count,
      projectCount: projectMemoriesCount,
      userCount: response.stats.user_memories_count ?? 0,
      chunksCount: response.stats.chunks_count,
      graphCount: 0,
      entityCount: 0,
      injectedMemoryIds: [
        ...response.sources.memories.map(m => m.id),
        ...(response.sources.user_memories?.map(m => m.id) || []),
      ].filter((id): id is string => id !== undefined),
    };
  } catch (error) {
    console.warn("Backend context injection failed, falling back to frontend:", error);
    return injectContext(client, userMessage, userTag, projectTag, {
      ...config,
      enableChunksSearch: config.enableChunksSearch ?? true,
      chunksSimilarityThreshold: config.chunksSimilarityThreshold ?? 0.45,
      chunksDocTypes: config.chunksDocTypes ?? [],
      enableGraphRecall: config.enableGraphRecall ?? false,
      enableEntityRecall: config.enableEntityRecall ?? false,
    });
  }
}
