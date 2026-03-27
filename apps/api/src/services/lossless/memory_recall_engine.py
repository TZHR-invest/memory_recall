from typing import Dict, Any, List, Optional, Callable
from dataclasses import dataclass
from datetime import datetime

from src.database import db
from src.models.lossless import CompactionResult
from src.services.lossless.raw_message_store import RawMessageStore, raw_message_store
from src.services.lossless.summary_store import SummaryStore, summary_store
from src.services.lossless.context_store import ContextStore, context_store
from src.services.lossless.compaction_engine import CompactionEngine, compaction_engine


@dataclass
class ContextEngineInfo:
    id: str = "memory-recall"
    name: str = "Memory Recall Engine"
    version: str = "3.0.0"
    owns_compaction: bool = True


@dataclass
class AgentMessage:
    role: str
    content: str


class MemoryRecallEngine:
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or {}
        self.info = ContextEngineInfo()

        self.raw_store = raw_message_store
        self.summary_store = summary_store
        self.context_store = context_store
        self.compaction_engine = compaction_engine

        self._entity_extractor = None

    @property
    def entity_extractor(self):
        if self._entity_extractor is None:
            from src.services.memory_extraction_service import (
                get_memory_extraction_service,
            )

            self._entity_extractor = get_memory_extraction_service()
        return self._entity_extractor

    async def bootstrap(self, params: Dict) -> Dict:
        user_id = params["user_id"]
        agent_id = params.get("agent_id")
        session_id = params["session_id"]

        exists = await self.context_store.exists(user_id, session_id)

        if not exists:
            await self._load_history_to_context(user_id, agent_id, session_id)

        return {"status": "ready"}

    async def ingest(self, params: Dict) -> Dict:
        user_id = params["user_id"]
        agent_id = params.get("agent_id")
        session_id = params.get("session_id")
        message = params["message"]

        content = self._extract_content(message)
        role = message.get("role", "user")

        memory_type = "dialogue" if agent_id else "preference"
        raw_id = await self.raw_store.store(
            user_id=user_id,
            agent_id=agent_id,
            session_id=session_id,
            memory_type=memory_type,
            role=role,
            content=content,
        )

        if session_id:
            await self.context_store.append_message(
                user_id, session_id, raw_id, agent_id
            )

        compaction_triggered = False
        if session_id:
            should_compact = await self._should_compact(user_id, session_id)
            if should_compact:
                compaction_triggered = True

        return {
            "raw_message_id": raw_id,
            "compaction_triggered": compaction_triggered,
        }

    async def assemble(self, params: Dict) -> Dict:
        user_id = params["user_id"]
        agent_id = params.get("agent_id")
        session_id = params["session_id"]
        token_budget = params.get("token_budget", 100000)
        fresh_tail_count = self.config.get("fresh_tail_count", 8)

        items = await self.context_store.get_context_items(
            user_id, session_id, agent_id
        )

        if not items:
            return {"messages": [], "estimated_tokens": 0}

        tail_start = max(0, len(items) - fresh_tail_count)
        evictable = items[:tail_start]
        fresh_tail = items[tail_start:]

        tail_tokens = await self._count_tokens(fresh_tail)
        remaining_budget = token_budget - tail_tokens

        selected = []
        if remaining_budget > 0:
            selected = await self._select_within_budget(evictable, remaining_budget)

        final_items = selected + fresh_tail

        messages = await self._resolve_to_messages(final_items)
        estimated_tokens = await self._count_tokens(final_items)

        system_prompt = await self._build_system_prompt(final_items)

        return {
            "messages": messages,
            "estimated_tokens": estimated_tokens,
            "system_prompt_addition": system_prompt,
        }

    async def compact(self, params: Dict) -> Dict:
        user_id = params["user_id"]
        agent_id = params.get("agent_id")
        session_id = params["session_id"]
        token_budget = params.get("token_budget", 100000)
        force = params.get("force", False)
        summarize_fn = params.get("summarize_fn")

        if not summarize_fn:
            return {
                "action_taken": False,
                "tokens_before": 0,
                "tokens_after": 0,
                "summary_id": None,
            }

        entity_extractor = self.entity_extractor if agent_id else None

        result = await self.compaction_engine.leaf_compact(
            user_id=user_id,
            agent_id=agent_id,
            session_id=session_id,
            summarize_fn=summarize_fn,
            token_budget=token_budget,
            force=force,
            entity_extractor=entity_extractor,
        )

        if result:
            return {
                "action_taken": result.action_taken,
                "tokens_before": result.tokens_before,
                "tokens_after": result.tokens_after,
                "summary_id": result.summary_id,
            }

        return {
            "action_taken": False,
            "tokens_before": 0,
            "tokens_after": 0,
            "summary_id": None,
        }

    async def afterTurn(self, params: Dict) -> None:
        pass

    async def dispose(self) -> None:
        pass

    async def recall(
        self,
        query: str,
        user_id: str,
        agent_id: Optional[str] = None,
        scope: str = "all",
        limit: int = 20,
    ) -> List[Dict]:
        return await self._hybrid_recall(query, user_id, agent_id, scope, limit)

    async def expand(self, summary_id: str, max_tokens: int = 5000) -> List[Dict]:
        return await self._expand_node(summary_id, max_tokens)

    def _extract_content(self, message: Dict) -> str:
        if isinstance(message, dict):
            return message.get("content", "")
        return str(message)

    async def _load_history_to_context(
        self, user_id: str, agent_id: Optional[str], session_id: str
    ) -> None:
        if agent_id:
            messages = await self.raw_store.get_by_agent(user_id, agent_id)
        else:
            messages = await self.raw_store.get_user_preferences(user_id)

        for msg in messages:
            if msg.session_id == session_id:
                await self.context_store.append_message(
                    user_id, session_id, msg.id, agent_id
                )

    async def _should_compact(self, user_id: str, session_id: str) -> bool:
        token_budget = self.config.get("token_budget", 100000)
        result = await self.compaction_engine.evaluate(
            user_id, session_id, token_budget
        )
        return result["should_compact"]

    async def _count_tokens(self, items: List) -> int:
        total = 0
        for item in items:
            if item.item_type == "message" and item.message_id:
                msg = await self.raw_store.get_by_id(item.message_id)
                if msg:
                    total += msg.token_count
            elif item.item_type == "summary" and item.summary_id:
                summary = await self.summary_store.get_summary(item.summary_id)
                if summary:
                    total += summary.token_count
        return total

    async def _select_within_budget(self, items: List, budget: int) -> List:
        selected = []
        used = 0

        for item in items:
            tokens = 0
            if item.item_type == "message" and item.message_id:
                msg = await self.raw_store.get_by_id(item.message_id)
                if msg:
                    tokens = msg.token_count
            elif item.item_type == "summary" and item.summary_id:
                summary = await self.summary_store.get_summary(item.summary_id)
                if summary:
                    tokens = summary.token_count

            if used + tokens <= budget:
                selected.append(item)
                used += tokens
            else:
                break

        return selected

    async def _resolve_to_messages(self, items: List) -> List[AgentMessage]:
        messages = []
        for item in items:
            if item.item_type == "message" and item.message_id:
                msg = await self.raw_store.get_by_id(item.message_id)
                if msg:
                    messages.append(
                        AgentMessage(
                            role=msg.role,
                            content=msg.content,
                        )
                    )
            elif item.item_type == "summary" and item.summary_id:
                summary = await self.summary_store.get_summary(item.summary_id)
                if summary:
                    messages.append(
                        AgentMessage(
                            role="system",
                            content=f"[历史摘要]\n{summary.content}",
                        )
                    )
        return messages

    async def _build_system_prompt(self, items: List) -> str:
        summary_items = [i for i in items if i.item_type == "summary"]
        if not summary_items:
            return ""

        parts = []
        for item in summary_items:
            if item.summary_id:
                summary = await self.summary_store.get_summary(item.summary_id)
                if summary:
                    parts.append(summary.content)

        if parts:
            return f"[历史上下文摘要]\n{' | '.join(parts)}"
        return ""

    async def _hybrid_recall(
        self, query: str, user_id: str, agent_id: Optional[str], scope: str, limit: int
    ) -> List[Dict]:
        results = []

        if scope == "manual_only":
            agent_filter = "agent_id IS NULL"
        elif scope == "agent_only" and agent_id:
            agent_filter = f"agent_id = '{agent_id}'"
        else:
            if agent_id:
                agent_filter = f"(agent_id IS NULL OR agent_id = '{agent_id}')"
            else:
                agent_filter = "agent_id IS NULL"

        raw_results = await db.fetch(
            f"""
            SELECT id, content, agent_id, memory_type, created_at
            FROM raw_messages
            WHERE user_id = $1 AND {agent_filter}
            ORDER BY created_at DESC
            LIMIT {limit}
        """,
            user_id,
        )

        for r in raw_results:
            results.append(
                {
                    "type": "raw_message",
                    "id": r["id"],
                    "content": r["content"],
                    "agent_id": r["agent_id"],
                    "memory_type": r["memory_type"],
                    "source": "recall",
                    "expandable": False,
                }
            )

        return results

    async def _expand_node(self, summary_id: str, max_tokens: int) -> List[Dict]:
        summary = await self.summary_store.get_summary(summary_id)
        if not summary:
            return []

        message_ids = await self.summary_store.get_summary_messages(summary_id)

        results = []
        total_tokens = 0

        for msg_id in message_ids:
            msg = await self.raw_store.get_by_id(msg_id)
            if msg:
                if total_tokens + msg.token_count > max_tokens:
                    break
                results.append(
                    {
                        "type": "raw_message",
                        "id": msg.id,
                        "content": msg.content,
                        "role": msg.role,
                        "created_at": msg.created_at.isoformat()
                        if msg.created_at
                        else None,
                    }
                )
                total_tokens += msg.token_count

        return results


memory_recall_engine = MemoryRecallEngine()
