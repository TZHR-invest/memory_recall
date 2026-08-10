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

from src.api.stats import get_timeline, get_overview, _resolve_container


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
                {"containers": 2, "static": 15, "dynamic": 30, "last_updated": None},
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
