/**
 * Configuration loader for Memory Recall OpenCode plugin
 * Supports environment variables, JSONC config file, and defaults
 */

import * as fs from "fs";
import * as path from "path";
import * as os from "os";

/**
 * Injection strategy types
 * - "once": Only inject on first message in session
 * - "smart": Initial injection + keyword-triggered recall (default)
 * - "always": Inject on every message (legacy behavior)
 */
export type InjectionStrategy = "once" | "smart" | "always";

/**
 * Configuration for initial injection (first message in session)
 */
export interface InitialInjectionConfig {
  profile: boolean;
  projectMemories: boolean;
  chunks: boolean;
  maxChunks: number;
}

/**
 * Configuration for smart recall (keyword-triggered)
 */
export interface SmartRecallConfig {
  enabled: boolean;
  keywords: string[];
  maxAdditionalMemories: number;
  maxAdditionalChunks: number;
}

/**
 * Default keywords for smart recall trigger
 */
export const DEFAULT_RECALL_KEYWORDS = [
  "记得", "之前", "上次", "以前", "回忆", "记忆",
  "recall", "remember", "previous", "earlier"
];

export interface Config {
  apiKey: string | null;
  baseUrl: string;
  userName: string;
  userContainerTag: string | null;
  projectContainerTag: string | null;
  similarityThreshold: number;
  maxMemories: number;
  maxProjectMemories: number;
  maxProfileItems: number;
  injectProfile: boolean;
  compactionThreshold: number;
  enableSummaryCapture: boolean;
  enableDocumentTracking: boolean;
  trackedDocPatterns: string[];
  language: "auto" | "zh_CN" | "en_US";
  logFile: string;
  logLevel: "debug" | "info" | "warn" | "error";
  enableEventHandling: boolean;
  enableChunksSearch: boolean;
  maxChunks: number;
  chunksSimilarityThreshold: number;
  chunksDocTypes: string[];
  enableGraphRecall: boolean;
  enableEntityRecall: boolean;
  graphMaxDepth: number;
  graphMaxNodes: number;
  enableSmartRecall: boolean;  // Deprecated: use injectionStrategy instead
  maxInjectedMemoryIds: number;
  recallThreshold: number;
  dynamicRecallSize: boolean;
  // New injection strategy config
  injectionStrategy: InjectionStrategy;
  initialInjection: InitialInjectionConfig;
  smartRecall: SmartRecallConfig;
}

const DEFAULT_CONFIG: Omit<Config, "apiKey"> = {
  baseUrl: "http://localhost:8000",
  userName: "User",
  userContainerTag: null,
  projectContainerTag: null,
  similarityThreshold: 0.4,
  maxMemories: 5,
  maxProjectMemories: 10,
  maxProfileItems: 5,
  injectProfile: true,
  compactionThreshold: 0.8,
  enableSummaryCapture: true,
  enableDocumentTracking: true,
  trackedDocPatterns: [
    "README*.md",
    "CHANGELOG*.md",
    "docs/*.md",
    "AGENTS.md",
  ],
  language: "auto",
  logFile: "~/.memory-recall-opencode.log",
  logLevel: "info",
  enableEventHandling: true,
  enableChunksSearch: true,
  maxChunks: 5,
  chunksSimilarityThreshold: 0.3,
  chunksDocTypes: [],
  enableGraphRecall: true,
  enableEntityRecall: true,
  graphMaxDepth: 2,
  graphMaxNodes: 5,
  enableSmartRecall: true,
  maxInjectedMemoryIds: 100,
  recallThreshold: 0.5,
  dynamicRecallSize: true,
  // New injection strategy defaults
  injectionStrategy: "smart",
  initialInjection: {
    profile: true,
    projectMemories: true,
    chunks: true,
    maxChunks: 3,
  },
  smartRecall: {
    enabled: true,
    keywords: DEFAULT_RECALL_KEYWORDS,
    maxAdditionalMemories: 3,
    maxAdditionalChunks: 2,
  },
};

function parseJsonc(content: string): Record<string, unknown> {
  const protectedStrings: string[] = [];
  const STRING_PLACEHOLDER_PREFIX = "__JSONC_STR_";
  
  const withoutStrings = content.replace(/"(?:[^"\\]|\\.)*"/g, (match) => {
    protectedStrings.push(match);
    return `${STRING_PLACEHOLDER_PREFIX}${protectedStrings.length - 1}__`;
  });

  const withoutComments = withoutStrings
    .replace(/\/\/.*$/gm, "")
    .replace(/\/\*[\s\S]*?\*\//g, "")
    .replace(/,(\s*[}\]])/g, "$1");

  const restored = withoutComments.replace(
    new RegExp(`${STRING_PLACEHOLDER_PREFIX}(\\d+)__`, "g"),
    (_, idx) => protectedStrings[parseInt(idx)]
  );

  try {
    return JSON.parse(restored);
  } catch {
    return {};
  }
}

