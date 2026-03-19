#!/usr/bin/env python3
"""
性能测试脚本

测试并发处理的性能，确保响应时间 < 2s
"""
import asyncio
import time
import statistics
import sys
import os

# 添加项目路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'apps', 'api', 'src'))

from services.memory_service import MemoryService


async def test_performance():
    """性能测试"""
    
    memory_service = MemoryService()
    
    # 测试用例
    test_cases = [
        "今天和张三在咖啡店聊天",  # 短文本
        "今天和张三在咖啡店聊天，讨论了机器学习项目，决定下周开始实施",  # 中等文本
        "今天和张三在咖啡店聊天，讨论了机器学习项目的进展，决定下周开始实施新的算法优化方案，预计可以提升模型准确率10%以上",  # 长文本
    ]
    
    results = []
    
    print("=" * 60)
    print("Phase 4 性能测试")
    print("=" * 60)
    print()
    
    for i, content in enumerate(test_cases):
        print(f"测试用例 {i+1}: 长度 {len(content)} 字符")
        start = time.time()
        
        try:
            result = await memory_service.create_memory_with_graph(
                content=content,
                user_id="test_user",
                enable_graph=True
            )
            
            elapsed = time.time() - start
            
            # 提取图谱信息
            graph_info = result.get("graph", {})
            entity_count = graph_info.get("entity_count", 0) if graph_info else 0
            relation_count = graph_info.get("relation_count", 0) if graph_info else 0
            
            results.append({
                "case": i + 1,
                "content_length": len(content),
                "elapsed": elapsed,
                "memory_id": result.get("memory_id"),
                "entity_count": entity_count,
                "relation_count": relation_count,
                "success": True
            })
            
            print(f"  ✓ 耗时: {elapsed:.2f}s")
            print(f"  ✓ 记忆 ID: {result.get('memory_id')}")
            print(f"  ✓ 实体数: {entity_count}, 关系数: {relation_count}")
            
        except Exception as e:
            elapsed = time.time() - start
            results.append({
                "case": i + 1,
                "content_length": len(content),
                "elapsed": elapsed,
                "success": False,
                "error": str(e)
            })
            print(f"  ✗ 失败: {e}")
        
        print()
    
    # 统计
    print("=" * 60)
    print("测试结果统计")
    print("=" * 60)
    
    successful_results = [r for r in results if r.get("success")]
    
    if successful_results:
        elapsed_times = [r["elapsed"] for r in successful_results]
        avg_time = statistics.mean(elapsed_times)
        max_time = max(elapsed_times)
        min_time = min(elapsed_times)
        
        print(f"成功用例: {len(successful_results)}/{len(results)}")
        print(f"平均耗时: {avg_time:.2f}s")
        print(f"最大耗时: {max_time:.2f}s")
        print(f"最小耗时: {min_time:.2f}s")
        print()
        
        # 验收标准
        print("验收标准检查:")
        print(f"  [{'✓' if max_time < 2.0 else '✗'}] 最大耗时 < 2s (实际: {max_time:.2f}s)")
        print(f"  [{'✓' if avg_time < 1.5 else '✗'}] 平均耗时 < 1.5s (实际: {avg_time:.2f}s)")
        
        if max_time >= 2.0:
            print()
            print("⚠️  警告: 最大耗时超过 2s，需要优化")
            return False
    else:
        print("所有测试用例都失败了")
        return False
    
    print()
    print("✓ 性能测试通过")
    return True


async def test_concurrent_performance():
    """并发性能测试"""
    
    memory_service = MemoryService()
    
    print("=" * 60)
    print("并发性能测试")
    print("=" * 60)
    print()
    
    # 创建 5 个并发请求
    tasks = []
    test_content = "测试并发处理性能，今天和张三在咖啡店讨论项目进展"
    
    start = time.time()
    
    for i in range(5):
        task = memory_service.create_memory_with_graph(
            content=f"{test_content} - 请求 {i+1}",
            user_id=f"test_user_{i}",
            enable_graph=True
        )
        tasks.append(task)
    
    # 并发执行
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    elapsed = time.time() - start
    
    # 统计成功数量
    success_count = sum(1 for r in results if not isinstance(r, Exception))
    
    print(f"并发请求数: 5")
    print(f"成功数量: {success_count}")
    print(f"总耗时: {elapsed:.2f}s")
    print(f"平均每个请求: {elapsed/5:.2f}s")
    
    if success_count == 5 and elapsed < 3.0:
        print()
        print("✓ 并发性能测试通过")
        return True
    else:
        print()
        print("✗ 并发性能测试失败")
        return False


if __name__ == "__main__":
    print("\n")
    print("╔══════════════════════════════════════════════════════════╗")
    print("║       Memory Recall - Phase 4 性能测试                    ║")
    print("╚══════════════════════════════════════════════════════════╝")
    print()
    
    # 运行基础性能测试
    result1 = asyncio.run(test_performance())
    
    print()
    
    # 运行并发性能测试
    result2 = asyncio.run(test_concurrent_performance())
    
    print()
    print("=" * 60)
    
    if result1 and result2:
        print("✓ 所有测试通过")
        sys.exit(0)
    else:
        print("✗ 部分测试失败")
        sys.exit(1)
