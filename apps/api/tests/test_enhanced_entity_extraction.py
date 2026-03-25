"""
测试增强实体提取器
演示如何解决实体词典精确匹配的局限性
"""

import asyncio
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.services.enhanced_entity_extractor import get_enhanced_entity_extractor
from src.database import db


async def test_entity_matching():
    """测试实体匹配策略"""

    print("\n" + "=" * 80)
    print("增强实体提取测试 - 解决精确匹配的局限性")
    print("=" * 80)

    extractor = get_enhanced_entity_extractor()

    # 初始化（模拟实体词典）
    extractor._initialized = True
    extractor.entity_dict = {
        "新技能学习": {
            "id": "e1",
            "type": "topic",
            "confidence": 0.9,
            "user_id": "test_user",
        },
        "张三": {
            "id": "e2",
            "type": "person",
            "confidence": 0.95,
            "user_id": "test_user",
        },
        "咖啡店": {
            "id": "e3",
            "type": "location",
            "confidence": 0.9,
            "user_id": "test_user",
        },
        "项目管理": {
            "id": "e4",
            "type": "topic",
            "confidence": 0.85,
            "user_id": "test_user",
        },
        "技术方案": {
            "id": "e5",
            "type": "topic",
            "confidence": 0.88,
            "user_id": "test_user",
        },
        "星巴克咖啡": {
            "id": "e6",
            "type": "location",
            "confidence": 0.9,
            "user_id": "test_user",
        },
    }

    user_id = "test_user"

    # ==================== 测试用例 ====================
    test_cases = [
        {
            "query": "学习了什么新技能",
            "expected_entity": "新技能学习",
            "issue": "查询和实体名称字序不同",
            "solutions": ["keyword", "fuzzy", "semantic"],
        },
        {
            "query": "张三的朋友",
            "expected_entity": "张三",
            "issue": "实体名称被查询包含",
            "solutions": ["exact", "keyword"],
        },
        {
            "query": "在咖啡的地方",
            "expected_entity": "咖啡店",
            "issue": "名称不完全一致",
            "solutions": ["keyword", "fuzzy", "semantic"],
        },
        {
            "query": "项目管理的经验",
            "expected_entity": "项目管理",
            "issue": "实体名称被查询包含",
            "solutions": ["exact", "keyword"],
        },
        {
            "query": "技术相关的方案",
            "expected_entity": "技术方案",
            "issue": "插入干扰词",
            "solutions": ["keyword", "regex"],
        },
        {
            "query": "星巴克",
            "expected_entity": "星巴克咖啡",
            "issue": "查询是实体的子串",
            "solutions": ["exact", "fuzzy"],
        },
        {
            "query": "学的新东西",
            "expected_entity": "新技能学习",
            "issue": "语义相似但字面不同",
            "solutions": ["semantic"],
        },
    ]

    print("\n测试用例:")
    print("-" * 80)

    for i, test_case in enumerate(test_cases, 1):
        query = test_case["query"]
        expected = test_case["expected_entity"]
        issue = test_case["issue"]

        print(f'\n{i}. 查询: "{query}"')
        print(f'   期望实体: "{expected}"')
        print(f"   问题: {issue}")
        print(f"   解决方案: {', '.join(test_case['solutions'])}")
        print("-" * 40)

        # 测试各种方法
        print("   测试结果:")

        # 1. 精确匹配
        exact_results = extractor._exact_match(
            query,
            {k: v for k, v in extractor.entity_dict.items() if v["user_id"] == user_id},
        )
        if exact_results:
            print(
                f"   ✅ 精确匹配: {exact_results[0][0]} (置信度: {exact_results[0][1]:.2f})"
            )
        else:
            print(f"   ❌ 精确匹配: 未找到")

        # 2. 关键词匹配
        keyword_results = extractor._keyword_match(
            query,
            {k: v for k, v in extractor.entity_dict.items() if v["user_id"] == user_id},
        )
        if keyword_results:
            print(
                f"   ✅ 关键词匹配: {keyword_results[0][0]} (置信度: {keyword_results[0][1]:.2f})"
            )
        else:
            print(f"   ❌ 关键词匹配: 未找到")

        # 3. 模糊匹配
        fuzzy_results = extractor._fuzzy_match(
            query,
            {k: v for k, v in extractor.entity_dict.items() if v["user_id"] == user_id},
            threshold=0.6,
        )
        if fuzzy_results:
            print(
                f"   ✅ 模糊匹配: {fuzzy_results[0][0]} (相似度: {fuzzy_results[0][1]:.2f})"
            )
        else:
            print(f"   ❌ 模糊匹配: 未找到")

        # 4. 正则匹配
        regex_results = extractor._regex_match(
            query,
            {k: v for k, v in extractor.entity_dict.items() if v["user_id"] == user_id},
        )
        if regex_results:
            print(
                f"   ✅ 正则匹配: {regex_results[0][0]} (置信度: {regex_results[0][1]:.2f})"
            )
        else:
            print(f"   ❌ 正则匹配: 未找到")

        # 5. 综合测试
        all_results = extractor.extract_entities(query, user_id)
        if all_results:
            print(f"   ⭐ 综合匹配:")
            for entity_name, method, confidence in all_results[:3]:
                marker = "✅" if entity_name == expected else "⚠️"
                print(
                    f"      {marker} {entity_name} (方法: {method}, 置信度: {confidence:.2f})"
                )
        else:
            print(f"   ❌ 综合匹配: 未找到任何实体")

    # ==================== 策略对比 ====================
    print("\n\n" + "=" * 80)
    print("策略对比总结")
    print("=" * 80)

    strategies = [
        {
            "name": "精确匹配 (exact)",
            "优点": "速度快、准确率高",
            "缺点": "只能匹配完全包含的字符串",
            "适用场景": "实体名称固定、查询包含实体名称",
            "示例": "查询'张三的朋友' → 匹配'张三'",
        },
        {
            "name": "关键词匹配 (keyword)",
            "优点": "容忍字序变化、容错性好",
            "缺点": "可能误匹配（关键词重叠但不相关）",
            "适用场景": "实体名称和查询包含相同关键词",
            "示例": "查询'学习了什么新技能' → 匹配'新技能学习'",
        },
        {
            "name": "模糊匹配 (fuzzy)",
            "优点": "容忍拼写错误、部分匹配",
            "缺点": "性能较慢、需要设置阈值",
            "适用场景": "查询和实体名称相似但不完全一致",
            "示例": "查询'咖啡' → 匹配'咖啡店'",
        },
        {
            "name": "语义匹配 (semantic)",
            "优点": "理解语义相似性、最强鲁棒性",
            "缺点": "需要生成 embedding、性能最慢",
            "适用场景": "查询和实体语义相似但字面不同",
            "示例": "查询'学的新东西' → 匹配'新技能学习'",
        },
        {
            "name": "正则匹配 (regex)",
            "优点": "容忍插入干扰词",
            "缺点": "可能误匹配、性能较慢",
            "适用场景": "查询中插入干扰词",
            "示例": "查询'技术相关的方案' → 匹配'技术方案'",
        },
        {
            "name": "综合策略 (hybrid)",
            "优点": "结合多种方法、最高召回率",
            "缺点": "复杂度高、需要调优权重",
            "适用场景": "生产环境推荐",
            "示例": "按置信度排序返回所有匹配结果",
        },
    ]

    for strategy in strategies:
        print(f"\n{strategy['name']}:")
        print(f"  优点: {strategy['优点']}")
        print(f"  缺点: {strategy['缺点']}")
        print(f"  适用场景: {strategy['适用场景']}")
        print(f"  示例: {strategy['示例']}")

    # ==================== 性能对比 ====================
    print("\n\n" + "=" * 80)
    print("性能对比")
    print("=" * 80)

    performance_data = [
        ("精确匹配", "O(n)", "< 1ms", "1000+", "最高"),
        ("关键词匹配", "O(n * m)", "5-10ms", "100-500", "中"),
        ("模糊匹配", "O(n * m²)", "50-100ms", "10-50", "慢"),
        ("语义匹配", "O(n * embedding)", "100-500ms", "5-20", "最慢"),
        ("正则匹配", "O(n * pattern)", "10-50ms", "50-100", "中"),
        ("综合策略", "混合", "100-200ms", "10-50", "推荐"),
    ]

    print(
        f"\n{'策略':<15} {'时间复杂度':<15} {'耗时':<15} {'推荐实体数量':<15} {'速度':<10}"
    )
    print("-" * 80)
    for name, complexity, time_cost, entity_count, speed in performance_data:
        print(
            f"{name:<15} {complexity:<15} {time_cost:<15} {entity_count:<15} {speed:<10}"
        )

    # ==================== 使用建议 ====================
    print("\n\n" + "=" * 80)
    print("使用建议")
    print("=" * 80)

    suggestions = [
        "1. 默认使用：精确匹配 + 关键词匹配（快速召回）",
        "2. 精确匹配未找到时：启用模糊匹配（中等召回）",
        "3. 关键查询时：启用语义匹配（最高召回，但慢）",
        "4. 生产环境：缓存常用查询结果，减少重复计算",
        "5. 调优建议：根据实际数据调整阈值和权重",
        "6. 监控指标：记录各策略的成功率和耗时",
    ]

    for suggestion in suggestions:
        print(f"  {suggestion}")

    print("\n" + "=" * 80 + "\n")


async def main():
    """主函数"""
    await test_entity_matching()


if __name__ == "__main__":
    asyncio.run(main())
