#!/usr/bin/env python3
"""
LLM 服务测试脚本
需要配置 VOLC_API_KEY 环境变量
"""
import sys
import os

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.llm.client import get_llm_client
from src.llm.extractor import get_extractor


def test_llm_client():
    """测试 LLM 客户端"""
    print("测试 LLM 客户端...")
    
    try:
        client = get_llm_client()
        print("✅ LLM 客户端初始化成功")
        
        # 测试简单的聊天
        response = client.chat_with_system(
            "你是一个友好的助手",
            "你好，请介绍一下自己"
        )
        print(f"\n✅ 聊天测试成功:\n{response[:200]}...")
        
        return True
    except Exception as e:
        print(f"❌ LLM 客户端测试失败: {e}")
        return False


def test_extractor():
    """测试结构化提取"""
    print("\n测试结构化提取...")
    
    try:
        extractor = get_extractor()
        print("✅ 提取器初始化成功")
        
        # 测试记忆提取
        test_text = "今天下午在咖啡店遇到老同学张三，聊了很久关于创业的想法"
        result = extractor.extract_memory(test_text)
        
        if result:
            print(f"\n✅ 记忆提取测试成功:")
            import json
            print(json.dumps(result, ensure_ascii=False, indent=2)[:500])
        else:
            print("❌ 记忆提取失败：无法解析结果")
        
        return result is not None
    except Exception as e:
        print(f"❌ 提取器测试失败: {e}")
        return False


if __name__ == "__main__":
    # 检查 API Key
    if not os.getenv("VOLC_API_KEY"):
        print("❌ 错误：未配置 VOLC_API_KEY 环境变量")
        print("\n请在 .env 文件中配置：")
        print("VOLC_API_KEY=your_api_key_here")
        sys.exit(1)
    
    # 运行测试
    test1 = test_llm_client()
    test2 = test_extractor()
    
    if test1 and test2:
        print("\n✅ 所有测试通过")
    else:
        print("\n❌ 部分测试失败")
        sys.exit(1)
