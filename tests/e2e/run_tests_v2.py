#!/usr/bin/env python3
"""
端到端测试 - 测试结果记录
"""
import httpx
import asyncio
import time
import json

BASE_URL = "http://192.168.0.206:8000"
RESULTS_FILE = "tests/e2e/test_results.json"


async def run_tests():
    """运行所有测试并记录结果"""
    results = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "tests": {}
    }
    
    async with httpx.AsyncClient(timeout=90.0) as client:
        
        # 测试 1: 创建记忆
        print("测试 1: 创建记忆（带图谱）...")
        try:
            start = time.time()
            r = await client.post(
                f"{BASE_URL}/api/v1/memories/with-graph",
                json={
                    "content": "今天和张三在咖啡店聊天，讨论了机器学习项目",
                    "user_id": "test_e2e",
                    "enable_graph": True
                }
            )
            elapsed = time.time() - start
            
            results["tests"]["create_memory"] = {
                "status": "passed" if r.status_code == 200 else "failed",
                "response_time": elapsed,
                "status_code": r.status_code
            }
            
            if r.status_code == 200:
                data = r.json()
                results["tests"]["create_memory"]["memory_id"] = data.get("memory_id")
                results["tests"]["create_memory"]["entity_count"] = data.get("graph", {}).get("entity_count", 0)
                results["tests"]["create_memory"]["entities"] = [e["entity"] for e in data.get("graph", {}).get("entities", [])]
                print(f"  ✅ 通过 - 实体: {results['tests']['create_memory']['entities']}")
            else:
                print(f"  ❌ 失败 - 状态码: {r.status_code}")
        except Exception as e:
            results["tests"]["create_memory"] = {"status": "error", "error": str(e)}
            print(f"  ❌ 错误: {e}")
        
        # 测试 2: 搜索记忆
        print("\n测试 2: 搜索记忆...")
        try:
            r = await client.post(
                f"{BASE_URL}/api/v1/memories/search",
                json={"query": "咖啡店", "limit": 5}
            )
            
            results["tests"]["search_memory"] = {
                "status": "passed" if r.status_code == 200 else "failed",
                "status_code": r.status_code
            }
            
            if r.status_code == 200:
                data = r.json()
                result_count = len(data.get("data", {}).get("results", []))
                results["tests"]["search_memory"]["result_count"] = result_count
                print(f"  ✅ 通过 - 结果数: {result_count}")
            else:
                print(f"  ❌ 失败 - 状态码: {r.status_code}")
        except Exception as e:
            results["tests"]["search_memory"] = {"status": "error", "error": str(e)}
            print(f"  ❌ 错误: {e}")
        
        # 测试 3: 实体提取准确率
        print("\n测试 3: 实体提取准确率...")
        test_cases = [
            ("今天和张三在咖啡店聊天", ["张三", "咖啡店"]),
            ("明天的会议改到下午3点，记得准备PPT", ["会议", "PPT"]),
            ("我和老王是多年的朋友", ["老王"]),
            ("今天在公司加班到很晚", ["公司"]),
        ]
        
        correct = 0
        total = 0
        entity_details = []
        
        for content, expected in test_cases:
            try:
                r = await client.post(
                    f"{BASE_URL}/api/v1/memories/with-graph",
                    json={"content": content, "user_id": "test_accuracy", "enable_graph": True}
                )
                
                if r.status_code == 200:
                    data = r.json()
                    entities = [e["entity"] for e in data.get("graph", {}).get("entities", [])]
                    
                    case_result = {
                        "content": content,
                        "expected": expected,
                        "actual": entities,
                        "found": []
                    }
                    
                    for exp in expected:
                        total += 1
                        if any(exp in e for e in entities):
                            correct += 1
                            case_result["found"].append(exp)
                    
                    entity_details.append(case_result)
            except Exception as e:
                print(f"  异常: {e}")
        
        accuracy = correct / total if total > 0 else 0
        results["tests"]["entity_accuracy"] = {
            "status": "passed" if accuracy >= 0.90 else "failed",
            "accuracy": accuracy,
            "correct": correct,
            "total": total,
            "details": entity_details
        }
        print(f"  准确率: {accuracy:.1%} ({correct}/{total})")
        print(f"  {'✅ 通过' if accuracy >= 0.90 else '❌ 未达标'}")
        
        # 测试 4: 性能测试
        print("\n测试 4: 性能测试...")
        times = []
        
        for i in range(5):
            try:
                start = time.time()
                r = await client.post(
                    f"{BASE_URL}/api/v1/memories/with-graph",
                    json={"content": f"性能测试 {i}", "user_id": "test_perf", "enable_graph": True}
                )
                times.append(time.time() - start)
            except Exception as e:
                print(f"  请求 {i} 异常: {e}")
        
        if times:
            avg = sum(times) / len(times)
            max_t = max(times)
            min_t = min(times)
            
            results["tests"]["performance"] = {
                "status": "passed" if avg < 2.0 else "failed",
                "avg_time": avg,
                "max_time": max_t,
                "min_time": min_t,
                "samples": len(times)
            }
            print(f"  平均响应时间: {avg:.2f}s")
            print(f"  最大: {max_t:.2f}s, 最小: {min_t:.2f}s")
            print(f"  {'✅ 通过' if avg < 2.0 else '❌ 未达标'}")
        else:
            results["tests"]["performance"] = {"status": "error", "error": "No successful requests"}
            print("  ❌ 所有请求失败")
    
    # 保存结果
    with open(RESULTS_FILE, "w") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    
    # 汇总
    print("\n" + "="*60)
    print("测试结果汇总")
    print("="*60)
    
    passed = sum(1 for t in results["tests"].values() if t.get("status") == "passed")
    total = len(results["tests"])
    
    for name, test in results["tests"].items():
        status = "✅ 通过" if test.get("status") == "passed" else "❌ 失败"
        print(f"{name}: {status}")
    
    print(f"\n总计: {passed}/{total} 通过")
    print(f"结果已保存到: {RESULTS_FILE}")
    
    return results


if __name__ == "__main__":
    asyncio.run(run_tests())
