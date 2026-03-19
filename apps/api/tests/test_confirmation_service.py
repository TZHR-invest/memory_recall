"""
测试智能确认服务（Phase 3 - 任务 1）

测试目标：
1. 可以正确判断是否需要确认
2. 可以正确识别新实体
3. 可以正确识别低置信度
4. 可以正确识别关系冲突
"""

import asyncio
import sys
import os

# 添加 apps/api 到 Python 路径
api_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, api_path)

from src.services.confirmation_service import get_confirmation_service


async def test_new_entity_confirmation():
    """测试新实体确认"""
    print("=" * 80)
    print("测试 1: 新实体确认")
    print("=" * 80)
    
    service = get_confirmation_service()
    
    # 测试用例：新实体，置信度 0.7
    entity = {"entity": "老王", "entity_type": "person", "confidence": 0.7}
    confirmation = await service.should_confirm(
        entity=entity,
        relations=[],
        existing_entities=[],
        existing_relations=[]
    )
    
    print(f"\n实体: {entity}")
    print(f"已存在实体: []")
    print(f"\n确认结果:")
    
    if confirmation:
        print(f"  ✓ 需要确认")
        print(f"  类型: {confirmation['type']}")
        print(f"  原因: {confirmation['reason']}")
        print(f"  建议: {confirmation['suggestion']}")
        
        # 验证
        assert confirmation["type"] == "new_entity", "确认类型应为 new_entity"
        assert confirmation["entity"]["entity"] == "老王", "实体名称应为老王"
        
        print("\n✓ 新实体确认测试通过")
        return True
    else:
        print("  ✗ 应该需要确认但未触发")
        return False


async def test_low_confidence_confirmation():
    """测试低置信度确认"""
    print("\n" + "=" * 80)
    print("测试 2: 低置信度确认")
    print("=" * 80)
    
    service = get_confirmation_service()
    
    # 测试用例：已存在实体，但置信度过低（0.5）
    entity = {"entity": "张三", "entity_type": "person", "confidence": 0.5}
    confirmation = await service.should_confirm(
        entity=entity,
        relations=[],
        existing_entities=[{"name": "张三", "type": "person"}],
        existing_relations=[]
    )
    
    print(f"\n实体: {entity}")
    print(f"已存在实体: [{{'name': '张三', 'type': 'person'}}]")
    print(f"\n确认结果:")
    
    if confirmation:
        print(f"  ✓ 需要确认")
        print(f"  类型: {confirmation['type']}")
        print(f"  原因: {confirmation['reason']}")
        
        # 验证
        assert confirmation["type"] == "low_confidence", "确认类型应为 low_confidence"
        assert confirmation["confidence"] == 0.5, "置信度应为 0.5"
        
        print("\n✓ 低置信度确认测试通过")
        return True
    else:
        print("  ✗ 应该需要确认但未触发")
        return False


async def test_relation_conflict():
    """测试关系冲突"""
    print("\n" + "=" * 80)
    print("测试 3: 关系冲突确认")
    print("=" * 80)
    
    service = get_confirmation_service()
    
    # 测试用例：关系冲突（friend vs colleague）
    entity = {"entity": "李四", "entity_type": "person", "confidence": 0.9}
    new_relations = [
        {"source": "李四", "destination": "王五", "relationship": "friend"}
    ]
    existing_relations = [
        {"source": "李四", "destination": "王五", "relationship": "colleague"}
    ]
    
    confirmation = await service.should_confirm(
        entity=entity,
        relations=new_relations,
        existing_entities=[{"name": "李四", "type": "person"}],
        existing_relations=existing_relations
    )
    
    print(f"\n实体: {entity}")
    print(f"新关系: {new_relations}")
    print(f"已存在关系: {existing_relations}")
    print(f"\n确认结果:")
    
    if confirmation:
        print(f"  ✓ 需要确认")
        print(f"  类型: {confirmation['type']}")
        print(f"  原因: {confirmation['reason']}")
        
        if confirmation['type'] == 'relation_conflict':
            conflict = confirmation.get('conflict', {})
            print(f"  冲突详情: {conflict.get('message', 'N/A')}")
        
        # 验证
        assert confirmation["type"] == "relation_conflict", "确认类型应为 relation_conflict"
        
        print("\n✓ 关系冲突确认测试通过")
        return True
    else:
        print("  ✗ 应该需要确认但未触发")
        return False


async def test_no_confirmation_needed():
    """测试不需要确认的情况"""
    print("\n" + "=" * 80)
    print("测试 4: 不需要确认")
    print("=" * 80)
    
    service = get_confirmation_service()
    
    # 测试用例：已存在实体，置信度足够高
    entity = {"entity": "张三", "entity_type": "person", "confidence": 0.9}
    confirmation = await service.should_confirm(
        entity=entity,
        relations=[],
        existing_entities=[{"name": "张三", "type": "person"}],
        existing_relations=[]
    )
    
    print(f"\n实体: {entity}")
    print(f"已存在实体: [{{'name': '张三', 'type': 'person'}}]")
    print(f"\n确认结果:")
    
    if confirmation is None:
        print(f"  ✓ 不需要确认")
        print(f"  原因: 实体已存在且置信度足够高")
        
        print("\n✓ 不需要确认测试通过")
        return True
    else:
        print(f"  ✗ 不应该需要确认但触发了")
        return False


async def test_confirmation_flow():
    """测试完整的确认流程"""
    print("\n" + "=" * 80)
    print("测试 5: 完整确认流程")
    print("=" * 80)
    
    service = get_confirmation_service()
    
    # 1. 判断是否需要确认
    entity = {"entity": "赵六", "entity_type": "person", "confidence": 0.65}
    confirmation = await service.should_confirm(
        entity=entity,
        relations=[],
        existing_entities=[],
        existing_relations=[]
    )
    
    print(f"\n步骤 1: 判断是否需要确认")
    print(f"  实体: {entity}")
    print(f"  结果: {'需要确认' if confirmation else '不需要确认'}")
    
    if not confirmation:
        print("  ✗ 测试失败：应该需要确认")
        return False
    
    # 2. 发送确认请求
    print(f"\n步骤 2: 发送确认请求")
    confirmation_id = await service.send_confirmation("test_user", confirmation)
    print(f"  确认ID: {confirmation_id}")
    
    # 3. 查看待确认列表
    print(f"\n步骤 3: 查看待确认列表")
    pending = service.get_pending_confirmations("test_user")
    print(f"  待确认数量: {len(pending)}")
    
    if len(pending) == 0:
        print("  ✗ 测试失败：应该有待确认项")
        return False
    
    # 4. 处理用户回复
    print(f"\n步骤 4: 处理用户回复（确认）")
    result = await service.handle_response(confirmation_id, "confirm")
    print(f"  结果: {result['status']}")
    print(f"  消息: {result['message']}")
    
    # 验证
    assert result["status"] == "confirmed", "状态应为 confirmed"
    
    print("\n✓ 完整确认流程测试通过")
    return True


async def main():
    """运行所有测试"""
    print("\n" + "=" * 80)
    print("Phase 3 - 任务 1: 智能确认服务")
    print("=" * 80)
    
    tests = [
        ("新实体确认", test_new_entity_confirmation),
        ("低置信度确认", test_low_confidence_confirmation),
        ("关系冲突确认", test_relation_conflict),
        ("不需要确认", test_no_confirmation_needed),
        ("完整确认流程", test_confirmation_flow)
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
        print("\n✓✓✓ 所有测试通过！智能确认服务已准备就绪。")
        return True
    else:
        print("\n✗ 部分测试失败")
        return False


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
