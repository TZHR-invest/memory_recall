import { tool } from "@opencode-ai/plugin";
import { z } from "zod";
import type { ApiClient, SearchResult } from "./client";
import type { Config } from "./config";
import { stripPrivateTags, isFullyPrivate } from "./context";

const MEMORY_TYPES = [
  "project-config",
  "architecture",
  "error-solution",
  "preference",
  "learned-pattern",
  "conversation",
] as const;

const toolSchema = {
  mode: z.enum(["add", "search", "profile", "list", "forget", "help"]).describe("Operation mode"),
  content: z.string().optional().describe("Content to store (for add mode)"),
  query: z.string().optional().describe("Search query (for search mode)"),
  type: z.enum(MEMORY_TYPES).optional().describe("Memory type (for add mode)"),
  scope: z.enum(["user", "project"]).optional().describe("Memory scope: user (cross-project) or project (current project)"),
  isStatic: z.boolean().optional().describe("Whether this is a permanent trait (default: false)"),
  memoryId: z.string().optional().describe("Memory ID to forget (for forget mode)"),
  limit: z.number().optional().describe("Max results (default: 10)"),
};

type ToolArgs = {
  mode: "add" | "search" | "profile" | "list" | "forget" | "help";
  content?: string;
  query?: string;
  type?: typeof MEMORY_TYPES[number];
  scope?: "user" | "project";
  isStatic?: boolean;
  memoryId?: string;
  limit?: number;
};

interface SearchWithScope extends SearchResult {
  scope?: string;
}

export function createTool(client: ApiClient, config: Config) {
  async function execute(args: ToolArgs, context: { sessionID: string; messageID: string; agent: string; directory: string; worktree: string; abort: AbortSignal; metadata: (input: { title?: string; metadata?: Record<string, unknown> }) => void }): Promise<string> {
    const mode = args.mode;

    try {
      const result = await executeMode(mode, args);
      return JSON.stringify(result);
    } catch (e) {
      const error = e instanceof Error ? e.message : String(e);
      return JSON.stringify({ success: false, error });
    }
  }

  async function executeMode(mode: string, args: ToolArgs): Promise<Record<string, unknown>> {
    const userTag = client.getUserTag();
    const projectTag = client.getProjectTag();

    switch (mode) {
      case "help":
        return {
          success: true,
          message: "Memory Recall Usage Guide",
          modes: {
            add: "Store a new memory",
            search: "Search memories",
            profile: "View user profile",
            list: "List recent memories",
            forget: "Remove a memory",
          },
          scopes: {
            user: "Cross-project",
            project: "This project (default)",
          },
          types: MEMORY_TYPES,
        };

      case "add": {
        const content = args.content;
        if (!content) {
          return { success: false, error: "content required" };
        }

        if (isFullyPrivate(content)) {
          return { success: false, error: "Cannot store fully private content" };
        }

        const sanitized = stripPrivateTags(content);
        const scope = args.scope || "project";
        const containerTag = scope === "user" ? userTag : projectTag;
        const isStatic = args.isStatic || false;
        const memoryType = args.type;

        const memory = await client.addMemory(sanitized, containerTag, isStatic, memoryType);

        return {
          success: true,
          message: "Memory added to " + scope + " scope",
          id: memory.id,
          scope,
          isStatic,
          type: memoryType,
        };
      }

      case "search": {
        const query = args.query;
        if (!query) {
          return { success: false, error: "query required" };
        }

        const scope = args.scope;
        const limit = args.limit || config.maxMemories;

        let results: SearchWithScope[];
        if (scope === "user") {
          results = await client.search(query, userTag, limit);
        } else if (scope === "project") {
          results = await client.search(query, projectTag, limit);
        } else {
          const [userResults, projectResults] = await Promise.all([
            client.search(query, userTag, limit),
            client.search(query, projectTag, limit),
          ]);
          results = [
            ...userResults.map((r): SearchWithScope => ({ ...r, scope: "user" })),
            ...projectResults.map((r): SearchWithScope => ({ ...r, scope: "project" })),
          ].sort((a, b) => b.similarity - a.similarity);
        }

        const formatted = results.slice(0, limit).map((r) => ({
          id: r.id,
          content: r.content,
          similarity: Math.round(r.similarity * 100),
          scope: r.scope,
        }));

        return {
          success: true,
          query,
          count: formatted.length,
          results: formatted,
        };
      }

      case "profile": {
        const query = args.query;
        const response = await client.getProfile(userTag, query);
        return {
          success: true,
          profile: response.profile,
        };
      }

      case "list": {
        const scope = args.scope || "project";
        const limit = args.limit || config.maxProjectMemories;
        const containerTag = scope === "user" ? userTag : projectTag;

        const memories = await client.listMemories(containerTag, limit);

        return {
          success: true,
          scope,
          count: memories.length,
          memories: memories.map((m) => ({
            id: m.id,
            content: m.content,
            isStatic: m.is_static,
            createdAt: m.created_at,
          })),
        };
      }

      case "forget": {
        const memoryId = args.memoryId;
        if (!memoryId) {
          return { success: false, error: "memoryId required" };
        }

        await client.forgetMemory(memoryId);

        return {
          success: true,
          message: "Memory " + memoryId + " removed",
        };
      }

      default:
        return { success: false, error: "Unknown mode: " + mode };
    }
  }

  return {
    "memory-recall": tool({
      description: "Manage persistent memory across sessions. Use 'search' to find relevant memories, 'add' to store new knowledge, 'profile' to view user profile, 'list' to see recent memories, 'forget' to remove a memory.",
      args: toolSchema,
      execute,
    }),
  };
}

export function detectMemoryKeyword(text: string): boolean {
  const keywords = [
    "remember", "save this", "don't forget", "note that", "keep in mind",
    "important", "for future reference", "crucial", "essential", "vital",
    "remember", "memorize", "save this", "note this", "learn this",
    "remember that", "never forget", "always remember",
    "remember", "remember this", "don't forget", "don't forget this", "note down", "note down this",
    "save this", "very important", "attention", "record this", "memo",
    "future reference", "this is key", "key information",
    "important", "must remember",
  ];
  const pattern = new RegExp(keywords.join("|"), "i");
  const textWithoutCode = text.replace(/```[\s\S]*?```/g, "").replace(/`[^`]+`/g, "");
  return pattern.test(textWithoutCode);
}
