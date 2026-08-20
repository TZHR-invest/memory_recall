import * as fs from "fs";
import * as path from "path";
import * as os from "os";
import { spawnSync } from "child_process";

export type InjectionStrategy = "once" | "smart" | "always";

export interface InitialInjectionConfig { profile: boolean; projectMemories: boolean; chunks: boolean; maxChunks: number; }
export interface SmartRecallConfig { enabled: boolean; keywords: string[]; maxAdditionalMemories: number; maxAdditionalChunks: number; }
export interface SemanticDedupConfig { enabled: boolean; threshold: number; }
export interface AsyncQueueConfig {
  enabled: boolean; maxConcurrency: number; maxSize: number; taskTimeoutMs: number;
  retryPolicy: { maxRetries: number; initialDelay: number; maxDelay: number; backoffMultiplier: number; };
}

export const DEFAULT_RECALL_KEYWORDS = [
  "记得", "之前", "上次", "以前", "回忆", "记忆",
  "项目", "代码", "架构", "设计", "配置", "实现", "功能",
  "技术", "框架", "模块", "组件", "接口", "服务", "文件",
  "怎么", "如何", "在哪", "什么", "为什么", "是否", "有没有",
  "偏好", "喜欢", "习惯", "风格", "约束", "决策", "约定", "规范",
  "recall", "remember", "previous", "earlier",
  "project", "code", "config", "architecture", "design",
  "how", "where", "what", "why", "when"
];

export interface Config {
  apiKey: string | null; baseUrl: string; userName: string; keyId: string | null;
  similarityThreshold: number; maxMemories: number; maxProjectMemories: number;
  maxProfileItems: number; maxStaticProfileItems: number; injectProfile: boolean;
  compactionThreshold: number; language: "auto" | "zh_CN" | "en_US";
  logFile: string; logLevel: "debug" | "info" | "warn" | "error";
  enableEventHandling: boolean; enableChunksSearch: boolean; maxChunks: number;
  chunksSimilarityThreshold: number; entityChunkThreshold: number; chunksDocTypes: string[];
  enableGraphRecall: boolean; enableEntityRecall: boolean; graphMaxDepth: number; graphMaxNodes: number;
  enableSmartRecall: boolean; maxInjectedMemoryIds: number; recallThreshold: number; dynamicRecallSize: boolean;
  injectionStrategy: InjectionStrategy; initialInjection: InitialInjectionConfig;
  smartRecall: SmartRecallConfig; semanticDedup: SemanticDedupConfig; asyncQueue: AsyncQueueConfig;
}

const DEFAULT_CONFIG: Omit<Config, "apiKey"> = {
  baseUrl: "http://localhost:8000", userName: "User", keyId: null,
  similarityThreshold: 0.4, maxMemories: 5, maxProjectMemories: 10,
  maxProfileItems: 5, maxStaticProfileItems: 30, injectProfile: true,
  compactionThreshold: 0.8, language: "auto",
  logFile: "~/.memory-recall-opencode.log", logLevel: "info",
  enableEventHandling: true, enableChunksSearch: true, maxChunks: 5,
  chunksSimilarityThreshold: 0.45, entityChunkThreshold: 0.30, chunksDocTypes: [],
  enableGraphRecall: true, enableEntityRecall: true, graphMaxDepth: 2, graphMaxNodes: 5,
  enableSmartRecall: true, maxInjectedMemoryIds: 100, recallThreshold: 0.5, dynamicRecallSize: true,
  injectionStrategy: "smart",
  initialInjection: { profile: true, projectMemories: true, chunks: true, maxChunks: 3 },
  smartRecall: { enabled: true, keywords: DEFAULT_RECALL_KEYWORDS, maxAdditionalMemories: 3, maxAdditionalChunks: 2 },
  semanticDedup: { enabled: true, threshold: 0.85 },
  asyncQueue: { enabled: false, maxConcurrency: 3, maxSize: 100, taskTimeoutMs: 180000, retryPolicy: { maxRetries: 3, initialDelay: 1000, maxDelay: 10000, backoffMultiplier: 2 } },
};

