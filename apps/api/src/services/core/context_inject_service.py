"""
上下文注入服务
统一处理用户画像、记忆、文档片段的获取和语义去重
"""

import logging
from typing import Dict, Any, List, Optional
import time
import re
import random
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

from src.config import settings
from src.database import db

# 注入标注阈值：记忆记录超过该天数时追加「记录于 N 天前」，
# 让 agent 在召回当下感知陈旧度，主动 search/update 维护（ADR-0009）。
STALE_DAYS = 90

# static 临时性标记：命中即视为"配置记录/一次性事件"，而非永久行为规则。
# 保守策略：宁误判为行为规则（多注入 token）也不误判为临时（不丢失规则）。
# 注意：'已修复'/'API' 单独不判（OMO 迁移修复是行为教训、EmQuantAPI 规范是行为规则）。
TRANSIENT_STATIC_MARKERS = [
    r"已吊销", r"已改为", r"已保存", r"已删除", r"已变更", r"已迁移",
    r"机器主机名", r"hostnamectl",
    r"关键bug已修复", r"bug\s*已修复",
]
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

        failed_channels: List[str] = []
        # --- profile 通道 ---
        try:
            profile = await self._get_profile(user_tag, config)
            trace.record_profile(
                profile.get("static", []),
                profile.get("dynamic", []),
                # enabled 由实际注入结果推导（修复默认值 False 与 _get_profile True 不一致）
                enabled=None,
            )
        except Exception as e:
            profile = {"static": [], "dynamic": []}
            trace.record_profile([], [], enabled=False)
            trace.record_channel_failure("profile")
            logger.warning("context-inject profile channel failed: %s", e)
        trace.mark_profile()

        try:
            user_memories = await self._get_memories(user_tag, query, config, trace, scope="user")
            if user_tag == project_tag:
                # user/project 指向同一容器时复用结果，避免重复 embedding 搜索
                project_memories = user_memories
            else:
                project_memories = await self._get_memories(project_tag, query, config, trace, scope="project")
        except Exception as e:
            user_memories = []
            project_memories = []
            trace.record_channel_failure("memories")
            logger.warning("context-inject memories channel failed: %s", e)
        trace.mark_memories()

        try:
            user_chunks = await self._get_chunks(user_tag, query, config, trace, scope="user")
            if user_tag == project_tag:
                project_chunks = user_chunks
            else:
                project_chunks = await self._get_chunks(project_tag, query, config, trace, scope="project")
        except Exception as e:
            user_chunks = []
            project_chunks = []
            trace.record_channel_failure("chunks")
            logger.warning("context-inject chunks channel failed: %s", e)
        trace.mark_chunks()

        failed_channels = list(trace.failed_channels)

        # 仅当全部通道失败（系统性故障：存储/嵌入不可用）才视为请求级错误；
        # 单通道失败返回已成功通道的部分结果。
        if set(failed_channels) >= {"profile", "memories", "chunks"}:
            err = f"all recall channels failed: {', '.join(failed_channels)}"
            trace.mark_error(err)
            try:
                if await recall_trace_service.should_record(force=include_trace):
                    await recall_trace_service.save(trace)
            except Exception:
                pass
            raise RuntimeError(f"Context injection failed: {err}")

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
        stats["failed_channels"] = failed_channels

        if await recall_trace_service.should_record(force=include_trace):
            await recall_trace_service.save(trace)

        result = {
            "context": context,
            "sources": sources,
            "stats": stats,
            "failed_channels": failed_channels,
        }
        if include_trace:
            result["trace"] = trace.to_dict()
        return result

    async def _get_profile(
        self,
        container_tag: str,
        config: Dict[str, Any],
    ) -> Dict[str, List[str]]:
        if not config.get("inject_profile", True):
            return {"static": [], "dynamic": []}

        try:
            max_static = config.get("max_static_profile_items", 30)
            max_dynamic = config.get("max_profile_items", 10)
            # 请求上限取缓存构建上限（100/50），避免 profile_service 的 max_static 预截断
            # 在分层分类之前丢弃老行为规则——cap 必须在分层之后施加
            fetch_static = max(max_static, 100)
            fetch_dynamic = max(max_dynamic, 50)
            profile_data = await profile_service.get_profile(
                container_tag,
                max_static=fetch_static,
                max_dynamic=fetch_dynamic,
            )
            profile = profile_data.get("profile", {})
            # static 分层注入：行为规则（无临时标记）全量注入永不截断，
            # 临时事实（配置记录/一次性事件）填剩余额度（列表已按 created_at DESC 排序，最新优先）
            # 注："永不截断"的保证范围是最新 100 条 static 内（_CACHE_STATIC_LIMIT 硬边界，超过后最老规则被预取丢弃）
            static_facts = profile.get("static", [])
            behavior_rules = [
                f for f in static_facts if not self._is_transient_static(f)
            ]
            transient_facts = [
                f for f in static_facts if self._is_transient_static(f)
            ]
            remaining = max(0, max_static - len(behavior_rules))
            static = behavior_rules + transient_facts[:remaining]
            # dynamic 为近期活动（时效即价值），按 max_profile_items 取最新
            return {
                "static": static,
                "dynamic": profile.get("dynamic", [])[:max_dynamic],
            }
        except Exception as e:
            logger.warning("profile fetch failed for %s: %s", container_tag, e)
            raise

    def _is_transient_static(self, content: str) -> bool:
        """判定 static 事实是否为临时性记录（配置记录/一次性事件），而非永久行为规则。

        保守策略：宁误判为行为规则（多注入 token）也不误判为临时（不丢失规则）。
        标记表见模块级 TRANSIENT_STATIC_MARKERS（与写入路径共用，防漂移）。
        """
        import re

        return any(re.search(m, content) for m in TRANSIENT_STATIC_MARKERS)

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
            # 排除已注入记忆（插件侧 LRU 跟踪）：向量命中/图谱扩展/实体扩展
            # 共用 seen_ids 判重，预置排除集合后全部链路自动生效
            seen_ids = set(config.get("exclude_memory_ids") or [])

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
                    # 采样命中时记录阈值前候选（SQL 阈值降低 + limit 放大），
                    # 用于漏召回分析；默认 TRACE_FULL_CANDIDATE_RATE=0 关闭，不改变生产行为
                    full_candidate = (
                        settings.TRACE_FULL_CANDIDATE_RATE > 0
                        and random.random() < settings.TRACE_FULL_CANDIDATE_RATE
                    )
                    search_limit = max_memories * 3 if full_candidate else max_memories
                    search_threshold = (
                        0.30 if full_candidate else config.get("memory_similarity_threshold", 0.40)
                    )
                    search_results = await memory_store.search(
                        query=query,
                        container_tag=container_tag,
                        limit=search_limit,
                        threshold=search_threshold,
                    )

                    if trace:
                        trace.record_vector(
                            search_results,
                            search_threshold,
                            scope=scope,
                            full_candidate=full_candidate,
                        )

                    # 边缘命中（0.40-0.45）二段验证：query 关键词与内容有交集才算低置信降级，
                    # 否则保留——避免"最近的热点研究"这类长内容记忆被误伤（trace 实测 4/5 被截）
                    edge_low, edge_high = config.get(
                        "memory_similarity_threshold", 0.40
                    ), config.get("memory_similarity_threshold", 0.40) + 0.05
                    if query:
                        _qk = self._extract_query_keywords(query)
                    else:
                        _qk = set()

                    for r in search_results:
                        mem_id = r.get("id")
                        if mem_id and mem_id not in seen_ids:
                            seen_ids.add(mem_id)
                            sim = r.get("similarity", 0.0)
                            in_edge = edge_low <= sim < edge_high
                            kw_hit = False
                            if in_edge:
                                _ck = self._extract_query_keywords(r.get("content", ""))
                                kw_hit = bool(_qk & _ck)
                            all_memories.append(
                                {
                                    "id": mem_id,
                                    "content": r.get("content", ""),
                                    "embedding": r.get("embedding"),
                                    "is_static": False,
                                    "similarity": sim,
                                    "created_at": r.get("created_at"),
                                    # 仅"边缘命中且关键词无交集"标记低置信：降级让 cap 截断
                                    "low_confidence": in_edge and not kw_hit,
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
                                                "created_at": target_memory.created_at.isoformat()
                                                if target_memory.created_at
                                                else None,
                                                # 标记渠道来源：供 L518 截断区分 core/entity_graph 增量
                                                "source": "memory_graph",
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
                                    new_ids = [
                                        m.id
                                        for m in entity_memories
                                        if m.id not in seen_ids
                                    ]
                                    logger.info(
                                        "entity_graph: %d entity_ids -> %d memories (%d new: %s)",
                                        len(entity_ids),
                                        len(entity_memories),
                                        len(new_ids),
                                        new_ids[:5],
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
                                                    "created_at": m.created_at.isoformat()
                                                    if m.created_at
                                                    else None,
                                                    "source": "entity_graph",
                                                }
                                            )
                                            if trace:
                                                trace.record_entity_graph_memory(
                                                    {"id": m.id, "content": m.content},
                                                    scope=scope,
                                                )
                        except Exception as e:
                            logger.error(
                                "entity_graph injection failed (entities=%s, entity_ids=%d): %s",
                                [en.name for en in entities[:5]] if entities else [],
                                len(entity_ids) if "entity_ids" in dir() else -1,
                                e,
                                exc_info=True,
                            )

            # 2026-04-24: 移除 recent_memories 填充逻辑
            # 原逻辑在语义搜索结果不足时用"最近记忆"补位，
            # 但这些记忆与query完全无关，造成噪音召回
            # 现改为：只返回语义搜索+图谱扩展的结果，不够就不够

            # 截断 source-aware：向量+记忆图谱占 max_memories*2 容量，
            # 实体图增量单独配额追加——避免后加入的实体图高价值增量被无差别挤掉
            # （修复：子代理 max_memories=3 时 [:6] 截断丢 entity_graph 增量，见 trace 902fc2fe）
            entity_graph_items = [
                m for m in all_memories if m.get("source") == "entity_graph"
            ]
            core_items = [
                m for m in all_memories if m.get("source") != "entity_graph"
            ]
            # 实体图增量配额：正常 max=5 → 2 条；子代理 max=3 → 1 条（保底 1）
            entity_quota = max(1, (max_memories + 2) // 3)
            return (
                core_items[: max_memories * 2] + entity_graph_items[:entity_quota]
            )
        except Exception as e:
            logger.warning("memories fetch failed for %s: %s", container_tag, e)
            raise

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
            # 防御性兜底：丢弃 HTML 噪音 chunk（存量修复 6d9d1b8 前的遗留/导入侧漏网），
            # 避免 `<div align=...>` 这类纯标记片段被注入上下文
            html_noise = re.compile(r"^\s*<[a-zA-Z/!]")
            all_chunks = [
                c for c in all_chunks if not html_noise.match(c.get("content") or "")
            ]
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
        except Exception as e:
            logger.warning("chunks fetch failed for %s: %s", container_tag, e)
            raise

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

    def _extract_query_keywords(self, text: str) -> set:
        """jieba 提取关键词用于边缘命中二段验证；jieba 不可用时回退到正则切分"""
        try:
            from src.services.jieba_service import extract_keywords

            words = extract_keywords(text)
        except ImportError:
            import re as _re

            tokens = _re.split(r"[，。！？、；：\s,.;!?]+", text)
            words = [t for t in tokens if len(t) >= 2 and not t.isdigit()]
        return {w.lower() for w in words}

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


    def _collect_items_with_tags(
        self,
        profile: Dict[str, List[str]],
        user_memories: List[Dict[str, Any]],
        project_memories: List[Dict[str, Any]],
        user_chunks: List[Dict[str, Any]],
        project_chunks: List[Dict[str, Any]],
    ) -> List[DedupItem]:
        items = []
        # 画像条目无 embedding，无法参与语义去重（semantic_dedup_service 只比较
        # 带 embedding 的条目，无 embedding 者无条件保留）。这里先登记画像内容，
        # 后续记忆条目若与画像内容逐字相同则直接跳过——画像优先级最高，保留画像版本，
        # 避免同一条记忆以 profile + userMemory/projectMemory 双身份重复注入
        # （trace 269dd48a：final[8] profile 与 final[25] userMemory 同内容并存）。
        seen_contents: set = set()

        for fact in profile.get("static", []):
            items.append(
                DedupItem(
                    content=fact,
                    source="profile",
                    priority=SOURCE_PRIORITY["profile"],
                )
            )
            seen_contents.add(fact.strip())

        for fact in profile.get("dynamic", []):
            items.append(
                DedupItem(
                    content=fact,
                    source="profile",
                    priority=SOURCE_PRIORITY["profile"],
                )
            )
            seen_contents.add(fact.strip())

        for m in project_memories:
            content = m.get("content", "")
            if content.strip() in seen_contents:
                continue
            items.append(
                DedupItem(
                    content=content,
                    source="projectMemory",
                    # 边缘命中（low_confidence）降 1 级：让 cap 优先保留高分记忆，减少 0.40-0.45 噪音注入
                    # entity_graph 增量（未被其他渠道召回的新信息）+0.5：在 dedup 排序与最终 cap 中存活
                    priority=SOURCE_PRIORITY["projectMemory"]
                    - (1 if m.get("low_confidence") else 0)
                    + (0.5 if m.get("source") == "entity_graph" else 0),
                    embedding=m.get("embedding"),
                    id=m.get("id"),
                    created_at=m.get("created_at"),
                    relation_type=m.get("relation_type"),
                )
            )

        for m in user_memories:
            content = m.get("content", "")
            if content.strip() in seen_contents:
                continue
            items.append(
                DedupItem(
                    content=content,
                    source="userMemory",
                    # 边缘命中（low_confidence）降 1 级：让 cap 优先保留高分记忆，减少 0.40-0.45 噪音注入
                    # entity_graph 增量（未被其他渠道召回的新信息）+0.5：在 dedup 排序与最终 cap 中存活
                    priority=SOURCE_PRIORITY["userMemory"]
                    - (1 if m.get("low_confidence") else 0)
                    + (0.5 if m.get("source") == "entity_graph" else 0),
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

    def _format_memory_with_relation(self, item: DedupItem, is_zh: bool) -> str:
        if not item.relation_type:
            content = item.content
        else:
            relation_labels = {
                "updates": "更新" if is_zh else "updated",
                "extends": "补充" if is_zh else "extended",
                "derives": "推断" if is_zh else "derived",
            }
            label = relation_labels.get(item.relation_type, item.relation_type)
            content = f"{item.content} [{label}]"

        age_days = self._age_days(item.created_at)
        if age_days is not None and age_days > STALE_DAYS:
            if is_zh:
                content = f"{content}（记录于 {age_days} 天前）"
            else:
                content = f"{content} (recorded {age_days} days ago)"
        return content

    @staticmethod
    def _age_days(created_at: Optional[str]) -> Optional[int]:
        """ISO 时间字符串距今天数；无效/缺失返回 None。"""
        if not created_at:
            return None
        try:
            dt = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return max(0, (datetime.now(timezone.utc) - dt).days)
        except (ValueError, TypeError):
            return None

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
            if not item.content:
                continue
            chinese_chars = sum(1 for c in item.content if "\u4e00" <= c <= "\u9fff")
            if chinese_chars / len(item.content) > 0.3:
                return True
        return False

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
            # 向后兼容：单容器旧字段，取 project + user 记忆总数
            "memories_count": len(
                [
                    i
                    for i in capped_items
                    if i.source in ("projectMemory", "userMemory")
                ]
            ),
        }


context_inject_service = ContextInjectService()
