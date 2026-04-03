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
    分割 SQL 语句，正确处理 PostgreSQL dollar-quoted strings

    支持:
    - $$ ... $$
    - $tag$ ... $tag$
    - 嵌套的 dollar-quoted strings
    """
    statements = []
    current_stmt = []
    i = 0
    in_dollar_quote = False
    current_tag = None

    while i < len(sql):
        # 检查 dollar quote 开始/结束
        if sql[i] == "$":
            # 匹配 $tag$ 或 $$
            tag_match = re.match(r"\$([a-zA-Z_][a-zA-Z0-9_]*)?\$", sql[i:])
            if tag_match:
                tag = tag_match.group(1)  # None for $$, or tag name

                if not in_dollar_quote:
                    # 进入 dollar quote
                    in_dollar_quote = True
                    current_tag = tag
                    end_pos = i + len(tag_match.group(0))
                    current_stmt.append(sql[i:end_pos])
                    i = end_pos
                    continue
                elif tag == current_tag:
                    # 退出 dollar quote（标签必须匹配）
                    in_dollar_quote = False
                    current_tag = None
                    end_pos = i + len(tag_match.group(0))
                    current_stmt.append(sql[i:end_pos])
                    i = end_pos
                    continue

        # 处理分号（在 dollar quote 外）
        if sql[i] == ";" and not in_dollar_quote:
            current_stmt.append(";")
            stmt = "".join(current_stmt).strip()
            if stmt and stmt != ";":
                statements.append(stmt)
            current_stmt = []
        else:
            current_stmt.append(sql[i])

        i += 1

    # 处理最后一个语句
    if current_stmt:
        stmt = "".join(current_stmt).strip()
        if stmt and stmt != ";":
            statements.append(stmt)

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
                print(f"  ✓ 语句 {i}/{len(statements)}")
            except Exception as e:
                error_msg = str(e).lower()
                if "already exists" in error_msg or "duplicate" in error_msg:
                    skip_count += 1
                    print(f"  ⚠ 语句 {i}/{len(statements)} 跳过（已存在）")
                else:
                    print(f"  ✗ 语句 {i}/{len(statements)} 失败: {e}")
                    print(f"     SQL: {statement[:200]}...")
                    raise

        print(f"✓ 迁移完成: {migration_file} (成功:{success_count} 跳过:{skip_count})")

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
