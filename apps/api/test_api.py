#!/usr/bin/env python3
"""
API 测试脚本
测试所有实现的端点
"""
import asyncio
import asyncpg
import sys
from datetime import datetime


async def test_database():
    """测试数据库连接"""
    print("=" * 60)
    print("测试数据库连接...")
    print("=" * 60)
    
    try:
        conn = await asyncpg.connect(
            host="localhost",
            port=5432,
            database="memory_recall",
            user="postgres",
            password="password"
        )
        
        print("✅ 数据库连接成功")
        
        # 测试查询
        version = await conn.fetchval("SELECT version()")
        print(f"✅ PostgreSQL 版本: {version}")
        
        # 检查 pgvector 扩展
        vector_ext = await conn.fetchval(
            "SELECT extname FROM pg_extension WHERE extname = 'vector'"
        )
        if vector_ext:
            print("✅ pgvector 扩展已启用")
        else:
            print("⚠️  pgvector 扩展未启用")
        
        # 检查表
        tables = await conn.fetch("""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = 'public' 
            AND table_type = 'BASE TABLE'
        """)
        print(f"✅ 找到 {len(tables)} 个表: {[t['table_name'] for t in tables]}")
        
        # 检查记忆数量
        count = await conn.fetchval("SELECT COUNT(*) FROM memories")
        print(f"✅ 记忆总数: {count}")
        
        await conn.close()
        return True
        
    except Exception as e:
        print(f"❌ 数据库连接失败: {e}")
        return False


async def test_embedding_service():
    """测试 Embedding 服务"""
    print("\n" + "=" * 60)
    print("测试 Embedding 服务...")
    print("=" * 60)
    
    try:
        sys.path.insert(0, '/home/wbaifan/.openclaw/workspace-ai_tui/projects/memory_recall/apps/api')
        from src.embedding.client import get_embedding_client
        
        client = get_embedding_client()
        
        # 测试向量化
        text = "这是一个测试文本"
        embedding = client.embed(text)
        
        if embedding and len(embedding) > 0:
            print(f"✅ Embedding 服务正常，向量维度: {len(embedding)}")
            return True
        else:
            print("❌ Embedding 服务返回空向量")
            return False
            
    except Exception as e:
        print(f"❌ Embedding 服务测试失败: {e}")
        return False


async def test_llm_service():
    """测试 LLM 服务"""
    print("\n" + "=" * 60)
    print("测试 LLM 服务...")
    print("=" * 60)
    
    try:
        sys.path.insert(0, '/home/wbaifan/.openclaw/workspace-ai_tui/projects/memory_recall/apps/api')
        from src.llm.client import get_llm_client
        
        client = get_llm_client()
        
        # 测试简单对话
        response = client.chat("你好，这是一个测试")
        
        if response:
            print(f"✅ LLM 服务正常，响应: {response[:50]}...")
            return True
        else:
            print("❌ LLM 服务返回空响应")
            return False
            
    except Exception as e:
        print(f"❌ LLM 服务测试失败: {e}")
        return False


async def test_query_parser():
    """测试查询解析器"""
    print("\n" + "=" * 60)
    print("测试查询解析器...")
    print("=" * 60)
    
    try:
        sys.path.insert(0, '/home/wbaifan/.openclaw/workspace-ai_tui/projects/memory_recall/apps/api')
        from src.services.query_parser import query_parser
        
        test_queries = [
            "上周在咖啡店和老同学见面",
            "最近开心的事",
            "昨天发生了什么",
            "和老同学相关的记忆",
            "最近3天的工作内容"
        ]
        
        for query in test_queries:
            result = query_parser.parse(query)
            print(f"\n查询: {query}")
            print(f"  - 时间范围: {result.get('time_range')}")
            print(f"  - 地点: {result.get('location')}")
            print(f"  - 人物: {result.get('people')}")
            print(f"  - 情绪: {result.get('emotion')}")
            print(f"  - 标签: {result.get('tags')}")
            print(f"  - 意图: {result.get('intent')}")
        
        print("\n✅ 查询解析器测试通过")
        return True
        
    except Exception as e:
        print(f"❌ 查询解析器测试失败: {e}")
        return False


async def main():
    """主测试函数"""
    print("\n" + "=" * 60)
    print("Memory Recall API - 端到端测试")
    print("=" * 60)
    
    results = {
        "数据库": await test_database(),
        "Embedding": await test_embedding_service(),
        "LLM": await test_llm_service(),
        "查询解析": await test_query_parser()
    }
    
    print("\n" + "=" * 60)
    print("测试结果汇总")
    print("=" * 60)
    
    for name, result in results.items():
        status = "✅ 通过" if result else "❌ 失败"
        print(f"{name}: {status}")
    
    all_passed = all(results.values())
    print("\n" + ("✅ 所有测试通过" if all_passed else "⚠️  部分测试失败"))
    
    return all_passed


if __name__ == "__main__":
    asyncio.run(main())
