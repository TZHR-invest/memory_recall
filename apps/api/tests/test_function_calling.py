"""
测试 Function Calling 调用
"""
import sys
import os
import asyncio

# 添加项目路径（确保能正确导入模块）
current_dir = os.path.dirname(os.path.abspath(__file__))
src_dir = os.path.join(current_dir, '..', 'src')
sys.path.insert(0, os.path.abspath(src_dir))

# 设置环境变量
os.environ.setdefault('DATABASE_URL', 'postgresql://postgres:postgres@localhost:5432/memory_recall')
os.environ.setdefault('VOLC_API_KEY', 'your-volc-api-key')
os.environ.setdefault('VOLC_API_BASE', 'https://ark.cn-beijing.volces.com/api/v3')
os.environ.setdefault('VOLC_LLM_MODEL', 'doubao-seed-2-0-mini-260215')

async def test_function_calling():
    """测试 Function Calling 调用"""
    try:
        # 导入 LLM 客户端
        from llm.client import get_llm_client
        from tools.extract_memories_tool import (
            EXTRACT_MEMORIES_TOOL,
            get_extract_memories_system_prompt
        )
        
        print("✅ 成功导入依赖")
        
        # 获取 LLM 客户端
        llm_client = get_llm_client()
        print("✅ 成功初始化 LLM 客户端")
        
        # 准备测试数据
        test_content = "今天下午在星巴克和张三讨论了新项目，感觉很有启发。"
        system_prompt = get_extract_memories_system_prompt()
        
        print(f"\n📝 测试内容: {test_content}")
        print(f"\n⚡ 开始调用 Function Calling...")
        
        # 构建 messages
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"请从以下文本中提取记忆：\n\n{test_content}"}
        ]
        
        # 调用 Function Calling
        response = llm_client.call_with_tools(
            messages=messages,
            tools=[EXTRACT_MEMORIES_TOOL],
            temperature=0.3,
            max_tokens=2000
        )
        
        print("\n✅ Function Calling 调用成功")
        
        # 解析结果
        if response.get("tool_calls"):
            print("\n📋 工具调用结果:")
            for tool_call in response["tool_calls"]:
                print(f"  工具名称: {tool_call['name']}")
                arguments = tool_call['arguments']
                memories = arguments.get('memories', [])
                
                print(f"\n  提取的记忆数量: {len(memories)}")
                
                for i, memory in enumerate(memories):
                    print(f"\n  记忆 {i+1}:")
                    print(f"    内容: {memory.get('content')}")
                    print(f"    时间: {memory.get('time')}")
                    print(f"    地点: {memory.get('location')}")
                    print(f"    人物: {memory.get('people')}")
                    print(f"    实体: {memory.get('entities')}")
                    print(f"    关系: {memory.get('relations')}")
                    print(f"    标签: {memory.get('tags')}")
                    print(f"    重要性: {memory.get('importance')}")
        else:
            print("\n⚠️ 没有工具调用，返回文本响应")
            print(f"  内容: {response.get('content')}")
        
        print("\n✅ 测试完成")
        
    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(test_function_calling())
