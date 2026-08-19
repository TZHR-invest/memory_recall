#!/usr/bin/env python3
"""
crystal schema 初始化脚本（M1 / Stage A 专用）

只执行 schema.sql 中的 crystal 段（`crystal.*` 命名空间），幂等可重跑。

为什么独立脚本：
- `init_db.py` 全量执行 schema.sql 在**已建库**上会失败——schema.sql 的 v5 段含 6 处
  非幂等 `ALTER TABLE ... ADD CONSTRAINT`（PG 不支持 IF NOT EXISTS），正式库约束已存在
  时 DuplicateTableError，crystal 段永远执行不到（2026-08-18 实测）。
- crystal 是绿地（新表），用命名空间隔离（migration-path §5：不引入迁移框架），
  只需幂等建 crystal.* 表，绝不触碰 v5 段。
- 回退 = `DROP SCHEMA crystal CASCADE`（migration-path Stage A）。

用法：
    venv/bin/python init_crystal_db.py
"""

import asyncio
import sys
from pathlib import Path

# 添加 apps/api 目录到 Python 路径
sys.path.insert(0, str(Path(__file__).parent))

from src.database import db


CRYSTAL_START_MARKER = "-- 12. crystal schema"
CRYSTAL_END_MARKER = "-- Complete"


def extract_crystal_section(schema_sql: str) -> str:
    """提取 schema.sql 中的 crystal 段（从 crystal 标记到 Complete 前）。"""
    start = schema_sql.index(CRYSTAL_START_MARKER)
    end = schema_sql.index(CRYSTAL_END_MARKER)
    return schema_sql[start:end]


async def init_crystal_schema():
    """初始化 crystal schema（幂等）"""
    print("=" * 60)
    print("Memory Recall - crystal schema 初始化（M1 / Stage A）")
    print("=" * 60)
    print()

    schema_file = Path(__file__).parent / "schema.sql"
    if not schema_file.exists():
        print(f"✗ 错误：找不到 schema.sql 文件: {schema_file}")
        sys.exit(1)

    print(f"读取 schema 文件: {schema_file}")
    with open(schema_file, "r", encoding="utf-8") as f:
        sql = f.read()

    crystal_sql = extract_crystal_section(sql)
    print(f"提取 crystal 段: {len(crystal_sql)} 字符（仅 crystal.* 命名空间，不触碰 v5 段）")

    # crystal 表演进增量段（migration-path §5：幂等 ALTER ... IF NOT EXISTS，先观察再决定是否上 Alembic）
    # 2026-08-18: evidence 加 idempotency_key（M1 幂等落库依据，entity-attributes §2）。
    # 注：schema.sql 已含 idempotency_key 列 + 索引（新库全量建）；本段仅服务"既有库增量"，
    #     幂等 IF NOT EXISTS 双跑安全。
    # 2026-08-19: crystal.workbench_review 表（G1 召回复盘 trace 落库，workbench 设计 §5）——
    #     schema.sql 已含（新库全量建）；本段服务既有库增量，IF NOT EXISTS 双跑安全。
    crystal_migrations = [
        (
            "ALTER TABLE crystal.evidence ADD COLUMN IF NOT EXISTS idempotency_key TEXT;"
            "CREATE INDEX IF NOT EXISTS idx_crystal_evidence_idempotency"
            " ON crystal.evidence(idempotency_key) WHERE idempotency_key IS NOT NULL;"
        ),
        (
            "CREATE TABLE IF NOT EXISTS crystal.workbench_review ("
            " id TEXT PRIMARY KEY DEFAULT 'wr_' || substr(replace(gen_random_uuid()::text, '-', ''), 1, 22),"
            " owner_type TEXT NOT NULL CHECK (owner_type IN ('personal', 'team')),"
            " owner_id TEXT NOT NULL,"
            " scope TEXT,"
            " query TEXT,"
            " source TEXT NOT NULL DEFAULT 'search' CHECK (source IN ('search', 'context_inject')),"
            " trace_json JSONB NOT NULL,"
            " created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()"
            ");"
            "CREATE INDEX IF NOT EXISTS idx_crystal_workbench_review_owner"
            " ON crystal.workbench_review(owner_type, owner_id, created_at DESC);"
            "CREATE INDEX IF NOT EXISTS idx_crystal_workbench_review_owner_scope"
            " ON crystal.workbench_review(owner_type, owner_id, scope);"
        ),
    ]

    print("连接数据库...")
    await db.connect()

    try:
        print("执行 crystal schema 初始化...")
        await db.execute(crystal_sql)
        for migration in crystal_migrations:
            await db.execute(migration)
        print()
        print("=" * 60)
        print("✓ crystal schema 初始化成功（幂等）！")
        print("=" * 60)
        print()
        print("已创建的表（crystal.*）：")
        print("  - evidence (不可再生原始观察)")
        print("  - evidence_processing (处理状态机 1:1)")
        print("  - claim (派生主张)")
        print("  - lineage_edge (谱系边)")
        print("  - claim_activity (变更审计日志)")
        print("  - claim_evidence (Claim↔Evidence 支持关系)")
        print("  - claim_usage (复用/outcome 离散价值信号)")
        print("  - workbench_review (召回复盘 trace 落库)")
        print()
        print("回退：DROP SCHEMA crystal CASCADE")

    except Exception as e:
        print()
        print("=" * 60)
        print(f"✗ 初始化失败: {e}")
        print("=" * 60)
        raise
    finally:
        await db.disconnect()


if __name__ == "__main__":
    asyncio.run(init_crystal_schema())
