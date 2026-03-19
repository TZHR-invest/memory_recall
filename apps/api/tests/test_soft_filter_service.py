"""
测试软过滤服务（Phase 3 - 任务 2）

测试目标：
1. 不排除任何结果
2. 匹配结果权重提升
3. 关系扩展正常工作
"""

import asyncio
import sys
import os

# 添加 apps/api 到 Python 路径
api_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, api_path)

from src.services.soft_filter_service import get_soft_filter_service


async def test_soft_filter_basic():
    """测试基本软过滤"""
    print("=" * 80)
    print("测试 1: 基本软过滤")
    print("=" * 80)
    
    service = get_soft_filter_service()
    
    # 测试数据
    results = [
        {"content": "和家人去郊外", "similarity": 0.8},
        {"content": "和朋友吃饭", "similarity": 0.75}
    ]
    
    print(f"\n原始结果:")
    for i, r in enumerate(results, 1):
        print(f"  {i}. {r['content']} (相似度: {r['similarity']:.2f})")
    
    # 应用软过滤
    filtered = await service.apply_soft_filter(results, person_filter="家人")
    
    print(f"\n软过滤后（person_filter='家人'）:")
    for i, r in enumerate(filtered, 1):
        match_info = f" [匹配: {r.get('person_match')}]" if 'person_match' in r else ""
        print(f"  {i}. {r['content']} (相似度: {r['similarity']:.2f}){match_info}")
    
    # 验证
    assert len(filtered) == 2, "不应该排除任何结果"
    assert filtered[0]["similarity"] > 0.8, "匹配结果权重应该提升"
    assert filtered[0].get("person_match") == "家人", "应该标记匹配的人物"
    
    print("\n✓ 基本软过滤测试通过")
    return True


async def test_location_normalization():
    """测试地点归一化"""
    print("\n" + "=" * 80)
    print("测试 2: 地点归一化")
    print("=" * 80)
    
    service = get_soft_filter_service()
    
    # 测试数据
    test_cases = [
        ("星巴克", "咖啡店"),
        ("瑞幸", "咖啡店"),
        ("肯德基", "快餐店"),
        ("海底捞", "火锅店"),
        ("万达", "商场")
    ]
    
    print(f"\n归一化测试:")
    for original, expected in test_cases:
        normalized = service._normalize_location(original)
        status = "✓" if normalized == expected else "✗"
        print(f"  {status} {original} → {normalized} (预期: {expected})")
        assert normalized == expected, f"{original} 应归一化为 {expected}，实际为 {normalized}"
    
    print("\n✓ 地点归一化测试通过")
    return True


async def test_person_relation_expansion():
    """测试人物关系扩展"""
    print("\n" + "=" * 80)
    print("测试 3: 人物关系扩展")
    print("=" * 80)
    
    service = get_soft_filter_service()
    
    # 测试数据
    test_cases = [
        ("家人", ["老婆", "老公", "孩子", "父母", "爸爸", "妈妈", "儿子", "女儿", "兄弟", "姐妹"]),
        ("朋友", ["朋友", "哥们", "闺蜜", "老友"]),
        ("同事", ["同事", "搭档", "合作者"])
    ]
    
    print(f"\n关系扩展测试:")
    for relation_type, expected in test_cases:
        expanded = service._expand_person_relation(relation_type)
        status = "✓" if set(expanded) == set(expected) else "✗"
        print(f"  {status} {relation_type} → {expanded}")
        assert set(expanded) == set(expected), f"{relation_type} 扩展不正确"
    
    print("\n✓ 人物关系扩展测试通过")
    return True


async def test_soft_filter_with_location():
    """测试地点软过滤"""
    print("\n" + "=" * 80)
    print("测试 4: 地点软过滤")
    print("=" * 80)
    
    service = get_soft_filter_service()
    
    # 测试数据
    results = [
        {"content": "在星巴克喝咖啡", "similarity": 0.8},
        {"content": "去瑞幸买咖啡", "similarity": 0.75},
        {"content": "在家休息", "similarity": 0.7}
    ]
    
    print(f"\n原始结果:")
    for i, r in enumerate(results, 1):
        print(f"  {i}. {r['content']} (相似度: {r['similarity']:.2f})")
    
    # 应用地点过滤（星巴克应归一化为咖啡店）
    filtered = await service.apply_soft_filter(results, location_filter="星巴克")
    
    print(f"\n软过滤后（location_filter='星巴克'）:")
    for i, r in enumerate(filtered, 1):
        match_info = f" [匹配: {r.get('location_match')}]" if 'location_match' in r else ""
        print(f"  {i}. {r['content']} (相似度: {r['similarity']:.2f}){match_info}")
    
    # 验证
    assert len(filtered) == 3, "不应该排除任何结果"
    
    # 星巴克应该被提升
    starbucks_result = next((r for r in filtered if "星巴克" in r["content"]), None)
    assert starbucks_result is not None, "应该包含星巴克结果"
    assert starbucks_result["similarity"] > 0.8, "星巴克结果权重应该提升"
    
    print("\n✓ 地点软过滤测试通过")
    return True


