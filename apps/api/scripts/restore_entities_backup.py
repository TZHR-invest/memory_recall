#!/usr/bin/env python3
"""
实体表恢复脚本

功能:
- 从备份 SQL 文件恢复 entities 表

用法:
    python restore_entities_backup.py <backup_file>
"""

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.database import db


async def restore_backup(backup_file: str):
    print(f"正在从 {backup_file} 恢复...")
    
    with open(backup_file, 'r', encoding='utf-8') as f:
        sql_content = f.read()
    
    print("清空现有表...")
    await db.execute("TRUNCATE TABLE memory_entities CASCADE")
    await db.execute("TRUNCATE TABLE entity_relations CASCADE")
    await db.execute("TRUNCATE TABLE entities CASCADE")
    
    print("执行恢复...")
    statements = [s.strip() for s in sql_content.split(';') if s.strip() and not s.strip().startswith('--')]
    
    for i, statement in enumerate(statements):
        if statement:
            try:
                await db.execute(statement)
                if (i + 1) % 100 == 0:
                    print(f"  已执行 {i + 1}/{len(statements)} 条语句")
            except Exception as e:
                print(f"  警告: 第 {i + 1} 条语句执行失败: {e}")
    
    total = await db.fetchval("SELECT COUNT(*) FROM entities")
    print(f"\n恢复完成! 共恢复 {total} 个实体")


async def main():
    parser = argparse.ArgumentParser(description="实体表恢复脚本")
    parser.add_argument("backup_file", help="备份 SQL 文件路径")
    
    args = parser.parse_args()
    
    print("=" * 60)
    print("实体表恢复")
    print("=" * 60)
    
    print(f"\n警告: 这将删除当前所有实体数据!")
    print("确认继续? [y/N]: ", end="")
    confirmation = input().strip().lower()
    
    if confirmation != 'y':
        print("已取消恢复")
        sys.exit(0)
    
    await restore_backup(args.backup_file)


if __name__ == "__main__":
    asyncio.run(main())
