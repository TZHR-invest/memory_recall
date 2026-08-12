import { tool } from "@opencode-ai/plugin";
import * as path from "path";
import type { ApiClient, SearchResult } from "./client";
import type { Config } from "./config";
import { stripPrivateTags, isFullyPrivate } from "./context";
import type { DocumentTracker } from "./document-tracker";
import { TaskQueue, type Task, type TaskExecutor } from "./queue";
import { getAllKeywords } from "./i18n";

const MEMORY_TYPES = [
  "project-config",
  "architecture",
  "error-solution",
  "preference",
  "learned-pattern",
  "conversation",
] as const;

const toolSchema = {
  mode: tool.schema.enum(["add", "search", "profile", "list", "forget", "import-docs", "status", "retry", "help"]).describe("Operation mode"),
  content: tool.schema.string().optional().describe("Content to store (for add mode)"),
  query: tool.schema.string().optional().describe("Search query (for search mode)"),
  type: tool.schema.enum(MEMORY_TYPES).optional().describe("Memory type (for add mode)"),
  scope: tool.schema.enum(["user", "project"]).optional().describe("Memory scope: user (cross-project) or project (current project)"),
  isStatic: tool.schema.boolean().optional().describe("Whether this is a permanent trait (default: false)"),
  memoryId: tool.schema.string().optional().describe("Memory ID to forget (for forget mode)"),
  limit: tool.schema.number().optional().describe("Max results (default: 10)"),
  force: tool.schema.boolean().optional().describe("Force re-import all documents (for import-docs mode)"),
  taskId: tool.schema.string().optional().describe("Task ID to query or retry (for status/retry mode)"),
  // 图谱召回增强参数（search mode）
  enableMemoryGraph: tool.schema.boolean().optional().describe("Enable Memory Graph recall - traverses memory evolution relations (updates/extends/derives)"),
  enableEntityGraph: tool.schema.boolean().optional().describe("Enable Entity Graph recall - traverses entity relations (friend/colleague/works_at etc.)"),
  graphDepth: tool.schema.number().optional().describe("Graph traversal depth (default: 2, max: 5)"),
  graphNodes: tool.schema.number().optional().describe("Max nodes to traverse per graph (default: 5, max: 20)"),
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
  // 图谱召回增强参数
  enableMemoryGraph?: boolean;
  enableEntityGraph?: boolean;
  graphDepth?: number;
  graphNodes?: number;
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
        
        // 默认启用 Memory Graph 召回，获取关联记忆
        // 用户可显式设置 enableMemoryGraph=false 禁用
        const enableMemoryGraph = args.enableMemoryGraph ?? true;
        const enableEntityGraph = args.enableEntityGraph ?? false;
        
        const graphDepth = Math.min(args.graphDepth ?? config.graphMaxDepth, 5);
        const graphNodes = Math.min(args.graphNodes ?? config.graphMaxNodes, 20);
        
        try {
          const effectiveUserTag = scope === "project" ? projectTag : userTag;
          const effectiveProjectTag = scope === "user" ? userTag : projectTag;
          
          const response = await client.injectContext(
            effectiveUserTag,
            effectiveProjectTag,
            query,
            {
              enable_memory_graph: enableMemoryGraph,
              enable_entity_graph: enableEntityGraph,
              memory_graph_depth: graphDepth,
              memory_graph_nodes: graphNodes,
              entity_graph_depth: graphDepth,
              entity_graph_nodes: graphNodes,
              max_memories: limit,
              max_chunks: limit,
              inject_profile: false,
              enable_semantic_dedup: true,
              dedup_threshold: 0.85,
            }
          );
          
          const memoryResults = response.sources.memories.slice(0, limit).map((m) => ({
            id: m.id,
            content: m.content,
            type: "memory",
            scope: scope,
          }));
          
          const userMemoryResults = (response.sources.user_memories || []).slice(0, limit).map((m) => ({
            id: m.id,
            content: m.content,
            type: "memory",
            scope: scope === "project" ? "project" : "user",
          }));
          
          const chunkResults = (response.sources.chunks || []).slice(0, limit).map((c) => ({
            id: c.id,
            content: c.content,
            type: "document",
            scope: scope,
          }));
          
          // 后端 _build_sources_with_tags 恒返回 user_chunks=[]（用户文档已并入 chunks 桶），
          // 故不单独合并 userChunkResults
          const allResults = [
            ...memoryResults,
            ...userMemoryResults,
            ...chunkResults,
          ];
          
          return {
            success: true,
            query,
            count: allResults.length,
            results: allResults,
            breakdown: {
              memories: memoryResults.length + userMemoryResults.length,
              documents: chunkResults.length,
            },
            graphRecall: {
              enabled: enableMemoryGraph || enableEntityGraph,
              memoryGraph: enableMemoryGraph,
              entityGraph: enableEntityGraph,
              depth: graphDepth,
              nodes: graphNodes,
            },
            stats: {
              totalItems: response.stats.total_items,
              afterDedup: response.stats.after_dedup,
              dedupedCount: response.stats.deduped_count,
            },
          };
        } catch (e) {
          const error = e instanceof Error ? e.message : String(e);
          return { success: false, error: "Search failed: " + error };
        }
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
      description: "Manage persistent memory across sessions. Modes: 'search' - find relevant memories (supports graph recall via enableMemoryGraph/enableEntityGraph), 'add' - store new knowledge, 'profile' - view user profile, 'list' - see recent memories, 'forget' - remove a memory, 'import-docs' - import project documents (README, docs/*.md, AGENTS.md), 'help' - show usage guide.",
      args: toolSchema,
      execute,
    }),
  };
}

export function detectMemoryKeyword(text: string): boolean {
  const keywords = getAllKeywords();
  const pattern = new RegExp(keywords.join("|"), "i");
  const textWithoutCode = text.replace(/```[\s\S]*?```/g, "").replace(/`[^`]+`/g, "");
  return pattern.test(textWithoutCode);
}
