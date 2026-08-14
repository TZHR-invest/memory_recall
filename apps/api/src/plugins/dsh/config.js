/**
 * memory-recall-dsh 配置解析
 *
 * 配置优先级：cordis patch config > 环境变量 > 默认值。
 * 环境变量（与 deepseek-tui / hermes 插件保持一致的前缀）：
 *   MEMORY_RECALL_API_KEY   API Key（rk_live_... / rk_test_...）
 *   MEMORY_RECALL_BASE_URL   后端地址（默认 http://localhost:8000）
 *   MEMORY_RECALL_KEY_ID     已获取的 keyId（可选，缺省启动时调 /auth/verify 自动获取）
 *
 * 标签约定（与 opencode / codex 插件一致）：
 *   userTag    = keyId（跨项目）
 *   projectTag = {keyId}_project-<cwd 目录名>
 * 全局容器覆盖：config.containerTag 设置后同时用作 user/project tag。
 */

/** 智能召回触发关键词（与 opencode 插件 DEFAULT_RECALL_KEYWORDS 对齐） */
export const DEFAULT_RECALL_KEYWORDS = [
  // 时间相关
  "记得", "之前", "上次", "以前", "回忆", "记忆",
  // 项目相关
  "项目", "代码", "架构", "设计", "配置", "实现", "功能",
  "技术", "框架", "模块", "组件", "接口", "服务", "文件",
  // 问题相关
  "怎么", "如何", "在哪", "什么", "为什么", "是否", "有没有",
  // 行为相关
  "偏好", "喜欢", "习惯", "风格", "约束", "决策", "约定", "规范",
  // 英文
  "recall", "remember", "previous", "earlier",
  "project", "code", "config", "architecture", "design",
  "how", "where", "what", "why", "when",
];

export const MEMORY_TYPES = [
  "project-config",
  "architecture",
  "error-solution",
  "preference",
  "learned-pattern",
  "conversation",
];

export const INJECTION_STRATEGIES = ["once", "smart", "always"];

export const CAPTURE_MODES = ["extract", "raw"];

const DEFAULTS = {
  baseUrl: "http://localhost:8000",
  userName: "User",
  autoRecall: true,
  autoCapture: true,
  injectionStrategy: "smart",
  maxMemories: 5,
  maxProfileItems: 5,
  maxStaticProfileItems: 30,
  injectProfile: true,
  enableChunksSearch: true,
  maxChunks: 3,
  language: "auto",
  similarityThreshold: 0.4,
  enableGraphRecall: true,
  enableEntityRecall: true,
  graphMaxDepth: 2,
  graphMaxNodes: 5,
  minRecallQueryLength: 5,
  captureMode: "extract",
  captureMinLength: 40,
  captureMaxChars: 4000,
  requestTimeoutMs: 30000,
  // 写入超时单独放宽：POST /memories 同步包含 embedding + LLM 实体提取 + 关系检测，
  // 实测可到 25s+（后端 LLM 调用延迟），30s 默认读超时会误杀写入
  writeTimeoutMs: 90000,
  debug: false,
};

/** 整数夹取：undefined → 默认值，越界 → 就近夹取（防止后端 422） */
function clampInt(value, min, max, fallback) {
  if (value === undefined || value === null || Number.isNaN(Number(value))) {
    return fallback;
  }
  return Math.min(max, Math.max(min, Math.trunc(Number(value))));
}

/** 浮点夹取：undefined → 默认值，越界 → 就近夹取 */
function clampNum(value, min, max, fallback) {
  if (value === undefined || value === null || Number.isNaN(Number(value))) {
    return fallback;
  }
  return Math.min(max, Math.max(min, Number(value)));
}

/** 取 cwd 的目录名作为项目名；异常路径回退 "default" */
export function projectDirName(cwd) {
  if (typeof cwd !== "string" || cwd.length === 0) return "default";
  const parts = cwd.replace(/[\\/]+$/, "").split(/[\\/]/);
  const base = parts[parts.length - 1] ?? "";
  return base.length > 0 ? base : "default";
}

/**
 * 归一化插件配置。
 * @param raw - cordis patch 传入的 config 对象（可能含 undefined 字段）
 * @returns 归一化后的配置（全部字段有值）
 */
