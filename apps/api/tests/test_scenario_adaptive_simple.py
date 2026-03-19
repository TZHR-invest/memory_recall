"""
简单测试：验证场景自适应工具定义和 Prompt

测试目标：
1. 工具定义正确
2. Prompt 格式正确
3. 场景类型定义完整
"""

import sys
import os

# 添加 apps/api 到 Python 路径
api_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, api_path)

from src.services.graph_tools import (
    EXTRACT_ENTITIES_WITH_SCENARIO_TOOL,
    SCENARIO_TYPES,
    ENTITY_TYPES,
    validate_tool_definition
)
from src.services.prompts import get_scenario_aware_extraction_prompt


def test_tool_definition():
    """测试工具定义"""
    print("=" * 80)
    print("测试 1: 工具定义验证")
    print("=" * 80)
    
    # 验证工具定义格式
    is_valid = validate_tool_definition(EXTRACT_ENTITIES_WITH_SCENARIO_TOOL)
    
    print(f"\n工具名称: {EXTRACT_ENTITIES_WITH_SCENARIO_TOOL['function']['name']}")
    print(f"工具描述: {EXTRACT_ENTITIES_WITH_SCENARIO_TOOL['function']['description']}")
    print(f"\n工具定义格式: {'✓ 有效' if is_valid else '✗ 无效'}")
    
    # 检查必需参数
    params = EXTRACT_ENTITIES_WITH_SCENARIO_TOOL['function']['parameters']
    properties = params.get('properties', {})
    
    print(f"\n参数列表:")
    for param_name, param_def in properties.items():
        print(f"  - {param_name}: {param_def.get('type', 'unknown')}")
        if 'enum' in param_def:
            print(f"    可选值: {param_def['enum']}")
    
    required = params.get('required', [])
    print(f"\n必需参数: {required}")
    
    # 验证
    assert is_valid, "工具定义格式无效"
    assert 'scenario' in properties, "缺少 scenario 参数"
    assert 'entities' in properties, "缺少 entities 参数"
    assert 'scenario' in required, "scenario 应为必需参数"
    assert 'entities' in required, "entities 应为必需参数"
    
    # 验证场景类型
    scenario_enum = properties['scenario'].get('enum', [])
    expected_scenarios = ['daily_chat', 'work_meeting', 'diary', 'technical']
    assert set(scenario_enum) == set(expected_scenarios), f"场景类型不匹配: {scenario_enum}"
    
    print("\n✓ 工具定义验证通过")
    return True


def test_scenario_types():
    """测试场景类型定义"""
    print("\n" + "=" * 80)
    print("测试 2: 场景类型定义")
    print("=" * 80)
    
    print(f"\n场景类型:")
    for scenario, desc in SCENARIO_TYPES.items():
        print(f"  - {scenario}: {desc}")
    
    # 验证场景类型
    expected_scenarios = ['daily_chat', 'work_meeting', 'diary', 'technical']
    assert set(SCENARIO_TYPES.keys()) == set(expected_scenarios), "场景类型定义不完整"
    
    print("\n✓ 场景类型定义完整")
    return True


def test_entity_types():
    """测试实体类型定义"""
    print("\n" + "=" * 80)
    print("测试 3: 实体类型定义")
    print("=" * 80)
    
    print(f"\n实体类型:")
    for entity_type, desc in ENTITY_TYPES.items():
        print(f"  - {entity_type}: {desc}")
    
    # 验证新增的实体类型
    new_types = ['time', 'task', 'decision', 'concept', 'solution', 'problem']
    for entity_type in new_types:
        assert entity_type in ENTITY_TYPES, f"缺少实体类型: {entity_type}"
    
    print("\n✓ 实体类型定义完整（包含 Phase 3 新增类型）")
    return True


def test_prompt():
    """测试 Prompt"""
    print("\n" + "=" * 80)
    print("测试 4: 场景自适应提取 Prompt")
    print("=" * 80)
    
    prompt = get_scenario_aware_extraction_prompt()
    
    # 检查 Prompt 内容
    assert "场景类型说明" in prompt, "Prompt 缺少场景类型说明"
    assert "daily_chat" in prompt, "Prompt 缺少 daily_chat 说明"
    assert "work_meeting" in prompt, "Prompt 缺少 work_meeting 说明"
    assert "diary" in prompt, "Prompt 缺少 diary 说明"
    assert "technical" in prompt, "Prompt 缺少 technical 说明"
    
    # 检查示例
    assert "示例 1：日常对话" in prompt, "Prompt 缺少示例 1"
    assert "示例 2：工作会议" in prompt, "Prompt 缺少示例 2"
    assert "示例 3：日记" in prompt, "Prompt 缺少示例 3"
    assert "示例 4：技术讨论" in prompt, "Prompt 缺少示例 4"
    
    # 检查实体类型说明
    assert "person" in prompt, "Prompt 缺少 person 说明"
    assert "location" in prompt, "Prompt 缺少 location 说明"
    assert "time" in prompt, "Prompt 缺少 time 说明"
    assert "task" in prompt, "Prompt 缺少 task 说明"
    
    print(f"\nPrompt 长度: {len(prompt)} 字符")
    print("\nPrompt 包含:")
    print("  ✓ 场景类型说明")
    print("  ✓ 实体类型说明")
    print("  ✓ 提取规则")
    print("  ✓ 4 个示例")
    
    # 显示 Prompt 的前 500 字符
    print(f"\nPrompt 预览:")
    print("-" * 80)
    print(prompt[:500] + "...")
    print("-" * 80)
    
    print("\n✓ Prompt 验证通过")
    return True


def main():
    """运行所有测试"""
    print("\n" + "=" * 80)
    print("Phase 3 - 任务 0: 场景自适应记忆提取")
    print("=" * 80)
    
    tests = [
        ("工具定义验证", test_tool_definition),
        ("场景类型定义", test_scenario_types),
        ("实体类型定义", test_entity_types),
        ("Prompt 验证", test_prompt)
    ]
    
    passed = 0
    failed = 0
    
    for test_name, test_func in tests:
        try:
            test_func()
            passed += 1
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
        print("\n✓✓✓ 所有测试通过！场景自适应提取功能已准备就绪。")
        return True
    else:
        print("\n✗ 部分测试失败")
        return False


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
