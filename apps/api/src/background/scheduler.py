"""
Background Task Scheduler

Runs periodic tasks:
- Profile rebuild (every 5 min)
- Cache invalidation (every 10 min)
"""

import asyncio
from typing import Optional, Callable, List
from datetime import datetime, timedelta
from dataclasses import dataclass


@dataclass
class TaskConfig:
    name: str
    interval_seconds: int
    task_func: Callable
    last_run: Optional[datetime] = None
    is_running: bool = False


class BackgroundScheduler:
    def __init__(self):
        self.tasks: List[TaskConfig] = []
        self._running = False
        self._task: Optional[asyncio.Task] = None

    def register_task(
        self,
        name: str,
        interval_seconds: int,
        task_func: Callable,
    ) -> None:
        self.tasks.append(
            TaskConfig(
                name=name,
                interval_seconds=interval_seconds,
                task_func=task_func,
            )
        )

    async def start(self) -> None:
        """启动调度器（作为后台任务运行，不阻塞）"""
        self._running = True
        self._task = asyncio.create_task(self._run_loop())

    async def stop(self) -> None:
        """停止调度器"""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    async def _run_loop(self) -> None:
        while self._running:
            now = datetime.utcnow()

            for task in self.tasks:
                if task.is_running:
                    continue

                if (
                    task.last_run is None
                    or (now - task.last_run).total_seconds() >= task.interval_seconds
                ):
                    asyncio.create_task(self._run_task(task))

            await asyncio.sleep(60)

    async def _run_task(self, task: TaskConfig) -> None:
        task.is_running = True
        try:
            await task.task_func()
            task.last_run = datetime.utcnow()
        except Exception as e:
            print(f"Background task '{task.name}' failed: {e}")
        finally:
            task.is_running = False


scheduler = BackgroundScheduler()


async def profile_rebuild_task() -> None:
    """Rebuild stale user profiles."""
    from src.database import db
    from src.services.core.profile_service import profile_service

    stale_threshold = datetime.utcnow() - timedelta(minutes=10)

    rows = await db.fetch(
        """
        SELECT DISTINCT container_tag FROM memories
        WHERE created_at > $1
        """,
        stale_threshold,
    )

    for row in rows:
        container_tag = row["container_tag"]
        # 用户级容器 tag = keyId (UUID, 无下划线); 子容器 (project/hermes) 画像
        # 运行时无人消费, 跳过重建避免产生死缓存
        if "_" in container_tag:
            continue
        try:
            await profile_service.invalidate_cache(container_tag)
            await profile_service.get_profile(container_tag)
        except Exception as e:
            print(f"Failed to rebuild profile for {container_tag}: {e}")


async def cache_cleanup_task() -> None:
    """Clean up old cache entries."""
    from src.database import db

    old_threshold = datetime.utcnow() - timedelta(hours=1)

    result = await db.execute(
        """
        UPDATE memory_profiles 
        SET last_updated = '1970-01-01'::timestamp
        WHERE last_updated < $1
        """,
        old_threshold,
    )

    print(f"Cache cleanup: {result}")


async def trace_cleanup_task() -> None:
    """Delete recall traces older than retention window."""
    from src.config import settings
    from src.services.core.recall_trace_service import recall_trace_service

    deleted = await recall_trace_service.cleanup(settings.TRACE_RETENTION_DAYS)
    print(f"Trace cleanup: deleted {deleted} records")


def setup_background_tasks() -> None:
    scheduler.register_task(
        name="profile_rebuild",
        interval_seconds=300,
        task_func=profile_rebuild_task,
    )

    scheduler.register_task(
        name="cache_cleanup",
        interval_seconds=600,
        task_func=cache_cleanup_task,
    )

    scheduler.register_task(
        name="trace_cleanup",
        interval_seconds=3600,
        task_func=trace_cleanup_task,
    )
