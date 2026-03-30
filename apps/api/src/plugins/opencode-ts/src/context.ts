import type { ApiClient, Profile, SearchResult, Memory, ChunkSearchResult } from "./client";
import { getAllKeywords, getLocale, type Locale } from "./i18n";

const keywordPattern = new RegExp(getAllKeywords().join("|"), "i");

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

export interface ContextOptions {
  profile: Profile | null;
  projectMemories: Memory[];
  userMemories: SearchResult[];
  projectChunks: ChunkSearchResult[];
  locale: string;
  maxProfileItems: number;
  maxProjectItems: number;
  maxUserItems: number;
  maxChunksItems: number;
}

export function formatContext(options: ContextOptions): string {
  const { profile, projectMemories, userMemories, projectChunks, locale, maxProfileItems, maxProjectItems, maxUserItems, maxChunksItems } = options;
  
  const isZh = locale === "zh_CN";
  const lines: string[] = [];

  const sectionTitle = isZh ? "## 用户上下文" : "## User Context";
  lines.push(sectionTitle);
  lines.push("");

  if (profile) {
    const staticFacts = profile.static.slice(0, maxProfileItems);
    const dynamicFacts = profile.dynamic.slice(0, maxProfileItems);

    if (staticFacts.length > 0) {
      const staticTitle = isZh ? "### 永久特征" : "### Static Facts";
      lines.push(staticTitle);
      staticFacts.forEach((fact) => lines.push("- " + fact));
      lines.push("");
    }

    if (dynamicFacts.length > 0) {
      const dynamicTitle = isZh ? "### 最近活动" : "### Recent Activities";
      lines.push(dynamicTitle);
      dynamicFacts.forEach((fact) => lines.push("- " + fact));
      lines.push("");
    }
  }

  if (projectMemories.length > 0) {
    const projectTitle = isZh ? "### 项目记忆" : "### Project Memories";
    lines.push(projectTitle);
    projectMemories.slice(0, maxProjectItems).forEach((m) => {
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
      const similarity = Math.round(m.similarity * 100);
      lines.push("- [" + similarity + "%] " + m.content);
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
  
  try {
    projectMemories = await client.listMemories(projectTag, config.maxProjectMemories);
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

  const profileCount = profile 
    ? Math.min(profile.static.length, config.maxProfileItems) + Math.min(profile.dynamic.length, config.maxProfileItems)
    : 0;
  const projectCount = Math.min(projectMemories.length, config.maxProjectMemories);
  const userCount = Math.min(userMemories.length, config.maxMemories);
  const chunksCount = Math.min(projectChunks.length, config.maxChunks);

  const context = formatContext({
    profile,
    projectMemories,
    userMemories,
    projectChunks,
    locale,
    maxProfileItems: config.maxProfileItems,
    maxProjectItems: config.maxProjectMemories,
    maxUserItems: config.maxMemories,
    maxChunksItems: config.maxChunks,
  });

  return {
    context,
    profileCount,
    projectCount,
    userCount,
    chunksCount,
  };
}
