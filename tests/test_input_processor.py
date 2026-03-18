"""
测试输入处理服务
"""

import sys
import os

# 添加项目根目录和 src 目录到 Python 路径
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
src_dir = os.path.join(project_root, 'src')
sys.path.insert(0, project_root)
sys.path.insert(0, src_dir)

from datetime import datetime
from src.services.input_processor import InputProcessor
from src.core.extractor import MemoryExtractor
from src.core.indexer import MemoryIndexer


def test_short_text():
    """测试短文本处理"""
    print("\n=== 测试短文本处理 ===")
    
    # 初始化
    extractor = MemoryExtractor()
    indexer = MemoryIndexer(index_dir="./test_index")
    processor = InputProcessor(extractor, indexer)
    
    # 测试用例 1：完整信息
    text1 = "今天下午3点在星巴克遇到了老同学张三，聊得很开心"
    result1 = processor.process_text(text1)
    
    print(f"\n输入：{text1}")
    print(f"状态：{result1['status']}")
    print(f"提取结果：{result1['extracted']}")
    print(f"问题：{result1['questions']}")
    
    assert result1['status'] == 'success'
    assert len(result1['questions']) == 0
    
    # 测试用例 2：信息模糊
    text2 = "昨天遇到一个有趣的人"
    result2 = processor.process_text(text2)
    
    print(f"\n输入：{text2}")
    print(f"状态：{result2['status']}")
    print(f"提取结果：{result2['extracted']}")
    print(f"问题：{result2['questions']}")
    
    # 测试用例 3：心情记录
    text3 = "今天心情不错"
    result3 = processor.process_text(text3)
    
    print(f"\n输入：{text3}")
    print(f"状态：{result3['status']}")
    print(f"提取结果：{result3['extracted']}")
    print(f"问题：{result3['questions']}")
    
    assert result3['status'] == 'success'
    assert len(result3['questions']) == 0
    
    print("\n✅ 短文本处理测试通过")


def test_medium_text():
    """测试中等长度文本处理"""
    print("\n=== 测试中等长度文本处理 ===")
    
    # 初始化
    extractor = MemoryExtractor()
    indexer = MemoryIndexer(index_dir="./test_index")
    processor = InputProcessor(extractor, indexer)
    
    # 测试用例：多个事件
    text = """
    今天上午在办公室开了一个重要的项目会议。老板提出了新的目标，我们需要在下个月完成原型。
    中午和同事去楼下新开的餐厅吃饭，味道不错，推荐了红烧排骨。
    下午一直在写代码，终于解决了困扰我两天的 bug，很有成就感。
    """
    
    result = processor.process_text(text)
    
    print(f"\n输入：{text[:50]}...")
    print(f"状态：{result['status']}")
    print(f"总段数：{result.get('total_segments', 'N/A')}")
    
    if result['status'] == 'success' and 'memories' in result:
        print(f"存储记忆数：{len(result['memories'])}")
        for i, memory in enumerate(result['memories']):
            print(f"\n记忆 {i+1}:")
            print(f"  内容：{memory['content'][:50]}...")
            print(f"  标签：{memory['extracted'].get('tags', [])}")
    
    print("\n✅ 中等长度文本处理测试通过")


def test_long_text():
    """测试长文本处理"""
    print("\n=== 测试长文本处理 ===")
    
    # 初始化
    extractor = MemoryExtractor()
    indexer = MemoryIndexer(index_dir="./test_index")
    processor = InputProcessor(extractor, indexer)
    
    # 测试用例：日记
    text = """
今天是一个非常充实的日子。

上午九点，我准时到达公司。刚坐下，老板就叫我去了会议室。原来是新的项目要启动了，我们需要为下个月的发布会做准备。这个项目对我来说是个挑战，但也是个机会。老板说相信我的能力，让我负责核心模块的设计。

会议结束后，我回到工位，开始梳理需求。代码、文档、测试计划，每一项都需要仔细考虑。中午的时候，同事小李叫我去吃饭。我们去了公司楼下新开的川菜馆，点了麻婆豆腐和回锅肉，味道确实不错。小李说他最近在学习新技术，我们也聊了很多关于职业发展的想法。

下午的时间过得很快。我一直在写代码，中间遇到几个 bug，但最终都解决了。最让我开心的是，核心算法的性能提升了 30%，这超出了我的预期。

下班后，我在公司楼下的咖啡店坐了一会儿。点了杯拿铁，看着窗外的行人，感觉很平静。这一天虽然忙碌，但很有成就感。
"""
    
    result = processor.process_text(text)
    
    print(f"\n输入长度：{len(text)} 字符")
    print(f"状态：{result['status']}")
    print(f"总段数：{result.get('total_segments', 'N/A')}")
    print(f"存储记忆数：{result.get('stored_memories', 'N/A')}")
    
    if result['status'] == 'success' and 'memories' in result:
        print(f"\n存储的记忆片段：")
        for i, memory in enumerate(result['memories'][:3]):  # 只显示前 3 个
            print(f"\n片段 {i+1}:")
            print(f"  内容：{memory['content']}")
            print(f"  时间：{memory['extracted'].get('time', {}).get('value')}")
            print(f"  地点：{memory['extracted'].get('location', {}).get('name')}")
            print(f"  标签：{memory['extracted'].get('tags', [])}")
    
    print("\n✅ 长文本处理测试通过")


def test_batch_process():
    """测试批量处理"""
    print("\n=== 测试批量处理 ===")
    
    # 初始化
    extractor = MemoryExtractor()
    indexer = MemoryIndexer(index_dir="./test_index")
    processor = InputProcessor(extractor, indexer)
    
    # 测试用例
    texts = [
        "今天在咖啡店遇到了老朋友",
        "下午开了一个重要的会议",
        "晚上在家看电影，很放松",
        "昨天加班到很晚，终于完成了项目",
        "周末和朋友去爬山，风景很美"
    ]
    
    result = processor.batch_process(texts)
    
    print(f"\n总输入数：{result['total']}")
    print(f"成功处理：{result['success']}")
    print(f"需要补充信息：{result['need_info']}")
    
    print("\n各条处理结果：")
    for i, r in enumerate(result['results']):
        print(f"\n输入 {i+1}：{texts[i]}")
        print(f"  状态：{r['status']}")
        if r['questions']:
            print(f"  问题：{r['questions']}")
    
    print("\n✅ 批量处理测试通过")


def test_index_stats():
    """测试索引统计"""
    print("\n=== 测试索引统计 ===")
    
    indexer = MemoryIndexer(index_dir="./test_index")
    stats = indexer.get_stats()
    
    print(f"\n索引统计：")
    print(f"  时间索引条目：{stats['time_entries']}")
    print(f"  位置索引条目：{stats['location_entries']}")
    print(f"  人物索引条目：{stats['people_entries']}")
    print(f"  标签索引条目：{stats['tags_entries']}")
    
    print("\n✅ 索引统计测试通过")


if __name__ == "__main__":
    print("=" * 60)
    print("Memory Recall - 输入处理服务测试")
    print("=" * 60)
    
    try:
        test_short_text()
        test_medium_text()
        test_long_text()
        test_batch_process()
        test_index_stats()
        
        print("\n" + "=" * 60)
        print("✅ 所有测试通过")
        print("=" * 60)
        
    except Exception as e:
        print(f"\n❌ 测试失败：{e}")
        import traceback
        traceback.print_exc()
