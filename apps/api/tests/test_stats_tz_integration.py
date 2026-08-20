"""
Integration tests for stats timeline timezone handling.

Verifies that `(created_at AT TIME ZONE $tz)::date` assigns memories to the
bucket of the *requested* timezone rather than the DB session timezone
(e.g. a memory written at 18:30 UTC = 02:30 next day Asia/Shanghai must
land on the Shanghai date when tz=Asia/Shanghai, and on the UTC date when
tz=UTC).

Skipped automatically when the database is unreachable.
"""

import os
import sys
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch
from zoneinfo import ZoneInfo

import pytest

sys.path.insert(
    0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)

from src.api.stats import get_timeline
from src.database import db


@pytest.mark.asyncio
async def test_timeline_bucket_follows_requested_timezone():
    try:
        # 先断开可能由其他模块（如 crystal 集成测试）在别的 event loop 上创建的全局池，
        # 再在当前 loop 上重建 —— 规避 asyncpg "attached to a different loop"（TESTING.md §环境注意点）
        await db.disconnect()
        await db.connect()
    except Exception:
        pytest.skip("database unavailable")

    key_id = f"tztest_{uuid.uuid4().hex[:8]}"
    container_tag = f"{key_id}_tztest"
    # 30 天前的 18:30 UTC = 上海次日 02:30，保证 UTC 与上海日期必然不同
    anchor_utc = (datetime.now(timezone.utc) - timedelta(days=30)).replace(
        hour=18, minute=30, second=0, microsecond=0
    )
    shanghai_date = anchor_utc.astimezone(ZoneInfo("Asia/Shanghai")).date()
    assert shanghai_date != anchor_utc.date()

    mem_id = None
    try:
        row = await db.fetchrow(
            """
            INSERT INTO memories (container_tag, content, created_at, is_latest, is_forgotten)
            VALUES ($1, $2, $3, TRUE, FALSE)
            RETURNING id
            """,
            container_tag,
            f"tz integration test {uuid.uuid4().hex[:6]}",
            anchor_utc,
        )
        mem_id = row["id"]

        with patch(
            "src.api.stats._resolve_container", new=AsyncMock(return_value=container_tag)
        ):
            data_sh = await get_timeline(
                container_tag=None,
                days=60,
                group_by="day",
                tz="Asia/Shanghai",
                current_user={"container_tag": container_tag, "key_id": key_id},
                _=None,
            )
            data_utc = await get_timeline(
                container_tag=None,
                days=60,
                group_by="day",
                tz="UTC",
                current_user={"container_tag": container_tag, "key_id": key_id},
                _=None,
            )

        by_date_sh = {p["date"]: p["count"] for p in data_sh["points"]}
        by_date_utc = {p["date"]: p["count"] for p in data_utc["points"]}
        assert by_date_sh.get(shanghai_date.isoformat(), 0) >= 1, (
            f"memory not bucketed on Shanghai date {shanghai_date.isoformat()}"
        )
        assert by_date_utc.get(anchor_utc.date().isoformat(), 0) >= 1, (
            f"memory not bucketed on UTC date {anchor_utc.date().isoformat()}"
        )
    finally:
        if mem_id:
            await db.execute("DELETE FROM memories WHERE id = $1", mem_id)
