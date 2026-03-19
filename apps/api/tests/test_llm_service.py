#!/usr/bin/env python3
"""
LLM 服务测试脚本
测试火山引擎 doubao-seed-2-0-pro-260215 模型
"""
import sys
import os
import json
from pathlib import Path

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 加载 .env 文件
from dotenv import load_dotenv
env_path = Path(__file__).parent.parent / ".env"
load_dotenv(env_path)

from src.llm.client import get_llm_client


def test_llm_client():
    """测试 LLM 客户端"""
    print("=" * 60)
    print("🧪 LLM 服务测试")
    print("=" * 60)
    
    try:
        # 检查环境变量
        api_key = os.getenv("VOLC_API_KEY")
        if not api_key:
            print("\n❌ 错误：未配置 VOLC_API_KEY 环境变量")
            print("\n请在 .env 文件中配置：")
            print("VOLC_API_KEY=your_api_key_here")
            return False
        
        print(f"\n✅ API Key 已配置: {api_key[:10]}...{api_key[-10:]}")
        
        # 初始化客户端
        client = get_llm_client()
        print("✅ LLM 客户端初始化成功")
        print(f"   模型: {client.model}")
        
        # 测试 1: 简单对话
        print("\n" + "=" * 60)
        print("📝 测试 1: 简单对话")
        print("=" * 60)
        
        response = client.chat_with_system(
            system_prompt="你是一个友好的助手。",
            user_message="你好，请自我介绍一下。"
        )
        
        if response:
            print(f"\n✅ 对话测试成功:")
            print(f"   响应: {response[:200]}...")
        else:
            print("❌ 对话测试失败")
            return False
        
        # 测试 2: 信息提取（JSON 格式）
        print("\n" + "=" * 60)
        print("📝 测试 2: 信息提取（JSON 格式）")
        print("=" * 60)
        
        test_text = "今天在咖啡店遇到老同学，聊了很久，心情很不错"
        
        result = client.extract_json(
            prompt=f"""
从以下文本中提取关键信息，并以 JSON 格式返回：

文本：{test_text}

提取字段：
- location: 地点信息
- people: 人物信息
- emotion: 情绪
- time: 时间信息（如果没有明确时间，使用"今天"）

返回格式示例：
{{
    "location": "咖啡店",
    "people": ["老同学"],
    "emotion": "心情不错",
    "time": "今天"
}}
            """
        )
        
        if result:
            print(f"\n✅ 信息提取测试成功:")
            print(f"   提取结果: {json.dumps(result, ensure_ascii=False, indent=2)}")
        else:
            print("❌ 信息提取测试失败")
            return False
        
        # 测试 3: 结构化提取（用于记忆服务）
        print("\n" + "=" * 60)
        print("📝 测试 3: 结构化提取（记忆服务场景）")
        print("=" * 60)
        
        memory_text = "昨天下午三点在公司的会议室开会，讨论了新项目的计划，参与者有张三和李四，会议持续了两个小时"
        
        memory_result = client.extract_json(
            prompt=f"""
从以下文本中提取记忆的关键信息，并以 JSON 格式返回：

文本：{memory_text}

提取字段：
- time: 时间信息对象，包含：
  - value: ISO 8601 格式的时间（如果无法确定具体时间，使用相对时间）
  - source: 时间来源（"explicit" 或 "inferred"）
  - confidence: 置信度（0-1）
  - original_text: 原文中的时间文本
- location: 地点信息对象，包含：
  - name: 地点名称
  - need_confirm: 是否需要确认（布尔值）
  - original_text: 原文中的地点文本
- people: 人物列表，每个人物包含：
  - name: 姓名
  - role: 角色（可选）
- topic: 主题信息对象，包含：
  - main: 主要话题
  - keywords: 关键词列表
- emotion: 情绪信息对象，包含：
  - type: 情绪类型
  - intensity: 强度（1-10）
- duration: 持续时间对象，包含：
  - value: 时长（分钟）
  - unit: 单位

返回格式示例：
{{
    "time": {{
        "value": "昨天下午3点",
        "source": "explicit",
        "confidence": 0.9,
        "original_text": "昨天下午三点"
    }},
    "location": {{
        "name": "公司的会议室",
        "need_confirm": false,
        "original_text": "公司的会议室"
    }},
    "people": [
        {{"name": "张三"}},
        {{"name": "李四"}}
    ],
    "topic": {{
        "main": "新项目的计划",
        "keywords": ["会议", "项目", "计划"]
    }},
    "emotion": {{
        "type": "中性",
        "intensity": 5
    }},
    "duration": {{
        "value": 120,
        "unit": "分钟"
    }}
}}
            """
        )
        
        if memory_result:
            print(f"\n✅ 结构化提取测试成功:")
            print(f"   提取结果: {json.dumps(memory_result, ensure_ascii=False, indent=2)}")
        else:
            print("❌ 结构化提取测试失败")
            return False
        
        print("\n" + "=" * 60)
        print("✅ 所有 LLM 测试通过")
        print("=" * 60)
        
        return True
        
    except Exception as e:
        print(f"\n❌ LLM 服务测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = test_llm_client()
    sys.exit(0 if success else 1)
