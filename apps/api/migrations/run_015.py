#!/usr/bin/env python3
import asyncio
import sys

sys.path.insert(0, ".")
from src.database import db


async def run_migration():
    with open("migrations/015_create_lossless_tables.sql", "r") as f:
        content = f.read()

    await db.connect()

    try:
        # 执行整个文件（让 PostgreSQL 处理语句分割）
        # 对于函数定义，需要特殊处理
        await db.execute(content)
        print("Migration 015 completed successfully!")
    except Exception as e:
        error_msg = str(e).lower()
        if "already exists" in error_msg:
            print("Tables already exist, skipping...")
        else:
            print(f"Error: {e}")
            raise
    finally:
        await db.disconnect()


if __name__ == "__main__":
    asyncio.run(run_migration())
