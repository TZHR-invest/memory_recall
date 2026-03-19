"""
性能测试脚本
测试 LLM、Embedding 缓存和数据库查询性能
"""
import asyncio
import sys
import os
import time
from pathlib import Path

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 加载 .env 文件
from dotenv import load_dotenv
env_path = Path(__file__).parent.parent / ".env"
load_dotenv(env_path)

from src.database import db
from src.llm.client import get_llm_client
from src.embedding.client import get_embedding_client
from src.cache.manager import cache_manager
from src.services.memory_service import memory_service
from src.services.recall_service import get_recall_service


async def test_llm_cache():
    """测试 LLM 缓存"""
    print("\n" + "=" * 60)
    print("📊 LLM 缓存性能测试")
    print("=" * 60)
    
    llm_client = get_llm_client()
    
    # 测试提示词
    test_prompts = [
        "从以下文本中提取关键信息：今天下午在图书馆遇到了老同学张三。",
        "从以下文本中提取关键信息：昨天晚上在公司加班到很晚，心情有点疲惫。",
        "从以下文本中提取关键信息：今天下午在图书馆遇到了老同学张三。",  # 重复，测试缓存
    ]
    
    print("\n测试结果:")
    for i, prompt in enumerate(test_prompts, 1):
        start_time = time.time()
        
        # 使用缓存
        messages = [{"role": "user", "content": prompt}]
        result = llm_client.chat(messages, temperature=0.3, use_cache=True)
        
        elapsed = time.time() - start_time
        cache_stats = cache_manager.stats()
        
        print(f"\n  测试 {i}:")
        print(f"    耗时: {elapsed:.3f}s")
        print(f"    缓存命中: {'是' if elapsed < 0.1 else '否'}")
        print(f"    缓存统计: 命中 {cache_stats['hits']}, 未命中 {cache_stats['misses']}")


async def test_embedding_cache():
    """测试 Embedding 缓存"""
    print("\n" + "=" * 60)
    print("📊 Embedding 缓存性能测试")
    print("=" * 60)
    
    embedding_client = get_embedding_client()
    
    # 测试文本
    test_texts = [
        "今天下午在图书馆遇到了老同学张三。",
        "昨天晚上在公司加班到很晚。",
        "今天下午在图书馆遇到了老同学张三。",  # 重复，测试缓存
    ]
    
    print("\n测试结果:")
    for i, text in enumerate(test_texts, 1):
        start_time = time.time()
        
        # 使用缓存
        embedding = embedding_client.embed(text, use_cache=True)
        
        elapsed = time.time() - start_time
        cache_stats = cache_manager.stats()
        
        print(f"\n  测试 {i}:")
        print(f"    耗时: {elapsed:.3f}s")
        print(f"    向量维度: {len(embedding) if embedding else 0}")
        print(f"    缓存命中: {'是' if elapsed < 0.1 else '否'}")


async def test_memory_creation():
    """测试记忆创建性能"""
    print("\n" + "=" * 60)
    print("📊 记忆创建性能测试")
    print("=" * 60)
    
    test_text = "今天下午在图书馆遇到了老同学张三，我们聊了很久关于工作和生活的话题，感觉很开心"
    
    # 第一次创建（无缓存）
    print("\n第一次创建（无缓存）:")
    start_time = time.time()
    result1 = await memory_service.process_text_input(test_text, auto_confirm=True)
    elapsed1 = time.time() - start_time
    print(f"  耗时: {elapsed1:.3f}s")
    print(f"  记忆 ID: {result1.get('memory_id')}")
    
    # 第二次创建（有缓存）
    print("\n第二次创建（相同文本，有缓存）:")
    start_time = time.time()
    result2 = await memory_service.process_text_input(test_text, auto_confirm=True)
    elapsed2 = time.time() - start_time
    print(f"  耗时: {elapsed2:.3f}s")
    print(f"  记忆 ID: {result2.get('memory_id')}")
    
    # 性能提升
    improvement = ((elapsed1 - elapsed2) / elapsed1) * 100 if elapsed1 > 0 else 0
    print(f"\n性能提升: {improvement:.1f}%")
    
    # 清理测试数据
    if result1.get("memory_id"):
        await memory_service.delete(result1["memory_id"])
    if result2.get("memory_id"):
        await memory_service.delete(result2["memory_id"])


async def test_search_performance():
    """测试搜索性能"""
    print("\n" + "=" * 60)
    print("📊 搜索性能测试")
    print("=" * 60)
    
    recall_service = get_recall_service()
    
    # 创建一些测试数据
    test_memories = [
        "今天下午在图书馆遇到了老同学张三。",
        "昨天晚上在公司加班到很晚，心情有点疲惫。",
        "上周末去公园散步，天气很好。",
    ]
    
    memory_ids = []
    for text in test_memories:
        result = await memory_service.process_text_input(text, auto_confirm=True)
        if result.get("memory_id"):
            memory_ids.append(result["memory_id"])
    
    # 测试搜索
    queries = [
        "图书馆",
        "加班",
        "公园",
    ]
    
    print("\n搜索测试:")
    for query in queries:
        start_time = time.time()
        results = await recall_service.search(query, limit=5, min_similarity=0.3)
        elapsed = time.time() - start_time
        
        print(f"\n  查询: {query}")
        print(f"    耗时: {elapsed:.3f}s")
        print(f"    结果数: {len(results)}")
    
    # 清理测试数据
    for memory_id in memory_ids:
        await memory_service.delete(memory_id)


async def show_cache_stats():
    """显示缓存统计"""
    print("\n" + "=" * 60)
    print("📊 缓存统计")
    print("=" * 60)
    
    stats = cache_manager.stats()
    
    print(f"\n  缓存大小: {stats['size']}/{stats['max_size']}")
    print(f"  命中次数: {stats['hits']}")
    print(f"  未命中次数: {stats['misses']}")
    print(f"  命中率: {stats['hit_rate']:.2%}")
    print(f"  总请求: {stats['total_requests']}")


async def main():
    """主测试函数"""
    print("=" * 60)
    print("🧪 Memory Recall - 性能测试")
    print("=" * 60)
    
    try:
        await db.connect()
        print("✅ 数据库连接成功")
        
        # 清空缓存
        cache_manager.clear()
        print("✅ 缓存已清空")
        
        # 运行测试
        await test_llm_cache()
        await test_embedding_cache()
        await test_memory_creation()
        await test_search_performance()
        await show_cache_stats()
        
        print("\n" + "=" * 60)
        print("✅ 性能测试完成")
        print("=" * 60)
        
    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await db.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
