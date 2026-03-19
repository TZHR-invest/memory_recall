#!/usr/bin/env python3
"""
本地性能测试 - 测试并发处理逻辑

不需要完整的 API 环境，只测试并发处理的性能
"""
import asyncio
import time
import statistics


async def mock_generate_embedding(content: str):
    """模拟生成 embedding（耗时操作）"""
    await asyncio.sleep(0.5)  # 模拟 API 调用延迟
    return [0.1] * 1024


async def mock_store_memory(content: str, embedding, user_id: str):
    """模拟存储记忆（耗时操作）"""
    await asyncio.sleep(0.1)  # 模拟数据库写入延迟
    return "test_memory_id"


async def mock_build_graph(content: str, user_id: str):
    """模拟图谱构建（耗时操作）"""
    await asyncio.sleep(0.8)  # 模拟 LLM 调用延迟
    return {
        "entities": [{"entity": "张三", "entity_type": "PERSON"}],
        "relations": [],
        "entity_count": 1,
        "relation_count": 0
    }


async def create_memory_sequential(content: str, user_id: str):
    """顺序执行（不使用并发）"""
    start = time.time()
    
    # 顺序执行
    embedding = await mock_generate_embedding(content)
    memory_id = await mock_store_memory(content, embedding, user_id)
    graph_result = await mock_build_graph(content, user_id)
    
    elapsed = time.time() - start
    return {
        "memory_id": memory_id,
        "graph": graph_result,
        "elapsed": elapsed
    }


async def create_memory_concurrent(content: str, user_id: str):
    """并发执行"""
    start = time.time()
    
    # 并发任务列表
    tasks = []
    
    # 任务 1: 向量存储
    async def store_vector():
        embedding = await mock_generate_embedding(content)
        memory_id = await mock_store_memory(content, embedding, user_id)
        return {"type": "vector", "memory_id": memory_id}
    
    tasks.append(store_vector())
    
    # 任务 2: 图谱构建
    async def build_graph():
        result = await mock_build_graph(content, user_id)
        return {"type": "graph", **result}
    
    tasks.append(build_graph())
    
    # 并发执行
    results = await asyncio.gather(*tasks)
    
    # 整合结果
    memory_id = None
    graph_result = None
    
    for result in results:
        if result["type"] == "vector":
            memory_id = result["memory_id"]
        elif result["type"] == "graph":
            graph_result = result
    
    elapsed = time.time() - start
    return {
        "memory_id": memory_id,
        "graph": graph_result,
        "elapsed": elapsed
    }


async def test_concurrent_vs_sequential():
    """测试并发 vs 顺序执行的性能差异"""
    
    print("=" * 60)
    print("并发处理性能测试")
    print("=" * 60)
    print()
    
    test_content = "今天和张三在咖啡店聊天"
    test_user = "test_user"
    
    # 测试顺序执行
    print("1. 顺序执行测试")
    print("   预期耗时: ~1.4s (0.5 + 0.1 + 0.8)")
    start = time.time()
    result_seq = await create_memory_sequential(test_content, test_user)
    elapsed_seq = time.time() - start
    print(f"   实际耗时: {elapsed_seq:.2f}s")
    print()
    
    # 测试并发执行
    print("2. 并发执行测试")
    print("   预期耗时: ~1.3s (max(0.5 + 0.1, 0.8))")
    start = time.time()
    result_con = await create_memory_concurrent(test_content, test_user)
    elapsed_con = time.time() - start
    print(f"   实际耗时: {elapsed_con:.2f}s")
    print()
    
    # 性能提升
    improvement = ((elapsed_seq - elapsed_con) / elapsed_seq) * 100
    print(f"性能提升: {improvement:.1f}%")
    print()
    
    # 验收标准
    print("验收标准检查:")
    if elapsed_con < 2.0:
        print(f"  [✓] 并发执行耗时 < 2s (实际: {elapsed_con:.2f}s)")
    else:
        print(f"  [✗] 并发执行耗时 < 2s (实际: {elapsed_con:.2f}s)")
    
    if elapsed_con < elapsed_seq:
        print(f"  [✓] 并发执行比顺序执行快")
    else:
        print(f"  [✗] 并发执行比顺序执行慢")
    
    print()
    
    return elapsed_con < 2.0 and elapsed_con < elapsed_seq


async def test_multiple_requests():
    """测试多次请求的性能稳定性"""
    
    print("=" * 60)
    print("多次请求性能测试")
    print("=" * 60)
    print()
    
    test_cases = [
        "短文本测试",
        "中等长度文本测试，包含更多信息",
        "长文本测试，包含更多详细信息，用于测试性能稳定性"
    ]
    
    results = []
    
    for i, content in enumerate(test_cases):
        print(f"测试用例 {i+1}: 长度 {len(content)} 字符")
        start = time.time()
        
        result = await create_memory_concurrent(content, "test_user")
        
        elapsed = time.time() - start
        results.append(elapsed)
        
        print(f"  耗时: {elapsed:.2f}s")
    
    print()
    
    # 统计
    avg_time = statistics.mean(results)
    max_time = max(results)
    
    print(f"平均耗时: {avg_time:.2f}s")
    print(f"最大耗时: {max_time:.2f}s")
    print()
    
    # 验收标准
    print("验收标准检查:")
    if max_time < 2.0:
        print(f"  [✓] 最大耗时 < 2s (实际: {max_time:.2f}s)")
    else:
        print(f"  [✗] 最大耗时 < 2s (实际: {max_time:.2f}s)")
    
    if avg_time < 1.5:
        print(f"  [✓] 平均耗时 < 1.5s (实际: {avg_time:.2f}s)")
    else:
        print(f"  [✗] 平均耗时 < 1.5s (实际: {avg_time:.2f}s)")
    
    print()
    
    return max_time < 2.0 and avg_time < 1.5


async def main():
    """主测试函数"""
    
    print("\n")
    print("╔══════════════════════════════════════════════════════════╗")
    print("║       Memory Recall - Phase 4 本地性能测试                ║")
    print("╚══════════════════════════════════════════════════════════╝")
    print()
    
    # 测试并发 vs 顺序
    result1 = await test_concurrent_vs_sequential()
    
    # 测试多次请求
    result2 = await test_multiple_requests()
    
    print()
    print("=" * 60)
    
    if result1 and result2:
        print("✓ 所有测试通过")
        return 0
    else:
        print("✗ 部分测试失败")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    exit(exit_code)
