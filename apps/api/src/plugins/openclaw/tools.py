from typing import Dict, Any
from src.plugins.openclaw.client import OpenClawClient


def register_tools(api, client: OpenClawClient, config: Dict[str, Any]):
    @api.tool(
        name="memory_store",
        description="Save information to long-term memory.",
        parameters={
            "type": "object",
            "properties": {
                "content": {
                    "type": "string",
                    "description": "Information to remember",
                },
                "containerTag": {
                    "type": "string",
                    "description": "Optional container tag for isolation",
                },
            },
            "required": ["content"],
        },
    )
    async def memory_store(tool_call_id: str, params: Dict[str, Any]) -> Dict[str, Any]:
        content = params["content"]
        container_tag = params.get("containerTag", client.container_tag)

        result = await client.store(content=content, container_tag=container_tag)

        preview = content[:80] + "..." if len(content) > 80 else content
        return {"content": [{"type": "text", "text": f'Stored: "{preview}"'}]}

    @api.tool(
        name="memory_search",
        description="Search through long-term memories for relevant information.",
        parameters={
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search query",
                },
                "limit": {
                    "type": "number",
                    "description": "Max results (default: 5)",
                },
                "containerTag": {
                    "type": "string",
                    "description": "Optional container tag",
                },
            },
            "required": ["query"],
        },
    )
    async def memory_search(
        tool_call_id: str, params: Dict[str, Any]
    ) -> Dict[str, Any]:
        query = params["query"]
        limit = params.get("limit", 5)
        container_tag = params.get("containerTag", client.container_tag)

        results = await client.search(
            query=query, limit=limit, container_tag=container_tag
        )

        if not results:
            return {
                "content": [{"type": "text", "text": "No relevant memories found."}]
            }

        lines = []
        for i, r in enumerate(results, 1):
            content = r.get("content", "")
            score = r.get("similarity", 0)
            pct = f" ({int(score * 100)}%)" if score else ""
            lines.append(f"{i}. {content}{pct}")

        return {
            "content": [
                {
                    "type": "text",
                    "text": f"Found {len(results)} memories:\n\n" + "\n".join(lines),
                }
            ]
        }

    @api.tool(
        name="memory_profile",
        description="Get a summary of what is known about the user.",
        parameters={
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Optional query to focus the profile",
                },
                "containerTag": {
                    "type": "string",
                    "description": "Optional container tag",
                },
            },
        },
    )
    async def memory_profile(
        tool_call_id: str, params: Dict[str, Any]
    ) -> Dict[str, Any]:
        query = params.get("query")
        container_tag = params.get("containerTag", client.container_tag)

        profile = await client.profile(query=query, container_tag=container_tag)

        static_facts = profile.get("profile", {}).get("static", [])
        dynamic_facts = profile.get("profile", {}).get("dynamic", [])

        if not static_facts and not dynamic_facts:
            return {
                "content": [
                    {"type": "text", "text": "No profile information available yet."}
                ]
            }

        sections = []
        if static_facts:
            sections.append(
                "## User Profile (Persistent)\n"
                + "\n".join(f"- {f}" for f in static_facts)
            )
        if dynamic_facts:
            sections.append(
                "## Recent Context\n" + "\n".join(f"- {f}" for f in dynamic_facts)
            )

        return {"content": [{"type": "text", "text": "\n\n".join(sections)}]}

    @api.tool(
        name="memory_forget",
        description="Delete a memory by ID.",
        parameters={
            "type": "object",
            "properties": {
                "memoryId": {
                    "type": "string",
                    "description": "Memory ID to forget",
                },
                "containerTag": {
                    "type": "string",
                    "description": "Optional container tag",
                },
            },
            "required": ["memoryId"],
        },
    )
    async def memory_forget(
        tool_call_id: str, params: Dict[str, Any]
    ) -> Dict[str, Any]:
        memory_id = params["memoryId"]
        container_tag = params.get("containerTag", client.container_tag)

        result = await client.forget(memory_id=memory_id, container_tag=container_tag)

        return {"content": [{"type": "text", "text": f"Memory {memory_id} forgotten."}]}