function parseJsonc(content: string): Record<string, unknown> {
  const protectedStrings: string[] = [];
  const PH = "__JSONC_STR_";
  const withoutStrings = content.replace(/"(?:[^"\\]|\\.)*"/g, (m) => { protectedStrings.push(m); return `${PH}${protectedStrings.length - 1}__`; });
  const withoutComments = withoutStrings.replace(/\/\/.*$/gm, "").replace(/\/\*[\s\S]*?\*\//g, "").replace(/,(\s*[}\]])/g, "$1");
  const restored = withoutComments.replace(new RegExp(`${PH}(\\d+)__`, "g"), (_, idx) => protectedStrings[parseInt(idx)]);
  try { return JSON.parse(restored); } catch { return {}; }
}
function getConfigPath(): string { return path.join(os.homedir(), ".config", "opencode", "memory-recall.jsonc"); }

export function loadConfig(overrides: Record<string, unknown> = {}): Config {
  const configPath = getConfigPath();
  let fileConfig: Record<string, unknown> = {};
  if (fs.existsSync(configPath)) {
    try { fileConfig = parseJsonc(fs.readFileSync(configPath, "utf-8")); } catch { /* use defaults */ }
  }
  const raw = buildRawConfig(overrides, fileConfig);
  if (raw.semanticDedup.threshold < 0 || raw.semanticDedup.threshold > 1) throw new Error(`semanticDedup.threshold must be between 0.0 and 1.0, got ${raw.semanticDedup.threshold}`);
  return raw;
}

