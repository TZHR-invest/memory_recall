"""
测试智能召回服务
"""

import asyncio
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.services.smart_recall_service import get_smart_recall_service
from src.database import db


async def test_smart_recall():
    """测试智能召回"""

    test_queries = [
        "张三的朋友",
        "最近一周做了什么",
        "咖啡店",
        "开心的事情",
        "上周在咖啡店见的朋友",
        "关于项目的讨论",
    ]

    user_id = "test_user"

    print("\n" + "=" * 60)
    print("智能召回测试")
    print("=" * 60)

    smart_recall = get_smart_recall_service()

    for query in test_queries:
        print(f"\n查询: {query}")
        print("-" * 60)

        try:
            result = await smart_recall.smart_recall(
                query=query, user_id=user_id, limit=5
            )

            print(f"策略: {result['route_decision']['strategy']}")
            print(f"原因: {result['route_decision']['reason']}")
            print(f"参数: {result['route_decision']['params']}")
            print(f"召回记忆数: {result['memory_count']}")

            if result["memory_count"] > 0:
                print(f"前3条记忆:")
                for i, mem in enumerate(result["used_memories"][:3], 1):
                    print(f"  {i}. {mem.get('content', '')[:50]}...")

        except Exception as e:
            print(f"❌ 错误: {e}")

    print("\n" + "=" * 60)


async def test_strategy_selection():
    """测试策略选择"""

    print("\n" + "=" * 60)
    print("策略选择测试")
    print("=" * 60)

    test_cases = [
        ("张三的朋友", "graph_recall"),
        ("最近一周", "time_recall"),
        ("咖啡店", "keyword_recall"),
        ("开心的事情", "vector_recall"),
        ("上周在咖啡店见的朋友", "hybrid_recall"),
    ]

    smart_recall = get_smart_recall_service()

    for query, expected_strategy in test_cases:
        print(f"\n查询: {query}")
        print(f"期望策略: {expected_strategy}")

        try:
            route_decision = await smart_recall._select_recall_strategy(query)

            print(f"实际策略: {route_decision['strategy']}")
            print(f"原因: {route_decision['reason']}")

            if route_decision["strategy"] == expected_strategy:
                print("✅ 匹配")
            else:
                print("⚠️ 不匹配，但可能是合理的选择")

        except Exception as e:
            print(f"❌ 错误: {e}")

    print("\n" + "=" * 60)


async def main():
    """主函数"""

    try:
        await test_strategy_selection()
        await test_smart_recall()
    finally:
        await db.close()


if __name__ == "__main__":
    asyncio.run(main())
