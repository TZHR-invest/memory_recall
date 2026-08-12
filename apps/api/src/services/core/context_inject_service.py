"""
上下文注入服务
统一处理用户画像、记忆、文档片段的获取和语义去重
"""

from typing import Dict, Any, List, Optional
import time

from src.config import settings
from src.database import db
from src.services.core.semantic_dedup_service import (
    semantic_dedup_service,
    DedupItem,
    SOURCE_PRIORITY,
)
from src.services.core.recall_trace_service import (
    RecallTrace,
    recall_trace_service,
)
from src.services.core.recall_embedding_service import recall_embedding_service
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
        include_trace: bool = False,
        trace: Optional[RecallTrace] = None,
    ) -> Dict[str, Any]:
        trace = trace or RecallTrace(
            mode="single",
            container_tag=container_tag,
            user_tag=container_tag,
            project_tag=None,
            query=query,
            config=config,
        )

        try:
            profile = await self._get_profile(container_tag, config)
            trace.record_profile(
                profile.get("static", []),
                profile.get("dynamic", []),
                enabled=config.get("inject_profile", False),
            )
            trace.mark_profile()

            memories = await self._get_memories(container_tag, query, config, trace)
            trace.mark_memories()

            chunks = await self._get_chunks(container_tag, query, config, trace)
            trace.mark_chunks()

            all_items = self._collect_items(profile, memories, chunks)

            dropped_log: List[Dict[str, Any]] = []
            if config.get("enable_semantic_dedup", True):
                deduped_items = await semantic_dedup_service.deduplicate(
                    all_items,
                    threshold=config.get("dedup_threshold", 0.85),
                    dropped_log=dropped_log,
                )
            else:
                deduped_items = all_items
            trace.record_dedup(
                deduped_items,
                dropped_log,
                config.get("dedup_threshold", 0.85),
            )
            trace.mark_dedup()

            capped_items = self._apply_injection_caps(deduped_items)

            context = self._format_context(capped_items, config.get("language", "auto"))
            trace.record_final(capped_items)
            trace.mark_format()

            sources = self._build_sources(profile, memories, chunks, capped_items)
            stats = self._build_stats(all_items, deduped_items, capped_items)

            if await recall_trace_service.should_record(force=include_trace):
                await recall_trace_service.save(trace)

            result = {
                "context": context,
                "sources": sources,
                "stats": stats,
            }
            if include_trace:
                result["trace"] = trace.to_dict()
            return result
        except Exception as e:
            trace.mark_error(str(e))
            try:
                if await recall_trace_service.should_record(force=include_trace):
                    await recall_trace_service.save(trace)
            except Exception:
                pass
            raise

    async def inject_with_tags(
        self,
        user_tag: str,
        project_tag: str,
        query: Optional[str],
        config: Dict[str, Any],
        include_trace: bool = False,
        trace: Optional[RecallTrace] = None,
    ) -> Dict[str, Any]:
        trace = trace or RecallTrace(
            mode="tags",
            container_tag=project_tag,
            user_tag=user_tag,
            project_tag=project_tag,
            query=query,
            config=config,
        )

        try:
            profile = await self._get_profile(user_tag, config)
            trace.record_profile(
                profile.get("static", []),
                profile.get("dynamic", []),
                enabled=config.get("inject_profile", False),
            )
            trace.mark_profile()

            user_memories = await self._get_memories(user_tag, query, config, trace, scope="user")
            project_memories = await self._get_memories(project_tag, query, config, trace, scope="project")
            trace.mark_memories()

            user_chunks = await self._get_chunks(user_tag, query, config, trace, scope="user")
            project_chunks = await self._get_chunks(project_tag, query, config, trace, scope="project")
            trace.mark_chunks()

            all_items = self._collect_items_with_tags(
                profile, user_memories, project_memories, user_chunks, project_chunks
            )

            dropped_log: List[Dict[str, Any]] = []
            if config.get("enable_semantic_dedup", True):
                deduped_items = await semantic_dedup_service.deduplicate(
                    all_items,
                    threshold=config.get("dedup_threshold", 0.85),
                    dropped_log=dropped_log,
                )
            else:
                deduped_items = all_items
            trace.record_dedup(
                deduped_items,
                dropped_log,
                config.get("dedup_threshold", 0.85),
            )
            trace.mark_dedup()

            capped_items = self._apply_injection_caps(deduped_items)

            context = self._format_context_with_tags(
                capped_items, config.get("language", "auto")
            )
            trace.record_final(capped_items)
            trace.mark_format()

            sources = self._build_sources_with_tags(
                profile,
                user_memories,
                project_memories,
                user_chunks,
                project_chunks,
                capped_items,
            )
            stats = self._build_stats_with_tags(all_items, deduped_items, capped_items)

            if await recall_trace_service.should_record(force=include_trace):
                await recall_trace_service.save(trace)

            result = {
                "context": context,
                "sources": sources,
                "stats": stats,
            }
            if include_trace:
                result["trace"] = trace.to_dict()
            return result
        except Exception as e:
            trace.mark_error(str(e))
            try:
                if await recall_trace_service.should_record(force=include_trace):
                    await recall_trace_service.save(trace)
            except Exception:
                pass
            raise

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
            # static 为永久特征（量少、价值与时间无关），按 max_static_profile_items 全量注入；
            # dynamic 为近期活动（时效即价值），按 max_profile_items 取最新
            return {
                "static": profile.get("static", [])[
                    : config.get("max_static_profile_items", 20)
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
        trace: Optional[RecallTrace] = None,
        scope: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        try:
            enable_memory_graph = config.get("enable_memory_graph", True)
            enable_entity_graph = config.get("enable_entity_graph", True)
            max_memories = config.get("max_memories", 5)
            if self._is_subagent_query(query):
                max_memories = min(max_memories, 3)

            all_memories = []
            seen_ids = set()

            if query:
                embedding_client = get_embedding_client()
                embed_start = time.monotonic()
                query_embedding = await embedding_client.embed(query)
                embed_ok = query_embedding is not None
                await recall_embedding_service.log(
                    container_tag,
                    "context_query",
                    query,
                    embed_ok,
                    cache_hit=embedding_client.last_cache_hit if embed_ok else False,
                    model=settings.VOLC_EMBEDDING_MODEL,
                    error=(embedding_client.last_error if not embed_ok else None),
                    elapsed_ms=(time.monotonic() - embed_start) * 1000,
                    output_dim=len(query_embedding) if embed_ok else None,
                )

                if query_embedding:
                    search_results = await memory_store.search(
                        query=query,
                        container_tag=container_tag,
                        limit=max_memories,
                        threshold=config.get("memory_similarity_threshold", 0.40),
                    )

                    if trace:
                        trace.record_vector(
                            search_results,
                            config.get("memory_similarity_threshold", 0.40),
                            scope=scope,
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
                                memory = await memory_store.get_by_id(mem["id"])
                                if not memory:
                                    continue

                                relations = memory.metadata.get("relations", {})
                                for rel_type, target_ids in relations.items():
                                    if not isinstance(target_ids, list):
                                        continue

                                    for target_id in target_ids:
                                        if len(all_memories) >= max_memories * 2:
                                            break

                                        target_memory = await memory_store.get_by_id(
                                            target_id
                                        )
                                        if (
                                            not target_memory
                                            or target_memory.is_forgotten
                                        ):
                                            continue

                                        if target_id in seen_ids:
                                            if trace:
                                                trace.record_memory_graph(
                                                    mem["id"], rel_type, {"id": target_id}, added=False, scope=scope
                                                )
                                            for existing_mem in all_memories:
                                                if existing_mem.get("id") == target_id:
                                                    if not existing_mem.get(
                                                        "relation_type"
                                                    ):
                                                        existing_mem[
                                                            "relation_type"
                                                        ] = rel_type
                                                    break
                                            continue

                                        seen_ids.add(target_id)
                                        all_memories.append(
                                            {
                                                "id": target_memory.id,
                                                "content": target_memory.content,
                                                "embedding": target_memory.embedding,
                                                "is_static": target_memory.is_static,
                                                "relation_type": rel_type,
                                            }
                                        )
                                        if trace:
                                            trace.record_memory_graph(
                                                mem["id"], rel_type, {"id": target_memory.id, "content": target_memory.content}, added=True, scope=scope
                                            )

                                    if len(all_memories) >= max_memories * 2:
                                        break
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
                                        if trace:
                                            for r_entity in related:
                                                trace.record_entity_graph_path(
                                                    entity.name,
                                                    "related",
                                                    r_entity.name,
                                                    scope=scope,
                                                )
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
                                            if trace:
                                                trace.record_entity_graph_memory(
                                                    {"id": m.id, "content": m.content},
                                                    scope=scope,
                                                )
                        except Exception:
                            pass

            # 2026-04-24: 移除 recent_memories 填充逻辑
            # 原逻辑在语义搜索结果不足时用"最近记忆"补位，
            # 但这些记忆与query完全无关，造成噪音召回
            # 现改为：只返回语义搜索+图谱扩展的结果，不够就不够

            return all_memories[: max_memories * 2]
        except Exception:
            return []

    async def _get_chunks(
        self,
        container_tag: str,
        query: Optional[str],
        config: Dict[str, Any],
        trace: Optional[RecallTrace] = None,
        scope: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        if not query:
            return []

        if not config.get("enable_chunks_search", True):
            return []

        try:
            from src.embedding.client import get_embedding_client

            embedding_client = get_embedding_client()
            embed_start = time.monotonic()
            query_embedding = await embedding_client.embed(query)
            embed_ok = query_embedding is not None
            await recall_embedding_service.log(
                container_tag,
                "context_chunks",
                query,
                embed_ok,
                cache_hit=embedding_client.last_cache_hit if embed_ok else False,
                model=settings.VOLC_EMBEDDING_MODEL,
                error=(embedding_client.last_error if not embed_ok else None),
                elapsed_ms=(time.monotonic() - embed_start) * 1000,
                output_dim=len(query_embedding) if embed_ok else None,
            )

            if query_embedding is None:
                return []

            max_chunks = config.get("max_chunks", 3)
            if self._is_subagent_query(query):
                max_chunks = min(max_chunks, 2)

            chunks = await document_store.search_chunks(
                query_embedding=query_embedding,
                container_tag=container_tag,
                limit=max_chunks,
                threshold=config.get("chunks_similarity_threshold", 0.45),
            )

            if trace:
                trace.record_chunks(
                    chunks,
                    config.get("chunks_similarity_threshold", 0.45),
                    scope=scope,
                )

            all_chunks = []
            seen_ids = set()

            for c in chunks:
                chunk = c.get("chunk")
                if chunk and chunk.id not in seen_ids:
                    seen_ids.add(chunk.id)
                    all_chunks.append(
                        {
                            "id": chunk.id,
                            "content": chunk.content,
                            "embedding": chunk.embedding,
                            "document_id": c.get("document_id"),
                            "title": c.get("title"),
                            "source": c.get("source"),
                            "similarity": c.get("similarity", 0.0),
                        }
                    )

            if config.get("enable_entity_graph", True) and query:
                try:
                    from src.services.core.entity_extraction import entity_extractor

                    query_entities = entity_extractor.extract(query)

                    if query_entities:
                        # Extract entity names from NER results, then look up
                        # real entity IDs from the database entities table.
                        # NER Entity objects have .text (not .id) — using e.id
                        # would be the Python object id, not the DB entity id.
                        entity_names = [e.text for e in query_entities[:5]]

                        if trace:
                            trace.record_entity_graph_entities(entity_names, scope=scope)

                        rows = await db.fetch(
                            """
                            SELECT id FROM entities
                            WHERE name = ANY($1) AND container_tag = $2
                            """,
                            entity_names,
                            container_tag,
                        )

                        entity_ids = [str(r["id"]) for r in rows]

                        if entity_ids:
                            entity_chunks = await document_store.find_chunks_by_entities(
                                entity_ids=entity_ids,
                                container_tag=container_tag,
                                limit=max_chunks,
                            )

                            for c in entity_chunks:
                                if c["id"] not in seen_ids:
                                    seen_ids.add(c["id"])
                                    all_chunks.append(
                                        {
                                            "id": c["id"],
                                            "content": c["content"],
                                            "embedding": c.get("embedding"),
                                            "document_id": c.get("document_id"),
                                            "title": c.get("title"),
                                            "source": c.get("source"),
                                            "similarity": self._chunk_similarity(
                                                query_embedding, c.get("embedding")
                                            ),
                                            "_entity_hit": True,
                                        }
                                    )
                except Exception:
                    pass

            threshold = config.get("chunks_similarity_threshold", 0.45)
            entity_threshold = config.get("entity_chunk_threshold", 0.30)
            filtered = []
            for c in all_chunks:
                if c.get("_entity_hit"):
                    if c.get("embedding") is None or c.get("similarity", 0.0) >= entity_threshold:
                        filtered.append(c)
                elif c.get("similarity", 0.0) >= threshold:
                    filtered.append(c)
            if trace:
                for c in filtered:
                    if c.get("_entity_hit"):
                        trace.record_chunk_entity_hit(
                            {
                                "id": c["id"],
                                "content": c["content"],
                                "document_id": c.get("document_id"),
                                "title": c.get("title"),
                                "source": c.get("source"),
                            },
                            scope=scope,
                        )
            for c in filtered:
                c.pop("_entity_hit", None)
            return filtered
        except Exception:
            return []

    def _chunk_similarity(
        self,
        query_embedding: List[float],
        chunk_embedding: Optional[List[float]],
    ) -> float:
        if not query_embedding or not chunk_embedding:
            return 0.0
        try:
            from src.services.core.semantic_dedup_service import semantic_dedup_service

            return semantic_dedup_service.compute_cosine_similarity(
                query_embedding, chunk_embedding
            )
        except Exception:
            return 0.0

    def _is_subagent_query(self, query: Optional[str]) -> bool:
        if not query:
            return False
        q = query.strip()
        if q.startswith("["):
            head = q[:200]
            if any(
                marker in head
                for marker in ("CONTEXT", "analyze-mode", "search-mode", "SYSTEM", "System:")
            ):
                return True
        return len(q) > 800

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
                    relation_type=m.get("relation_type"),
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
                    relation_type=m.get("relation_type"),
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
                    relation_type=m.get("relation_type"),
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

    def _apply_injection_caps(self, items: List[DedupItem]) -> List[DedupItem]:
        """最终注入分层 cap：profile 不裁剪；memory 12 条（project 6 + user 6）；chunk 4 条。

        在去重后、渲染前统一应用，保证 context/stats/trace.final 三者一致。
        project/user 分开 cap 防止一方挤占另一方（project 记忆量大时 user 偏好不应被挤出）；
        截断按 dedup 输出顺序（来源优先级：profile > projectMemory > userMemory > chunk）。
        """
        project_memory_items = [i for i in items if i.source == "projectMemory"][:6]
        user_memory_items = [i for i in items if i.source == "userMemory"][:6]
        chunk_items = [i for i in items if i.source == "chunk"][:4]
        profile_items = [i for i in items if i.source == "profile"]
        return (
            profile_items + project_memory_items + user_memory_items + chunk_items
        )

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
                content = self._format_memory_with_relation(item, is_zh)
                lines.append(f"- {content}")
            lines.append("")

        if chunk_items:
            lines.append("### 项目文档" if is_zh else "### Project Documents")
            for item in chunk_items:
                lines.append(f"- {item.content}")
            lines.append("")

        if len(lines) <= 3:
            return ""

        return "\n".join(lines)

    def _format_memory_with_relation(self, item: DedupItem, is_zh: bool) -> str:
        if not item.relation_type:
            return item.content

        relation_labels = {
            "updates": "更新" if is_zh else "updated",
            "extends": "补充" if is_zh else "extended",
            "derives": "推断" if is_zh else "derived",
        }
        label = relation_labels.get(item.relation_type, item.relation_type)
        return f"{item.content} [{label}]"

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
                content = self._format_memory_with_relation(item, is_zh)
                lines.append(f"- {content}")
            lines.append("")

        if user_memory_items:
            lines.append("### 用户记忆" if is_zh else "### User Memories")
            for item in user_memory_items:
                content = self._format_memory_with_relation(item, is_zh)
                lines.append(f"- {content}")
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
        capped_items: List[DedupItem],
    ) -> Dict[str, Any]:
        capped_memories = [
            i for i in capped_items if i.source in ("userMemory", "projectMemory")
        ]
        capped_chunks = [i for i in capped_items if i.source == "chunk"]
        return {
            "profile": profile.get("static", []) + profile.get("dynamic", []),
            "memories": [
                {"id": i.id, "content": i.content} for i in capped_memories
            ],
            "chunks": [{"id": i.id, "content": i.content} for i in capped_chunks],
        }

    def _build_sources_with_tags(
        self,
        profile: Dict[str, List[str]],
        user_memories: List[Dict[str, Any]],
        project_memories: List[Dict[str, Any]],
        user_chunks: List[Dict[str, Any]],
        project_chunks: List[Dict[str, Any]],
        capped_items: List[DedupItem],
    ) -> Dict[str, Any]:
        return {
            "profile": profile.get("static", []) + profile.get("dynamic", []),
            "memories": [
                {"id": i.id, "content": i.content}
                for i in capped_items
                if i.source == "projectMemory"
            ],
            "user_memories": [
                {"id": i.id, "content": i.content}
                for i in capped_items
                if i.source == "userMemory"
            ],
            "chunks": [
                {"id": i.id, "content": i.content}
                for i in capped_items
                if i.source == "chunk"
            ],
            "user_chunks": [],
        }

    def _build_stats(
        self,
        all_items: List[DedupItem],
        deduped_items: List[DedupItem],
        capped_items: List[DedupItem],
    ) -> Dict[str, int]:
        memories_count = len(
            [i for i in capped_items if i.source in ("userMemory", "projectMemory")]
        )
        return {
            "total_items": len(all_items),
            "after_dedup": len(deduped_items),
            "deduped_count": len(all_items) - len(deduped_items),
            "capped_count": len(capped_items),
            "profile_count": len([i for i in capped_items if i.source == "profile"]),
            "memories_count": memories_count,
            "project_memories_count": len(
                [i for i in capped_items if i.source == "projectMemory"]
            ),
            "user_memories_count": len(
                [i for i in capped_items if i.source == "userMemory"]
            ),
            "chunks_count": len([i for i in capped_items if i.source == "chunk"]),
        }

    def _build_stats_with_tags(
        self,
        all_items: List[DedupItem],
        deduped_items: List[DedupItem],
        capped_items: List[DedupItem],
    ) -> Dict[str, int]:
        return {
            "total_items": len(all_items),
            "after_dedup": len(deduped_items),
            "deduped_count": len(all_items) - len(deduped_items),
            "capped_count": len(capped_items),
            "profile_count": len([i for i in capped_items if i.source == "profile"]),
            "project_memories_count": len(
                [i for i in capped_items if i.source == "projectMemory"]
            ),
            "user_memories_count": len(
                [i for i in capped_items if i.source == "userMemory"]
            ),
            "chunks_count": len([i for i in capped_items if i.source == "chunk"]),
        }


context_inject_service = ContextInjectService()
