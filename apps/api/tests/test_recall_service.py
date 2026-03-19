#!/usr/bin/env python3
"""
召回服务测试脚本
"""
import sys
import os
import asyncio
from pathlib import Path
from datetime import datetime, timedelta

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 加载 .env 文件
from dotenv import load_dotenv
env_path = Path(__file__).parent.parent / ".env"
load_dotenv(env_path)

from src.services.recall_service import get_recall_service
from src.services.memory_service import memory_service
from src.database import db
from src.models.memory import MemoryCreate, TimeInfo, LocationInfo, PersonInfo, EmotionInfo


async def setup_test_data():
    """创建测试数据"""
    print("=" * 60)
    print("📝 创建测试数据")
    print("=" * 60)
    
    # 连接数据库
    await db.connect()
    
    # 创建测试记忆
    test_memories = [
        MemoryCreate(
            content="今天在咖啡店遇到老同学，聊了很久，心情很不错",
            input_type="text",
            time=TimeInfo(value=datetime.now(), source="inferred", confidence=0.9),
            location=LocationInfo(name="咖啡店"),
            emotion=EmotionInfo(type="开心", intensity=8),
            tags=["生活", "社交"]
        ),
        MemoryCreate(
            content="昨天在公司开会讨论新项目，和张三、李四一起讨论了两个小时",
            input_type="text",
            time=TimeInfo(value=datetime.now() - timedelta(days=1), source="inferred", confidence=0.9),
            location=LocationInfo(name="公司会议室"),
            people=[PersonInfo(name="张三"), PersonInfo(name="李四")],
            tags=["工作", "会议"]
        ),
        MemoryCreate(
            content="周末去公园跑步，天气很好，感觉很放松",
            input_type="text",
            time=TimeInfo(value=datetime.now() - timedelta(days=2), source="inferred", confidence=0.9),
            location=LocationInfo(name="公园"),
            emotion=EmotionInfo(type="放松", intensity=7),
            tags=["生活", "运动"]
        ),
        MemoryCreate(
            content="读了一本关于人工智能的书，学到很多新知识",
            input_type="text",
            time=TimeInfo(value=datetime.now() - timedelta(days=3), source="inferred", confidence=0.9),
            tags=["学习", "阅读"]
        ),
        MemoryCreate(
            content="和朋友去餐厅吃饭，食物很美味，聊得很开心",
            input_type="text",
            time=TimeInfo(value=datetime.now() - timedelta(days=4), source="inferred", confidence=0.9),
            location=LocationInfo(name="餐厅"),
            people=[PersonInfo(name="朋友")],
            emotion=EmotionInfo(type="开心", intensity=8),
            tags=["生活", "美食"]
        )
    ]
    
    memory_ids = []
    for memory_data in test_memories:
        memory_id = await memory_service.create(memory_data)
        memory_ids.append(memory_id)
        print(f"✅ 创建记忆: {memory_id}")
    
    print(f"\n共创建 {len(memory_ids)} 条测试记忆")
    
    return memory_ids


