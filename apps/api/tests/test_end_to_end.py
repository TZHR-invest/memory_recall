#!/usr/bin/env python3
"""
端到端测试脚本
测试完整的记忆创建和召回流程
"""
import sys
import os
import asyncio
from pathlib import Path
from datetime import datetime

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 加载 .env 文件
from dotenv import load_dotenv
env_path = Path(__file__).parent.parent / ".env"
load_dotenv(env_path)

from src.services.memory_service import memory_service
from src.services.recall_service import get_recall_service
from src.database import db


async def test_end_to_end():
    """端到端测试"""
    print("=" * 60)
    print("🧪 Memory Recall - 端到端测试")
    print("=" * 60)
    
    try:
        # 连接数据库
        await db.connect()
        print("✅ 数据库连接成功")
        
        # 测试 1: 创建记忆
        print("\n" + "=" * 60)
        print("📝 测试 1: 创建记忆（文本输入处理）")
        print("=" * 60)
        
        test_text = "今天下午在图书馆遇到了老同学张三，我们聊了很久关于工作和生活的话题，感觉很开心"
        print(f"\n输入文本: {test_text}")
        
        result = await memory_service.process_text_input(test_text, auto_confirm=True)
        
        if result["success"]:
            print("\n✅ 记忆创建成功")
            print(f"记忆 ID: {result['memory_id']}")
            
            memory_data = result["memory_data"]
            print(f"\n提取的信息:")
            print(f"  - 内容: {memory_data.content}")
            if memory_data.time:
                print(f"  - 时间: {memory_data.time.value}")
            if memory_data.location:
                print(f"  - 地点: {memory_data.location.name}")
            if memory_data.people:
                print(f"  - 人物: {[p.name for p in memory_data.people]}")
            if memory_data.emotion:
                print(f"  - 情绪: {memory_data.emotion.type}")
            if memory_data.tags:
                print(f"  - 标签: {memory_data.tags}")
            
            memory_id = result["memory_id"]
        else:
            print(f"❌ 记忆创建失败: {result.get('error')}")
            return False
        
        # 测试 2: 检索记忆
        print("\n" + "=" * 60)
        print("📝 测试 2: 检索记忆")
        print("=" * 60)
        
        recall_service = get_recall_service()
        
        # 按关键词检索
        query = "图书馆 张三"
        print(f"\n查询: {query}")
        
        results = await recall_service.search(query, limit=5, min_similarity=0.3)
        
        print(f"\n找到 {len(results)} 条相关记忆:")
        for i, result in enumerate(results, 1):
            print(f"\n{i}. {result['content'][:50]}...")
            print(f"   相似度: {result['similarity']:.4f}")
        
        # 按人物检索
        print(f"\n按人物检索: 张三")
        memories = await recall_service.search_by_person("张三")
        
        print(f"\n找到 {len(memories)} 条相关记忆:")
        for i, memory in enumerate(memories, 1):
            print(f"\n{i}. {memory.content[:50]}...")
        
        # 按地点检索
        print(f"\n按地点检索: 图书馆")
        memories = await recall_service.search_by_location("图书馆")
        
        print(f"\n找到 {len(memories)} 条相关记忆:")
        for i, memory in enumerate(memories, 1):
            print(f"\n{i}. {memory.content[:50]}...")
        
        # 测试 3: 获取记忆详情
        print("\n" + "=" * 60)
        print("📝 测试 3: 获取记忆详情")
        print("=" * 60)
        
        memory = await memory_service.get(memory_id)
        
        if memory:
            print(f"\n✅ 获取记忆成功")
            print(f"记忆 ID: {memory.id}")
            print(f"内容: {memory.content}")
            print(f"创建时间: {memory.created_at}")
            if memory.time:
                print(f"时间: {memory.time.value}")
            if memory.location:
                print(f"地点: {memory.location.name}")
            if memory.people:
                print(f"人物: {[p.name for p in memory.people]}")
        else:
            print("❌ 获取记忆失败")
        
        # 测试 4: 删除记忆
        print("\n" + "=" * 60)
        print("📝 测试 4: 删除记忆")
        print("=" * 60)
        
        deleted = await memory_service.delete(memory_id)
        
        if deleted:
            print(f"\n✅ 记忆已删除: {memory_id}")
        else:
            print("❌ 删除记忆失败")
        
        print("\n" + "=" * 60)
        print("✅ 端到端测试通过")
        print("=" * 60)
        
        return True
        
    except Exception as e:
        print(f"\n❌ 端到端测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        # 断开数据库连接
        await db.disconnect()


if __name__ == "__main__":
    success = asyncio.run(test_end_to_end())
    sys.exit(0 if success else 1)
