from typing import Dict, Any
from src.plugins.openclaw.client import OpenClawClient
from src.plugins.openclaw.tools import register_tools
from src.plugins.openclaw.hooks import recall_handler, capture_handler


def create_plugin(config: Dict[str, Any]):
    client = OpenClawClient(config)

    def register(api):
        if not config.get("apiKey"):
            api.logger.info("memory-recall: not configured - set apiKey")
            return

        register_tools(api, client, config)

        if config.get("autoRecall", True):

            @api.on("before_agent_start")
            async def handle_recall(event, ctx):
                return await recall_handler(client, config, event, ctx)

        if config.get("autoCapture", True):

            @api.on("agent_end")
            async def handle_capture(event, ctx):
                return await capture_handler(client, config, event, ctx)

        api.register_service(
            {
                "id": "memory-recall",
                "start": lambda: api.logger.info("memory-recall: connected"),
                "stop": lambda: api.logger.info("memory-recall: stopped"),
            }
        )

    return {
        "id": "memory-recall",
        "name": "Memory Recall",
        "kind": "memory",
        "register": register,
    }
