"""
Background Task Scheduler

Runs periodic tasks:
- Profile rebuild (every 5 min)
- Expiration check (daily)
- Cleanup (daily)
"""

import asyncio
from typing import Optional, Callable, List
from datetime import datetime, time
from dataclasses import dataclass


@dataclass
class TaskConfig:
    name: str
    interval_seconds: int
    task_func: Callable
    last_run: Optional[datetime] = None
    is_running: bool = False


class BackgroundScheduler:
    """Background task scheduler"""

    def __init__(self):
        self.tasks: List[TaskConfig] = []
        self._running = False

    def register_task(
        self,
        name: str,
        interval_seconds: int,
        task_func: Callable,
    ) -> None:
        """Register a periodic task"""
        self.tasks.append(
            TaskConfig(
                name=name,
                interval_seconds=interval_seconds,
                task_func=task_func,
            )
        )

    async def start(self) -> None:
        """Start the scheduler"""
        self._running = True
        await self._run_loop()

    async def stop(self) -> None:
        """Stop the scheduler"""
        self._running = False

    async def _run_loop(self) -> None:
        """Main scheduler loop"""
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
        """Run a single task"""
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
    """Rebuild dirty user profiles"""
    from src.database import db
    from src.services.evolution.user_profile_service import user_profile_service

    rows = await db.fetch(
        """
        SELECT user_id FROM user_profiles
        WHERE is_dirty = TRUE
        LIMIT 10
        """
    )

    for row in rows:
        try:
            await user_profile_service.rebuild(row["user_id"])
        except Exception as e:
            print(f"Failed to rebuild profile for {row['user_id']}: {e}")


async def expiration_check_task() -> None:
    """Check for memories expiring soon"""
    from src.database import db
    from src.services.evolution.forgetting_service import forgetting_service

    rows = await db.fetch(
        """
        SELECT DISTINCT user_id FROM raw_messages
        WHERE is_expired = FALSE
          AND expiration_date BETWEEN NOW() AND NOW() + INTERVAL '7 days'
        """
    )

    for row in rows:
        try:
            expiring = await forgetting_service.get_expiring_soon(
                row["user_id"], days=7
            )

            for memory in expiring[:5]:
                from datetime import datetime
                import uuid

                await db.execute(
                    """
                    INSERT INTO notifications (id, user_id, notification_type, memory_id, message, created_at)
                    VALUES ($1, $2, 'expiration_warning', $3, $4, $5)
                    ON CONFLICT DO NOTHING
                    """,
                    str(uuid.uuid4()),
                    row["user_id"],
                    memory["id"],
                    f"Memory expiring soon: {memory['content'][:50]}...",
                    datetime.utcnow(),
                )
        except Exception as e:
            print(f"Expiration check failed for {row['user_id']}: {e}")


async def cleanup_task() -> None:
    """Clean up old expired memories and orphaned chunks"""
    from src.database import db
    from src.services.evolution.forgetting_service import forgetting_service

    expired_deleted = await db.fetchval(
        """
        DELETE FROM raw_messages
        WHERE is_expired = TRUE
          AND expiration_date < NOW() - INTERVAL '30 days'
        RETURNING COUNT(*)
        """
    )

    chunks_deleted = await db.fetchval(
        """
        DELETE FROM content_chunks
        WHERE memory_id NOT IN (SELECT id FROM raw_messages)
        RETURNING COUNT(*)
        """
    )

    print(
        f"Cleanup: deleted {expired_deleted} expired memories, {chunks_deleted} orphaned chunks"
    )


def setup_background_tasks() -> None:
    """Register all background tasks"""
    scheduler.register_task(
        name="profile_rebuild",
        interval_seconds=300,  # 5 minutes
        task_func=profile_rebuild_task,
    )

    scheduler.register_task(
        name="expiration_check",
        interval_seconds=86400,  # 24 hours
        task_func=expiration_check_task,
    )

    scheduler.register_task(
        name="cleanup",
        interval_seconds=86400,  # 24 hours
        task_func=cleanup_task,
    )