function getConfigPath(): string {
  return path.join(os.homedir(), ".config", "opencode", "memory-recall.jsonc");
}

export function loadConfig(overrides: Record<string, unknown> = {}): Config {
  const configPath = getConfigPath();
  let fileConfig: Record<string, unknown> = {};

  if (fs.existsSync(configPath)) {
    try {
      const content = fs.readFileSync(configPath, "utf-8");
      fileConfig = parseJsonc(content);
    } catch {
      // Silently fail - will use defaults
    }
  }

  // Priority: env > overrides > file > defaults
  const config: Config = {
    apiKey:
      process.env.MEMORY_RECALL_API_KEY ||
      (overrides.apiKey as string | null) ||
      (fileConfig.apiKey as string | null) ||
      null,
    baseUrl:
      process.env.MEMORY_RECALL_BASE_URL ||
      (overrides.baseUrl as string) ||
      (fileConfig.baseUrl as string) ||
      DEFAULT_CONFIG.baseUrl,
    userName:
      (overrides.userName as string) ||
      (fileConfig.userName as string) ||
      DEFAULT_CONFIG.userName,
    userContainerTag:
      (overrides.userContainerTag as string | null) ||
      (fileConfig.userContainerTag as string | null) ||
      DEFAULT_CONFIG.userContainerTag,
    projectContainerTag:
      (overrides.projectContainerTag as string | null) ||
      (fileConfig.projectContainerTag as string | null) ||
      DEFAULT_CONFIG.projectContainerTag,
    similarityThreshold:
      (overrides.similarityThreshold as number) ||
      (fileConfig.similarityThreshold as number) ||
      DEFAULT_CONFIG.similarityThreshold,
    maxMemories:
      (overrides.maxMemories as number) ||
      (fileConfig.maxMemories as number) ||
      DEFAULT_CONFIG.maxMemories,
    maxProjectMemories:
      (overrides.maxProjectMemories as number) ||
      (fileConfig.maxProjectMemories as number) ||
      DEFAULT_CONFIG.maxProjectMemories,
    maxProfileItems:
      (overrides.maxProfileItems as number) ||
      (fileConfig.maxProfileItems as number) ||
      DEFAULT_CONFIG.maxProfileItems,
    injectProfile:
      (overrides.injectProfile as boolean) ??
      (fileConfig.injectProfile as boolean) ??
      DEFAULT_CONFIG.injectProfile,
    compactionThreshold:
      (overrides.compactionThreshold as number) ||
      (fileConfig.compactionThreshold as number) ||
      DEFAULT_CONFIG.compactionThreshold,
    enableSummaryCapture:
      (overrides.enableSummaryCapture as boolean) ??
      (fileConfig.enableSummaryCapture as boolean) ??
      DEFAULT_CONFIG.enableSummaryCapture,
    enableDocumentTracking:
      (overrides.enableDocumentTracking as boolean) ??
      (fileConfig.enableDocumentTracking as boolean) ??
      DEFAULT_CONFIG.enableDocumentTracking,
    trackedDocPatterns:
      (overrides.trackedDocPatterns as string[]) ||
      (fileConfig.trackedDocPatterns as string[]) ||
      DEFAULT_CONFIG.trackedDocPatterns,
    language:
      (process.env.MEMORY_RECALL_LANGUAGE as Config["language"]) ||
      (overrides.language as Config["language"]) ||
      (fileConfig.language as Config["language"]) ||
      DEFAULT_CONFIG.language,
    logFile:
      (overrides.logFile as string) ||
      (fileConfig.logFile as string) ||
      DEFAULT_CONFIG.logFile,
    logLevel:
      (overrides.logLevel as Config["logLevel"]) ||
      (fileConfig.logLevel as Config["logLevel"]) ||
      DEFAULT_CONFIG.logLevel,
    enableEventHandling:
      (overrides.enableEventHandling as boolean) ??
      (fileConfig.enableEventHandling as boolean) ??
      DEFAULT_CONFIG.enableEventHandling,
    enableChunksSearch:
      (overrides.enableChunksSearch as boolean) ??
      (fileConfig.enableChunksSearch as boolean) ??
      DEFAULT_CONFIG.enableChunksSearch,
    maxChunks:
      (overrides.maxChunks as number) ||
      (fileConfig.maxChunks as number) ||
      DEFAULT_CONFIG.maxChunks,
    chunksSimilarityThreshold:
      (overrides.chunksSimilarityThreshold as number) ||
      (fileConfig.chunksSimilarityThreshold as number) ||
      DEFAULT_CONFIG.chunksSimilarityThreshold,
    chunksDocTypes:
      (overrides.chunksDocTypes as string[]) ||
      (fileConfig.chunksDocTypes as string[]) ||
      DEFAULT_CONFIG.chunksDocTypes,
    enableGraphRecall:
      (overrides.enableGraphRecall as boolean) ??
      (fileConfig.enableGraphRecall as boolean) ??
      DEFAULT_CONFIG.enableGraphRecall,
    enableEntityRecall:
      (overrides.enableEntityRecall as boolean) ??
      (fileConfig.enableEntityRecall as boolean) ??
      DEFAULT_CONFIG.enableEntityRecall,
    graphMaxDepth:
      (overrides.graphMaxDepth as number) ||
      (fileConfig.graphMaxDepth as number) ||
      DEFAULT_CONFIG.graphMaxDepth,
    graphMaxNodes:
      (overrides.graphMaxNodes as number) ||
      (fileConfig.graphMaxNodes as number) ||
      DEFAULT_CONFIG.graphMaxNodes,
    enableSmartRecall:
      (overrides.enableSmartRecall as boolean) ??
      (fileConfig.enableSmartRecall as boolean) ??
      DEFAULT_CONFIG.enableSmartRecall,
    maxInjectedMemoryIds:
      (overrides.maxInjectedMemoryIds as number) ||
      (fileConfig.maxInjectedMemoryIds as number) ||
      DEFAULT_CONFIG.maxInjectedMemoryIds,
    recallThreshold:
      (overrides.recallThreshold as number) ||
      (fileConfig.recallThreshold as number) ||
      DEFAULT_CONFIG.recallThreshold,
    dynamicRecallSize:
      (overrides.dynamicRecallSize as boolean) ??
      (fileConfig.dynamicRecallSize as boolean) ??
      DEFAULT_CONFIG.dynamicRecallSize,
    // New injection strategy config
    injectionStrategy:
      (process.env.MEMORY_RECALL_INJECTION_STRATEGY as InjectionStrategy) ||
      (overrides.injectionStrategy as InjectionStrategy) ||
      (fileConfig.injectionStrategy as InjectionStrategy) ||
      DEFAULT_CONFIG.injectionStrategy,
    initialInjection: {
      profile:
        ((overrides.initialInjection as Record<string, unknown>)?.profile as boolean) ??
        ((fileConfig.initialInjection as Record<string, unknown>)?.profile as boolean) ??
        DEFAULT_CONFIG.initialInjection.profile,
      projectMemories:
        ((overrides.initialInjection as Record<string, unknown>)?.projectMemories as boolean) ??
        ((fileConfig.initialInjection as Record<string, unknown>)?.projectMemories as boolean) ??
        DEFAULT_CONFIG.initialInjection.projectMemories,
      chunks:
        ((overrides.initialInjection as Record<string, unknown>)?.chunks as boolean) ??
        ((fileConfig.initialInjection as Record<string, unknown>)?.chunks as boolean) ??
        DEFAULT_CONFIG.initialInjection.chunks,
      maxChunks:
        ((overrides.initialInjection as Record<string, unknown>)?.maxChunks as number) ||
        ((fileConfig.initialInjection as Record<string, unknown>)?.maxChunks as number) ||
        DEFAULT_CONFIG.initialInjection.maxChunks,
    },
    smartRecall: {
      enabled:
        ((overrides.smartRecall as Record<string, unknown>)?.enabled as boolean) ??
        ((fileConfig.smartRecall as Record<string, unknown>)?.enabled as boolean) ??
        DEFAULT_CONFIG.smartRecall.enabled,
      keywords:
        ((overrides.smartRecall as Record<string, unknown>)?.keywords as string[]) ||
        ((fileConfig.smartRecall as Record<string, unknown>)?.keywords as string[]) ||
        DEFAULT_CONFIG.smartRecall.keywords,
      maxAdditionalMemories:
        ((overrides.smartRecall as Record<string, unknown>)?.maxAdditionalMemories as number) ||
        ((fileConfig.smartRecall as Record<string, unknown>)?.maxAdditionalMemories as number) ||
        DEFAULT_CONFIG.smartRecall.maxAdditionalMemories,
      maxAdditionalChunks:
        ((overrides.smartRecall as Record<string, unknown>)?.maxAdditionalChunks as number) ||
        ((fileConfig.smartRecall as Record<string, unknown>)?.maxAdditionalChunks as number) ||
        DEFAULT_CONFIG.smartRecall.maxAdditionalChunks,
    },
  };

  return config;
}

export function isConfigured(config: Config): boolean {
  return config.apiKey !== null && config.apiKey.length > 0;
}

export function getUserTag(config: Config): string {
  return config.userContainerTag || `user-${config.userName.toLowerCase().replace(/\s+/g, "-")}`;
}

export function getProjectTag(config: Config, directory: string): string {
  if (config.projectContainerTag) {
    return config.projectContainerTag;
  }
  const projectName = path.basename(directory);
  return `project-${projectName.toLowerCase().replace(/\s+/g, "-")}`;
}