export function resolveConfig(raw = {}) {
  const env = process.env ?? {};
  // 空字符串视为未配置（patch 可能写入空占位），回退环境变量
  const apiKey = (typeof raw.apiKey === "string" && raw.apiKey.trim().length > 0)
    ? raw.apiKey.trim()
    : (env.MEMORY_RECALL_API_KEY || null);
  const baseUrl = (raw.baseUrl ?? env.MEMORY_RECALL_BASE_URL ?? DEFAULTS.baseUrl)
    .replace(/\/+$/, "");
  const keyId = raw.keyId ?? env.MEMORY_RECALL_KEY_ID ?? null;

  const injectionStrategy = raw.injectionStrategy ?? DEFAULTS.injectionStrategy;
  if (!INJECTION_STRATEGIES.includes(injectionStrategy)) {
    throw new Error(
      `memory-recall-dsh: injectionStrategy 必须是 ${INJECTION_STRATEGIES.join("/")}，收到 ${JSON.stringify(injectionStrategy)}`
    );
  }
  const captureMode = raw.captureMode ?? DEFAULTS.captureMode;
  if (!CAPTURE_MODES.includes(captureMode)) {
    throw new Error(
      `memory-recall-dsh: captureMode 必须是 ${CAPTURE_MODES.join("/")}，收到 ${JSON.stringify(captureMode)}`
    );
  }

  return {
    apiKey,
    baseUrl,
    keyId,
    userName: raw.userName ?? DEFAULTS.userName,
    containerTag: raw.containerTag ?? null,
    projectTagOverride: raw.projectTagOverride ?? null,
    autoRecall: raw.autoRecall ?? DEFAULTS.autoRecall,
    autoCapture: raw.autoCapture ?? DEFAULTS.autoCapture,
    injectionStrategy,
    maxMemories: clampInt(raw.maxMemories, 1, 20, DEFAULTS.maxMemories),
    maxProfileItems: clampInt(raw.maxProfileItems, 1, 50, DEFAULTS.maxProfileItems),
    maxStaticProfileItems: clampInt(raw.maxStaticProfileItems, 1, 100, DEFAULTS.maxStaticProfileItems),
    injectProfile: raw.injectProfile ?? DEFAULTS.injectProfile,
    enableChunksSearch: raw.enableChunksSearch ?? DEFAULTS.enableChunksSearch,
    maxChunks: clampInt(raw.maxChunks, 1, 10, DEFAULTS.maxChunks),
    language: raw.language ?? DEFAULTS.language,
    similarityThreshold: clampNum(raw.similarityThreshold, 0, 1, DEFAULTS.similarityThreshold),
    enableGraphRecall: raw.enableGraphRecall ?? DEFAULTS.enableGraphRecall,
    enableEntityRecall: raw.enableEntityRecall ?? DEFAULTS.enableEntityRecall,
    graphMaxDepth: clampInt(raw.graphMaxDepth, 1, 5, DEFAULTS.graphMaxDepth),
    graphMaxNodes: clampInt(raw.graphMaxNodes, 1, 20, DEFAULTS.graphMaxNodes),
    smartRecallKeywords: Array.isArray(raw.smartRecallKeywords) && raw.smartRecallKeywords.length > 0
      ? raw.smartRecallKeywords
      : DEFAULT_RECALL_KEYWORDS,
    minRecallQueryLength: clampInt(raw.minRecallQueryLength, 1, 200, DEFAULTS.minRecallQueryLength),
    captureMode,
    captureMinLength: clampInt(raw.captureMinLength, 1, 10000, DEFAULTS.captureMinLength),
    captureMaxChars: clampInt(raw.captureMaxChars, 200, 20000, DEFAULTS.captureMaxChars),
    requestTimeoutMs: clampInt(raw.requestTimeoutMs, 1000, 120000, DEFAULTS.requestTimeoutMs),
    writeTimeoutMs: clampInt(raw.writeTimeoutMs, 5000, 300000, DEFAULTS.writeTimeoutMs),
    debug: raw.debug ?? DEFAULTS.debug,
  };
}

/** 按配置生成项目 tag：{keyId}_project-<目录名> */
export function projectTagFor(keyId, cwd) {
  return `${keyId}_project-${projectDirName(cwd)}`;
}

/**
 * 语言检测：配置非 auto 时直接采用；auto 时按中文字符占比（>30% 判 zh_CN）。
 */
export function detectLocale(text, language = "auto") {
  if (language !== "auto") return language;
  if (typeof text !== "string" || text.length === 0) return "zh_CN";
  const chineseChars = (text.match(/[\u4e00-\u9fff]/g) ?? []).length;
  const totalChars = text.replace(/\s/g, "").length;
  return totalChars > 0 && chineseChars / totalChars > 0.3 ? "zh_CN" : "en_US";
}

/** 关键词触发：文本包含任一召回关键词 */
export function shouldTriggerRecall(text, keywords) {
  if (typeof text !== "string" || text.length === 0) return false;
  return keywords.some((kw) => text.includes(kw));
}
