"""
测试 Function Calling 功能

验证：
1. 可以成功调用 Function Calling
2. 可以解析工具调用结果
3. 错误处理完善
"""
import asyncio
import sys
import os

# 添加项目路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "apps/api/src"))

# 使用绝对导入
from llm.client import get_llm_client
from services.graph_tools import EXTRACT_ENTITIES_TOOL, ESTABLISH_RELATIONS_TOOL


class TestLLMService:
    """测试用的 LLM 服务"""
    
    def __init__(self):
        self.llm_client = get_llm_client()
    
    async def call_with_tools(
        self,
        system_prompt: str,
        user_prompt: str,
        tools,
        temperature: float = 0.3,
        max_tokens: int = 2000
    ):
        """测试 Function Calling"""
        import json
        
        try:
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ]
            
            response = self.llm_client.client.chat.completions.create(
                model=self.llm_client.model,
                messages=messages,
                tools=tools,
                tool_choice="auto",
                temperature=temperature,
                max_tokens=max_tokens
            )
            
            message = response.choices[0].message
            
            result = {
                "content": message.content,
                "tool_calls": []
            }
            
            if message.tool_calls:
                for tool_call in message.tool_calls:
                    try:
                        arguments = json.loads(tool_call.function.arguments)
                    except json.JSONDecodeError as e:
                        print(f"解析工具参数失败: {e}")
                        arguments = {}
                    
                    result["tool_calls"].append({
                        "id": tool_call.id,
                        "type": tool_call.type,
                        "function": {
                            "name": tool_call.function.name,
                            "arguments": arguments
                        }
                    })
            
            return result
            
        except Exception as e:
            print(f"Function Calling 调用失败: {e}")
            return {
                "content": None,
                "tool_calls": [],
                "error": str(e)
            }


async def test_function_calling():
    """测试 Function Calling"""
    print("=" * 60)
    print("测试 Function Calling 功能")
    print("=" * 60)
    
    # 获取服务实例
    llm_service = TestLLMService()
    
    # 测试 1：实体提取
    print("\n### 测试 1：实体提取")
    print("-" * 60)
    
    test_cases = [
        "今天和张三在咖啡店聊天",
        "明天要和李四去北京出差",
        "周末和老王爬山，心情很愉快"
    ]
    
    for i, test_text in enumerate(test_cases, 1):
        print(f"\n测试用例 {i}: {test_text}")
        
        try:
            response = await llm_service.call_with_tools(
                system_prompt="你是一个实体提取专家。",
                user_prompt=f"请从以下文本中提取实体：\n\n{test_text}",
                tools=[EXTRACT_ENTITIES_TOOL]
            )
            
            print(f"响应类型: {'tool_calls' if response.get('tool_calls') else 'content'}")
            
            if response.get("tool_calls"):
                print("✓ 成功获取工具调用")
                for tool_call in response["tool_calls"]:
                    print(f"  工具名称: {tool_call['function']['name']}")
                    print(f"  参数: {tool_call['function']['arguments']}")
            else:
                print("✗ 没有工具调用")
                if response.get("content"):
                    print(f"  文本响应: {response['content'][:100]}...")
        
        except Exception as e:
            print(f"✗ 测试失败: {e}")
    
    # 测试 2：关系推理
    print("\n### 测试 2：关系推理")
    print("-" * 60)
    
    relation_test_cases = [
        {
            "text": "今天和张三在咖啡店聊天",
            "entities": ["张三", "咖啡店", "聊天"]
        },
        {
            "text": "我和老王是多年的朋友",
            "entities": ["我", "老王"]
        }
    ]
    
    for i, test_case in enumerate(relation_test_cases, 1):
        print(f"\n测试用例 {i}: {test_case['text']}")
        print(f"实体列表: {test_case['entities']}")
        
        try:
            response = await llm_service.call_with_tools(
                system_prompt="你是一个关系推理专家。",
                user_prompt=f"实体列表：{', '.join(test_case['entities'])}\n\n文本：{test_case['text']}",
                tools=[ESTABLISH_RELATIONS_TOOL]
            )
            
            print(f"响应类型: {'tool_calls' if response.get('tool_calls') else 'content'}")
            
            if response.get("tool_calls"):
                print("✓ 成功获取工具调用")
                for tool_call in response["tool_calls"]:
                    print(f"  工具名称: {tool_call['function']['name']}")
                    print(f"  参数: {tool_call['function']['arguments']}")
            else:
                print("✗ 没有工具调用")
                if response.get("content"):
                    print(f"  文本响应: {response['content'][:100]}...")
        
        except Exception as e:
            print(f"✗ 测试失败: {e}")
    
    # 测试 3：错误处理
    print("\n### 测试 3：错误处理")
    print("-" * 60)
    
    # 测试无效的工具定义
    print("\n测试无效工具定义...")
    try:
        invalid_tool = {
            "type": "function",
            "function": {
                "name": "invalid_tool",
                "description": "无效工具"
                # 缺少 parameters
            }
        }
        
        response = await llm_service.call_with_tools(
            system_prompt="测试",
            user_prompt="测试",
            tools=[invalid_tool]
        )
        
        if response.get("error"):
            print(f"✓ 正确处理错误: {response['error']}")
        else:
            print("⚠ 期望错误但没有返回错误")
    
    except Exception as e:
        print(f"✗ 未处理的异常: {e}")
    
    print("\n" + "=" * 60)
    print("测试完成")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(test_function_calling())
