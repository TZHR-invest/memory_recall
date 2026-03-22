"""
简单测试：验证 Function Calling 工具定义
"""
import sys
import os

# 添加项目路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

# 测试工具定义
try:
    from tools.extract_memories_tool import (
        EXTRACT_MEMORIES_TOOL,
        get_extract_memories_system_prompt
    )
    
    print("✅ 成功导入工具定义")
    print("\n📋 工具名称:", EXTRACT_MEMORIES_TOOL["function"]["name"])
    print("\n📋 工具描述（前 200 字符）:", EXTRACT_MEMORIES_TOOL["function"]["description"][:200])
    print("\n📋 参数字段:", list(EXTRACT_MEMORIES_TOOL["function"]["parameters"]["properties"].keys()))
    
    # 测试系统 Prompt
    system_prompt = get_extract_memories_system_prompt()
    print("\n✅ 成功生成系统 Prompt")
    print("\n📋 系统 Prompt（前 200 字符）:", system_prompt[:200])
    
    print("\n✅ 所有测试通过")
    
except Exception as e:
    print(f"❌ 测试失败: {e}")
    import traceback
    traceback.print_exc()
