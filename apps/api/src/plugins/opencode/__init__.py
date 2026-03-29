from typing import Dict, Any, Set
from src.plugins.opencode.client import OpenCodeClient
from src.plugins.opencode.tool import create_tool, handle_chat_message


def create_plugin(config: Dict[str, Any]):
    client = OpenCodeClient(config)
    injected_sessions: Set[str] = set()

    def register(ctx):
        if not config.get("apiKey"):
            return

        tool = create_tool(client, config)

        ctx.tool("supermemory", tool["schema"], tool["execute"])

        @ctx.hook("chat.message")
        async def on_chat_message(input_data, output_data):
            await handle_chat_message(
                client=client,
                config=config,
                input=input_data,
                output=output_data,
                injected_sessions=injected_sessions,
            )

    return {
        "id": "memory-recall-opencode",
        "name": "Memory Recall for OpenCode",
        "register": register,
    }
