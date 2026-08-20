/**
 * 共享核 - 记忆召回触发器（宿主无关）
 * 概念中立：仅处理关键词触发逻辑，不依赖 opencode 特定 config 结构。
 * 原属 opencode 插件，现抽至 _shared 供多宿主复用。
 */

export interface SmartRecallConfig {
  enabled: boolean;
  keywords: string[];
  maxAdditionalMemories: number;
  maxAdditionalChunks: number;
}

/**
 * 默认召回关键词（与 opencode config.ts 保持一致，独立定义以消除跨宿主依赖）
 * 关键词分类：
 * - 时间相关：触发历史记忆召回
 * - 项目相关：触发项目信息召回
 * - 问题相关：触发技术问题召回
 * - 行为相关：触发偏好/约束召回
 */
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
  "how", "where", "what", "why", "when"
];

export function shouldTriggerRecall(
  message: string,
  config: SmartRecallConfig
): boolean {
  if (!config.enabled) {
    return false;
  }

  const keywords = config.keywords.length > 0
    ? config.keywords
    : DEFAULT_RECALL_KEYWORDS;

  const lowerMessage = message.toLowerCase();

  return keywords.some(keyword =>
    lowerMessage.includes(keyword.toLowerCase())
  );
}

export function findTriggerKeyword(
  message: string,
  config: SmartRecallConfig
): string | null {
  if (!config.enabled) {
    return null;
  }

  const keywords = config.keywords.length > 0
    ? config.keywords
    : DEFAULT_RECALL_KEYWORDS;

  const lowerMessage = message.toLowerCase();

  for (const keyword of keywords) {
    if (lowerMessage.includes(keyword.toLowerCase())) {
      return keyword;
    }
  }

  return null;
}
