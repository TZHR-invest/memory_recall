#!/usr/bin/env python3
"""
Embedding 服务测试脚本
需要配置 VOLC_API_KEY 环境变量
"""
import sys
import os

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.embedding.client import get_embedding_client
from src.database import db


async def test_embedding_client():
    """测试 Embedding 客户端"""
    print("测试 Embedding 客户端...")
    
    try:
        client = get_embedding_client()
        print("✅ Embedding 客户端初始化成功")
        
        # 测试单个文本
        test_text = "今天在咖啡店遇到老同学，聊了很久"
        embedding = client.embed(test_text)
        
        if embedding:
            print(f"\n✅ 单个文本 Embedding 测试成功:")
            print(f"  - 维度: {len(embedding)}")
            print(f"  - 前 10 维: {embedding[:10]}")
        else:
            print("❌ Embedding 生成失败")
            return False
        
        # 测试批量文本
        test_texts = [
            "今天在咖啡店遇到老同学",
            "昨天在公司开会讨论项目",
            "明天要和朋友去爬山"
        ]
        
        embeddings = client.embed_batch(test_texts)
        
        if embeddings:
            print(f"\n✅ 批量 Embedding 测试成功:")
            print(f"  - 数量: {len(embeddings)}")
            print(f"  - 维度: {len(embeddings[0])}")
        else:
            print("❌ 批量 Embedding 生成失败")
            return False
        
        return True
    except Exception as e:
        print(f"❌ Embedding 客户端测试失败: {e}")
        return False


async def test_vector_storage():
    """测试向量存储和检索"""
    print("\n测试向量存储和检索...")
    
    try:
        # 连接数据库
        await db.connect()
        print("✅ 数据库连接成功")
        
        # 获取 Embedding 客户端
        client = get_embedding_client()
        
        # 生成测试向量
        test_text = "这是一条测试记忆"
        embedding = client.embed(test_text)
        
        if not embedding:
            print("❌ Embedding 生成失败")
            return False
        
        # 存储向量
        import uuid
        test_id = f"test_{uuid.uuid4().hex[:12]}"
        
        await db.execute("""
            INSERT INTO memories (id, content, input_type, embedding)
            VALUES ($1, $2, $3, $4)
        """, test_id, test_text, "text", embedding)
        
        print("✅ 向量存储成功")
        
        # 检索向量
        result = await db.fetchrow("""
            SELECT id, content, 
                   1 - (embedding <=> $1::vector) as similarity
            FROM memories
            WHERE id = $2
        """, embedding, test_id)
        
        if result:
            print(f"\n✅ 向量检索测试成功:")
            print(f"  - ID: {result['id']}")
            print(f"  - 内容: {result['content']}")
            print(f"  - 相似度: {result['similarity']}")
        else:
            print("❌ 向量检索失败")
            return False
        
        # 清理测试数据
        await db.execute("DELETE FROM memories WHERE id = $1", test_id)
        
        # 断开数据库
        await db.disconnect()
        
        return True
    except Exception as e:
        print(f"❌ 向量存储测试失败: {e}")
        return False


if __name__ == "__main__":
    import asyncio
    
    # 检查 API Key
    if not os.getenv("VOLC_API_KEY"):
        print("❌ 错误：未配置 VOLC_API_KEY 环境变量")
        print("\n请在 .env 文件中配置：")
        print("VOLC_API_KEY=your_api_key_here")
        sys.exit(1)
    
    # 运行测试
    test1 = asyncio.run(test_embedding_client())
    test2 = asyncio.run(test_vector_storage())
    
    if test1 and test2:
        print("\n✅ 所有测试通过")
    else:
        print("\n❌ 部分测试失败")
        sys.exit(1)
