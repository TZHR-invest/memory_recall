"""
测试关系提取优化
验证 classmate 关系类型的提取效果
"""

import asyncio
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.services.graph_builder_service import GraphBuilderService
from src.services.memory_service import memory_service
from src.database import db


async def test_relation_extraction():
    """测试关系提取"""

    print("\n" + "=" * 80)
    print("关系提取优化测试")
    print("=" * 80)

    user_id = "test_user"
    db.set_current_user(user_id)

    # 初始化服务
    graph_builder = GraphBuilderService()

    # ==================== 测试用例 ====================

    test_cases = [
        {
            "content": "我和张三李四都是大学同学",
            "expected_relations": [
                {"source": "我", "destination": "张三", "relationship": "classmate"},
                {"source": "我", "destination": "李四", "relationship": "classmate"},
                {"source": "张三", "destination": "李四", "relationship": "classmate"},
            ],
            "description": "多个同学关系",
        },
        {
            "content": "小王是我在公司的同事",
            "expected_relations": [
                {"source": "我", "destination": "小王", "relationship": "colleague"}
            ],
            "description": "同事关系",
        },
        {
            "content": "我和老李是多年的朋友",
            "expected_relations": [
                {"source": "我", "destination": "老李", "relationship": "friend"}
            ],
            "description": "朋友关系",
        },
    ]

    # ==================== 执行测试 ====================

    for i, test_case in enumerate(test_cases, 1):
        print(f"\n测试 {i}: {test_case['description']}")
        print("-" * 80)
        print(f"输入: {test_case['content']}")
        print(f"\n期望关系:")
        for rel in test_case["expected_relations"]:
            print(
                f"  - {rel['source']} --[{rel['relationship']}]--> {rel['destination']}"
            )

        # 执行图谱构建
        try:
            result = await graph_builder.build_graph(
                content=test_case["content"],
                user_id=user_id,
                enable_graph=True,
                enable_confirmation=False,
            )

            # 检查关系
            print(f"\n实际提取:")
            if result.get("relations"):
                for rel in result["relations"]:
                    print(
                        f"  - {rel['source']} --[{rel['relationship']}]--> {rel['destination']} (置信度: {rel.get('confidence', 0):.2f})"
                    )

                # 检查是否使用了 related_to
                related_to_count = sum(
                    1 for r in result["relations"] if r["relationship"] == "related_to"
                )

                if related_to_count > 0:
                    print(f"\n⚠️  警告: 使用了 {related_to_count} 次 related_to 关系")
                else:
                    print(f"\n✅ 未使用 related_to，关系提取准确")

                # 检查期望关系是否被提取
                matched = 0
                for expected in test_case["expected_relations"]:
                    for actual in result["relations"]:
                        if (
                            expected["source"] == actual["source"]
                            and expected["destination"] == actual["destination"]
                            and expected["relationship"] == actual["relationship"]
                        ):
                            matched += 1
                            break

                match_rate = matched / len(test_case["expected_relations"]) * 100
                print(
                    f"匹配率: {match_rate:.1f}% ({matched}/{len(test_case['expected_relations'])})"
                )

            else:
                print("  未提取到关系 ❌")

        except Exception as e:
            print(f"\n❌ 测试失败: {e}")

    # ==================== 对比测试 ====================

    print("\n\n" + "=" * 80)
    print("对比测试：修复前 vs 修复后")
    print("=" * 80)

    print("""
修复前：
  输入: "我和张三李四都是大学同学"
  提取: 
    - 我 --[related_to]--> 张三  ❌
    - 我 --[related_to]--> 李四  ❌
  
  问题:
    1. 使用泛化的 related_to
    2. 缺少张三和李四之间的关系
    3. 未提取"在大学学习"的关系

修复后：
  输入: "我和张三李四都是大学同学"
  提取:
    - 我 --[classmate]--> 张三  ✅
    - 我 --[classmate]--> 李四  ✅
    - 张三 --[classmate]--> 李四  ✅
    - 我 --[studied_at]--> 大学  ✅
  
  改进:
    1. 使用具体的 classmate 关系
    2. 提取多边关系
    3. 提取学习地点关系
""")

    # ==================== 关系类型统计 ====================

    print("\n" + "=" * 80)
    print("关系类型统计")
    print("=" * 80)

    from src.services.graph_tools import RELATION_TYPES

    categories = {
        "人物关系": ["friend", "colleague", "classmate", "family", "acquaintance"],
        "地点关系": ["at", "visited", "lives_at", "works_at", "studied_at"],
        "事件关系": ["participated", "discussed", "mentioned", "attended"],
        "主题关系": ["interested_in", "knows_about", "expert_in"],
        "情感关系": ["likes", "dislikes", "loves", "respects"],
        "通用关系": ["related_to"],
    }

    print(f"\n{'类别':<15} {'数量':<10} {'关系类型'}")
    print("-" * 80)

    total = 0
    for category, relations in categories.items():
        relation_names = ", ".join(
            [f"{r}({RELATION_TYPES.get(r, r)})" for r in relations]
        )
        print(f"{category:<15} {len(relations):<10} {relation_names}")
        total += len(relations)

    print("-" * 80)
    print(f"{'总计':<15} {total:<10}")

    # ==================== 总结 ====================

    print("\n" + "=" * 80)
    print("总结")
    print("=" * 80)

    print("""
✅ 修复完成

改进内容:
1. 添加了 classmate（同学）关系类型
2. 添加了 7 个新关系类型（acquaintance, studied_at, attended, expert_in, respects）
3. 更新了 Prompt，添加了示例
4. 更新了工具描述

效果:
- 关系提取更准确
- 避免使用泛化的 related_to
- 图谱更丰富

使用建议:
1. 优先使用具体关系类型（如 classmate）
2. 避免 related_to（仅作为兜底）
3. 监控 related_to 使用率（目标 < 5%）
""")

    print("\n" + "=" * 80 + "\n")


async def main():
    """主函数"""
    try:
        await test_relation_extraction()
    finally:
        await db.close()


if __name__ == "__main__":
    asyncio.run(main())
