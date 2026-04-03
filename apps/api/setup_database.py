#!/usr/bin/env python3
"""
完整数据库初始化脚本（新环境）

步骤：
1. 连接到 postgres 默认数据库
2. 创建数据库（如果不存在）
3. 安装 pgvector 扩展
4. 执行 schema.sql 创建表

使用方式：
    python setup_database.py
"""

import asyncio
import sys
import os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from src.config import settings


async def setup_database():
    """完整数据库初始化"""
    import asyncpg

    print("=" * 60)
    print("Memory Recall - 数据库初始化")
    print("=" * 60)
    print()

    # 步骤 1：连接到 postgres 默认数据库
    print("[1/4] 连接到 PostgreSQL 服务器...")
    try:
        conn = await asyncpg.connect(
            host=settings.DATABASE_HOST,
            port=settings.DATABASE_PORT,
            user=settings.DATABASE_USER,
            password=settings.DATABASE_PASSWORD,
            database="postgres",  # 连接到默认数据库
        )
    except Exception as e:
        print(f"✗ 连接失败: {e}")
        print()
        print("请确保：")
        print("  1. PostgreSQL 已安装并运行")
        print("  2. 数据库用户已创建")
        print("  3. .env 中的数据库配置正确")
        sys.exit(1)

    try:
        # 步骤 2：创建数据库（如果不存在）
        db_name = settings.DATABASE_NAME
        print(f"[2/4] 检查数据库 '{db_name}'...")

        exists = await conn.fetchval(
            "SELECT 1 FROM pg_database WHERE datname = $1", db_name
        )

        if exists:
            print(f"    数据库 '{db_name}' 已存在")
        else:
            print(f"    创建数据库 '{db_name}'...")
            await conn.execute(f"CREATE DATABASE {db_name}")
            print(f"    ✓ 数据库 '{db_name}' 创建成功")

        await conn.close()

        # 步骤 3：连接到目标数据库并安装扩展
        print(f"[3/4] 安装 pgvector 扩展...")
        conn = await asyncpg.connect(
            host=settings.DATABASE_HOST,
            port=settings.DATABASE_PORT,
            user=settings.DATABASE_USER,
            password=settings.DATABASE_PASSWORD,
            database=db_name,
        )

        await conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
        print("    ✓ pgvector 扩展安装成功")

        # 步骤 4：执行 schema.sql
        print("[4/4] 创建数据库表...")
        schema_file = Path(__file__).parent / "schema.sql"

        if not schema_file.exists():
            print(f"✗ 错误：找不到 schema.sql 文件: {schema_file}")
            sys.exit(1)

        with open(schema_file, "r", encoding="utf-8") as f:
            sql = f.read()

        # 移除已执行的扩展创建语句
        sql = sql.replace("CREATE EXTENSION IF NOT EXISTS vector;", "")

        await conn.execute(sql)
        print("    ✓ 数据库表创建成功")

        await conn.close()

        print()
        print("=" * 60)
        print("✓ 数据库初始化完成！")
        print("=" * 60)
        print()
        print("已创建的表：")
        print("  - api_keys (API 密钥管理)")
        print("  - memories (核心记忆存储)")
        print("  - memory_relations (记忆关系)")
        print("  - memory_profiles (用户画像缓存)")
        print("  - documents (文档元数据)")
        print("  - chunks (文档分块)")
        print("  - entities (实体/知识图谱)")
        print("  - entity_relations (实体关系)")
        print("  - memory_entities (记忆-实体关联)")
        print()

    except Exception as e:
        print()
        print("=" * 60)
        print(f"✗ 初始化失败: {e}")
        print("=" * 60)
        raise


async def check_connection():
    """检查数据库连接是否正常"""
    import asyncpg

    print("检查数据库连接...")

    try:
        conn = await asyncpg.connect(
            host=settings.DATABASE_HOST,
            port=settings.DATABASE_PORT,
            user=settings.DATABASE_USER,
            password=settings.DATABASE_PASSWORD,
            database=settings.DATABASE_NAME,
        )

        version = await conn.fetchval("SELECT version()")
        await conn.close()

        print(f"✓ 连接成功")
        print(f"  PostgreSQL 版本: {version[:50]}...")
        return True

    except Exception as e:
        print(f"✗ 连接失败: {e}")
        return False


if __name__ == "__main__":
    if "--check" in sys.argv:
        asyncio.run(check_connection())
    else:
        asyncio.run(setup_database())
