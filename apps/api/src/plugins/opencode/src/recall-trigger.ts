import type { SmartRecallConfig } from "./config";
import { DEFAULT_RECALL_KEYWORDS } from "./config";

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
