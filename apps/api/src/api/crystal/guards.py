"""crystal /api/v2 部署前置闸门（MR-027 D4，2026-09-30）

背景：v2 路由随代码一起挂载，但 crystal schema 只存在于**已执行 init_crystal_db.py** 的库。
生产库（memory_recall，本机 206）从未初始化 ⇒ 任何 `/api/v2/*` 请求都撞
`relation "crystal.claim" does not exist` 并以**裸 500** 返回——把"未部署"伪装成内部错误，
排查者要翻日志才知道是 schema 缺失（2026-09-30 .205 侧实测报告即为此）。

本闸门把该状态显式化为 503 + 统一信封（`code=503`），并给出可执行的处置指引；
schema 就绪时不产生任何行为变化（只多一次每 TTL 一次的 `to_regclass` 探测）。
"""

import logging
import time


from src.database import db

from .errors import CrystalAPIError

logger = logging.getLogger(__name__)

# 探测结果缓存时长：schema 属部署态，60s 粒度足够；避免每个 v2 请求都查一遍 pg_class
_SCHEMA_CHECK_TTL_SECONDS = 60
_SCHEMA_STATE = {"checked_at": 0.0, "ready": True}

_SCHEMA_MISSING_MESSAGE = (
    "crystal schema 未初始化：/api/v2 在当前数据库尚未部署。"
    "请在 apps/api 目录执行 `venv/bin/python init_crystal_db.py`（幂等）后重试；"
    "若目标不是当前库，先核对 DATABASE_NAME/DATABASE_HOST 指向。"
)


async def require_crystal_schema() -> None:
    """v2 前置依赖：schema 缺失 ⇒ 503（统一信封），其余情况放行。"""
    now = time.monotonic()
    if now - _SCHEMA_STATE["checked_at"] < _SCHEMA_CHECK_TTL_SECONDS:
        if not _SCHEMA_STATE["ready"]:
            raise CrystalAPIError(503, _SCHEMA_MISSING_MESSAGE)
        return

    try:
        ready = await db.fetchval("SELECT to_regclass('crystal.claim') IS NOT NULL")
    except Exception as e:  # noqa: BLE001 —— 探测失败 fail-open：DB 抖动不该伪装成"未部署"
        logger.warning("crystal schema 探测失败（放行请求，交由端点自身报错）: %s", e)
        return

    _SCHEMA_STATE["checked_at"] = now
    _SCHEMA_STATE["ready"] = bool(ready)
    if not ready:
        raise CrystalAPIError(503, _SCHEMA_MISSING_MESSAGE)


# 供测试重置缓存（避免模块级缓存跨用例串味）
def reset_crystal_schema_cache() -> None:
    _SCHEMA_STATE["checked_at"] = 0.0
    _SCHEMA_STATE["ready"] = True
