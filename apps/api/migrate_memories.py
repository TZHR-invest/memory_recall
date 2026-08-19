#!/usr/bin/env python3
"""
crystal 旧数据迁移脚本（M3 / Stage C，migration-script-design v1）

memories（v5 active 记忆）→ crystal.evidence（agent_add）→ 对账重生成 claim。
一次性全量、开发者触发、幂等可回放、断点续传；孤儿旧版本（is_latest=FALSE）不迁移。

用法：
    venv/bin/python migrate_memories.py --dry-run          # 只统计不写入
    venv/bin/python migrate_memories.py --owner <key_id>   # 限定单个 key 迁移
    venv/bin/python migrate_memories.py                    # 全量迁移

映射规则（migration-script-design §1）：
- is_latest=TRUE → evidence（source_kind=agent_add, scope/owner 从 container_tag 拆）
- is_latest=FALSE / is_forgotten=TRUE → 不迁移（v5 历史保留）
- 幂等键 = sha256("migrate:" + memory_id) 前 32 位 → 重跑跳过
"""

import argparse
import asyncio
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

sys.path.insert(0, str(Path(__file__).parent))

from src.database import db

from src.api.crystal.reconcile_service import reconcile_evidence

BATCH_SIZE = 100


def migrate_idempotency_key(memory_id: str) -> str:
    """迁移幂等键（migration-script-design §3.1）：sha256("migrate:"+memory_id) 前 32 位"""
    return hashlib.sha256(f"migrate:{memory_id}".encode("utf-8")).hexdigest()[:32]


def parse_container_tag(container_tag: str, api_keys_by_id: Dict[str, str]) -> Optional[Dict[str, Any]]:
    """container_tag → (scope, owner_id)。

    - {keyId}（uuid 无下划线）→ scope=NULL, owner_id=keyId
    - {keyId}_project-<dir> → scope='project-<dir>', owner_id=keyId
    - 其他 → None（无法归属，跳过 + 告警）

    api_keys_by_id: {key_id: user_id}（当前库中真实存在的 key；不存在的 key 的容器不迁移）
    """
    # 直接匹配用户级（uuid 形态，无下划线）
    if container_tag in api_keys_by_id:
        return {"scope": None, "owner_id": container_tag}
    # 项目级：{keyId}_project-<dir>
    for key_id in api_keys_by_id:
        prefix = f"{key_id}_project-"
        if container_tag.startswith(prefix):
            dir_part = container_tag[len(prefix):]
            return {"scope": f"project-{dir_part}", "owner_id": key_id}
    return None


async def _load_api_keys(conn) -> Dict[str, str]:
    """加载当前 active api_keys：{key_id: user_id}"""
    rows = await conn.fetch(
        "SELECT id::text AS id, user_id FROM api_keys WHERE is_active = TRUE"
    )
    return {r["id"]: r["user_id"] for r in rows}


async def _count_migratable(conn, owner_id: Optional[str]) -> int:
    """统计可迁移的 active 记忆数（is_latest=TRUE AND NOT is_forgotten）

    owner 过滤 = 该 key 的所有容器（用户级 {keyId} + 项目级 {keyId}_*）。
    """
    if owner_id:
        return await conn.fetchval(
            """SELECT COUNT(*) FROM memories
               WHERE is_latest = TRUE AND is_forgotten = FALSE
                 AND (container_tag = $1 OR container_tag LIKE $1 || '\_%')""",
            owner_id,
        )
    return await conn.fetchval(
        "SELECT COUNT(*) FROM memories WHERE is_latest = TRUE AND is_forgotten = FALSE"
    )


async def _load_batch(
    conn,
    owner_id: Optional[str],
    last_memory_id: Optional[str],
    limit: int = BATCH_SIZE,
) -> List[Any]:
    """按 memory id 排序分页取一批（断点续传：> last_memory_id）

    owner 过滤 = 该 key 的所有容器（用户级 {keyId} + 项目级 {keyId}_*）。
    """
    if owner_id:
        return await conn.fetch(
            """SELECT id, container_tag, content, created_at, metadata, is_latest, is_forgotten
               FROM memories
               WHERE is_latest = TRUE AND is_forgotten = FALSE
                 AND (container_tag = $1 OR container_tag LIKE $1 || '\_%')
                 AND id > $2
               ORDER BY id
               LIMIT $3""",
            owner_id,
            last_memory_id or "",
            limit,
        )
    return await conn.fetch(
        """SELECT id, container_tag, content, created_at, metadata, is_latest, is_forgotten
           FROM memories
           WHERE is_latest = TRUE AND is_forgotten = FALSE
             AND id > $1
           ORDER BY id
           LIMIT $2""",
        last_memory_id or "",
        limit,
    )


async def _migrate_one(
    conn,
    memory: Any,
    api_keys_by_id: Dict[str, str],
    dry_run: bool = False,
) -> str:
    """迁移单条 memory → evidence（返回 migrated/skipped/failed）"""
    parsed = parse_container_tag(memory["container_tag"], api_keys_by_id)
    if parsed is None:
        return "skipped"  # 无法归属

    idem_key = migrate_idempotency_key(memory["id"])

    if dry_run:
        return "migrated"  # dry-run 只统计

    # 幂等查重
    existing = await conn.fetchval(
        """SELECT id FROM crystal.evidence
           WHERE owner_type='personal' AND owner_id=$1 AND idempotency_key=$2""",
        parsed["owner_id"],
        idem_key,
    )
    if existing:
        return "skipped"  # 已迁移

    # 落 evidence + processing
    ev_id = await conn.fetchval(
        """INSERT INTO crystal.evidence
           (observed_at, source_kind, content, scope, owner_type, owner_id,
            source_ref, extraction_type, idempotency_key, created_at)
           VALUES ($1, 'agent_add', $2, $3, 'personal', $4, $5, 'paraphrase', $6, NOW())
           RETURNING id""",
        memory["created_at"] or datetime.now(timezone.utc),
        memory["content"],
        parsed["scope"],
        parsed["owner_id"],
        json.dumps({"migrated_from_memory_id": memory["id"]}),
        idem_key,
    )
    await conn.execute(
        """INSERT INTO crystal.evidence_processing
           (evidence_id, processing_state, current_step, updated_at)
           VALUES ($1, 'pending', 'embedding', NOW())""",
        ev_id,
    )
    return "migrated"


