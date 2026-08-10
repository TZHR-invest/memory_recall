"""
Tests for the personal data stats API:
- timeline zero-filling logic
- overview container resolution
- overview response shape (effective-caliber fields)
"""

import sys
import os
from unittest.mock import AsyncMock, patch

import pytest

sys.path.insert(
    0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)

from src.api.stats import get_timeline, get_overview, get_entities, get_activity, _resolve_container, _resolve_tz


class TestResolveContainer:
    @pytest.mark.asyncio
    async def test_default_uses_current_user_container(self):
        user = {"container_tag": "abc", "key_id": "abc", "permissions": ["read"]}
        with patch("src.api.stats.verify_container_ownership", new=AsyncMock()) as v:
            assert await _resolve_container(None, user) == "abc"
            v.assert_called_once_with("abc", "abc")

    @pytest.mark.asyncio
    async def test_explicit_container_passed_through(self):
        user = {"container_tag": "abc", "key_id": "abc"}
        with patch("src.api.stats.verify_container_ownership", new=AsyncMock()) as v:
            assert await _resolve_container("abc_proj_x", user) == "abc_proj_x"
            v.assert_called_once_with("abc_proj_x", "abc")


class TestTimeline:
    @pytest.mark.asyncio
    async def test_zero_fills_days(self):
        from datetime import datetime, timezone, timedelta
        now = datetime.now(timezone.utc)
        rows = [{"bucket": (now - timedelta(days=2)).date(), "count": 3}]
        with patch("src.api.stats._resolve_container", new=AsyncMock(return_value="c")), \
             patch("src.api.stats.db.fetch", new=AsyncMock(return_value=rows)):
            data = await get_timeline(
                container_tag=None,
                days=7,
                group_by="day",
                current_user={"container_tag": "c", "key_id": "c"},
                _=None,
            )
        assert len(data["points"]) == 7
        assert data["total"] == 3
        assert [p["count"] for p in data["points"]].count(3) == 1
        assert data["points"][0]["count"] == 0

    @pytest.mark.asyncio
    async def test_week_grouping(self):
        from datetime import datetime, timezone, timedelta
        now = datetime.now(timezone.utc)
        week_start = (now - timedelta(days=now.weekday())).replace(
            hour=0, minute=0, second=0, microsecond=0, tzinfo=timezone.utc
        )
        rows = [{"bucket": week_start, "count": 5}]
        with patch("src.api.stats._resolve_container", new=AsyncMock(return_value="c")), \
             patch("src.api.stats.db.fetch", new=AsyncMock(return_value=rows)):
            data = await get_timeline(
                container_tag=None,
                days=14,
                group_by="week",
                current_user={"container_tag": "c", "key_id": "c"},
                _=None,
            )
        assert data["group_by"] == "week"
        assert data["total"] == 5
        assert sum(p["count"] for p in data["points"]) == 5
        assert data["points"][-1]["count"] == 5

    @pytest.mark.asyncio
    async def test_month_grouping(self):
        rows = []
        with patch("src.api.stats._resolve_container", new=AsyncMock(return_value="c")), \
             patch("src.api.stats.db.fetch", new=AsyncMock(return_value=rows)):
            data = await get_timeline(
                container_tag=None,
                days=365,
                group_by="month",
                current_user={"container_tag": "c", "key_id": "c"},
                _=None,
            )
        assert len(data["points"]) >= 12
        assert all(p["count"] == 0 for p in data["points"])

    @pytest.mark.asyncio
    async def test_last_bucket_is_local_today_in_shanghai(self):
        from datetime import datetime
        from zoneinfo import ZoneInfo
        with patch("src.api.stats._resolve_container", new=AsyncMock(return_value="c")), \
             patch("src.api.stats.db.fetch", new=AsyncMock(return_value=[])):
            data = await get_timeline(
                container_tag=None,
                days=30,
                group_by="day",
                tz="Asia/Shanghai",
                current_user={"container_tag": "c", "key_id": "c"},
                _=None,
            )
        assert data["points"][-1]["date"] == datetime.now(ZoneInfo("Asia/Shanghai")).date().isoformat()

    @pytest.mark.asyncio
    async def test_invalid_tz_falls_back_to_utc(self):
        from datetime import datetime, timezone
        with patch("src.api.stats._resolve_container", new=AsyncMock(return_value="c")), \
             patch("src.api.stats.db.fetch", new=AsyncMock(return_value=[])):
            data = await get_timeline(
                container_tag=None,
                days=30,
                group_by="day",
                tz="Not/AZone",
                current_user={"container_tag": "c", "key_id": "c"},
                _=None,
            )
        assert data["points"][-1]["date"] == datetime.now(timezone.utc).date().isoformat()


class TestResolveTz:
    def test_valid_tz_passes_through(self):
        assert _resolve_tz("Asia/Shanghai") == "Asia/Shanghai"
        assert _resolve_tz("UTC") == "UTC"
        assert _resolve_tz("America/New_York") == "America/New_York"

    def test_invalid_or_empty_falls_back_to_utc(self):
        assert _resolve_tz("Not/AZone") == "UTC"
        assert _resolve_tz("") == "UTC"
        assert _resolve_tz(None) == "UTC"