function buildRawConfig(overrides: Record<string, unknown>, fileConfig: Record<string, unknown>): Config {
  const cfg: Config = {
    apiKey: (process.env.MEMORY_RECALL_API_KEY as string) || (overrides.apiKey as string | null) || (fileConfig.apiKey as string | null) || null,
    baseUrl: (process.env.MEMORY_RECALL_BASE_URL as string) || (overrides.baseUrl as string) || (fileConfig.baseUrl as string) || DEFAULT_CONFIG.baseUrl,
    userName: (overrides.userName as string) || (fileConfig.userName as string) || DEFAULT_CONFIG.userName,
    keyId: (overrides.keyId as string | null) || (fileConfig.keyId as string | null) || DEFAULT_CONFIG.keyId,
    similarityThreshold: (overrides.similarityThreshold as number) || (fileConfig.similarityThreshold as number) || DEFAULT_CONFIG.similarityThreshold,
    maxMemories: (overrides.maxMemories as number) || (fileConfig.maxMemories as number) || DEFAULT_CONFIG.maxMemories,
    maxProjectMemories: (overrides.maxProjectMemories as number) || (fileConfig.maxProjectMemories as number) || DEFAULT_CONFIG.maxProjectMemories,
    maxProfileItems: (overrides.maxProfileItems as number) || (fileConfig.maxProfileItems as number) || DEFAULT_CONFIG.maxProfileItems,
    maxStaticProfileItems: (overrides.maxStaticProfileItems as number) || (fileConfig.maxStaticProfileItems as number) || DEFAULT_CONFIG.maxStaticProfileItems,
    injectProfile: (overrides.injectProfile as boolean) ?? (fileConfig.injectProfile as boolean) ?? DEFAULT_CONFIG.injectProfile,
    compactionThreshold: (overrides.compactionThreshold as number) || (fileConfig.compactionThreshold as number) || DEFAULT_CONFIG.compactionThreshold,
    language: (process.env.MEMORY_RECALL_LANGUAGE as Config["language"]) || (overrides.language as Config["language"]) || (fileConfig.language as Config["language"]) || DEFAULT_CONFIG.language,
    logFile: (overrides.logFile as string) || (fileConfig.logFile as string) || DEFAULT_CONFIG.logFile,
    logLevel: (overrides.logLevel as Config["logLevel"]) || (fileConfig.logLevel as Config["logLevel"]) || DEFAULT_CONFIG.logLevel,
    enableEventHandling: (overrides.enableEventHandling as boolean) ?? (fileConfig.enableEventHandling as boolean) ?? DEFAULT_CONFIG.enableEventHandling,
    enableChunksSearch: (overrides.enableChunksSearch as boolean) ?? (fileConfig.enableChunksSearch as boolean) ?? DEFAULT_CONFIG.enableChunksSearch,
    maxChunks: (overrides.maxChunks as number) || (fileConfig.maxChunks as number) || DEFAULT_CONFIG.maxChunks,
    chunksSimilarityThreshold: (overrides.chunksSimilarityThreshold as number) || (fileConfig.chunksSimilarityThreshold as number) || DEFAULT_CONFIG.chunksSimilarityThreshold,
    entityChunkThreshold: (overrides.entityChunkThreshold as number) ?? (fileConfig.entityChunkThreshold as number) ?? DEFAULT_CONFIG.entityChunkThreshold,
    chunksDocTypes: (overrides.chunksDocTypes as string[]) || (fileConfig.chunksDocTypes as string[]) || DEFAULT_CONFIG.chunksDocTypes,
    enableGraphRecall: (overrides.enableGraphRecall as boolean) ?? (fileConfig.enableGraphRecall as boolean) ?? DEFAULT_CONFIG.enableGraphRecall,
    enableEntityRecall: (overrides.enableEntityRecall as boolean) ?? (fileConfig.enableEntityRecall as boolean) ?? DEFAULT_CONFIG.enableEntityRecall,
    graphMaxDepth: (overrides.graphMaxDepth as number) || (fileConfig.graphMaxDepth as number) || DEFAULT_CONFIG.graphMaxDepth,
    graphMaxNodes: (overrides.graphMaxNodes as number) || (fileConfig.graphMaxNodes as number) || DEFAULT_CONFIG.graphMaxNodes,
    enableSmartRecall: (overrides.enableSmartRecall as boolean) ?? (fileConfig.enableSmartRecall as boolean) ?? DEFAULT_CONFIG.enableSmartRecall,
    maxInjectedMemoryIds: (overrides.maxInjectedMemoryIds as number) || (fileConfig.maxInjectedMemoryIds as number) || DEFAULT_CONFIG.maxInjectedMemoryIds,
    recallThreshold: (overrides.recallThreshold as number) || (fileConfig.recallThreshold as number) || DEFAULT_CONFIG.recallThreshold,
    dynamicRecallSize: (overrides.dynamicRecallSize as boolean) ?? (fileConfig.dynamicRecallSize as boolean) ?? DEFAULT_CONFIG.dynamicRecallSize,
    injectionStrategy: (process.env.MEMORY_RECALL_INJECTION_STRATEGY as InjectionStrategy) || (overrides.injectionStrategy as InjectionStrategy) || (fileConfig.injectionStrategy as InjectionStrategy) || DEFAULT_CONFIG.injectionStrategy,
    initialInjection: {
      profile: ((overrides.initialInjection as Record<string, unknown>)?.profile as boolean) ?? ((fileConfig.initialInjection as Record<string, unknown>)?.profile as boolean) ?? DEFAULT_CONFIG.initialInjection.profile,
      projectMemories: ((overrides.initialInjection as Record<string, unknown>)?.projectMemories as boolean) ?? ((fileConfig.initialInjection as Record<string, unknown>)?.projectMemories as boolean) ?? DEFAULT_CONFIG.initialInjection.projectMemories,
      chunks: ((overrides.initialInjection as Record<string, unknown>)?.chunks as boolean) ?? ((fileConfig.initialInjection as Record<string, unknown>)?.chunks as boolean) ?? DEFAULT_CONFIG.initialInjection.chunks,
      maxChunks: ((overrides.initialInjection as Record<string, unknown>)?.maxChunks as number) || ((fileConfig.initialInjection as Record<string, unknown>)?.maxChunks as number) || DEFAULT_CONFIG.initialInjection.maxChunks,
    },
    smartRecall: {
      enabled: ((overrides.smartRecall as Record<string, unknown>)?.enabled as boolean) ?? ((fileConfig.smartRecall as Record<string, unknown>)?.enabled as boolean) ?? DEFAULT_CONFIG.smartRecall.enabled,
      keywords: ((overrides.smartRecall as Record<string, unknown>)?.keywords as string[]) || ((fileConfig.smartRecall as Record<string, unknown>)?.keywords as string[]) || DEFAULT_CONFIG.smartRecall.keywords,
      maxAdditionalMemories: ((overrides.smartRecall as Record<string, unknown>)?.maxAdditionalMemories as number) || ((fileConfig.smartRecall as Record<string, unknown>)?.maxAdditionalMemories as number) || DEFAULT_CONFIG.smartRecall.maxAdditionalMemories,
      maxAdditionalChunks: ((overrides.smartRecall as Record<string, unknown>)?.maxAdditionalChunks as number) || ((fileConfig.smartRecall as Record<string, unknown>)?.maxAdditionalChunks as number) || DEFAULT_CONFIG.smartRecall.maxAdditionalChunks,
    },
    semanticDedup: {
      enabled: ((overrides.semanticDedup as Record<string, unknown>)?.enabled as boolean) ?? ((fileConfig.semanticDedup as Record<string, unknown>)?.enabled as boolean) ?? DEFAULT_CONFIG.semanticDedup.enabled,
      threshold: ((overrides.semanticDedup as Record<string, unknown>)?.threshold as number) || ((fileConfig.semanticDedup as Record<string, unknown>)?.threshold as number) || DEFAULT_CONFIG.semanticDedup.threshold,
    },
    asyncQueue: {
      enabled: ((overrides.asyncQueue as Record<string, unknown>)?.enabled as boolean) ?? ((fileConfig.asyncQueue as Record<string, unknown>)?.enabled as boolean) ?? DEFAULT_CONFIG.asyncQueue.enabled,
      maxConcurrency: ((overrides.asyncQueue as Record<string, unknown>)?.maxConcurrency as number) || ((fileConfig.asyncQueue as Record<string, unknown>)?.maxConcurrency as number) || DEFAULT_CONFIG.asyncQueue.maxConcurrency,
      maxSize: ((overrides.asyncQueue as Record<string, unknown>)?.maxSize as number) || ((fileConfig.asyncQueue as Record<string, unknown>)?.maxSize as number) || DEFAULT_CONFIG.asyncQueue.maxSize,
      taskTimeoutMs: ((overrides.asyncQueue as Record<string, unknown>)?.taskTimeoutMs as number) || ((fileConfig.asyncQueue as Record<string, unknown>)?.taskTimeoutMs as number) || DEFAULT_CONFIG.asyncQueue.taskTimeoutMs,
      retryPolicy: {
        maxRetries: ((overrides.asyncQueue as Record<string, unknown>)?.retryPolicy as Record<string, unknown>)?.maxRetries as number || ((fileConfig.asyncQueue as Record<string, unknown>)?.retryPolicy as Record<string, unknown>)?.maxRetries as number || DEFAULT_CONFIG.asyncQueue.retryPolicy.maxRetries,
        initialDelay: ((overrides.asyncQueue as Record<string, unknown>)?.retryPolicy as Record<string, unknown>)?.initialDelay as number || ((fileConfig.asyncQueue as Record<string, unknown>)?.retryPolicy as Record<string, unknown>)?.initialDelay as number || DEFAULT_CONFIG.asyncQueue.retryPolicy.initialDelay,
        maxDelay: ((overrides.asyncQueue as Record<string, unknown>)?.retryPolicy as Record<string, unknown>)?.maxDelay as number || ((fileConfig.asyncQueue as Record<string, unknown>)?.retryPolicy as Record<string, unknown>)?.maxDelay as number || DEFAULT_CONFIG.asyncQueue.retryPolicy.maxDelay,
        backoffMultiplier: ((overrides.asyncQueue as Record<string, unknown>)?.retryPolicy as Record<string, unknown>)?.backoffMultiplier as number || ((fileConfig.asyncQueue as Record<string, unknown>)?.retryPolicy as Record<string, unknown>)?.backoffMultiplier as number || DEFAULT_CONFIG.asyncQueue.retryPolicy.backoffMultiplier,
      },
    },
  };
  return cfg;
}

export function isConfigured(config: Config): boolean { return config.apiKey !== null && config.apiKey.length > 0; }
export function getUserTag(config: Config): string | null { return config.keyId ?? null; }

function gitRootName(directory: string): string | null {
  try {
    const res = spawnSync("git", ["rev-parse", "--show-toplevel"], { cwd: directory, encoding: "utf8", timeout: 5000 });
    if (res.status !== 0) return null;
    const name = path.basename((res.stdout ?? "").trim());
    if (!name || name.startsWith(".")) return null;
    return name;
  } catch { return null; }
}

export function getScope(config: Config, directory: string | null | undefined): string | null {
  if (!directory) return null;
  const projectName = path.basename(directory);
  const candidate = projectName && !projectName.startsWith(".") ? projectName : gitRootName(directory);
  const base = (candidate ?? "default").toLowerCase().replace(/\s+/g, "-");
  return `project-${base}`;
}

export function containerTagToScope(containerTag: string | null, keyId: string | null): string | null {
  if (!containerTag) return null;
  if (keyId && containerTag === keyId) return null;
  if (keyId && containerTag.startsWith(`${keyId}_`)) return containerTag.slice(keyId.length + 1);
  return containerTag;
}
