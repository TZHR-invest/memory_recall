"""画像通道分层渲染与体量闸门（MR-027，2026-09-30）

覆盖三件事：
1. static/dynamic **分节渲染**（此前两桶合并挂在「### 永久特征」下，动态条目被读成永久记忆）；
2. 单条长度闸门 PROFILE_ITEM_MAX_CHARS 截断 + stats.profile_truncated_count 可见；
3. profile_worthy=false 在 **dynamic 桶**同样生效（此前只对 static 生效，是"退出画像"开关的半成品）。
"""

import asyncio
import sys
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(
    0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)

from src.services.core.context_inject_service import (
    PROFILE_ITEM_MAX_CHARS,
    context_inject_service,
)
from src.services.core.semantic_dedup_service import DedupItem, SOURCE_PRIORITY


def _profile_item(content: str, bucket: str) -> DedupItem:
    return DedupItem(
        content=content,
        source="profile",
        priority=SOURCE_PRIORITY["profile"],
        bucket=bucket,
    )


class TestProfileSectionSplit:
    def test_static_and_dynamic_render_in_separate_sections(self):
        items = [
            _profile_item("我是素食主义者", "static"),
            _profile_item("正在做后端去重", "dynamic"),
        ]

        ctx = context_inject_service._format_context_with_tags(items, "zh_CN")

        assert "### 永久特征" in ctx
        assert "### 近期动态" in ctx

        static_seg = ctx.split("### 永久特征", 1)[1].split("### 近期动态", 1)[0]
        dynamic_seg = ctx.split("### 近期动态", 1)[1]

        assert "我是素食主义者" in static_seg
        assert "正在做后端去重" not in static_seg, "动态条目不得出现在永久特征节"
        assert "正在做后端去重" in dynamic_seg

    def test_dynamic_only_still_gets_its_own_section(self):
        """只有 dynamic 时不再借用「永久特征」标题（这是修复前的误读来源）。"""
        ctx = context_inject_service._format_context_with_tags(
            [_profile_item("近期在做 crystal 迁移", "dynamic")], "zh_CN"
        )
        assert "### 永久特征" not in ctx
        assert "### 近期动态" in ctx

    def test_static_only_unaffected(self):
        ctx = context_inject_service._format_context_with_tags(
            [_profile_item("始终用中文回复", "static")], "zh_CN"
        )
        assert "### 永久特征" in ctx
        assert "### 近期动态" not in ctx

    def test_english_sections(self):
        ctx = context_inject_service._format_context_with_tags(
            [
                _profile_item("vegetarian", "static"),
                _profile_item("working on dedup", "dynamic"),
            ],
            "en_US",
        )
        assert "### Static Facts" in ctx
        assert "### Recent Activity" in ctx


class TestProfileItemTruncation:
    def test_short_items_untouched(self):
        facts = ["短偏好一", "短偏好二"]
        out, truncated = context_inject_service._truncate_profile_items(facts)
        assert out == facts
        assert truncated == 0

    def test_oversize_item_truncated_with_marker(self):
        long_text = "长留档内容" * 500  # 2,500 字
        out, truncated = context_inject_service._truncate_profile_items([long_text])

        assert truncated == 1
        assert len(out) == 1
        assert out[0].startswith("长留档内容")
        assert "已截断" in out[0]
        assert str(len(long_text) - PROFILE_ITEM_MAX_CHARS) in out[0]
        # 头部保留 + 标注，长度受控（不是原样注入）
        assert len(out[0]) < len(long_text)

    def test_empty_list(self):
        out, truncated = context_inject_service._truncate_profile_items([])
        assert out == []
        assert truncated == 0


class TestProfileChannelEndToEnd:
    """走完整 inject_with_tags：分节 + 闸门 + stats 计数一致。"""

    @pytest.fixture
    def mock_stores(self):
        with patch(
            "src.services.core.context_inject_service.profile_service"
        ) as profile_mock, patch(
            "src.services.core.context_inject_service.memory_store"
        ) as store_mock, patch(
            "src.services.core.context_inject_service.document_store"
        ) as doc_mock:
            profile_mock.get_profile = AsyncMock(
                return_value={
                    "profile": {
                        "static": ["始终用中文回复"],
                        "dynamic": ["历史 cron prompt 全量备份：" + "正文" * 2000],
                    }
                }
            )
            store_mock.search = AsyncMock(return_value=[])
            store_mock.get_by_id = AsyncMock(return_value=None)
            store_mock.get_entities_for_memories = AsyncMock(return_value=[])
            store_mock.find_memories_by_entities = AsyncMock(return_value=[])
            doc_mock.search_chunks = AsyncMock(return_value=[])
            yield profile_mock, store_mock, doc_mock

    def test_long_dynamic_item_capped_and_counted(self, mock_stores):
        result = asyncio.run(
            context_inject_service.inject_with_tags(
                user_tag="user_test",
                project_tag="user_test_project",
                query="任意",
                config={
                    "inject_profile": True,
                    "max_profile_items": 5,
                    "max_static_profile_items": 30,
                    "max_memories": 0,
                    "max_chunks": 0,
                    "enable_semantic_dedup": False,
                    "enable_memory_graph": False,
                    "enable_entity_graph": False,
                    "language": "zh_CN",
                },
            )
        )

        ctx = result["context"]
        assert result["stats"]["profile_truncated_count"] == 1
        assert result["stats"]["profile_count"] == 2

        static_seg = ctx.split("### 永久特征", 1)[1].split("### 近期动态", 1)[0]
        dynamic_seg = ctx.split("### 近期动态", 1)[1]
        assert "始终用中文回复" in static_seg
        # 动态长条被截断后仍在该节，但不再是 8K 级全文
        assert "已截断" in dynamic_seg
        assert len(dynamic_seg) < 2000


class TestProfileWorthySymmetric:
    """profile_worthy=false 必须同时作用于 static 与 dynamic 两桶。"""

    def test_dynamic_bucket_honors_profile_worthy_false(self):
        from src.services.core.profile_service import profile_service

        def _mem(content, metadata=None, is_static=False):
            m = MagicMock()
            m.content = content
            m.metadata = metadata or {}
            m.is_static = is_static
            return m

        static_memories = [
            _mem("真偏好", {}),
            _mem("已退出画像的静态项", {"profile_worthy": False}),
        ]
        dynamic_memories = [
            _mem("cron prompt 全量备份", {"profile_worthy": False, "kind": "cron_prompt_backup"}),
            _mem("近期正常活动", {}),
        ]

        with patch(
            "src.services.core.profile_service.memory_store"
        ) as store_mock:
            store_mock.get_static_memories = AsyncMock(return_value=static_memories)
            store_mock.get_dynamic_memories = AsyncMock(return_value=dynamic_memories)

            built = asyncio.run(profile_service._build_profile("user_test"))

        assert built["static_memories"] == ["真偏好"]
        assert built["dynamic_memories"] == ["近期正常活动"]
