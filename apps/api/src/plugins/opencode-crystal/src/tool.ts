import { tool } from "@opencode-ai/plugin";
import type { ApiClientCrystal } from "./client";
import type { Config } from "./config";
import { stripPrivateTags, isFullyPrivate } from "./context";
import { TaskQueue } from "../../_shared/queue.ts";
import type { Task } from "../../_shared/queue.ts";
import { getAllKeywords } from "../../_shared/i18n.ts";

const MEMORY_TYPES = ["project-config","architecture","error-solution","preference","learned-pattern","conversation"] as const;

const toolSchema = {
  mode: tool.schema.enum(["add","search","profile","list","forget","confirm","correct","promote-scope","status","retry","help"]).describe("Operation mode"),
  content: tool.schema.string().optional().describe("Content to store (for add mode)"),
  query: tool.schema.string().optional().describe("Search query (for search mode)"),
  type: tool.schema.enum(MEMORY_TYPES).optional().describe("Memory type (for add mode)"),
  scope: tool.schema.enum(["user","project"]).optional().describe("Memory scope: user (cross-project) or project (current project)"),
  isStatic: tool.schema.boolean().optional().describe("Whether this is a permanent trait (default: false)"),
  memoryId: tool.schema.string().optional().describe("Memory/Claim ID to forget/confirm/correct"),
  claimId: tool.schema.string().optional().describe("Claim ID (alias for memoryId)"),
  newStatement: tool.schema.string().optional().describe("New statement for correct mode"),
  reason: tool.schema.string().optional().describe("Reason for correct/forget/promote-scope"),
  action: tool.schema.enum(["adopt","reject"]).optional().describe("Action for promote-scope"),
  limit: tool.schema.number().optional().describe("Max results (default: 10)"),
  taskId: tool.schema.string().optional().describe("Task ID to query or retry (for status/retry mode)"),
  enableMemoryGraph: tool.schema.boolean().optional().describe("Enable Memory Graph recall"),
  enableEntityGraph: tool.schema.boolean().optional().describe("Enable Entity Graph recall"),
  graphDepth: tool.schema.number().optional().describe("Graph traversal depth (default: 2, max: 5)"),
  graphNodes: tool.schema.number().optional().describe("Max nodes to traverse per graph (default: 5, max: 20)"),
};

type ToolArgs = {
  mode: "add"|"search"|"profile"|"list"|"forget"|"confirm"|"correct"|"promote-scope"|"status"|"retry"|"help";
  content?: string; query?: string; type?: typeof MEMORY_TYPES[number];
  scope?: "user"|"project"; isStatic?: boolean;
  memoryId?: string; claimId?: string; newStatement?: string; reason?: string; action?: "adopt"|"reject";
  limit?: number; taskId?: string;
  enableMemoryGraph?: boolean; enableEntityGraph?: boolean; graphDepth?: number; graphNodes?: number;
};

function resolveScope(args: ToolArgs, projectScope: string | null): string | null {
  if (args.scope === "user") return null;
  return projectScope;
}

function resolveClaimId(args: ToolArgs): string | undefined {
  return args.claimId ?? args.memoryId;
}

