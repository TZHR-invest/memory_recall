/**
 * Session Summary 重要内容提取器
 */

export function extractImportantSections(summary: string): string | null {
  const parts: string[] = [];

  const instructionsMatch = summary.match(/## Instructions\n([\s\S]*?)(?=\n## |$)/);
  if (instructionsMatch) {
    const content = instructionsMatch[1].trim();
    if (content) {
      parts.push("【偏好/约束】\n" + content);
    }
  }

  const discoveriesMatch = summary.match(/## Discoveries\n([\s\S]*?)(?=\n## |$)/);
  if (discoveriesMatch) {
    const cleaned = discoveriesMatch[1]
      .replace(/```[\s\S]*?```/g, '\n[代码已省略]\n')
      .replace(/\n{3,}/g, '\n\n')
      .trim();
    if (cleaned) {
      parts.push("【发现/决策】\n" + cleaned);
    }
  }

  const constraintsMatch = summary.match(/##\s*(?:\d+\.\s*)?Explicit Constraints[\s\S]*?((?:-\s*"[^"]+"\n?)+)/);
  if (constraintsMatch) {
    const content = constraintsMatch[1]
      .replace(/-\s*"/g, '- ')
      .replace(/"\n?/g, '\n')
      .trim();
    if (content) {
      parts.push("【明确约束】\n" + content);
    }
  }

  if (parts.length === 0) return null;

  return parts.join("\n\n");
}

export function calculateOverlap(text1: string, text2: string): number {
  const words1 = new Set(text1.toLowerCase().split(/\s+/));
  const words2 = new Set(text2.toLowerCase().split(/\s+/));
  
  let intersection = 0;
  for (const word of words1) {
    if (words2.has(word)) intersection++;
  }
  
  const union = Math.max(words1.size, words2.size);
  return union === 0 ? 0 : intersection / union;
}

export function shouldSave(
  newContent: string,
  existingMemories: { content: string }[],
  threshold: number = 0.8
): boolean {
  for (const exist of existingMemories) {
    if (exist.content === newContent) return false;
    if (exist.content.includes(newContent) || newContent.includes(exist.content)) {
      return false;
    }
    const overlap = calculateOverlap(newContent, exist.content);
    if (overlap > threshold) return false;
  }
  
  return true;
}
