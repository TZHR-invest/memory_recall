"""
Phase 3 集成测试

测试目标：
1. 场景自适应正常工作
2. 确认服务集成成功
3. 完整流程测试通过
"""

import asyncio
import sys
import os

# 添加 apps/api 到 Python 路径
api_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, api_path)

# 模拟数据库连接（避免实际连接）
class MockDB:
    async def fetch(self, query, *args):
        return []
    
    async def fetchrow(self, query, *args):
        return None
    
    async def fetchval(self, query, *args):
        return None
    
    async def execute(self, query, *args):
        return None

# 模拟 LLM 服务
class MockLLMService:
    async def call_with_tools(self, system_prompt, user_prompt, tools):
        # 模拟返回场景自适应提取结果
        if "extract_entities_with_scenario" in str(tools):
            return {
                "tool_calls": [{
                    "function": {
                        "name": "extract_entities_with_scenario",
                        "arguments": {
                            "scenario": "daily_chat",
                            "entities": [
                                {"entity": "老王", "entity_type": "person", "confidence": 0.9},
                                {"entity": "咖啡店", "entity_type": "location", "confidence": 0.85}
                            ]
                        }
                    }
                }]
            }
        # 模拟返回关系提取结果
        elif "establish_relations" in str(tools):
            return {
                "tool_calls": [{
                    "function": {
                        "name": "establish_relations",
                        "arguments": {
                            "relations": [
                                {"source": "老王", "destination": "咖啡店", "relationship": "at", "confidence": 0.88}
                            ]
                        }
                    }
                }]
            }
        return {"content": "{}"}

# 测试场景自适应集成
async def test_scenario_adaptive_integration():
    """测试场景自适应集成"""
    print("=" * 80)
    print("测试 1: 场景自适应集成")
    print("=" * 80)
    
    # 导入服务
    from src.services.graph_builder_service import GraphBuilderService
    
    # 创建服务实例并注入模拟依赖
    service = GraphBuilderService()
    service.llm_service = MockLLMService()
    
    # 测试场景自适应提取
    content = "和老王在咖啡店吃饭"
    result = await service._extract_entities_adaptive(content)
    
    print(f"\n输入文本: {content}")
    print(f"识别场景: {result['scenario']}")
    print(f"提取实体:")
    for entity in result['entities']:
        print(f"  - {entity['entity']} ({entity['entity_type']}) - 置信度: {entity.get('confidence', 0.8):.2f}")
    
    # 验证
    assert result['scenario'] == 'daily_chat', "应识别为日常对话场景"
    assert len(result['entities']) >= 2, "应提取至少 2 个实体"
    
    print("\n✓ 场景自适应集成测试通过")
    return True


# 测试确认服务集成
async def test_confirmation_integration():
    """测试确认服务集成"""
    print("\n" + "=" * 80)
    print("测试 2: 确认服务集成")
    print("=" * 80)
    
    from src.services.graph_builder_service import GraphBuilderService
    from src.services.confirmation_service import get_confirmation_service
    
    # 创建服务实例
    service = GraphBuilderService()
    service.llm_service = MockLLMService()
    
    # 模拟确认服务
    confirmation_service = get_confirmation_service()
    
    # 测试新实体确认
    entity = {"entity": "老王", "entity_type": "person", "confidence": 0.7}
    confirmation = await confirmation_service.should_confirm(
        entity=entity,
        relations=[],
        existing_entities=[],
        existing_relations=[]
    )
    
    print(f"\n实体: {entity}")
    print(f"确认结果: {'需要确认' if confirmation else '不需要确认'}")
    
    if confirmation:
        print(f"  类型: {confirmation['type']}")
        print(f"  原因: {confirmation['reason']}")
    
    # 验证
    assert confirmation is not None, "新实体应该需要确认"
    assert confirmation['type'] == 'new_entity', "确认类型应为 new_entity"
    
    print("\n✓ 确认服务集成测试通过")
    return True


