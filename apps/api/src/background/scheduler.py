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
        try:
            await profile_service.invalidate_cache(row["container_tag"])
            await profile_service.get_profile(row["container_tag"])
        except Exception as e:
            print(f"Failed to rebuild profile for {row['container_tag']}: {e}")


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


async def forgotten_memories_cleanup_task() -> None:
    """Permanently delete soft-deleted memories older than 7 days."""
    from src.database import db

    retention_days = 7
    threshold = datetime.utcnow() - timedelta(days=retention_days)

    forgotten_memories = await db.fetch(
        """
        SELECT id FROM memories 
        WHERE is_forgotten = TRUE AND updated_at < $1
        """,
        threshold,
    )

    if not forgotten_memories:
        print(f"Forgotten memories cleanup: no memories to delete (threshold: {retention_days} days)")
        return

    memory_ids = [row["id"] for row in forgotten_memories]

    await db.execute(
        """
        DELETE FROM memory_entities 
        WHERE memory_id = ANY($1)
        """,
        memory_ids,
    )

    result = await db.execute(
        """
        DELETE FROM memories 
        WHERE is_forgotten = TRUE AND updated_at < $1
        """,
        threshold,
    )

    orphaned_entities = await db.execute(
        """
        DELETE FROM entities 
        WHERE id NOT IN (SELECT entity_id FROM memory_entities)
          AND id NOT IN (SELECT entity_id FROM chunk_entities)
        """
    )

    orphaned_relations = await db.execute(
        """
        DELETE FROM entity_relations 
        WHERE source_memory_id = ANY($1)
        """,
        memory_ids,
    )

    print(
        f"Forgotten memories cleanup: deleted {result} memories, "
        f"{orphaned_entities} orphaned entities, {orphaned_relations} orphaned relations "
        f"(threshold: {retention_days} days)"
    )


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
        name="forgotten_memories_cleanup",
        interval_seconds=86400,
        task_func=forgotten_memories_cleanup_task,
    )
