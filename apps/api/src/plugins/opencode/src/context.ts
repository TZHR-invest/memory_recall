import type { ApiClient, Profile, SearchResult, Memory, ChunkSearchResult, GraphNode, GraphEdge, GraphResponse } from "./client";
import { getAllKeywords, getLocale, type Locale } from "./i18n";

const keywordPattern = new RegExp(getAllKeywords().join("|"), "i");

export function computeContentHash(content: string): string {
  return Bun.hash(content).toString(16).padStart(16, "0");
}

export interface CrossScopeDedupResult {
  staticFacts: string[];
  dynamicFacts: string[];
  dedupedProjectMemories: Memory[];
  dedupStats: {
    projectMemoriesFiltered: number;
  };
}

export function deduplicateAcrossScopes(
  profile: Profile | null,
  projectMemories: Memory[]
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
  
  return {
    staticFacts,
    dynamicFacts,
    dedupedProjectMemories,
    dedupStats: {
      projectMemoriesFiltered: projectMemories.length - dedupedProjectMemories.length,
    },
  };
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
  maxProjectItems: number;
  maxUserItems: number;
  maxChunksItems: number;
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

export function formatContext(options: ContextOptions): string {
  const { profile, projectMemories, userMemories, projectChunks, locale, maxProfileItems, maxProjectItems, maxUserItems, maxChunksItems } = options;
  
  const isZh = locale === "zh_CN";
  const lines: string[] = [];

  const sectionTitle = isZh ? "## 用户上下文" : "## User Context";
  lines.push(sectionTitle);
  lines.push("");

  const deduped = deduplicateAcrossScopes(profile, projectMemories);
  const { staticFacts, dynamicFacts, dedupedProjectMemories } = deduped;

  if (staticFacts.length > 0) {
    const staticTitle = isZh ? "### 永久特征" : "### Static Facts";
    lines.push(staticTitle);
    staticFacts.slice(0, maxProfileItems).forEach((fact) => lines.push("- " + fact));
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

  if (projectChunks.length > 0) {
    const chunksTitle = isZh ? "### 项目文档" : "### Project Documents";
    lines.push(chunksTitle);
    projectChunks.slice(0, maxChunksItems).forEach((c) => {
      const similarity = Math.round(c.similarity * 100);
      const docTitle = c.document_title || "Document";
      lines.push(`- [${docTitle}: ${similarity}%] ${c.content}`);
    });
    lines.push("");
  }

  if (userMemories.length > 0) {
    const userTitle = isZh ? "### 相关记忆" : "### Related Memories";
    lines.push(userTitle);
    userMemories.slice(0, maxUserItems).forEach((m) => {
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
  }
): Promise<ContextResult> {
  const locale = detectLocale(userMessage, config.language);

  let profile: Profile | null = null;
  if (config.injectProfile) {
    try {
      const response = await client.getProfile(userTag, userMessage);
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
    // Filter out Session Summaries - they are only used during compaction restore
    // Session Summaries are historical conversation compressions, not permanent knowledge
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

  const profileCount = profile 
    ? Math.min(profile.static.length, config.maxProfileItems) + Math.min(profile.dynamic.length, config.maxProfileItems)
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
    maxProjectItems: config.maxProjectMemories,
    maxUserItems: config.maxMemories,
    maxChunksItems: config.maxChunks,
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