async def test_recall_service():
    """测试召回服务"""
    print("\n" + "=" * 60)
    print("🧪 召回服务测试")
    print("=" * 60)
    
    try:
        # 初始化服务
        recall_service = get_recall_service()
        print("✅ 召回服务初始化成功")
        
        # 测试 1: 向量相似度检索
        print("\n" + "=" * 60)
        print("📝 测试 1: 向量相似度检索")
        print("=" * 60)
        
        query = "咖啡店"
        print(f"\n查询: {query}")
        
        results = await recall_service.search(query, limit=5)
        
        print(f"\n找到 {len(results)} 条相关记忆:")
        for i, result in enumerate(results, 1):
            print(f"\n{i}. {result['content'][:50]}...")
            print(f"   相似度: {result['similarity']:.4f}")
            print(f"   向量分数: {result.get('vector_score', 0):.4f}")
            print(f"   关键词分数: {result.get('keyword_score', 0):.4f}")
        
        # 测试 2: 关键词检索
        print("\n" + "=" * 60)
        print("📝 测试 2: 关键词检索")
        print("=" * 60)
        
        query = "工作 会议"
        print(f"\n查询: {query}")
        
        results = await recall_service.search(query, limit=5)
        
        print(f"\n找到 {len(results)} 条相关记忆:")
        for i, result in enumerate(results, 1):
            print(f"\n{i}. {result['content'][:50]}...")
            print(f"   相似度: {result['similarity']:.4f}")
        
        # 测试 3: 混合检索
        print("\n" + "=" * 60)
        print("📝 测试 3: 混合检索")
        print("=" * 60)
        
        query = "和朋友一起很开心"
        print(f"\n查询: {query}")
        
        results = await recall_service.search(query, limit=5, min_similarity=0.3)
        
        print(f"\n找到 {len(results)} 条相关记忆:")
        for i, result in enumerate(results, 1):
            print(f"\n{i}. {result['content'][:50]}...")
            print(f"   相似度: {result['similarity']:.4f}")
            if result.get('location_name'):
                print(f"   地点: {result['location_name']}")
        
        # 测试 4: 按人物检索
        print("\n" + "=" * 60)
        print("📝 测试 4: 按人物检索")
        print("=" * 60)
        
        person_name = "张三"
        print(f"\n查询人物: {person_name}")
        
        memories = await recall_service.search_by_person(person_name)
        
        print(f"\n找到 {len(memories)} 条相关记忆:")
        for i, memory in enumerate(memories, 1):
            print(f"\n{i}. {memory.content[:50]}...")
            if memory.people:
                print(f"   人物: {[p.name for p in memory.people]}")
        
        # 测试 5: 按地点检索
        print("\n" + "=" * 60)
        print("📝 测试 5: 按地点检索")
        print("=" * 60)
        
        location = "咖啡店"
        print(f"\n查询地点: {location}")
        
        memories = await recall_service.search_by_location(location)
        
        print(f"\n找到 {len(memories)} 条相关记忆:")
        for i, memory in enumerate(memories, 1):
            print(f"\n{i}. {memory.content[:50]}...")
            if memory.location:
                print(f"   地点: {memory.location.name}")
        
        # 测试 6: 按时间范围检索
        print("\n" + "=" * 60)
        print("📝 测试 6: 按时间范围检索")
        print("=" * 60)
        
        start_time = datetime.now() - timedelta(days=3)
        end_time = datetime.now()
        print(f"\n查询时间范围: {start_time.date()} 到 {end_time.date()}")
        
        memories = await recall_service.search_by_time(start_time, end_time)
        
        print(f"\n找到 {len(memories)} 条相关记忆:")
        for i, memory in enumerate(memories, 1):
            print(f"\n{i}. {memory.content[:50]}...")
            if memory.time:
                print(f"   时间: {memory.time.value}")
        
        # 测试 7: 获取最近的记忆
        print("\n" + "=" * 60)
        print("📝 测试 7: 获取最近的记忆")
        print("=" * 60)
        
        memories = await recall_service.get_recent(days=7)
        
        print(f"\n最近 7 天的记忆 ({len(memories)} 条):")
        for i, memory in enumerate(memories, 1):
            print(f"\n{i}. {memory.content[:50]}...")
            print(f"   创建时间: {memory.created_at}")
        
        print("\n" + "=" * 60)
        print("✅ 所有召回服务测试通过")
        print("=" * 60)
        
        return True
        
    except Exception as e:
        print(f"\n❌ 召回服务测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        # 断开数据库连接
        await db.disconnect()


async def cleanup_test_data(memory_ids):
    """清理测试数据"""
    print("\n" + "=" * 60)
    print("🧹 清理测试数据")
    print("=" * 60)
    
    for memory_id in memory_ids:
        await db.execute("DELETE FROM memories WHERE id = $1", memory_id)
        print(f"✅ 删除测试记忆: {memory_id}")


async def main():
    """主函数"""
    # 创建测试数据
    memory_ids = await setup_test_data()
    
    try:
        # 运行测试
        success = await test_recall_service()
        
        if not success:
            sys.exit(1)
    finally:
        # 清理测试数据
        await cleanup_test_data(memory_ids)


if __name__ == "__main__":
    asyncio.run(main())
