#!/usr/bin/env python3
"""
数据库初始化脚本（新环境使用）
直接执行 schema.sql，不需要迁移机制
"""

import asyncio
import sys
import os
from pathlib import Path

# 添加项目根目录到 Python 路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.database import db
from src.config import settings


async def init_database():
    """初始化数据库（新环境）"""
    print("=" * 60)
    print("Memory Recall - 数据库初始化")
    print("=" * 60)
    print()

    # 读取 schema.sql
    schema_file = Path(__file__).parent / "schema.sql"

    if not schema_file.exists():
        print(f"✗ 错误：找不到 schema.sql 文件: {schema_file}")
        sys.exit(1)

    print(f"读取 schema 文件: {schema_file}")
    with open(schema_file, "r", encoding="utf-8") as f:
        sql = f.read()

    # 连接数据库
    print("连接数据库...")
    await db.connect()

    try:
        # 执行 schema
        print("执行数据库初始化...")
        await db.execute(sql)
        print()
        print("=" * 60)
        print("✓ 数据库初始化成功！")
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
        print("  - chunk_entities (分块-实体关联)")
        print("  - recall_traces (召回链路 Trace)")
        print()

    except Exception as e:
        print()
        print("=" * 60)
        print(f"✗ 初始化失败: {e}")
        print("=" * 60)
        raise
    finally:
        await db.disconnect()


if __name__ == "__main__":
    asyncio.run(init_database())
