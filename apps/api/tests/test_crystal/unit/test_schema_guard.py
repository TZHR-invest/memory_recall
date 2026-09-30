"""crystal /api/v2 部署前置闸门（MR-027 D4，2026-09-30）

v2 路由随代码挂载，但 crystal schema 只在执行过 init_crystal_db.py 的库存在。
生产库未初始化时，任何 v2 请求此前都撞 `relation "crystal.claim" does not exist` 并
以**裸 500** 返回（把"未部署"伪装成内部错误）。闸门改为 503 + 统一信封 + 处置指引。
"""

import sys
import os
from unittest.mock import AsyncMock, patch

import pytest

sys.path.insert(
    0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)

from src.api.crystal.errors import CrystalAPIError
from src.api.crystal.guards import (
    reset_crystal_schema_cache,
    require_crystal_schema,
)


@pytest.fixture(autouse=True)
def _clean_cache():
    reset_crystal_schema_cache()
    yield
    reset_crystal_schema_cache()


class TestCrystalSchemaGuard:
    @pytest.mark.asyncio
    async def test_schema_present_passes(self):
        with patch("src.api.crystal.guards.db") as db_mock:
            db_mock.fetchval = AsyncMock(return_value=True)
            await require_crystal_schema()

    @pytest.mark.asyncio
    async def test_schema_missing_raises_503_with_guidance(self):
        with patch("src.api.crystal.guards.db") as db_mock:
            db_mock.fetchval = AsyncMock(return_value=False)
            with pytest.raises(CrystalAPIError) as ei:
                await require_crystal_schema()

        assert ei.value.status_code == 503
        assert "init_crystal_db.py" in ei.value.message
        assert "crystal schema" in ei.value.message

    @pytest.mark.asyncio
    async def test_probe_failure_is_fail_open(self):
        """DB 抖动不该被伪装成"未部署"：探测异常时放行，由端点自身报错。"""
        with patch("src.api.crystal.guards.db") as db_mock:
            db_mock.fetchval = AsyncMock(side_effect=RuntimeError("connection reset"))
            await require_crystal_schema()  # 不抛

    @pytest.mark.asyncio
    async def test_result_cached_within_ttl(self):
        with patch("src.api.crystal.guards.db") as db_mock:
            db_mock.fetchval = AsyncMock(return_value=True)
            await require_crystal_schema()
            await require_crystal_schema()
            assert db_mock.fetchval.await_count == 1, "TTL 内应命中缓存，不重复探测"

    @pytest.mark.asyncio
    async def test_missing_state_cached_and_keeps_failing(self):
        with patch("src.api.crystal.guards.db") as db_mock:
            db_mock.fetchval = AsyncMock(return_value=False)
            for _ in range(2):
                with pytest.raises(CrystalAPIError) as ei:
                    await require_crystal_schema()
                assert ei.value.status_code == 503
            assert db_mock.fetchval.await_count == 1
