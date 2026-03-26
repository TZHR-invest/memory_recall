import logging
from typing import List, Dict, Any, Optional
from datetime import datetime

from src.database import db
from src.services.lossless.summary_store import SummaryStore
from src.services.lossless.raw_message_store import RawMessageStore

logger = logging.getLogger(__name__)


class DAGExpandService:
    def __init__(
        self,
        summary_store: Optional[SummaryStore] = None,
        raw_store: Optional[RawMessageStore] = None,
    ):
        self.summary_store = summary_store or SummaryStore()
        self.raw_store = raw_store or RawMessageStore()

    async def expand_node(
        self,
        summary_id: str,
        max_tokens: int = 5000,
        max_depth: int = 10,
    ) -> Dict[str, Any]:
        summary = await self.summary_store.get_summary(summary_id)
        if not summary:
            return {"error": f"Summary not found: {summary_id}"}

        nodes = await self._collect_nodes(summary_id, max_depth)
        nodes = self._sort_by_depth(nodes)

        result_nodes = []
        total_tokens = 0

        for node in nodes:
            if total_tokens >= max_tokens:
                break

            node_data = await self._build_node_data(node)
            if node_data:
                result_nodes.append(node_data)
                total_tokens += node_data.get("token_count", 0)

        return {
            "root_summary_id": summary_id,
            "nodes": result_nodes,
            "total_nodes": len(result_nodes),
            "total_tokens": total_tokens,
        }

    async def expand_to_messages(
        self,
        summary_id: str,
        max_tokens: int = 5000,
    ) -> Dict[str, Any]:
        summary = await self.summary_store.get_summary(summary_id)
        if not summary:
            return {"error": f"Summary not found: {summary_id}"}

        message_ids = await self._collect_all_message_ids(summary_id)

        messages = []
        total_tokens = 0

        for msg_id in message_ids:
            if total_tokens >= max_tokens:
                break

            msg = await self.raw_store.get_by_id(msg_id)
            if msg:
                messages.append(
                    {
                        "id": msg.id,
                        "content": msg.content,
                        "role": msg.role,
                        "token_count": msg.token_count,
                        "created_at": msg.created_at.isoformat()
                        if msg.created_at
                        else None,
                    }
                )
                total_tokens += msg.token_count

        return {
            "summary_id": summary_id,
            "messages": messages,
            "total_messages": len(messages),
            "total_tokens": total_tokens,
        }

    async def get_summary_tree(
        self,
        summary_id: str,
        max_depth: int = 5,
    ) -> Dict[str, Any]:
        summary = await self.summary_store.get_summary(summary_id)
        if not summary:
            return {"error": f"Summary not found: {summary_id}"}

        tree = await self._build_tree(summary_id, 0, max_depth)
        return tree

    async def _collect_nodes(
        self,
        summary_id: str,
        max_depth: int,
        visited: Optional[set] = None,
    ) -> List[Dict]:
        if visited is None:
            visited = set()

        if summary_id in visited or max_depth <= 0:
            return []

        visited.add(summary_id)

        summary = await self.summary_store.get_summary(summary_id)
        if not summary:
            return []

        nodes = [{"summary": summary, "depth": 0}]

        parents = await self.summary_store.get_summary_parents(summary_id)
        for parent in parents:
            if parent.summary_id and parent.summary_id not in visited:
                child_nodes = await self._collect_nodes(
                    parent.summary_id, max_depth - 1, visited
                )
                for cn in child_nodes:
                    cn["depth"] += 1
                nodes.extend(child_nodes)

        return nodes

    def _sort_by_depth(self, nodes: List[Dict]) -> List[Dict]:
        return sorted(nodes, key=lambda x: x["depth"])

    async def _build_node_data(self, node: Dict) -> Optional[Dict[str, Any]]:
        summary = node["summary"]
        depth = node["depth"]

        message_ids = await self.summary_store.get_summary_messages(summary.summary_id)

        return {
            "summary_id": summary.summary_id,
            "content": summary.content,
            "kind": summary.kind,
            "depth": summary.depth,
            "tree_depth": depth,
            "token_count": summary.token_count,
            "message_count": len(message_ids),
            "created_at": summary.created_at.isoformat()
            if summary.created_at
            else None,
        }

    async def _collect_all_message_ids(
        self,
        summary_id: str,
        visited: Optional[set] = None,
    ) -> List[str]:
        if visited is None:
            visited = set()

        if summary_id in visited:
            return []

        visited.add(summary_id)

        direct_message_ids = await self.summary_store.get_summary_messages(summary_id)

        parent_summaries = await self.summary_store.get_summary_parents(summary_id)
        for parent in parent_summaries:
            if parent.summary_id:
                parent_messages = await self._collect_all_message_ids(
                    parent.summary_id, visited
                )
                direct_message_ids.extend(parent_messages)

        return direct_message_ids

    async def _build_tree(
        self,
        summary_id: str,
        current_depth: int,
        max_depth: int,
    ) -> Dict[str, Any]:
        summary = await self.summary_store.get_summary(summary_id)
        if not summary:
            return {}

        message_ids = await self.summary_store.get_summary_messages(summary_id)

        tree = {
            "summary_id": summary.summary_id,
            "content": summary.content,
            "kind": summary.kind,
            "depth": summary.depth,
            "token_count": summary.token_count,
            "message_count": len(message_ids),
            "children": [],
        }

        if current_depth < max_depth:
            parents = await self.summary_store.get_summary_parents(summary_id)
            for parent in parents:
                if parent.summary_id:
                    child_tree = await self._build_tree(
                        parent.summary_id, current_depth + 1, max_depth
                    )
                    if child_tree:
                        tree["children"].append(child_tree)

        return tree


dag_expand_service = DAGExpandService()