async def run_migration(
    owner_id: Optional[str] = None,
    dry_run: bool = False,
    run_id: Optional[str] = None,
) -> Dict[str, Any]:
    """执行迁移（脚本 + admin 端点共用）。

    返回 {run_id, total, migrated, skipped, failed, status}。
    """
    import uuid

    run_id = run_id or f"mig_{uuid.uuid4().hex[:12]}"
    stats = {"run_id": run_id, "total": 0, "migrated": 0, "skipped": 0, "failed": 0}

    async with db.get_connection() as conn:
        api_keys_by_id = await _load_api_keys(conn)
        stats["total"] = await _count_migratable(conn, owner_id)
        if stats["total"] == 0:
            stats["status"] = "done"
            return stats

        if not dry_run:
            await conn.execute(
                """INSERT INTO crystal.migration_state
                   (run_id, owner_id, total, status, created_at, updated_at)
                   VALUES ($1, $2, $3, 'running', NOW(), NOW())""",
                run_id,
                owner_id,
                stats["total"],
            )

        # 断点续传：从上次 last_memory_id 继续
        last_memory_id = None
        if not dry_run:
            last_memory_id = await conn.fetchval(
                """SELECT last_memory_id FROM crystal.migration_state
                   WHERE run_id=$1 ORDER BY updated_at DESC LIMIT 1""",
                run_id,
            )

        while True:
            batch = await _load_batch(conn, owner_id, last_memory_id)
            if not batch:
                break
            for memory in batch:
                try:
                    result = await _migrate_one(conn, memory, api_keys_by_id, dry_run)
                    stats[result] += 1
                    last_memory_id = memory["id"]
                except Exception as e:
                    stats["failed"] += 1
                    print(f"✗ 迁移失败 memory={memory['id']}: {e}")
            # 每批后更新断点
            if not dry_run:
                await conn.execute(
                    """UPDATE crystal.migration_state
                       SET migrated=$1, skipped=$2, failed=$3, last_memory_id=$4, updated_at=NOW()
                       WHERE run_id=$5""",
                    stats["migrated"],
                    stats["skipped"],
                    stats["failed"],
                    last_memory_id,
                    run_id,
                )
            if len(batch) < BATCH_SIZE:
                break

        if not dry_run:
            await conn.execute(
                """UPDATE crystal.migration_state
                   SET status='done', updated_at=NOW()
                   WHERE run_id=$1""",
                run_id,
            )
        stats["status"] = "done" if stats["failed"] == 0 else "failed"
        return stats


async def reconcile_migrated(
    owner_id: Optional[str] = None,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """迁移后对账重生成 claim（migration-script-design §5.2：同步逐条对账）。

    对 evidence_processing 中 pending 的迁移 evidence 逐条对账。
    """
    stats = {"reconciled": 0, "failed": 0}
    if dry_run:
        return stats
    async with db.get_connection() as conn:
        if owner_id:
            rows = await conn.fetch(
                """SELECT p.evidence_id FROM crystal.evidence_processing p
                   JOIN crystal.evidence e ON e.id = p.evidence_id
                   WHERE p.processing_state IN ('pending','failed')
                     AND e.owner_id=$1 AND e.source_ref->>'migrated_from_memory_id' IS NOT NULL
                   LIMIT 500""",
                owner_id,
            )
        else:
            rows = await conn.fetch(
                """SELECT p.evidence_id FROM crystal.evidence_processing p
                   JOIN crystal.evidence e ON e.id = p.evidence_id
                   WHERE p.processing_state IN ('pending','failed')
                     AND e.source_ref->>'migrated_from_memory_id' IS NOT NULL
                   LIMIT 500"""
            )
    for r in rows:
        try:
            result = await reconcile_evidence(r["evidence_id"])
            if result.get("status") in ("done", "already_processing"):
                stats["reconciled"] += 1
            else:
                stats["failed"] += 1
        except Exception as e:
            stats["failed"] += 1
            print(f"✗ 对账失败 evidence={r['evidence_id']}: {e}")
    return stats


async def main():
    parser = argparse.ArgumentParser(description="crystal 旧数据迁移（memories → evidence → claim）")
    parser.add_argument("--dry-run", action="store_true", help="只统计不写入")
    parser.add_argument("--owner", type=str, default=None, help="限定单个 key_id 迁移")
    parser.add_argument("--reconcile-only", action="store_true", help="只对账已迁移的 pending evidence，不迁移")
    args = parser.parse_args()

    await db.connect()
    try:
        if args.reconcile_only:
            stats = await reconcile_migrated(args.owner, args.dry_run)
            print(f"对账完成: {stats}")
            return

        stats = await run_migration(args.owner, args.dry_run)
        print(f"迁移统计: total={stats['total']} migrated={stats['migrated']} "
              f"skipped={stats['skipped']} failed={stats['failed']} status={stats['status']}")

        if not args.dry_run:
            print("开始对账重生成 claim...")
            rc = await reconcile_migrated(args.owner)
            print(f"对账统计: {rc}")
    finally:
        await db.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