# 测试软过滤集成
async def test_soft_filter_integration():
    """测试软过滤集成"""
    print("\n" + "=" * 80)
    print("测试 3: 软过滤集成")
    print("=" * 80)
    
    from src.services.soft_filter_service import get_soft_filter_service
    
    # 获取服务实例
    service = get_soft_filter_service()
    
    # 测试数据
    results = [
        {"content": "和家人在星巴克喝咖啡", "similarity": 0.8},
        {"content": "和朋友去瑞幸", "similarity": 0.75}
    ]
    
    print(f"\n原始结果:")
    for r in results:
        print(f"  - {r['content']} (相似度: {r['similarity']:.2f})")
    
    # 应用软过滤
    filtered = await service.apply_soft_filter(
        results,
        location_filter="星巴克",
        person_filter="家人"
    )
    
    print(f"\n软过滤后:")
    for r in filtered:
        match_info = []
        if 'location_match' in r:
            match_info.append(f"地点: {r['location_match']}")
        if 'person_match' in r:
            match_info.append(f"人物: {r['person_match']}")
        match_str = f" [匹配: {', '.join(match_info)}]" if match_info else ""
        print(f"  - {r['content']} (相似度: {r['similarity']:.2f}){match_str}")
    
    # 验证
    assert len(filtered) == 2, "不应该排除任何结果"
    assert filtered[0]['similarity'] > 0.8, "匹配结果权重应该提升"
    
    print("\n✓ 软过滤集成测试通过")
    return True


# 测试完整流程
async def test_full_integration():
    """测试完整集成流程"""
    print("\n" + "=" * 80)
    print("测试 4: 完整集成流程")
    print("=" * 80)
    
    from src.services.graph_builder_service import GraphBuilderService
    
    # 创建服务实例
    service = GraphBuilderService()
    service.llm_service = MockLLMService()
    
    print("\n流程步骤:")
    print("  1. 场景自适应提取")
    
    # 测试场景自适应提取
    content = "和老王在咖啡店吃饭"
    result = await service._extract_entities_adaptive(content)
    
    print(f"     输入: {content}")
    print(f"     场景: {result['scenario']}")
    print(f"     实体数: {len(result['entities'])}")
    
    print("\n  2. 智能确认判断")
    
    # 测试确认判断
    confirmation_service = service.confirmation_service
    entity = result['entities'][0] if result['entities'] else {}
    
    if entity:
        confirmation = await confirmation_service.should_confirm(
            entity=entity,
            relations=[],
            existing_entities=[],
            existing_relations=[]
        )
        
        if confirmation:
            print(f"     需要确认: {confirmation['type']}")
            print(f"     原因: {confirmation['reason']}")
        else:
            print(f"     不需要确认")
    
    print("\n  3. 验证结果")
    
    # 验证
    assert result['scenario'] in ['daily_chat', 'work_meeting', 'diary', 'technical'], "场景类型应有效"
    assert len(result['entities']) > 0, "应提取至少一个实体"
    
    print("     ✓ 场景识别正确")
    print("     ✓ 实体提取成功")
    print("     ✓ 流程完整")
    
    print("\n✓ 完整集成流程测试通过")
    return True


# 主测试函数
async def main():
    """运行所有集成测试"""
    print("\n" + "=" * 80)
    print("Phase 3 - 任务 3: 集成测试")
    print("=" * 80)
    
    tests = [
        ("场景自适应集成", test_scenario_adaptive_integration),
        ("确认服务集成", test_confirmation_integration),
        ("软过滤集成", test_soft_filter_integration),
        ("完整集成流程", test_full_integration)
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
            import traceback
            traceback.print_exc()
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
        print("\n✓✓✓ 所有测试通过！Phase 3 集成已完成。")
        return True
    else:
        print("\n✗ 部分测试失败")
        return False


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
