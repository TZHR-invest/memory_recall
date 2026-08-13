"""陈旧记忆标注单元测试（ADR-0009：注入可见性）。

验证 _format_memory_with_relation 对超过 STALE_DAYS 的记忆追加「记录于 N 天前」。
"""

from datetime import datetime, timedelta, timezone

from src.services.core.context_inject_service import ContextInjectService, STALE_DAYS
from src.services.core.semantic_dedup_service import DedupItem


service = ContextInjectService()


def _iso(days_ago: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days_ago)).isoformat()


class TestStaleAnnotation:
    def test_recent_memory_no_annotation(self):
        item = DedupItem(
            content="最近沉淀的记忆",
            source="projectMemory",
            priority=3,
            created_at=_iso(10),
        )
        assert service._format_memory_with_relation(item, True) == "最近沉淀的记忆"

    def test_old_memory_annotated_zh(self):
        item = DedupItem(
            content="过时配置记录",
            source="projectMemory",
            priority=3,
            created_at=_iso(STALE_DAYS + 30),
        )
        out = service._format_memory_with_relation(item, True)
        assert f"记录于 {STALE_DAYS + 30} 天前" in out

    def test_old_memory_annotated_en(self):
        item = DedupItem(
            content="stale config note",
            source="projectMemory",
            priority=3,
            created_at=_iso(200),
        )
        out = service._format_memory_with_relation(item, False)
        assert "recorded 200 days ago" in out

    def test_missing_created_at_no_annotation(self):
        item = DedupItem(content="无时间字段", source="projectMemory", priority=3)
        assert service._format_memory_with_relation(item, True) == "无时间字段"

    def test_invalid_created_at_no_annotation(self):
        item = DedupItem(
            content="坏时间",
            source="projectMemory",
            priority=3,
            created_at="not-a-date",
        )
        assert service._format_memory_with_relation(item, True) == "坏时间"

    def test_relation_type_with_annotation(self):
        item = DedupItem(
            content="旧版本结论",
            source="projectMemory",
            priority=3,
            created_at=_iso(120),
            relation_type="updates",
        )
        out = service._format_memory_with_relation(item, True)
        assert out.startswith("旧版本结论 [更新]")
        assert "记录于 120 天前" in out
