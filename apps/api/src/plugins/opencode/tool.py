import json
from typing import Dict, Any, List, Optional
from src.plugins.opencode.client import OpenCodeClient
from src.plugins.opencode.context import (
    detect_memory_keyword,
    strip_private_tags,
    is_fully_private,
    format_context,
    MEMORY_NUDGE,
)


MEMORY_TYPES = [
    "project-config",
    "architecture",
    "error-solution",
    "preference",
    "learned-pattern",
    "conversation",
]


def create_tool(client: OpenCodeClient, config: Dict[str, Any]):
    def tool_schema():
        return {
            "name": "supermemory",
            "description": "Manage persistent memory system. Use 'search' to find memories, 'add' to store knowledge.",
            "parameters": {
                "type": "object",
                "properties": {
                    "mode": {
                        "type": "string",
                        "enum": ["add", "search", "profile", "list", "forget", "help"],
                        "description": "Operation mode",
                    },
                    "content": {
                        "type": "string",
                        "description": "Content to store (for add)",
                    },
                    "query": {"type": "string", "description": "Search query"},
                    "type": {
                        "type": "string",
                        "enum": MEMORY_TYPES,
                        "description": "Memory type (for add)",
                    },
                    "scope": {
                        "type": "string",
                        "enum": ["user", "project"],
                        "description": "Memory scope",
                    },
                    "memoryId": {
                        "type": "string",
                        "description": "Memory ID (for forget)",
                    },
                    "limit": {"type": "number", "description": "Max results"},
                },
            },
        }

    async def execute(args: Dict[str, Any], ctx: Dict[str, Any]) -> str:
        mode = args.get("mode", "help")
        directory = ctx.get("directory", "/default")
        git_email = ctx.get("gitEmail")

        user_tag = client.get_user_tag(git_email)
        project_tag = client.get_project_tag(directory)

        try:
            if mode == "help":
                return json.dumps(
                    {
                        "success": True,
                        "message": "Supermemory Usage Guide",
                        "modes": ["add", "search", "profile", "list", "forget"],
                        "scopes": {
                            "user": "Cross-project",
                            "project": "This project (default)",
                        },
                        "types": MEMORY_TYPES,
                    }
                )

            if mode == "add":
                content = args.get("content", "")
                if not content:
                    return json.dumps({"success": False, "error": "content required"})

                if is_fully_private(content):
                    return json.dumps(
                        {
                            "success": False,
                            "error": "Cannot store fully private content",
                        }
                    )

                sanitized = strip_private_tags(content)
                scope = args.get("scope", "project")
                container_tag = user_tag if scope == "user" else project_tag

                result = await client.add(
                    content=sanitized,
                    container_tag=container_tag,
                    memory_type=args.get("type"),
                )

                return json.dumps(
                    {
                        "success": True,
                        "id": result.get("id"),
                        "scope": scope,
                    }
                )

            if mode == "search":
                query = args.get("query", "")
                if not query:
                    return json.dumps({"success": False, "error": "query required"})

                scope = args.get("scope")
                limit = args.get("limit", 10)

                if scope == "user":
                    results = await client.search(query, user_tag, limit)
                elif scope == "project":
                    results = await client.search(query, project_tag, limit)
                else:
                    user_results = await client.search(query, user_tag, limit)
                    project_results = await client.search(query, project_tag, limit)
                    results = (user_results or []) + (project_results or [])

                return json.dumps(
                    {
                        "success": True,
                        "query": query,
                        "count": len(results),
                        "results": [
                            {
                                "id": r.get("id"),
                                "content": r.get("content"),
                                "similarity": int((r.get("similarity") or 0) * 100),
                            }
                            for r in results[:limit]
                        ],
                    }
                )

            if mode == "profile":
                profile = await client.profile(user_tag, args.get("query"))
                return json.dumps(
                    {
                        "success": True,
                        "profile": profile.get("profile", {}),
                    }
                )

            if mode == "list":
                scope = args.get("scope", "project")
                limit = args.get("limit", 20)
                container_tag = user_tag if scope == "user" else project_tag

                memories = await client.list_memories(container_tag, limit)
                return json.dumps(
                    {
                        "success": True,
                        "scope": scope,
                        "count": len(memories),
                        "memories": memories,
                    }
                )

            if mode == "forget":
                memory_id = args.get("memoryId")
                if not memory_id:
                    return json.dumps({"success": False, "error": "memoryId required"})

                await client.forget(memory_id)
                return json.dumps(
                    {"success": True, "message": f"Memory {memory_id} removed"}
                )

            return json.dumps({"success": False, "error": f"Unknown mode: {mode}"})

        except Exception as e:
            return json.dumps({"success": False, "error": str(e)})

    return {
        "schema": tool_schema,
        "execute": execute,
    }


async def handle_chat_message(
    client: OpenCodeClient,
    config: Dict[str, Any],
    input: Dict[str, Any],
    output: Dict[str, Any],
    injected_sessions: set,
):
    parts = output.get("parts", [])
    text_parts = [p for p in parts if p.get("type") == "text"]
    if not text_parts:
        return

    user_message = "\n".join(p.get("text", "") for p in text_parts)
    if not user_message.strip():
        return

    if detect_memory_keyword(user_message):
        nudge_part = {
            "id": f"prt_memory_nudge_{id(user_message)}",
            "sessionID": input.get("sessionID"),
            "type": "text",
            "text": MEMORY_NUDGE,
            "synthetic": True,
        }
        output["parts"].append(nudge_part)

    session_id = input.get("sessionID")
    if session_id in injected_sessions:
        return
    injected_sessions.add(session_id)

    directory = config.get("directory", "/default")
    git_email = config.get("gitEmail")

    user_tag = client.get_user_tag(git_email)
    project_tag = client.get_project_tag(directory)

    try:
        profile = await client.profile(user_tag, user_message)
        project_memories = await client.list_memories(
            project_tag, config.get("maxProjectMemories", 10)
        )
        user_memories = await client.search(
            user_message, user_tag, config.get("maxMemories", 5)
        )

        context = format_context(profile, project_memories, user_memories)
        if context:
            context_part = {
                "id": f"prt_memory_context_{id(user_message)}",
                "sessionID": session_id,
                "type": "text",
                "text": context,
                "synthetic": True,
            }
            output["parts"].insert(0, context_part)
    except Exception:
        pass
