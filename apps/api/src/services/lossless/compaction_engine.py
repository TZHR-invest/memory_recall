import uuid
from typing import Optional, List, Dict, Any, Tuple, Callable
from datetime import datetime
from dataclasses import dataclass

from src.database import db
from src.models.lossless import CompactionResult, CompressionLevel
from src.services.lossless.raw_message_store import RawMessageStore
from src.services.lossless.summary_store import SummaryStore
from src.services.lossless.context_store import ContextStore


FALLBACK_MAX_CHARS = 512 * 4
DEFAULT_LEAF_CHUNK_TOKENS = 20000
DEFAULT_FRESH_TAIL_COUNT = 8
DEFAULT_CONTEXT_THRESHOLD = 0.75


def estimate_tokens(text: str) -> int:
    return max(1, len(text) // 4)


def generate_summary_id(content: str) -> str:
    return f"sum_{uuid.uuid4().hex[:16]}"


def format_timestamp(value: datetime) -> str:
    return value.strftime("%Y-%m-%d %H:%M")


@dataclass
class ChunkSelection:
    items: List[Dict]
    total_tokens: int
    ordinals: List[int]


class CompactionEngine:
    def __init__(
        self,
        config: Optional[Dict[str, Any]] = None,
        raw_store: Optional[RawMessageStore] = None,
        summary_store: Optional[SummaryStore] = None,
        context_store: Optional[ContextStore] = None,
    ):
        self.config = config or {}
        self.raw_store = raw_store or RawMessageStore()
        self.summary_store = summary_store or SummaryStore()
        self.context_store = context_store or ContextStore()

    def _resolve_leaf_chunk_tokens(self) -> int:
        val = self.config.get("leaf_chunk_tokens", DEFAULT_LEAF_CHUNK_TOKENS)
        if isinstance(val, (int, float)) and val > 0:
            return int(val)
        return DEFAULT_LEAF_CHUNK_TOKENS

    def _resolve_fresh_tail_count(self) -> int:
        val = self.config.get("fresh_tail_count", DEFAULT_FRESH_TAIL_COUNT)
        if isinstance(val, (int, float)) and val >= 0:
            return int(val)
        return DEFAULT_FRESH_TAIL_COUNT

    def _resolve_context_threshold(self) -> float:
        val = self.config.get("context_threshold", DEFAULT_CONTEXT_THRESHOLD)
        if isinstance(val, (int, float)) and 0 < val <= 1:
            return float(val)
        return DEFAULT_CONTEXT_THRESHOLD

    async def evaluate(
        self,
        user_id: str,
        session_id: str,
        token_budget: int,
    ) -> Dict[str, Any]:
        current_tokens = await self.context_store.get_token_count(user_id, session_id)
        threshold = int(self._resolve_context_threshold() * token_budget)

        return {
            "should_compact": current_tokens > threshold,
            "reason": "threshold" if current_tokens > threshold else "none",
            "current_tokens": current_tokens,
            "threshold": threshold,
        }

    async def evaluate_leaf_trigger(
        self,
        user_id: str,
        session_id: str,
    ) -> Dict[str, Any]:
        raw_tokens_outside_tail = await self._count_raw_tokens_outside_tail(
            user_id, session_id
        )
        threshold = self._resolve_leaf_chunk_tokens()

        return {
            "should_compact": raw_tokens_outside_tail >= threshold,
            "raw_tokens_outside_tail": raw_tokens_outside_tail,
            "threshold": threshold,
        }

    async def leaf_compact(
        self,
        user_id: str,
        agent_id: Optional[str],
        session_id: str,
        summarize_fn: Callable[[str, bool], str],
        token_budget: int = 100000,
        force: bool = False,
        summary_model: Optional[str] = None,
    ) -> Optional[CompactionResult]:
        tokens_before = await self.context_store.get_token_count(user_id, session_id)
        threshold = int(self._resolve_context_threshold() * token_budget)

        if not force and tokens_before <= threshold:
            leaf_trigger = await self.evaluate_leaf_trigger(user_id, session_id)
            if not leaf_trigger["should_compact"]:
                return None

        chunk = await self._select_oldest_leaf_chunk(user_id, session_id)
        if not chunk.items:
            return None

        source_text = self._format_messages(chunk.items)
        summary_result = await self._summarize_with_escalation(
            source_text, summarize_fn
        )

        if not summary_result:
            return None

        summary_content, level = summary_result
        summary_id = await self._create_summary(
            user_id=user_id,
            agent_id=agent_id,
            content=summary_content,
            chunk=chunk,
            level=level,
            model=summary_model,
        )

        await self._update_context_items(
            user_id, agent_id, session_id, chunk.ordinals, summary_id
        )

        tokens_after = await self.context_store.get_token_count(user_id, session_id)

        return CompactionResult(
            action_taken=True,
            summary_id=summary_id,
            tokens_before=tokens_before,
            tokens_after=tokens_after,
            level=level,
        )

    async def _select_oldest_leaf_chunk(
        self,
        user_id: str,
        session_id: str,
    ) -> ChunkSelection:
        fresh_tail_count = self._resolve_fresh_tail_count()
        threshold = self._resolve_leaf_chunk_tokens()

        items = await self.context_store.get_context_items(user_id, session_id)

        message_items = [i for i in items if i.item_type == "message"]

        if not message_items:
            return ChunkSelection(items=[], total_tokens=0, ordinals=[])

        fresh_tail_ordinal = float("inf")
        if len(message_items) > fresh_tail_count:
            tail_start = len(message_items) - fresh_tail_count
            fresh_tail_ordinal = message_items[tail_start].ordinal

        chunk = []
        chunk_tokens = 0
        ordinals = []

        for item in message_items:
            if item.ordinal >= fresh_tail_ordinal:
                break

            if item.message_id is None:
                continue

            msg = await self.raw_store.get_by_id(item.message_id)
            if msg:
                chunk.append(
                    {
                        "ordinal": item.ordinal,
                        "message": msg,
                    }
                )
                chunk_tokens += msg.token_count
                ordinals.append(item.ordinal)

                if chunk_tokens >= threshold:
                    break

        return ChunkSelection(items=chunk, total_tokens=chunk_tokens, ordinals=ordinals)

    async def _count_raw_tokens_outside_tail(
        self,
        user_id: str,
        session_id: str,
    ) -> int:
        fresh_tail_count = self._resolve_fresh_tail_count()

        items = await self.context_store.get_context_items(user_id, session_id)
        message_items = [i for i in items if i.item_type == "message"]

        if not message_items:
            return 0

        fresh_tail_ordinal = float("inf")
        if len(message_items) > fresh_tail_count:
            tail_start = len(message_items) - fresh_tail_count
            fresh_tail_ordinal = message_items[tail_start].ordinal

        raw_tokens = 0
        for item in message_items:
            if item.ordinal >= fresh_tail_ordinal:
                break
            if item.message_id is None:
                continue

            msg = await self.raw_store.get_by_id(item.message_id)
            if msg:
                raw_tokens += msg.token_count

        return raw_tokens

    def _format_messages(self, chunk_items: List[Dict]) -> str:
        parts = []
        for item in chunk_items:
            msg = item["message"]
            timestamp = format_timestamp(msg.created_at) if msg.created_at else ""
            parts.append(f"[{timestamp}]\n{msg.content}")
        return "\n\n".join(parts)

    async def _summarize_with_escalation(
        self,
        source_text: str,
        summarize_fn: Callable[[str, bool], str],
    ) -> Optional[Tuple[str, CompressionLevel]]:
        source_text = source_text.strip()
        if not source_text:
            return ("[Truncated from 0 tokens]", "fallback")

        input_tokens = estimate_tokens(source_text)

        try:
            summary = summarize_fn(source_text, aggressive=False)
            summary = summary.strip() if summary else ""

            if summary and estimate_tokens(summary) < input_tokens:
                return (summary, "normal")

            if summary:
                aggressive_summary = summarize_fn(source_text, aggressive=True)
                aggressive_summary = (
                    aggressive_summary.strip() if aggressive_summary else ""
                )

                if (
                    aggressive_summary
                    and estimate_tokens(aggressive_summary) < input_tokens
                ):
                    return (aggressive_summary, "aggressive")

        except Exception:
            pass

        truncated = source_text[:FALLBACK_MAX_CHARS]
        return (f"{truncated}\n[Truncated from {input_tokens} tokens]", "fallback")

    async def _create_summary(
        self,
        user_id: str,
        agent_id: Optional[str],
        content: str,
        chunk: ChunkSelection,
        level: CompressionLevel,
        model: Optional[str] = None,
    ) -> str:
        summary_id = generate_summary_id(content)
        token_count = estimate_tokens(content)

        messages = [item["message"] for item in chunk.items]
        earliest_at = (
            min(m.created_at for m in messages if m.created_at) if messages else None
        )
        latest_at = (
            max(m.created_at for m in messages if m.created_at) if messages else None
        )
        source_message_token_count = sum(m.token_count for m in messages)

        summary_id = await self.summary_store.create_summary(
            user_id=user_id,
            agent_id=agent_id,
            content=content,
            kind="leaf",
            depth=0,
            token_count=token_count,
            earliest_at=earliest_at,
            latest_at=latest_at,
            source_message_token_count=source_message_token_count,
            model=model or "unknown",
            compression_level=level,
        )

        message_ids = [item["message"].id for item in chunk.items if item["message"].id]
        await self.summary_store.link_messages(summary_id, message_ids)

        return summary_id

    async def _update_context_items(
        self,
        user_id: str,
        agent_id: Optional[str],
        session_id: str,
        ordinals: List[int],
        summary_id: str,
    ) -> None:
        if not ordinals:
            return

        start_ordinal = min(ordinals)
        end_ordinal = max(ordinals)

        await self.context_store.replace_range_with_summary(
            user_id=user_id,
            session_id=session_id,
            start_ordinal=start_ordinal,
            end_ordinal=end_ordinal,
            summary_id=summary_id,
            agent_id=agent_id,
        )

    async def summarize_content(
        self,
        content: str,
        summarize_fn: Callable[[str, bool], str],
    ) -> Optional[str]:
        summary_result = await self._summarize_with_escalation(content, summarize_fn)
        if summary_result:
            return summary_result[0]
        return None


compaction_engine = CompactionEngine()
