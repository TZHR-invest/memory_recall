#!/usr/bin/env python3
"""
简化的端到端测试 - 分别测试每个功能
"""
import httpx
import asyncio
import time
import sys

BASE_URL = "http://192.168.0.206:8000"


def log(msg):
    """带 flush 的打印"""
    print(msg, flush=True)


async def test_1_create_memory():
    """测试 1: 创建记忆"""
    log("\n" + "="*60)
    log("测试 1: 创建记忆（带图谱）")
    log("="*60)
    
    async with httpx.AsyncClient(timeout=60.0) as client:
        try:
            start = time.time()
            response = await client.post(
                f"{BASE_URL}/api/v1/memories/with-graph",
                json={
                    "content": "今天和张三在咖啡店聊天，讨论了机器学习项目",
                    "user_id": "test_user_e2e",
                    "enable_graph": True
                }
            )
            elapsed = time.time() - start
            
            log(f"状态码: {response.status_code}")
            log(f"响应时间: {elapsed:.2f}s")
            
            if response.status_code == 200:
                data = response.json()
                log(f"✅ 创建成功")
                log(f"   memory_id: {data.get('memory_id')}")
                log(f"   实体数: {data.get('graph', {}).get('entity_count', 0)}")
                log(f"   关系数: {data.get('graph', {}).get('relation_count', 0)}")
                
                entities = data.get('graph', {}).get('entities', [])
                log(f"   实体列表: {[e['entity'] for e in entities]}")
                
                return True
            else:
                log(f"❌ 失败: {response.text}")
                return False
        except Exception as e:
            log(f"❌ 异常: {e}")
            return False


async def test_2_search_memory():
    """测试 2: 搜索记忆"""
    log("\n" + "="*60)
    log("测试 2: 搜索记忆")
    log("="*60)
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            response = await client.post(
                f"{BASE_URL}/api/v1/memories/search",
                json={
                    "query": "咖啡店 聊天",
                    "limit": 5
                }
            )
            
            log(f"状态码: {response.status_code}")
            
            if response.status_code == 200:
                data = response.json()
                results = data.get('data', {}).get('results', [])
                log(f"✅ 搜索成功")
                log(f"   结果数: {len(results)}")
                if results:
                    log(f"   最相关: {results[0].get('content', '')[:50]}...")
                return True
            else:
                log(f"❌ 失败: {response.text}")
                return False
        except Exception as e:
            log(f"❌ 异常: {e}")
            return False


async def test_3_entity_accuracy():
    """测试 3: 实体提取准确率"""
    log("\n" + "="*60)
    log("测试 3: 实体提取准确率")
    log("="*60)
    
    test_cases = [
        ("今天和张三在咖啡店聊天", ["张三", "咖啡店"]),
        ("明天的会议改到下午3点，记得准备PPT", ["会议", "PPT"]),
        ("我和老王是多年的朋友", ["老王"]),
    ]
    
    correct = 0
    total = 0
    
    async with httpx.AsyncClient(timeout=60.0) as client:
        for content, expected in test_cases:
            try:
                response = await client.post(
                    f"{BASE_URL}/api/v1/memories/with-graph",
                    json={
                        "content": content,
                        "user_id": "test_user_accuracy",
                        "enable_graph": True
                    }
                )
                
                if response.status_code == 200:
                    data = response.json()
                    entities = [e['entity'] for e in data.get('graph', {}).get('entities', [])]
                    
                    log(f"\n   内容: {content}")
                    log(f"   期望: {expected}")
                    log(f"   实际: {entities}")
                    
                    for exp in expected:
                        total += 1
                        if any(exp in e for e in entities):
                            correct += 1
                            log(f"   ✅ 找到: {exp}")
                        else:
                            log(f"   ❌ 未找到: {exp}")
            except Exception as e:
                log(f"   异常: {e}")
    
    accuracy = correct / total if total > 0 else 0
    log(f"\n实体提取准确率: {accuracy:.1%} ({correct}/{total})")
    
    return accuracy >= 0.90


async def test_4_performance():
    """测试 4: 性能测试"""
    log("\n" + "="*60)
    log("测试 4: 性能测试")
    log("="*60)
    
    times = []
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        for i in range(5):
            try:
                start = time.time()
                response = await client.post(
                    f"{BASE_URL}/api/v1/memories/with-graph",
                    json={
                        "content": f"测试记忆 {i}",
                        "user_id": "test_user_perf",
                        "enable_graph": True
                    }
                )
                elapsed = time.time() - start
                times.append(elapsed)
                log(f"   请求 {i}: {elapsed:.2f}s (状态: {response.status_code})")
            except Exception as e:
                log(f"   请求 {i} 异常: {e}")
    
    if times:
        avg = sum(times) / len(times)
        log(f"\n平均响应时间: {avg:.2f}s")
        log(f"最大响应时间: {max(times):.2f}s")
        log(f"最小响应时间: {min(times):.2f}s")
        return avg < 2.0
    return False


async def main():
    log("\n" + "="*60)
    log("Memory Recall 端到端测试（简化版）")
    log("="*60)
    
    results = {}
    
    # 测试 1
    results["创建记忆"] = await test_1_create_memory()
    
    # 测试 2
    results["搜索记忆"] = await test_2_search_memory()
    
    # 测试 3
    results["实体准确率"] = await test_3_entity_accuracy()
    
    # 测试 4
    results["性能测试"] = await test_4_performance()
    
    # 汇总
    log("\n" + "="*60)
    log("测试结果汇总")
    log("="*60)
    
    for name, passed in results.items():
        status = "✅ 通过" if passed else "❌ 失败"
        log(f"{name}: {status}")
    
    passed = sum(1 for v in results.values() if v)
    total = len(results)
    log(f"\n总计: {passed}/{total} 通过")
    
    if passed == total:
        log("\n🎉 所有测试通过！")


if __name__ == "__main__":
    asyncio.run(main())
