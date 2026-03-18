#!/usr/bin/env python3
"""
数据库连接测试脚本
"""
import asyncio
import asyncpg


async def test_connection():
    """测试数据库连接"""
    # 读取环境变量
    import os
    db_host = os.getenv('DATABASE_HOST', 'localhost')
    db_port = os.getenv('DATABASE_PORT', '5432')
    db_name = os.getenv('DATABASE_NAME', 'memory_recall')
    db_user = os.getenv('DATABASE_USER', 'postgres')
    db_password = os.getenv('DATABASE_PASSWORD', 'password')
    
    # 构建连接字符串
    conn_string = f"postgresql://{db_user}:{db_password}@{db_host}:{db_port}/{db_name}"
    
    print(f"测试数据库连接: {db_host}:{db_port}/{db_name}")
    
    try:
        # 连接数据库
        conn = await asyncpg.connect(conn_string)
        print("✅ 数据库连接成功")
        
        # 测试查询
        result = await conn.fetchval("SELECT version()")
        print(f"\n数据库版本:\n{result}")
        
        # 测试 pgvector 扩展
        vector_test = await conn.fetchval("SELECT '[1,2,3]'::vector")
        print(f"\n✅ pgvector 测试成功: {vector_test}")
        
        # 测试表是否存在
        tables = await conn.fetch("""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = 'public' 
            AND table_type = 'BASE TABLE'
        """)
        
        print(f"\n数据库表数量: {len(tables)}")
        for table in tables:
            count = await conn.fetchval(f"SELECT COUNT(*) FROM {table['table_name']}")
            print(f"  - {table['table_name']}: {count} 条记录")
        
        # 关闭连接
        await conn.close()
        print("\n✅ 所有测试通过")
        
    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        raise


if __name__ == "__main__":
    asyncio.run(test_connection())