export function createTool(client: ApiClientCrystal, config: Config, taskQueue?: TaskQueue) {
  async function execute(args: ToolArgs, _ctx: { sessionID: string; messageID: string; agent: string; directory: string; worktree: string; abort: AbortSignal; metadata: (input: { title?: string; metadata?: Record<string, unknown> }) => void }): Promise<string> {
    try {
      const result = await executeMode(args);
      return JSON.stringify(result);
    } catch (e) {
      const error = e instanceof Error ? e.message : String(e);
      return JSON.stringify({ success: false, error });
    }
  }

  async function executeMode(args: ToolArgs): Promise<Record<string, unknown>> {
    const projectScope = client.getScope();
    switch (args.mode) {
      case "help":
        return { success: true, message: "Memory Recall (crystal) Usage", modes: { add: "Store evidence (POST /api/v2/evidence)", search: "Search claims (POST /api/v2/search)", profile: "View profile via context-inject preference", list: "List claims (GET workbench/claims)", forget: "Forget claim", confirm: "Confirm claim", correct: "Correct claim (user_correction Evidence → supersede)", "promote-scope": "Promote scope (adopt/reject)", status: "Queue status", retry: "Retry failed task" }, scopes: { user: "Cross-project (scope=NULL)", project: "This project (default)" }, types: MEMORY_TYPES };
      case "add": {
        const content = args.content;
        if (!content) return { success: false, error: "content required" };
        if (isFullyPrivate(content)) return { success: false, error: "Cannot store fully private content" };
        const sanitized = stripPrivateTags(content);
        const scope = resolveScope(args, projectScope);
        if (config.asyncQueue.enabled && taskQueue) {
          const taskId = taskQueue.enqueue("add", { content: sanitized, containerTag: scope ?? "", isStatic: args.isStatic ?? false, memoryType: args.type });
          return { success: true, message: "Evidence queued for async processing", taskId, scope: args.scope ?? "project", isStatic: args.isStatic ?? false, type: args.type };
        }
        const res = await client.addEvidence(sanitized, scope);
        return { success: true, message: "Evidence added to " + (args.scope ?? "project") + " scope", evidence_id: res.evidence_id, processing_state: res.processing_state, accepted: res.accepted, scope: args.scope ?? "project" };
      }
      case "search": {
        const query = args.query;
        if (!query) return { success: false, error: "query required" };
        const scope = args.scope !== undefined ? resolveScope(args, projectScope) : projectScope;
        const limit = args.limit || config.maxMemories;
        try {
          const res = await client.search(query, scope, { limit, include_explain: false, claim_kind: undefined });
          const results = (res.results || []).slice(0, limit).map((r) => ({ id: r.claim_id, claim_id: r.claim_id, content: r.statement, statement: r.statement, claim_kind: r.claim_kind, scope: r.scope, scores: r.scores }));
          return { success: true, query, count: results.length, results, breakdown: { claims: results.length } };
        } catch (e) { return { success: false, error: "Search failed: " + (e instanceof Error ? e.message : String(e)) }; }
      }
      case "profile": {
        const scope = null;
        try {
          const res = await client.contextInject(args.query ?? null, scope, { include_explain: false });
          return { success: true, profile: res.profile, memories: res.memories };
        } catch (e) { return { success: false, error: "Profile failed: " + (e instanceof Error ? e.message : String(e)) }; }
      }
      case "list": {
        const scope = args.scope !== undefined ? resolveScope(args, projectScope) : projectScope;
        const limit = args.limit || config.maxProjectMemories;
        const res = await client.listClaims({ scope, limit });
        const items = (res.items || []).map((c) => ({ id: c.claim_id, claim_id: c.claim_id, content: c.statement, statement: c.statement, claim_kind: c.claim_kind, scope: c.scope, status: c.status, createdAt: c.created_at }));
        return { success: true, scope: args.scope ?? "project", count: items.length, claims: items, memories: items, next_cursor: (res as Record<string, unknown>).next_cursor ?? null, has_more: (res as Record<string, unknown>).has_more ?? false };
      }
      case "forget": {
        const claimId = resolveClaimId(args);
        if (!claimId) return { success: false, error: "claimId (or memoryId) required" };
        await client.forgetClaim(claimId, args.reason);
        return { success: true, message: "Claim " + claimId + " forgotten (retract)" };
      }
      case "confirm": {
        const claimId = resolveClaimId(args);
        if (!claimId) return { success: false, error: "claimId required" };
        const res = await client.confirmClaim(claimId);
        return { success: true, message: "Claim " + claimId + " confirmed", data: res };
      }
      case "correct": {
        const claimId = resolveClaimId(args);
        if (!claimId) return { success: false, error: "claimId required" };
        if (!args.newStatement) return { success: false, error: "newStatement required" };
        const res = await client.correctClaim(claimId, args.newStatement, args.reason);
        return { success: true, message: "Claim " + claimId + " corrected", data: res };
      }
      case "promote-scope": {
        const claimId = resolveClaimId(args);
        if (!claimId) return { success: false, error: "claimId required" };
        if (!args.action) return { success: false, error: "action required (adopt|reject)" };
        const res = await client.promoteScope(claimId, args.action, args.reason);
        return { success: true, message: "Promote-scope " + args.action + " for " + claimId, data: res };
      }
      case "status": {
        if (!taskQueue) return { success: false, error: "Async queue is not enabled. Set 'asyncQueue.enabled: true' in config." };
        if (!args.taskId) {
          const all = taskQueue.getAllTasks();
          return { success: true, count: all.length, pending: all.filter(t=>t.status==="pending").length, running: all.filter(t=>t.status==="running").length, successCount: all.filter(t=>t.status==="success").length, failed: all.filter(t=>t.status==="failed").length, tasks: all.map(t=>({ id:t.id, type:t.type, status:t.status, retryCount:t.retryCount, createdAt:t.createdAt, error:t.error })) };
        }
        const t = taskQueue.getStatus(args.taskId);
        if (!t) return { success: false, error: "Task not found: " + args.taskId };
        return { success: true, task: { id:t.id, type:t.type, status:t.status, retryCount:t.retryCount, maxRetries:t.maxRetries, error:t.error, errorHistory:t.errorHistory, createdAt:t.createdAt, startedAt:t.startedAt, completedAt:t.completedAt } };
      }
      case "retry": {
        if (!taskQueue) return { success: false, error: "Async queue is not enabled. Set 'asyncQueue.enabled: true' in config." };
        if (!args.taskId) return { success: false, error: "taskId required for retry" };
        const ok = taskQueue.retry(args.taskId);
        if (!ok) return { success: false, error: "Cannot retry task. Task may not exist or not in failed status." };
        return { success: true, message: "Task requeued for execution", taskId: args.taskId };
      }
      default: return { success: false, error: "Unknown mode: " + (args as Record<string, unknown>).mode };
    }
  }

  return {
    "memory-recall": tool({
      description: "Manage persistent memory via crystal /api/v2. Modes: 'add'→evidence, 'search'→POST search, 'profile'→context-inject preference, 'list'→workbench claims, 'forget'→retract, 'confirm'/'correct'/'promote-scope'→workbench裁决, 'status'/'retry'→queue.",
      args: toolSchema,
      execute,
    }),
  };
}

export function detectMemoryKeyword(text: string): boolean {
  const keywords = getAllKeywords();
  const pattern = new RegExp(keywords.join("|"), "i");
  const withoutCode = text.replace(/```[\s\S]*?```/g, "").replace(/`[^`]+`/g, "");
  return pattern.test(withoutCode);
}
