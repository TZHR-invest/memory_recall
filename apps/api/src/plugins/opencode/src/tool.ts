import { tool } from "@opencode-ai/plugin";
import { z } from "zod";
import * as path from "path";
import type { ApiClient, SearchResult } from "./client";
import type { Config } from "./config";
import { stripPrivateTags, isFullyPrivate } from "./context";
import type { DocumentTracker } from "./document-tracker";
import { TaskQueue, type Task, type TaskExecutor } from "./queue";

const MEMORY_TYPES = [
  "project-config",
  "architecture",
  "error-solution",
  "preference",
  "learned-pattern",
  "conversation",
] as const;

const toolSchema = {
  mode: z.enum(["add", "search", "profile", "list", "forget", "import-docs", "status", "retry", "help"]).describe("Operation mode"),
  content: z.string().optional().describe("Content to store (for add mode)"),
  query: z.string().optional().describe("Search query (for search mode)"),
  type: z.enum(MEMORY_TYPES).optional().describe("Memory type (for add mode)"),
  scope: z.enum(["user", "project"]).optional().describe("Memory scope: user (cross-project) or project (current project)"),
  isStatic: z.boolean().optional().describe("Whether this is a permanent trait (default: false)"),
  memoryId: z.string().optional().describe("Memory ID to forget (for forget mode)"),
  limit: z.number().optional().describe("Max results (default: 10)"),
  force: z.boolean().optional().describe("Force re-import all documents (for import-docs mode)"),
  taskId: z.string().optional().describe("Task ID to query or retry (for status/retry mode)"),
};

type ToolArgs = {
  mode: "add" | "search" | "profile" | "list" | "forget" | "import-docs" | "status" | "retry" | "help";
  content?: string;
  query?: string;
  type?: typeof MEMORY_TYPES[number];
  scope?: "user" | "project";
  isStatic?: boolean;
  memoryId?: string;
  limit?: number;
  force?: boolean;
  taskId?: string;
};

interface SearchWithScope extends SearchResult {
  scope?: string;
}

export function createTool(client: ApiClient, config: Config, documentTracker: DocumentTracker | null, taskQueue?: TaskQueue) {
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
            "import-docs": "Import project documents (README, docs/*.md, etc.)",
            status: "Query async task status",
            retry: "Retry a failed task",
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

        // 如果启用异步队列，使用队列
        if (config.asyncQueue.enabled && taskQueue) {
          const taskId = taskQueue.enqueue("add", {
            content: sanitized,
            containerTag,
            isStatic,
            memoryType,
          });

          return {
            success: true,
            message: "Memory queued for async processing",
            taskId,
            scope,
            isStatic,
            type: memoryType,
          };
        }

        // 同步模式（默认）
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

      case "import-docs": {
        if (!documentTracker) {
          return { success: false, error: "Document tracking is disabled. Enable 'enableDocumentTracking' in config." };
        }

        const force = args.force || false;

        // 如果启用异步队列，批量入队每个文档
        if (config.asyncQueue.enabled && taskQueue) {
          // force 模式：清除状态，重新导入所有文档
          if (force) {
            documentTracker.clearState();
          }

          const pendingFiles = documentTracker.getPendingFiles();
          
          if (pendingFiles.length === 0) {
            return {
              success: true,
              message: "No new documents to import",
              queuedCount: 0,
              patterns: config.trackedDocPatterns,
            };
          }

          // 批量入队
          const taskIds: string[] = [];
          for (const filePath of pendingFiles) {
            const relativePath = path.relative(documentTracker.getDirectory(), filePath);
            const taskId = taskQueue.enqueue("import-doc", {
              filePath,
              relativePath,
            });
            taskIds.push(taskId);
          }

          return {
            success: true,
            message: `${taskIds.length} documents queued for async processing`,
            queuedCount: taskIds.length,
            taskIds,
            patterns: config.trackedDocPatterns,
          };
        }

        // 同步模式（默认）
        if (force) {
          documentTracker.clearState();
        }

        const importedCount = await documentTracker.scanAndMemorize();
        const trackedDocs = documentTracker.getTrackedDocuments();

        return {
          success: true,
          message: force ? "Force re-imported documents" : "Scanned and imported documents",
          importedCount,
          totalTracked: trackedDocs.length,
          patterns: config.trackedDocPatterns,
        };
      }

      case "status": {
        const taskId = args.taskId;
        
        if (!taskQueue) {
          return { success: false, error: "Async queue is not enabled. Set 'asyncQueue.enabled: true' in config." };
        }

        // 如果没有 taskId，返回所有任务
        if (!taskId) {
          const allTasks = taskQueue.getAllTasks();
          return {
            success: true,
            count: allTasks.length,
            pending: allTasks.filter(t => t.status === "pending").length,
            running: allTasks.filter(t => t.status === "running").length,
            successCount: allTasks.filter(t => t.status === "success").length,
            failed: allTasks.filter(t => t.status === "failed").length,
            tasks: allTasks.map(t => ({
              id: t.id,
              type: t.type,
              status: t.status,
              retryCount: t.retryCount,
              createdAt: t.createdAt,
              error: t.error,
            })),
          };
        }

        // 查询单个任务
        const task = taskQueue.getStatus(taskId);
        if (!task) {
          return { success: false, error: "Task not found: " + taskId };
        }

        return {
          success: true,
          task: {
            id: task.id,
            type: task.type,
            status: task.status,
            retryCount: task.retryCount,
            maxRetries: task.maxRetries,
            error: task.error,
            errorHistory: task.errorHistory,
            createdAt: task.createdAt,
            startedAt: task.startedAt,
            completedAt: task.completedAt,
          },
        };
      }

      case "retry": {
        const taskId = args.taskId;
        
        if (!taskQueue) {
          return { success: false, error: "Async queue is not enabled. Set 'asyncQueue.enabled: true' in config." };
        }

        if (!taskId) {
          return { success: false, error: "taskId required for retry" };
        }

        const success = taskQueue.retry(taskId);
        if (!success) {
          return { success: false, error: "Cannot retry task. Task may not exist or not in failed status." };
        }

        return {
          success: true,
          message: "Task requeued for execution",
          taskId,
        };
      }

      default:
        return { success: false, error: "Unknown mode: " + mode };
    }
  }

  return {
    "memory-recall": tool({
      description: "Manage persistent memory across sessions. Modes: 'search' - find relevant memories, 'add' - store new knowledge, 'profile' - view user profile, 'list' - see recent memories, 'forget' - remove a memory, 'import-docs' - import project documents (README, docs/*.md, AGENTS.md), 'help' - show usage guide.",
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
