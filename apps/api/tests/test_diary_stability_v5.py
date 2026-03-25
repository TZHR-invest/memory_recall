"""
测试日记提取稳定性 - 运行3次并保存结果用于分析
"""

import sys
import os
import json
import asyncio
from datetime import datetime

# 添加项目路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from services.memory_extraction_service import get_memory_extraction_service


async def test_diary_extraction():
    """测试日记提取稳定性"""

    # 读取日记内容
    diary_path = os.path.join(os.path.dirname(__file__), "..", "..", "..", "日记.txt")
    with open(diary_path, "r", encoding="utf-8") as f:
        diary_content = f.read()

    print(f"📖 日记内容长度: {len(diary_content)} 字符")
    print(f"📖 日记内容预览:\n{diary_content[:200]}...\n")

    # 获取提取服务
    service = get_memory_extraction_service()

    # 存储结果
    results = []

    # 运行3次提取
    for i in range(1, 4):
        print(f"\n{'=' * 60}")
        print(f"🔄 第 {i} 次提取...")
        print(f"{'=' * 60}")

        start_time = datetime.now()
        result = await service.extract_memories(diary_content)
        end_time = datetime.now()

        duration = (end_time - start_time).total_seconds()

        if result["success"]:
            memories = result["memories"]
            print(f"✅ 提取成功 - 用时 {duration:.2f}s")
            print(f"📊 提取记忆数量: {len(memories)}")

            # 统计实体
            all_entities = []
            for m in memories:
                all_entities.extend(m.get("entities", []))

            entity_types = {}
            for e in all_entities:
                t = e.get("type", "unknown")
                entity_types[t] = entity_types.get(t, 0) + 1

            print(f"📊 实体统计: {entity_types}")

            # 显示记忆内容
            print(f"\n📝 记忆内容:")
            for j, m in enumerate(memories, 1):
                content = m.get("content", "")
                time_info = m.get("time", {})
                entities = m.get("entities", [])

                print(
                    f"  [{j}] {content[:50]}..."
                    if len(content) > 50
                    else f"  [{j}] {content}"
                )
                if time_info.get("value"):
                    print(
                        f"      时间: {time_info.get('value')} ({time_info.get('period', 'N/A')})"
                    )
                if entities:
                    entity_names = [e.get("name", "") for e in entities]
                    print(
                        f"      实体: {', '.join(entity_names[:5])}{'...' if len(entity_names) > 5 else ''}"
                    )

            results.append(
                {
                    "run": i,
                    "success": True,
                    "duration": duration,
                    "memory_count": len(memories),
                    "entity_count": len(all_entities),
                    "entity_types": entity_types,
                    "memories": memories,
                }
            )
        else:
            print(f"❌ 提取失败: {result.get('error')}")
            results.append(
                {
                    "run": i,
                    "success": False,
                    "error": result.get("error"),
                    "duration": duration,
                }
            )

    # 保存结果
    output_dir = os.path.join(os.path.dirname(__file__), "extraction_results")
    os.makedirs(output_dir, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_file = os.path.join(output_dir, f"diary_stability_{timestamp}.json")

    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    print(f"\n{'=' * 60}")
    print(f"📁 结果已保存到: {output_file}")
    print(f"{'=' * 60}")

    # 稳定性分析
    print(f"\n📊 稳定性分析:")
    print(f"{'=' * 60}")

    memory_counts = [r["memory_count"] for r in results if r["success"]]
    if memory_counts:
        avg_count = sum(memory_counts) / len(memory_counts)
        min_count = min(memory_counts)
        max_count = max(memory_counts)

        print(f"  记忆数量: {memory_counts}")
        print(f"  平均: {avg_count:.1f}, 最小: {min_count}, 最大: {max_count}")
        print(f"  波动范围: {max_count - min_count}")

        if max_count == min_count:
            print(f"  ✅ 记忆数量完全稳定")
        elif max_count - min_count <= 2:
            print(f"  ⚠️ 记忆数量基本稳定（波动 ≤ 2）")
        else:
            print(f"  ❌ 记忆数量不稳定（波动 > 2）")

    # 实体一致性分析
    print(f"\n📊 实体一致性分析:")
    entity_sets = []
    for r in results:
        if r["success"]:
            entities = set()
            for m in r["memories"]:
                for e in m.get("entities", []):
                    entities.add(f"{e.get('name')}:{e.get('type')}")
            entity_sets.append(entities)

    if len(entity_sets) >= 2:
        common_entities = entity_sets[0].intersection(*entity_sets[1:])
        all_entities_union = entity_sets[0].union(*entity_sets[1:])

        print(f"  共同实体数量: {len(common_entities)}")
        print(f"  总实体数量: {len(all_entities_union)}")
        print(
            f"  一致性比例: {len(common_entities) / len(all_entities_union) * 100:.1f}%"
        )

        if common_entities:
            print(f"\n  共同实体:")
            for e in sorted(common_entities):
                print(f"    - {e}")

        missing_in_each = []
        for i, es in enumerate(entity_sets):
            missing = all_entities_union - es
            if missing:
                missing_in_each.append((i + 1, missing))

        if missing_in_each:
            print(f"\n  各次缺失的实体:")
            for run, missing in missing_in_each:
                print(f"    第{run}次缺失: {sorted(missing)}")

    return results


if __name__ == "__main__":
    asyncio.run(test_diary_extraction())
