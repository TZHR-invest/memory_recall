"""
上下文注入服务
统一处理用户画像、记忆、文档片段的获取和语义去重
"""

from typing import Dict, Any, List, Optional

from src.database import db
from src.services.core.semantic_dedup_service import (
    semantic_dedup_service,
    DedupItem,
    SOURCE_PRIORITY,
)
from src.services.core.profile_service import profile_service
from src.services.core.memory_store import memory_store
from src.services.core.document_store import document_store
from src.embedding.client import get_embedding_client


class ContextInjectService:
    async def inject(
        self,
        container_tag: str,
        query: Optional[str],
        config: Dict[str, Any],
    ) -> Dict[str, Any]:
        profile = await self._get_profile(container_tag, config)
        memories = await self._get_memories(container_tag, query, config)
        chunks = await self._get_chunks(container_tag, query, config)

        all_items = self._collect_items(profile, memories, chunks)

        if config.get("enable_semantic_dedup", True):
            deduped_items = await semantic_dedup_service.deduplicate(
                all_items,
                threshold=config.get("dedup_threshold", 0.85),
            )
        else:
            deduped_items = all_items

        context = self._format_context(deduped_items, config.get("language", "auto"))

        sources = self._build_sources(profile, memories, chunks, deduped_items)
        stats = self._build_stats(all_items, deduped_items)

        return {
            "context": context,
            "sources": sources,
            "stats": stats,
        }

    async def inject_with_tags(
        self,
        user_tag: str,
        project_tag: str,
        query: Optional[str],
        config: Dict[str, Any],
    ) -> Dict[str, Any]:
        profile = await self._get_profile(user_tag, config)
        user_memories = await self._get_memories(user_tag, query, config)
        project_memories = await self._get_memories(project_tag, query, config)
        user_chunks = await self._get_chunks(user_tag, query, config)
        project_chunks = await self._get_chunks(project_tag, query, config)

        all_items = self._collect_items_with_tags(
            profile, user_memories, project_memories, user_chunks, project_chunks
        )

        if config.get("enable_semantic_dedup", True):
            deduped_items = await semantic_dedup_service.deduplicate(
                all_items,
                threshold=config.get("dedup_threshold", 0.85),
            )
        else:
            deduped_items = all_items

        context = self._format_context_with_tags(
            deduped_items, config.get("language", "auto")
        )

        sources = self._build_sources_with_tags(
            profile,
            user_memories,
            project_memories,
            user_chunks,
            project_chunks,
            deduped_items,
        )
        stats = self._build_stats_with_tags(all_items, deduped_items)

        return {
            "context": context,
            "sources": sources,
            "stats": stats,
        }

    async def _get_profile(
        self,
        container_tag: str,
        config: Dict[str, Any],
    ) -> Dict[str, List[str]]:
        if not config.get("inject_profile", True):
            return {"static": [], "dynamic": []}

        try:
            profile_data = await profile_service.get_profile(container_tag)
            profile = profile_data.get("profile", {})
            return {
                "static": profile.get("static", [])[
                    : config.get("max_profile_items", 10)
                ],
                "dynamic": profile.get("dynamic", [])[
                    : config.get("max_profile_items", 10)
                ],
            }
        except Exception:
            return {"static": [], "dynamic": []}

    async def _get_memories(
        self,
        container_tag: str,
        query: Optional[str],
        config: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        try:
            enable_memory_graph = config.get("enable_memory_graph", True)
            enable_entity_graph = config.get("enable_entity_graph", True)
            max_memories = config.get("max_memories", 5)

            all_memories = []
            seen_ids = set()

            if query:
                embedding_client = get_embedding_client()
                query_embedding = await embedding_client.embed(query)

                if query_embedding:
                    search_results = await memory_store.search(
                        query=query,
                        container_tag=container_tag,
                        limit=max_memories,
                        threshold=config.get("memory_similarity_threshold", 0.3),
                    )

                    for r in search_results:
                        mem_id = r.get("id")
                        if mem_id and mem_id not in seen_ids:
                            seen_ids.add(mem_id)
                            all_memories.append(
                                {
                                    "id": mem_id,
                                    "content": r.get("content", ""),
                                    "embedding": r.get("embedding"),
                                    "is_static": False,
                                    "similarity": r.get("similarity", 0.0),
                                }
                            )

                    if enable_memory_graph and all_memories:
                        memory_graph_depth = config.get("memory_graph_depth", 2)
                        memory_graph_nodes = config.get("memory_graph_nodes", 3)

                        for mem in all_memories[:3]:
                            try:
                                related = await memory_store.traverse_memory_relations(
                                    memory_id=mem["id"],
                                    max_depth=memory_graph_depth,
                                    max_nodes=memory_graph_nodes,
                                )
                                for m in related:
                                    if m.id not in seen_ids:
                                        seen_ids.add(m.id)
                                        all_memories.append(
                                            {
                                                "id": m.id,
                                                "content": m.content,
                                                "embedding": m.embedding,
                                                "is_static": m.is_static,
                                                "source": "memory_graph",
                                            }
                                        )
                            except Exception:
                                pass

                    if enable_entity_graph and all_memories:
                        entity_graph_depth = config.get("entity_graph_depth", 2)
                        entity_graph_nodes = config.get("entity_graph_nodes", 3)

                        try:
                            memory_ids = [m["id"] for m in all_memories]
                            entities = await memory_store.get_entities_for_memories(
                                memory_ids
                            )

                            if entities:
                                related_entities = []
                                for entity in entities[:5]:
                                    try:
                                        related = await memory_store.traverse_entity_relations(
                                            entity_id=entity.id,
                                            max_depth=entity_graph_depth,
                                            max_nodes=entity_graph_nodes,
                                            container_tag=container_tag,
                                        )
                                        related_entities.extend(related)
                                    except Exception:
                                        pass

                                if related_entities:
                                    entity_ids = list(
                                        set(e.id for e in related_entities)
                                    )
                                    entity_memories = (
                                        await memory_store.find_memories_by_entities(
                                            entity_ids=entity_ids,
                                            container_tag=container_tag,
                                            limit=max_memories,
                                        )
                                    )

                                    for m in entity_memories:
                                        if m.id not in seen_ids:
                                            seen_ids.add(m.id)
                                            all_memories.append(
                                                {
                                                    "id": m.id,
                                                    "content": m.content,
                                                    "embedding": m.embedding,
                                                    "is_static": m.is_static,
                                                    "source": "entity_graph",
                                                }
                                            )
                        except Exception:
                            pass

            if len(all_memories) < max_memories:
                recent_memories = await memory_store.get_by_container(
                    container_tag=container_tag,
                    limit=max_memories * 2,
                )

                for m in recent_memories:
                    # 过滤 Session Summary（会话摘要由 compaction hook 单独注入）
                    if m.content.startswith(
                        "[Session Summary]"
                    ) or m.content.startswith("[会话摘要]"):
                        continue

                    if m.id not in seen_ids:
                        seen_ids.add(m.id)
                        all_memories.append(
                            {
                                "id": m.id,
                                "content": m.content,
                                "embedding": m.embedding,
                                "is_static": m.is_static,
                            }
                        )

                    if len(all_memories) >= max_memories * 2:
                        break

            return all_memories[: max_memories * 2]
        except Exception:
            return []

    async def _get_chunks(
        self,
        container_tag: str,
        query: Optional[str],
        config: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        if not query:
            return []

        if not config.get("enable_chunks_search", True):
            return []

        try:
            from src.embedding.client import get_embedding_client

            embedding_client = get_embedding_client()
            query_embedding = await embedding_client.embed(query)

            if query_embedding is None:
                return []

            chunks = await document_store.search_chunks(
                query_embedding=query_embedding,
                container_tag=container_tag,
                limit=config.get("max_chunks", 3),
                threshold=config.get("chunks_similarity_threshold", 0.3),
            )

            results = []
            for c in chunks:
                chunk = c.get("chunk")
                if chunk:
                    results.append(
                        {
                            "id": getattr(chunk, "id", None),
                            "content": getattr(chunk, "content", ""),
                            "embedding": getattr(chunk, "embedding", None),
                            "document_id": c.get("document_id"),
                            "title": c.get("title"),
                            "source": c.get("source"),
                            "similarity": c.get("similarity", 0.0),
                        }
                    )
            return results
        except Exception:
            return []

    def _collect_items(
        self,
        profile: Dict[str, List[str]],
        memories: List[Dict[str, Any]],
        chunks: List[Dict[str, Any]],
    ) -> List[DedupItem]:
        items = []

        for fact in profile.get("static", []):
            items.append(
                DedupItem(
                    content=fact,
                    source="profile",
                    priority=SOURCE_PRIORITY["profile"],
                )
            )

        for fact in profile.get("dynamic", []):
            items.append(
                DedupItem(
                    content=fact,
                    source="profile",
                    priority=SOURCE_PRIORITY["profile"],
                )
            )

        for m in memories:
            items.append(
                DedupItem(
                    content=m.get("content", ""),
                    source="userMemory",
                    priority=SOURCE_PRIORITY["userMemory"],
                    embedding=m.get("embedding"),
                    id=m.get("id"),
                )
            )

        for c in chunks:
            content = c.get("content", "")
            title = c.get("title")
            source = c.get("source")

            if title or source:
                source_info = f" [{title or '未知'}"
                if source:
                    source_info += f" | {source}"
                source_info += "]"
                content = f"{content}{source_info}"

            items.append(
                DedupItem(
                    content=content,
                    source="chunk",
                    priority=SOURCE_PRIORITY["chunk"],
                    embedding=c.get("embedding"),
                    id=c.get("id"),
                )
            )

        return items

    def _collect_items_with_tags(
        self,
        profile: Dict[str, List[str]],
        user_memories: List[Dict[str, Any]],
        project_memories: List[Dict[str, Any]],
        user_chunks: List[Dict[str, Any]],
        project_chunks: List[Dict[str, Any]],
    ) -> List[DedupItem]:
        items = []

        for fact in profile.get("static", []):
            items.append(
                DedupItem(
                    content=fact,
                    source="profile",
                    priority=SOURCE_PRIORITY["profile"],
                )
            )

        for fact in profile.get("dynamic", []):
            items.append(
                DedupItem(
                    content=fact,
                    source="profile",
                    priority=SOURCE_PRIORITY["profile"],
                )
            )

        for m in project_memories:
            items.append(
                DedupItem(
                    content=m.get("content", ""),
                    source="projectMemory",
                    priority=SOURCE_PRIORITY["projectMemory"],
                    embedding=m.get("embedding"),
                    id=m.get("id"),
                )
            )

        for m in user_memories:
            items.append(
                DedupItem(
                    content=m.get("content", ""),
                    source="userMemory",
                    priority=SOURCE_PRIORITY["userMemory"],
                    embedding=m.get("embedding"),
                    id=m.get("id"),
                )
            )

        for c in project_chunks:
            content = c.get("content", "")
            title = c.get("title")
            source = c.get("source")

            if title or source:
                source_info = f" [{title or '未知'}"
                if source:
                    source_info += f" | {source}"
                source_info += "]"
                content = f"{content}{source_info}"

            items.append(
                DedupItem(
                    content=content,
                    source="chunk",
                    priority=SOURCE_PRIORITY["chunk"],
                    embedding=c.get("embedding"),
                    id=c.get("id"),
                )
            )

        for c in user_chunks:
            content = c.get("content", "")
            title = c.get("title")
            source = c.get("source")

            if title or source:
                source_info = f" [{title or '未知'}"
                if source:
                    source_info += f" | {source}"
                source_info += "]"
                content = f"{content}{source_info}"

            items.append(
                DedupItem(
                    content=content,
                    source="chunk",
                    priority=SOURCE_PRIORITY["chunk"],
                    embedding=c.get("embedding"),
                    id=c.get("id"),
                )
            )

        return items

    def _format_context(
        self,
        items: List[DedupItem],
        language: str,
    ) -> str:
        is_zh = language == "zh_CN" or (
            language == "auto" and self._detect_chinese(items)
        )

        lines = []
        lines.append("## 用户上下文" if is_zh else "## User Context")
        lines.append("")

        profile_items = [i for i in items if i.source == "profile"]
        memory_items = [i for i in items if i.source in ("userMemory", "projectMemory")]
        chunk_items = [i for i in items if i.source == "chunk"]

        if profile_items:
            lines.append("### 永久特征" if is_zh else "### Static Facts")
            for item in profile_items:
                lines.append(f"- {item.content}")
            lines.append("")

        if memory_items:
            lines.append("### 相关记忆" if is_zh else "### Related Memories")
            for item in memory_items:
                lines.append(f"- {item.content}")
            lines.append("")

        if chunk_items:
            lines.append("### 项目文档" if is_zh else "### Project Documents")
            for item in chunk_items:
                lines.append(f"- {item.content}")
            lines.append("")

        if len(lines) <= 3:
            return ""

        return "\n".join(lines)

    def _format_context_with_tags(
        self,
        items: List[DedupItem],
        language: str,
    ) -> str:
        is_zh = language == "zh_CN" or (
            language == "auto" and self._detect_chinese(items)
        )

        lines = []
        lines.append("## 用户上下文" if is_zh else "## User Context")
        lines.append("")

        profile_items = [i for i in items if i.source == "profile"]
        project_memory_items = [i for i in items if i.source == "projectMemory"]
        user_memory_items = [i for i in items if i.source == "userMemory"]
        chunk_items = [i for i in items if i.source == "chunk"]

        if profile_items:
            lines.append("### 永久特征" if is_zh else "### Static Facts")
            for item in profile_items:
                lines.append(f"- {item.content}")
            lines.append("")

        if project_memory_items:
            lines.append("### 项目记忆" if is_zh else "### Project Memories")
            for item in project_memory_items:
                lines.append(f"- {item.content}")
            lines.append("")

        if user_memory_items:
            lines.append("### 用户记忆" if is_zh else "### User Memories")
            for item in user_memory_items:
                lines.append(f"- {item.content}")
            lines.append("")

        if chunk_items:
            lines.append("### 项目文档" if is_zh else "### Project Documents")
            for item in chunk_items:
                lines.append(f"- {item.content}")
            lines.append("")

        if len(lines) <= 3:
            return ""

        return "\n".join(lines)

    def _detect_chinese(self, items: List[DedupItem]) -> bool:
        for item in items:
            chinese_chars = sum(1 for c in item.content if "\u4e00" <= c <= "\u9fff")
            if chinese_chars / len(item.content) > 0.3:
                return True
        return False

    def _build_sources(
        self,
        profile: Dict[str, List[str]],
        memories: List[Dict[str, Any]],
        chunks: List[Dict[str, Any]],
        deduped_items: List[DedupItem],
    ) -> Dict[str, Any]:
        return {
            "profile": profile.get("static", []) + profile.get("dynamic", []),
            "memories": [
                {"id": m.get("id"), "content": m.get("content")} for m in memories
            ],
            "chunks": [
                {"id": c.get("id"), "content": c.get("content")} for c in chunks
            ],
        }

    def _build_sources_with_tags(
        self,
        profile: Dict[str, List[str]],
        user_memories: List[Dict[str, Any]],
        project_memories: List[Dict[str, Any]],
        user_chunks: List[Dict[str, Any]],
        project_chunks: List[Dict[str, Any]],
        deduped_items: List[DedupItem],
    ) -> Dict[str, Any]:
        return {
            "profile": profile.get("static", []) + profile.get("dynamic", []),
            "memories": [
                {"id": m.get("id"), "content": m.get("content")}
                for m in project_memories
            ],
            "user_memories": [
                {"id": m.get("id"), "content": m.get("content")} for m in user_memories
            ],
            "chunks": [
                {"id": c.get("id"), "content": c.get("content")} for c in project_chunks
            ],
            "user_chunks": [
                {"id": c.get("id"), "content": c.get("content")} for c in user_chunks
            ],
        }

    def _build_stats(
        self,
        all_items: List[DedupItem],
        deduped_items: List[DedupItem],
    ) -> Dict[str, int]:
        memories_count = len(
            [i for i in deduped_items if i.source in ("userMemory", "projectMemory")]
        )
        return {
            "total_items": len(all_items),
            "after_dedup": len(deduped_items),
            "deduped_count": len(all_items) - len(deduped_items),
            "profile_count": len([i for i in deduped_items if i.source == "profile"]),
            "memories_count": memories_count,
            "project_memories_count": len(
                [i for i in deduped_items if i.source == "projectMemory"]
            ),
            "user_memories_count": len(
                [i for i in deduped_items if i.source == "userMemory"]
            ),
            "chunks_count": len([i for i in deduped_items if i.source == "chunk"]),
        }

    def _build_stats_with_tags(
        self,
        all_items: List[DedupItem],
        deduped_items: List[DedupItem],
    ) -> Dict[str, int]:
        return {
            "total_items": len(all_items),
            "after_dedup": len(deduped_items),
            "deduped_count": len(all_items) - len(deduped_items),
            "profile_count": len([i for i in deduped_items if i.source == "profile"]),
            "project_memories_count": len(
                [i for i in deduped_items if i.source == "projectMemory"]
            ),
            "user_memories_count": len(
                [i for i in deduped_items if i.source == "userMemory"]
            ),
            "chunks_count": len([i for i in deduped_items if i.source == "chunk"]),
        }


context_inject_service = ContextInjectService()
