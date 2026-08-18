"""写入侧 profile_worthy 标记（2026-08-18 画像净化）：验证 static 记忆写入时自动打标。

规则：preference/无 type → true（进画像）；其他类型（learned-pattern 等）→ false（不进画像，可向量召回）；
已有显式标记不覆盖。
"""
import sys
import os

sys.path.insert(
    0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)

import pytest
from unittest.mock import AsyncMock, patch
from contextlib import ExitStack

from src.services.core.memory_store import MemoryStore, Memory


class TestProfileWorthyWrite:
    """"""

    def _process(self, store, mem, extraction=None):
        """模拟 process_memory_async 主体：实体提取后写 profile_worthy"""
        import asyncio
        # 直接调用真实 process_memory_async，但 patch 掉 LLM 提取与关系创建
        with ExitStack() as st:
            st.enter_context(
                patch.object(store, "get_by_id", new_callable=AsyncMock, return_value=mem)
            )
            # patch 实体提取：返回 is_static（不覆盖我们关心的），不产实体
            st.enter_context(
                patch.object(store, "_get_llm_extractor", new_callable=AsyncMock)
            )
            st.enter_context(
                patch.object(
                    store,
                    "_store_entity_graph",
                    new_callable=AsyncMock,
                )
            )
            # 关系创建跳过
            st.enter_context(
                patch(
                    "src.services.core.memory_store.relation_service",
                    new_callable=AsyncMock,
                )
            )
            # update_metadata 捕获
            mock_upd = st.enter_context(
                patch.object(store, "update_metadata", new_callable=AsyncMock)
            )
            # invalidate_cache
            st.enter_context(
                patch(
                    "src.services.core.memory_store.profile_service",
                    new_callable=AsyncMock,
                )
            )
            asyncio.get_event_loop().run_until_complete(
                store.process_memory_async(mem.id)
            )
        return mock_upd

    def test_async_learned_pattern_static_marks_false(self):
        """异步路径：learned-pattern static → profile_worthy=false（项目内容不进画像）"""
        import asyncio
        store = MemoryStore()
        mem = Memory(
            id="mem_pw1",
            container_tag="test_pw",
            content="某项目的临时配置经验",
            is_static=True,
            metadata={"type": "learned-pattern", "_pending_extract_entities": True},
        )
        # 用真实 process_memory_async + mock 提取
        with ExitStack() as st:
            st.enter_context(patch.object(store, "get_by_id", new_callable=AsyncMock, side_effect=[mem, mem, None]))
            extractor = AsyncMock()
            extractor.extract_with_relations.return_value = {
                "entities": [], "relations": [], "is_static": True, "confidence": 0.5
            }
            st.enter_context(patch.object(store, "_get_llm_extractor", new_callable=AsyncMock, return_value=extractor))
            st.enter_context(patch.object(store, "_store_entity_graph", new_callable=AsyncMock))
            st.enter_context(patch("src.services.core.memory_store.relation_service", new_callable=AsyncMock))
            mock_upd = st.enter_context(patch.object(store, "update_metadata", new_callable=AsyncMock))
            st.enter_context(patch("src.services.core.profile_service.profile_service", new_callable=AsyncMock))
            # 第三个 get_by_id（latest）返回 None 时走 meta 分支
            asyncio.get_event_loop().run_until_complete(store.process_memory_async("mem_pw1"))

        # 捕获 update_metadata 调用
        calls = mock_upd.call_args_list
        assert len(calls) >= 1
        meta = calls[-1].args[1]
        assert meta.get("profile_worthy") is False, f"learned-pattern static 应标记 false，实际 {meta.get('profile_worthy')}"

    def test_async_preference_static_marks_true(self):
        """异步路径：preference static → profile_worthy=true（用户偏好进画像）"""
        import asyncio
        store = MemoryStore()
        mem = Memory(
            id="mem_pw2",
            container_tag="test_pw",
            content="用户喜欢用中文回复",
            is_static=True,
            metadata={"type": "preference", "_pending_extract_entities": True},
        )
        with ExitStack() as st:
            st.enter_context(patch.object(store, "get_by_id", new_callable=AsyncMock, side_effect=[mem, mem, None]))
            extractor = AsyncMock()
            extractor.extract_with_relations.return_value = {
                "entities": [], "relations": [], "is_static": True, "confidence": 0.5
            }
            st.enter_context(patch.object(store, "_get_llm_extractor", new_callable=AsyncMock, return_value=extractor))
            st.enter_context(patch.object(store, "_store_entity_graph", new_callable=AsyncMock))
            st.enter_context(patch("src.services.core.memory_store.relation_service", new_callable=AsyncMock))
            mock_upd = st.enter_context(patch.object(store, "update_metadata", new_callable=AsyncMock))
            st.enter_context(patch("src.services.core.profile_service.profile_service", new_callable=AsyncMock))
            asyncio.get_event_loop().run_until_complete(store.process_memory_async("mem_pw2"))

        calls = mock_upd.call_args_list
        assert len(calls) >= 1
        meta = calls[-1].args[1]
        assert meta.get("profile_worthy") is True, f"preference static 应标记 true，实际 {meta.get('profile_worthy')}"

    def test_existing_profile_worthy_not_overwritten(self):
        """已有显式 profile_worthy 标记不覆盖（存量 9 true / 34 false 保护）"""
        import asyncio
        store = MemoryStore()
        mem = Memory(
            id="mem_pw3",
            container_tag="test_pw",
            content="存量已标记内容",
            is_static=True,
            metadata={"type": "learned-pattern", "profile_worthy": True,
                      "_pending_extract_entities": True},  # 显式 true（如存量 npm 2FA）
        )
        with ExitStack() as st:
            st.enter_context(patch.object(store, "get_by_id", new_callable=AsyncMock, side_effect=[mem, mem, None]))
            extractor = AsyncMock()
            extractor.extract_with_relations.return_value = {
                "entities": [], "relations": [], "is_static": True, "confidence": 0.5
            }
            st.enter_context(patch.object(store, "_get_llm_extractor", new_callable=AsyncMock, return_value=extractor))
            st.enter_context(patch.object(store, "_store_entity_graph", new_callable=AsyncMock))
            st.enter_context(patch("src.services.core.memory_store.relation_service", new_callable=AsyncMock))
            mock_upd = st.enter_context(patch.object(store, "update_metadata", new_callable=AsyncMock))
            st.enter_context(patch("src.services.core.profile_service.profile_service", new_callable=AsyncMock))
            asyncio.get_event_loop().run_until_complete(store.process_memory_async("mem_pw3"))

        calls = mock_upd.call_args_list
        assert len(calls) >= 1
        meta = calls[-1].args[1]
        assert meta.get("profile_worthy") is True, "显式标记不应被覆盖"
