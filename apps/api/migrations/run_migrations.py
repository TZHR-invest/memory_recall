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


def split_sql_statements(sql: str) -> list:
    """
    分割 SQL 语句，正确处理 PostgreSQL 代码块（$$ ... $$）

    Args:
        sql: SQL 文件内容

    Returns:
        语句列表
    """
    statements = []
    current_statement = []
    in_dollar_quote = False  # 是否在 $$ 代码块内

    for line in sql.split("\n"):
        stripped_line = line.strip()

        # 跳过空行（但在代码块内保留）
        if not stripped_line and not in_dollar_quote:
            continue

        # 处理单行注释（以 -- 开头，不在代码块内时跳过）
        if stripped_line.startswith("--") and not in_dollar_quote:
            if not current_statement:
                continue

        # 处理 $$ 引用
        # 找到所有 $$ 的位置
        pos = 0
        while True:
            idx = line.find("$$", pos)
            if idx == -1:
                break
            # 切换状态
            in_dollar_quote = not in_dollar_quote
            pos = idx + 2

        # 添加到当前语句
        current_statement.append(line)

        # 只在代码块外检测语句结束
        if not in_dollar_quote and stripped_line.endswith(";"):
            statements.append("\n".join(current_statement))
            current_statement = []

    # 处理最后可能剩余的语句
    if current_statement:
        statements.append("\n".join(current_statement))

    return statements


async def run_migration(migration_file: str):
    """执行单个迁移文件"""
    print(f"执行迁移: {migration_file}")

    # 读取 SQL 文件
    with open(migration_file, "r", encoding="utf-8") as f:
        sql = f.read()

    # 连接数据库
    await db.connect()

    try:
        # 分割 SQL 语句
        statements = split_sql_statements(sql)

        print(f"  共 {len(statements)} 条语句")
        print()

        # 执行每条语句
        success_count = 0
        skip_count = 0

        for i, statement in enumerate(statements, 1):
            # 清理语句
            statement = statement.strip()
            if not statement or statement == ";":
                continue

            try:
                await db.execute(statement)
                success_count += 1
                print(f"  ✓ 语句 {i}/{len(statements)} 执行成功")
            except Exception as e:
                error_msg = str(e).lower()
                # 某些语句可能因为对象已存在而失败，这是正常的
                if "already exists" in error_msg or "duplicate" in error_msg:
                    skip_count += 1
                    print(f"  ⚠ 语句 {i}/{len(statements)} 跳过（对象已存在）")
                else:
                    print(f"  ✗ 语句 {i}/{len(statements)} 执行失败: {e}")
                    print(f"     SQL: {statement[:150]}...")
                    raise

        print()
        print(f"✓ 迁移完成: {migration_file}")
        print(f"  成功: {success_count} 条")
        print(f"  跳过: {skip_count} 条")

    except Exception as e:
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
