#!/usr/bin/env python3
"""
数据库迁移执行脚本（改进版）
正确处理 PostgreSQL 函数定义（$$ 代码块）
"""

import asyncio
import sys
import os
from pathlib import Path
import re

# 添加项目根目录到 Python 路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.database import db
from src.config import settings


async def run_migration(migration_file: str):
    """执行单个迁移文件"""
    print(f"执行迁移: {migration_file}")

    # 读取 SQL 文件
    with open(migration_file, "r", encoding="utf-8") as f:
        sql = f.read()

    # 连接数据库
    await db.connect()

    try:
        # 直接执行整个文件，数据库会正确处理 $$ 块
        await db.execute(sql)
        print(f"✓ 迁移完成: {migration_file}")

    except Exception as e:
        error_msg = str(e).lower()
        # 某些语句可能因为对象已存在而失败，这是正常的
        if "already exists" in error_msg or "duplicate" in error_msg:
            print(f"⚠ 迁移跳过（对象已存在）: {migration_file}")
        else:
            print(f"✗ 迁移失败: {e}")
            raise
    finally:
        await db.disconnect()


async def main():
    """主函数"""
    migrations_dir = Path(__file__).parent

    # 获取所有迁移文件（按文件名排序）
    migration_files = sorted(migrations_dir.glob("*.sql"))

    if not migration_files:
        print("没有找到迁移文件")
        return

    print(f"找到 {len(migration_files)} 个迁移文件")
    print("=" * 60)
    print()

    # 执行每个迁移
    for migration_file in migration_files:
        await run_migration(str(migration_file))
        print()

    print("=" * 60)
    print("所有迁移执行完成！")


if __name__ == "__main__":
    asyncio.run(main())
