"""
crystal 对账后台 worker（reconciliation-design §1/§2.1）

- 轮询扫描 evidence_processing WHERE state IN (pending, processing, failed)
- processing 超时（updated_at < NOW()-30s）视为死锁重新认领
- 单 worker 串行 + batch（batch_size=50），避免同 evidence 并发对账
- 独立 asyncio 任务（5s 粒度），不走 scheduler 的 60s 循环；生命周期挂 main.py lifespan
"""

import asyncio
import json
import logging
from datetime import timedelta
from typing import Optional

from src.database import db

from .reconcile_service import reconcile_evidence

logger = logging.getLogger(__name__)

SCAN_INTERVAL_SECONDS = 5  # 轮询间隔
BATCH_SIZE = 50
PROCESSING_TIMEOUT_SECONDS = 30  # processing 超时兜底


async def _claim_batch() -> list:
    """认领一批待对账 evidence（CAS 防并发）：
    pending/processing/failed 且 updated_at < NOW()-30s（processing 超时兜底）。
    排除 M2.1 双上限隔离项（current_step='isolated'，留存 workbench 待裁决，不自动重试）。
    """
    async with db.get_connection() as conn:
        rows = await conn.fetch(
            """SELECT p.evidence_id
               FROM crystal.evidence_processing p
               WHERE (p.processing_state IN ('pending', 'failed')
                      OR (p.processing_state = 'processing'
                          AND p.updated_at < NOW() - interval '30 seconds'))
                 AND p.current_step IS DISTINCT FROM 'isolated'
               ORDER BY p.updated_at ASC
               LIMIT $1
               FOR UPDATE SKIP LOCKED""",
            BATCH_SIZE,
        )
        ids = [r["evidence_id"] for r in rows]
        if not ids:
            return []
        # CAS 认领：只认领仍处于可处理状态的
        await conn.execute(
            """UPDATE crystal.evidence_processing
               SET processing_state='processing', current_step='embedding', updated_at=NOW()
               WHERE evidence_id = ANY($1::text[])
                 AND processing_state IN ('pending','processing','failed')""",
            ids,
        )
        return ids


async def crystal_reconcile_task() -> None:
    """对账 worker 单轮处理（扫描 + 逐条对账）"""
    try:
        batch = await _claim_batch()
        for evidence_id in batch:
            try:
                await reconcile_evidence(evidence_id)
            except Exception as e:
                logger.error(f"crystal 对账 worker 单条失败 evidence={evidence_id}: {e}")
                # reconcile_evidence 内部已处理 failed 状态；这里兜底防 worker 崩溃
                try:
                    async with db.get_connection() as conn:
                        await conn.execute(
                            """UPDATE crystal.evidence_processing
                               SET processing_state='failed',
                                   last_error=COALESCE(last_error, '{}'::jsonb) || $2::jsonb,
                                   updated_at=NOW()
                               WHERE evidence_id=$1""",
                            evidence_id,
                            json.dumps(
                                {"step": "worker", "message": str(e), "attempts": 1}
                            ),
                        )
                except Exception as e2:
                    logger.error(f"crystal 对账 worker 标记 failed 也失败: {e2}")
        if batch:
            logger.info(f"crystal 对账 worker: 处理 {len(batch)} 条")
    except Exception as e:
        logger.error(f"crystal 对账 worker 扫描失败: {e}")


async def crystal_reconcile_loop(stop_event: asyncio.Event) -> None:
    """对账 worker 自旋循环（独立 asyncio 任务，5s 轮询）。

    不走 scheduler 的 60s 循环（scheduler._run_loop 每 60s 才检查任务，
    对账要 5s 粒度）；复用 scheduler 生命周期由 main.py lifespan 启停。
    """
    logger.info("crystal 对账 worker 启动")
    while not stop_event.is_set():
        try:
            await crystal_reconcile_task()
        except Exception as e:
            logger.error(f"crystal 对账 worker 循环异常: {e}")
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=SCAN_INTERVAL_SECONDS)
        except asyncio.TimeoutError:
            pass
    logger.info("crystal 对账 worker 停止")


_worker_task: Optional[asyncio.Task] = None
_stop_event: Optional[asyncio.Event] = None


def start_crystal_worker() -> None:
    """启动对账 worker（main.py lifespan 调用）"""
    global _worker_task, _stop_event
    if _worker_task is not None and not _worker_task.done():
        return
    _stop_event = asyncio.Event()
    _worker_task = asyncio.create_task(crystal_reconcile_loop(_stop_event))


def stop_crystal_worker() -> None:
    """停止对账 worker（main.py lifespan 调用）"""
    global _worker_task, _stop_event
    if _stop_event is not None:
        _stop_event.set()
    if _worker_task is not None:
        try:
            _worker_task.cancel()
        except Exception:
            pass
        _worker_task = None
        _stop_event = None