class TestOverview:
    @pytest.mark.asyncio
    async def test_overview_effective_caliber_fields(self):
        user = {"container_tag": "c", "key_id": "c"}
        containers = [
            {"container_tag": "c_hermes", "count": 1763, "active_count": 1129, "forgotten_count": 20},
            {"container_tag": "c", "count": 112, "active_count": 111, "forgotten_count": 1},
        ]
        with (
            patch("src.api.stats._resolve_container", new=AsyncMock(return_value="c")),
            patch("src.api.stats.db.fetch") as mock_fetch,
            patch("src.api.stats.db.fetchrow") as mock_fetchrow,
            patch("src.api.stats.db.fetchval") as mock_fetchval,
        ):
            mock_fetchrow.side_effect = [
                {
                    "total": 1240,
                    "static": 70,
                    "dynamic": 1170,
                    "inferred": 10,
                    "forgotten": 66,
                    "old_versions": 910,
                    "with_embedding": 2497,
                    "effective_embedding_count": 1239,
                    "all_rows": 2498,
                    "avg_confidence": 0.85,
                },
                {"total": 12, "done": 10, "total_tokens": 5000, "total_chunks": 100},
                {"total": 50, "errors": 2},
                {"total": 60, "ok": 58, "cache_hits": 40},
                {"processing": 0, "failed": 0},
                {"containers": 2, "static": 15, "dynamic": 30, "main_static": 10, "main_dynamic": 20, "main_last_updated": None, "last_updated": None},
            ]
            mock_fetch.side_effect = [
                [
                    {"relation_type": "extends", "count": 800},
                    {"relation_type": "updates", "count": 300},
                    {"relation_type": "derives", "count": 40},
                ],
                containers,
            ]
            mock_fetchval.side_effect = [9656, 123, 456]

            data = await get_overview(
                container_tag=None,
                current_user=user,
                _=None,
            )

        containers = data["containers"]
        assert containers[0]["active_count"] == 1129
        assert containers[0]["forgotten_count"] == 20
        assert containers[1]["active_count"] == 111
        assert sum(c["active_count"] for c in containers) == 1240
        assert data["memories"]["effective_embedding_count"] == 1239
        assert data["memories"]["with_embedding"] == 2497
        by_type = {r["relation_type"]: r["count"] for r in data["memory_relations_by_type"]}
        assert by_type == {"extends": 800, "updates": 300, "derives": 40}
        assert data["anomalies"]["processing"] == 0
        assert data["profiles"]["static"] == 15
        assert data["profiles"]["main_static"] == 10
        assert data["profiles"]["main_dynamic"] == 20


class TestEntities:
    @pytest.mark.asyncio
    async def test_memory_relation_types_included(self):
        user = {"container_tag": "c", "key_id": "c"}
        with (
            patch("src.api.stats._resolve_container", new=AsyncMock(return_value="c")),
            patch("src.api.stats.db.fetch") as mock_fetch,
            patch("src.api.stats.db.fetchval") as mock_fetchval,
        ):
            mock_fetch.side_effect = [
                [{"type": "person", "count": 10}],
                [{"name": "张三", "type": "person", "mention_count": 5}],
                [{"relation_type": "works_at", "count": 3, "avg_weight": 0.9}],
                [{"relation_type": "extends", "count": 2886, "avg_confidence": 0.85}],
            ]
            mock_fetchval.return_value = 2

            data = await get_entities(
                container_tag=None,
                top_n=10,
                current_user=user,
                _=None,
            )

        assert [r["relation_type"] for r in data["memory_relation_types"]] == ["extends"]
        assert data["memory_relation_types"][0]["count"] == 2886
        assert data["memory_relation_types"][0]["avg_confidence"] == 0.85
        assert data["relation_types"][0]["relation_type"] == "works_at"
        assert data["isolated_entities"] == 2


class TestActivity:
    @pytest.mark.asyncio
    async def test_tz_propagates_to_recall_trend(self):
        user = {"container_tag": "c", "key_id": "c"}
        with (
            patch("src.api.stats._resolve_container", new=AsyncMock(return_value="c")),
            patch(
                "src.api.stats.db.fetchrow",
                new=AsyncMock(return_value={"total": 5, "errors": 0, "avg_ms": 10.0, "p95_ms": 20.0}),
            ),
            patch("src.api.stats.db.fetch") as mock_fetch,
        ):
            mock_fetch.return_value = []

            data = await get_activity(
                container_tag=None,
                days=7,
                tz="Asia/Shanghai",
                current_user=user,
                _=None,
            )

        assert data["days"] == 7
        assert data["recalls"]["total"] == 5
        # 5 次 fetch 调用：mode_dist / recall_trend / emb_by_kind / emb_errors / top_queries
        calls = mock_fetch.call_args_list
        assert len(calls) == 5
        # recall_trend 是第 2 次调用，参数 (sql, exact, prefix, since, tz_name)
        assert calls[1].args[4] == "Asia/Shanghai"

    @pytest.mark.asyncio
    async def test_default_tz_is_utc(self):
        user = {"container_tag": "c", "key_id": "c"}
        with (
            patch("src.api.stats._resolve_container", new=AsyncMock(return_value="c")),
            patch(
                "src.api.stats.db.fetchrow",
                new=AsyncMock(return_value={"total": 0, "errors": 0, "avg_ms": None, "p95_ms": None}),
            ),
            patch("src.api.stats.db.fetch") as mock_fetch,
        ):
            mock_fetch.return_value = []
            await get_activity(
                container_tag=None,
                days=7,
                current_user=user,
                _=None,
            )
        calls = mock_fetch.call_args_list
        assert calls[1].args[4] == "UTC"
