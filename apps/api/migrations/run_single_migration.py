#!/usr/bin/env python3
"""
运行单个迁移文件
"""
import asyncio
import sys
import os
from pathlib import Path

# 添加项目根目录到 Python 路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.database import db


async def run_migration(migration_file: str):
    """执行单个迁移文件"""
    print(f"执行迁移: {migration_file}")
    
    # 读取 SQL 文件
    with open(migration_file, 'r', encoding='utf-8') as f:
        sql = f.read()
    
    # 连接数据库
    await db.connect()
    
    try:
        # 分割 SQL 语句（按分号分割，但要处理函数定义）
        statements = []
        current_statement = []
        in_function = False
        
        for line in sql.split('\n'):
            # 检测函数定义开始
            if '$$' in line and 'AS $$' in line:
                in_function = True
            
            current_statement.append(line)
            
            # 检测函数定义结束
            if in_function and '$$' in line and 'AS $$' not in line:
                in_function = False
                # 检查是否语句结束
                if line.strip().endswith(';'):
                    statements.append('\n'.join(current_statement))
                    current_statement = []
            elif not in_function and line.strip().endswith(';'):
                statements.append('\n'.join(current_statement))
                current_statement = []
        
        # 处理剩余语句
        if current_statement:
            statements.append('\n'.join(current_statement))
        
        # 执行每条语句
        for i, statement in enumerate(statements, 1):
            statement = statement.strip()
            if not statement or statement == ';':
                continue
            
            try:
                await db.execute(statement)
                print(f"  ✓ 语句 {i}/{len(statements)} 执行成功")
            except Exception as e:
                error_msg = str(e).lower()
                if 'already exists' in error_msg or 'duplicate' in error_msg:
                    print(f"  ⚠ 语句 {i}/{len(statements)} 跳过（对象已存在）")
                else:
                    print(f"  ⚠ 语句 {i}/{len(statements)} 失败: {str(e)[:100]}")
                    # 继续执行下一条语句
        
        print(f"✓ 迁移完成: {migration_file}")
        
    except Exception as e:
        print(f"✗ 迁移失败: {e}")
        raise
    finally:
        await db.disconnect()


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("用法: python run_single_migration.py <migration_file>")
        sys.exit(1)
    
    migration_file = sys.argv[1]
    asyncio.run(run_migration(migration_file))
