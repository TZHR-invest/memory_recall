#!/usr/bin/env python3
"""
数据库初始化脚本
用于初始化 PostgreSQL + pgvector 数据库
"""
import asyncio
import asyncpg
from pathlib import Path


async def init_database():
    """初始化数据库"""
    # 读取环境变量
    import os
    db_host = os.getenv('DATABASE_HOST', 'localhost')
    db_port = os.getenv('DATABASE_PORT', '5432')
    db_name = os.getenv('DATABASE_NAME', 'memory_recall')
    db_user = os.getenv('DATABASE_USER', 'postgres')
    db_password = os.getenv('DATABASE_PASSWORD', 'password')
    
    # 构建连接字符串
    conn_string = f"postgresql://{db_user}:{db_password}@{db_host}:{db_port}/{db_name}"
    
    print(f"正在连接数据库: {db_host}:{db_port}/{db_name}")
    
    try:
        # 连接数据库
        conn = await asyncpg.connect(conn_string)
        print("✅ 数据库连接成功")
        
        # 读取 schema.sql
        schema_path = Path(__file__).parent / "schema.sql"
        with open(schema_path, 'r', encoding='utf-8') as f:
            schema_sql = f.read()
        
        print("正在执行 schema.sql...")
        
        # 执行 SQL
        await conn.execute(schema_sql)
        print("✅ 数据库 schema 创建成功")
        
        # 验证表是否创建
        tables = await conn.fetch("""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = 'public' 
            AND table_type = 'BASE TABLE'
        """)
        
        print(f"\n已创建的表:")
        for table in tables:
            print(f"  - {table['table_name']}")
        
        # 验证 pgvector 扩展
        extensions = await conn.fetch("""
            SELECT extname 
            FROM pg_extension 
            WHERE extname = 'vector'
        """)
        
        if extensions:
            print("\n✅ pgvector 扩展已安装")
        else:
            print("\n❌ pgvector 扩展未安装")
        
        # 关闭连接
        await conn.close()
        print("\n✅ 数据库初始化完成")
        
    except Exception as e:
        print(f"❌ 数据库初始化失败: {e}")
        raise


if __name__ == "__main__":
    asyncio.run(init_database())
