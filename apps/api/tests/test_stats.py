"""
Tests for the personal data stats API:
- timeline zero-filling logic
- overview container resolution
"""

import sys
import os
from unittest.mock import AsyncMock, patch

import pytest

sys.path.insert(
    0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)

from src.api.stats import get_timeline, _resolve_container


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
