/**
 * memory-recall-dsh 工具注册
 *
 * 提供 5 个模型可用工具：memory_store / memory_search / memory_profile /
 * memory_list / memory_forget。全部 fail-open：调用失败返回 {success:false}，
 * 不抛异常打断 agent 循环。容器 tag 按调用方 agent 的会话 cwd 推导（多项目并存时
 * 各 agent 各归其位）。
 */
import { defineTool } from "@deepseek-ai/dsh-tools";
import { MEMORY_TYPES } from "./config.js";

const TEXT = (text) => ({ type: "text", text });

const resultSchema = (extra = {}) => ({
  type: "object",
  additionalProperties: false,
  properties: {
    success: { type: "boolean", required: true },
    message: { type: "string", required: true },
    ...extra,
  },
});

/** 单条记忆展示行 */
function formatMemoryRow(item) {
  const content = item.content ?? "";
  let line = `- ${content}`;
  if (typeof item.similarity === "number") {
    line += ` [${Math.round(item.similarity * 100)}%]`;
  }
  return line;
}

/**
 * 注册全部记忆工具。
 * @param ctx - cordis context（须注入 tools 服务）
 * @param deps - { client, config, resolveTags(agent) }
 */
export function registerTools(ctx, { client, config, resolveTags }) {
  const call = async (exec, fn) => {
    const tags = await resolveTags(exec?.agent ?? null);
    if (!tags) {
      return { success: false, message: "Memory Recall 未配置（缺 API Key 或未验证）" };
    }
    try {
      return await fn(tags);
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      ctx.logger?.warn?.("[memory-recall-dsh] 工具调用失败: %s", message);
      return { success: false, message: `Memory Recall 调用失败: ${message}` };
    }
  };

  ctx.tools.register(defineTool({
    name: "memory_store",
    description: "把一条信息存入长期记忆（后端自动提取实体、检测关系；type=preference 自动归为永久特征）。用于保存用户偏好、项目约束、技术决策、踩坑经验等跨会话有用的信息。",
    parameters: {
      content: {
        type: "string",
        required: true,
        description: "要记住的信息内容（简洁、一句话以内）",
      },
      scope: {
        type: "string",
        enum: ["project", "user"],
        description: "作用域：project=当前项目（默认，项目隔离），user=跨项目（用户级）",
      },
      type: {
        type: "string",
        enum: MEMORY_TYPES,
        description: "记忆类型（preference 会自动存为永久特征）",
      },
      isStatic: {
        type: "boolean",
        description: "是否为永久特征（默认 false；type=preference 时自动 true）",
      },
      containerTag: {
        type: "string",
        description: "容器 tag 覆盖（一般不需要）",
      },
    },
    output: {
      schema: resultSchema({
        id: { type: "string" },
        container_tag: { type: "string" },
      }),
      render: (_args, value) => [TEXT(value.message)],
    },
    execute(args, exec) {
      return call(exec, async (tags) => {
        const content = String(args.content).trim();
        if (!content) return { success: false, message: "content 不能为空" };
        const scope = args.scope ?? "project";
        const containerTag = args.containerTag ?? (scope === "user" ? tags.user : tags.project);
        const isStatic = args.isStatic === true || args.type === "preference";
        const memory = await client.addMemory(content, containerTag, {
          isStatic,
          type: args.type ?? null,
        }, exec?.signal);
        return {
          success: true,
          message: `已保存记忆（${memory.id}，容器 ${memory.container_tag}）`,
          id: memory.id,
          container_tag: memory.container_tag,
        };
      });
    },
    presentCall: (args) => ({
      card: "generic",
      title: "Store memory",
      kind: "other",
      rawInput: args.content,
    }),
  }));

  ctx.tools.register(defineTool({
    name: "memory_search",
    description: "语义搜索长期记忆，返回与查询最相关的记忆条目（含相似度）。了解项目历史、用户偏好、之前讨论过的决策前先调用它。",
    parameters: {
      query: {
        type: "string",
        required: true,
        description: "搜索查询（用自然语言描述想找的信息）",
      },
      limit: {
        type: "number",
        description: "返回条数上限（默认 5，最大 20）",
      },
      containerTag: {
        type: "string",
        description: "容器 tag 覆盖（默认当前项目容器）",
      },
    },
    output: {
      schema: resultSchema({
        results: {
          type: "array",
          items: {
            type: "object",
            additionalProperties: true,
            properties: {
              id: { type: "string" },
              content: { type: "string" },
              similarity: { type: "number" },
            },
          },
        },
      }),
      render: (_args, value) => [TEXT(value.message)],
    },
    execute(args, exec) {
      return call(exec, async (tags) => {
        const limit = Math.min(Math.max(Number(args.limit) || 5, 1), 20);
        const containerTag = args.containerTag ?? tags.project;
        const response = await client.search(String(args.query), containerTag, {
          limit,
          threshold: config.similarityThreshold,
        }, exec?.signal);
        const results = Array.isArray(response.results) ? response.results : [];
        if (results.length === 0) {
          return { success: true, message: "没有找到相关记忆。", results: [] };
        }
        const message = `找到 ${results.length} 条相关记忆：\n${results.map(formatMemoryRow).join("\n")}`;
        return {
          success: true,
          message,
          results: results.map((r) => ({
            id: r.id,
            content: r.content,
            similarity: r.similarity,
          })),
        };
      });
    },
    presentCall: (args) => ({
      card: "generic",
      title: "Search memories",
      kind: "other",
      rawInput: args.query,
    }),
  }));

  ctx.tools.register(defineTool({
    name: "memory_profile",
    description: "获取用户画像摘要：永久特征（偏好、习惯、规则）与近期动态。需要了解用户是谁、有什么偏好约束时调用。",
    parameters: {
      query: {
        type: "string",
        description: "可选查询：聚焦画像中的某一方面",
      },
      containerTag: {
        type: "string",
        description: "容器 tag 覆盖（默认用户级容器）",
      },
    },
    output: {
      schema: resultSchema({
        profile: {
          type: "object",
          additionalProperties: true,
          properties: {
            static: { type: "array", items: { type: "string" } },
            dynamic: { type: "array", items: { type: "string" } },
          },
        },
      }),
      render: (_args, value) => [TEXT(value.message)],
    },
    execute(args, exec) {
      return call(exec, async (tags) => {
        const containerTag = args.containerTag ?? tags.user;
        const response = await client.profile(containerTag, args.query ?? null, exec?.signal);
        const staticItems = response?.profile?.static ?? [];
        const dynamicItems = response?.profile?.dynamic ?? [];
        const sections = [];
        if (staticItems.length > 0) {
          sections.push(`永久特征（${staticItems.length}）:\n${staticItems.map((s) => `- ${s}`).join("\n")}`);
        }
        if (dynamicItems.length > 0) {
          sections.push(`近期动态（${dynamicItems.length}）:\n${dynamicItems.map((d) => `- ${d}`).join("\n")}`);
        }
        const message = sections.length > 0 ? sections.join("\n\n") : "画像为空，暂无已记录的用户特征。";
        return { success: true, message, profile: { static: staticItems, dynamic: dynamicItems } };
      });
    },
    presentCall: () => ({
      card: "generic",
      title: "Read user profile",
      kind: "other",
      rawInput: null,
    }),
  }));

  ctx.tools.register(defineTool({
    name: "memory_list",
    description: "列出当前项目（或指定容器）最近的记忆条目，用于浏览已记住了什么。",
    parameters: {
      limit: {
        type: "number",
        description: "条数上限（默认 20，最大 50）",
      },
      containerTag: {
        type: "string",
        description: "容器 tag 覆盖（默认当前项目容器）",
      },
    },
    output: {
      schema: resultSchema({
        memories: {
          type: "array",
          items: {
            type: "object",
            additionalProperties: true,
            properties: {
              id: { type: "string" },
              content: { type: "string" },
              created_at: { type: "string" },
            },
          },
        },
      }),
      render: (_args, value) => [TEXT(value.message)],
    },
    execute(args, exec) {
      return call(exec, async (tags) => {
        const limit = Math.min(Math.max(Number(args.limit) || 20, 1), 50);
        const containerTag = args.containerTag ?? tags.project;
        const response = await client.listMemories(containerTag, limit, exec?.signal);
        const memories = Array.isArray(response.memories) ? response.memories : [];
        if (memories.length === 0) {
          return { success: true, message: "暂无记忆。", memories: [] };
        }
        const message = `最近 ${memories.length} 条记忆：\n${memories.map((m) => `- ${m.content ?? ""}`).join("\n")}`;
        return { success: true, message, memories };
      });
    },
    presentCall: () => ({
      card: "generic",
      title: "List memories",
      kind: "other",
      rawInput: null,
    }),
  }));

  ctx.tools.register(defineTool({
    name: "memory_forget",
    description: "删除一条记忆（按记忆 ID，可用 memory_search / memory_list 获取）。用于纠正错误或过时的记忆。",
    parameters: {
      memoryId: {
        type: "string",
        required: true,
        description: "要删除的记忆 ID",
      },
      containerTag: {
        type: "string",
        description: "容器 tag 覆盖（默认当前项目容器，仅供校验）",
      },
    },
    output: {
      schema: resultSchema(),
      render: (_args, value) => [TEXT(value.message)],
    },
    execute(args, exec) {
      return call(exec, async () => {
        if (!args.memoryId) return { success: false, message: "memoryId 不能为空" };
        await client.forgetMemory(String(args.memoryId), exec?.signal);
        return { success: true, message: `已删除记忆 ${args.memoryId}` };
      });
    },
    presentCall: (args) => ({
      card: "generic",
      title: "Forget memory",
      kind: "other",
      rawInput: args.memoryId,
    }),
  }));
}