async def test_combined_filter():
    """测试组合过滤"""
    print("\n" + "=" * 80)
    print("测试 5: 组合过滤（地点 + 人物）")
    print("=" * 80)
    
    service = get_soft_filter_service()
    
    # 测试数据
    results = [
        {"content": "和家人在星巴克喝咖啡", "similarity": 0.8},
        {"content": "和朋友去瑞幸", "similarity": 0.75},
        {"content": "自己在家休息", "similarity": 0.7}
    ]
    
    print(f"\n原始结果:")
    for i, r in enumerate(results, 1):
        print(f"  {i}. {r['content']} (相似度: {r['similarity']:.2f})")
    
    # 应用组合过滤
    filtered = await service.apply_soft_filter(
        results,
        location_filter="星巴克",
        person_filter="家人"
    )
    
    print(f"\n软过滤后（location_filter='星巴克', person_filter='家人'）:")
    for i, r in enumerate(filtered, 1):
        match_info = []
        if 'location_match' in r:
            match_info.append(f"地点: {r['location_match']}")
        if 'person_match' in r:
            match_info.append(f"人物: {r['person_match']}")
        match_str = f" [匹配: {', '.join(match_info)}]" if match_info else ""
        print(f"  {i}. {r['content']} (相似度: {r['similarity']:.2f}){match_str}")
    
    # 验证
    assert len(filtered) == 3, "不应该排除任何结果"
    
    # 第一个结果应该最高（匹配了地点和人物）
    assert filtered[0]["content"] == "和家人在星巴克喝咖啡", "最匹配的结果应排在第一位"
    assert filtered[0]["similarity"] > 0.8, "双重匹配的结果权重应该提升更多"
    
    print("\n✓ 组合过滤测试通过")
    return True


async def test_no_exclusion():
    """测试不排除任何结果"""
    print("\n" + "=" * 80)
    print("测试 6: 不排除任何结果")
    print("=" * 80)
    
    service = get_soft_filter_service()
    
    # 测试数据
    results = [
        {"content": "和家人去郊外", "similarity": 0.8},
        {"content": "和朋友吃饭", "similarity": 0.75},
        {"content": "自己去公园", "similarity": 0.7}
    ]
    
    print(f"\n原始结果数量: {len(results)}")
    
    # 应用软过滤（使用不存在的过滤条件）
    filtered = await service.apply_soft_filter(results, person_filter="不存在的过滤条件")
    
    print(f"软过滤后结果数量: {len(filtered)}")
    
    # 验证
    assert len(filtered) == len(results), "不应该排除任何结果"
    
    # 所有结果的相似度应该保持不变或降低（因为不匹配）
    for original, filtered_result in zip(results, filtered):
        print(f"  {original['content']}: {original['similarity']:.2f} → {filtered_result['similarity']:.2f}")
    
    print("\n✓ 不排除任何结果测试通过")
    return True


async def test_keyword_utils():
    """测试关键词工具方法"""
    print("\n" + "=" * 80)
    print("测试 7: 关键词工具方法")
    print("=" * 80)
    
    service = get_soft_filter_service()
    
    # 测试地点关键词
    location_keywords = service.get_location_keywords("星巴克")
    print(f"\n地点关键词（星巴克）: {location_keywords}")
    assert "星巴克" in location_keywords, "应包含原始地点"
    assert "咖啡店" in location_keywords, "应包含归一化地点"
    
    # 测试人物关键词
    person_keywords = service.get_person_keywords("家人")
    print(f"人物关键词（家人）: {person_keywords}")
    assert "家人" in person_keywords, "应包含原始人物类型"
    assert "老婆" in person_keywords or "老公" in person_keywords, "应包含扩展的人物"
    
    print("\n✓ 关键词工具方法测试通过")
    return True


async def main():
    """运行所有测试"""
    print("\n" + "=" * 80)
    print("Phase 3 - 任务 2: 软过滤服务")
    print("=" * 80)
    
    tests = [
        ("基本软过滤", test_soft_filter_basic),
        ("地点归一化", test_location_normalization),
        ("人物关系扩展", test_person_relation_expansion),
        ("地点软过滤", test_soft_filter_with_location),
        ("组合过滤", test_combined_filter),
        ("不排除任何结果", test_no_exclusion),
        ("关键词工具方法", test_keyword_utils)
    ]
    
    passed = 0
    failed = 0
    
    for test_name, test_func in tests:
        try:
            success = await test_func()
            if success:
                passed += 1
            else:
                failed += 1
        except AssertionError as e:
            print(f"\n✗ 测试失败: {test_name}")
            print(f"  错误: {e}")
            failed += 1
        except Exception as e:
            print(f"\n✗ 测试异常: {test_name}")
            print(f"  错误: {e}")
            failed += 1
    
    # 输出总结
    print("\n" + "=" * 80)
    print("测试总结")
    print("=" * 80)
    print(f"总测试数: {len(tests)}")
    print(f"通过数: {passed}")
    print(f"失败数: {failed}")
    print(f"通过率: {passed / len(tests) * 100:.1f}%")
    
    if passed == len(tests):
        print("\n✓✓✓ 所有测试通过！软过滤服务已准备就绪。")
        return True
    else:
        print("\n✗ 部分测试失败")
        return False


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
