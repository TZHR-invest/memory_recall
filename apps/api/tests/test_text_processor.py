#!/usr/bin/env python3
"""
文本处理器测试脚本
"""
import sys
import os
import asyncio
from pathlib import Path

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 加载 .env 文件
from dotenv import load_dotenv
env_path = Path(__file__).parent.parent / ".env"
load_dotenv(env_path)

from src.processors.text_processor import get_text_processor


async def test_text_processor():
    """测试文本处理器"""
    print("=" * 60)
    print("🧪 文本处理器测试")
    print("=" * 60)
    
    try:
        # 初始化处理器
        processor = get_text_processor()
        print("✅ 文本处理器初始化成功")
        
        # 测试 1: 简单文本
        print("\n" + "=" * 60)
        print("📝 测试 1: 简单文本")
        print("=" * 60)
        
        test_text_1 = "今天在咖啡店遇到老同学，聊了很久，心情很不错"
        print(f"\n输入文本: {test_text_1}")
        
        result_1 = await processor.process(test_text_1, auto_confirm=True)
        
        if result_1["success"]:
            print("\n✅ 处理成功")
            memory_data = result_1["memory_data"]
            print(f"\n提取结果:")
            print(f"  - 内容: {memory_data.content}")
            if memory_data.time:
                print(f"  - 时间: {memory_data.time.value} (置信度: {memory_data.time.confidence})")
            if memory_data.location:
                print(f"  - 地点: {memory_data.location.name}")
            if memory_data.people:
                print(f"  - 人物: {[p.name for p in memory_data.people]}")
            if memory_data.emotion:
                print(f"  - 情绪: {memory_data.emotion.type} (强度: {memory_data.emotion.intensity})")
            if memory_data.tags:
                print(f"  - 标签: {memory_data.tags}")
            if memory_data.embedding:
                print(f"  - 向量维度: {len(memory_data.embedding)}")
        else:
            print(f"❌ 处理失败: {result_1.get('error')}")
            return False
        
        # 测试 2: 复杂文本（需要确认）
        print("\n" + "=" * 60)
        print("📝 测试 2: 复杂文本（需要确认）")
        print("=" * 60)
        
        test_text_2 = "昨天下午三点在公司的会议室开会，讨论了新项目的计划，参与者有张三和李四，会议持续了两个小时"
        print(f"\n输入文本: {test_text_2}")
        
        result_2 = await processor.process(test_text_2, auto_confirm=False)
        
        if result_2["success"]:
            print("\n✅ 处理成功")
            memory_data = result_2["memory_data"]
            print(f"\n提取结果:")
            print(f"  - 内容: {memory_data.content}")
            if memory_data.time:
                print(f"  - 时间: {memory_data.time.value} (置信度: {memory_data.time.confidence})")
            if memory_data.location:
                print(f"  - 地点: {memory_data.location.name}")
            if memory_data.people:
                print(f"  - 人物: {[p.name for p in memory_data.people]}")
            if memory_data.duration:
                print(f"  - 时长: {memory_data.duration.value} {memory_data.duration.unit}")
            if memory_data.topic:
                print(f"  - 主题: {memory_data.topic.main}")
                print(f"  - 关键词: {memory_data.topic.keywords}")
            if memory_data.tags:
                print(f"  - 标签: {memory_data.tags}")
            
            if result_2["need_confirm"]:
                print(f"\n⚠️  需要确认:")
                for question in result_2["questions"]:
                    print(f"  - {question['question']}")
            else:
                print("\n✅ 无需确认")
        else:
            print(f"❌ 处理失败: {result_2.get('error')}")
            return False
        
        # 测试 3: 简短文本
        print("\n" + "=" * 60)
        print("📝 测试 3: 简短文本")
        print("=" * 60)
        
        test_text_3 = "今天很开心"
        print(f"\n输入文本: {test_text_3}")
        
        result_3 = await processor.process(test_text_3, auto_confirm=True)
        
        if result_3["success"]:
            print("\n✅ 处理成功")
            memory_data = result_3["memory_data"]
            print(f"\n提取结果:")
            print(f"  - 内容: {memory_data.content}")
            if memory_data.emotion:
                print(f"  - 情绪: {memory_data.emotion.type}")
        else:
            print(f"❌ 处理失败: {result_3.get('error')}")
            return False
        
        print("\n" + "=" * 60)
        print("✅ 所有文本处理器测试通过")
        print("=" * 60)
        
        return True
        
    except Exception as e:
        print(f"\n❌ 文本处理器测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = asyncio.run(test_text_processor())
    sys.exit(0 if success else 1)
