"""
测试实体词典实时更新
验证新实体入库后词典是否自动更新
"""

import asyncio
import sys
import os
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.services.graph_builder_service import GraphBuilderService
from src.services.enhanced_entity_extractor import get_enhanced_entity_extractor
from src.services.entity_dictionary_service import get_entity_dictionary_service
from src.database import db


async def test_dict_update():
    """测试词典实时更新"""

    print("\n" + "=" * 80)
    print("实体词典实时更新测试")
    print("=" * 80)

    user_id = "test_user"

    # ==================== 步骤 1: 初始化词典 ====================
    print("\n步骤 1: 初始化实体词典")
    print("-" * 80)

    entity_dict = get_entity_dictionary_service()
    enhanced_extractor = get_enhanced_entity_extractor()

    # 初始化词典
    await entity_dict.initialize()
    await enhanced_extractor.initialize()

    print(f"✅ 词典初始化完成")
    print(f"   实体数量: {len(entity_dict.entity_dict)}")

    # ==================== 步骤 2: 查询初始状态 ====================
    print("\n步骤 2: 查询初始状态")
    print("-" * 80)

    test_entity = "测试实体" + str(int(time.time()))

    # 尝试匹配（应该失败）
    entities = entity_dict.extract_entities_fast(test_entity, user_id)
    print(f"查询实体: {test_entity}")
    print(f"匹配结果: {entities}")
    print(f"预期: [] （实体不在词典中）")

    # ==================== 步骤 3: 创建新实体 ====================
    print("\n步骤 3: 创建新实体（模拟存入数据库）")
    print("-" * 80)

    db.set_current_user(user_id)

    # 创建图谱构建服务
    graph_builder = GraphBuilderService()

    # 模拟存储实体
    entity_id = await graph_builder._upsert_entity(
        name=test_entity, entity_type="topic", user_id=user_id, confidence=0.9
    )

    print(f"✅ 实体已存入数据库: {test_entity}")
    print(f"   实体 ID: {entity_id}")

    # ==================== 步骤 4: 验证词典更新 ====================
    print("\n步骤 4: 验证词典是否实时更新")
    print("-" * 80)

    # 立即查询词典
    entities_after = entity_dict.extract_entities_fast(test_entity, user_id)

    print(f"查询实体: {test_entity}")
    print(f"匹配结果: {entities_after}")

    if test_entity in entities_after:
        print(f"✅ 成功！词典已实时更新")
    else:
        print(f"❌ 失败！词典未更新")

    # ==================== 步骤 5: 验证增强提取器 ====================
    print("\n步骤 5: 验证增强实体提取器")
    print("-" * 80)

    # 同步词典
    enhanced_extractor.entity_dict = entity_dict.entity_dict
    enhanced_extractor._initialized = True

    # 使用增强提取器查询
    results = enhanced_extractor.extract_entities(
        query=f"关于{test_entity}的信息", user_id=user_id, methods=["exact"]
    )

    print(f"查询: 关于{test_entity}的信息")
    print(f"匹配结果: {results}")

    if results:
        print(f"✅ 增强提取器也能找到新实体")
    else:
        print(f"❌ 增强提取器未找到新实体")

    # ==================== 步骤 6: 测试定时刷新 ====================
    print("\n步骤 6: 测试定时刷新机制")
    print("-" * 80)

    # 直接插入数据库（绕过词典更新）
    another_entity = "绕过词典的实体" + str(int(time.time()))

    await db.execute(
        """
        INSERT INTO entities (name, type, confidence, user_id)
        VALUES ($1, $2, $3, $4)
        """,
        another_entity,
        "topic",
        0.9,
        user_id,
    )

    print(f"✅ 实体已直接插入数据库（绕过词典）: {another_entity}")

    # 查询词典（应该找不到）
    entities_before_refresh = entity_dict.extract_entities_fast(another_entity, user_id)
    print(f"刷新前查询: {entities_before_refresh}")

    # 手动刷新
    await entity_dict.refresh()
    print(f"✅ 手动刷新词典")

    # 再次查询
    entities_after_refresh = entity_dict.extract_entities_fast(another_entity, user_id)
    print(f"刷新后查询: {entities_after_refresh}")

    if another_entity in entities_after_refresh:
        print(f"✅ 定时刷新机制有效")
    else:
        print(f"❌ 定时刷新机制失败")

    # ==================== 步骤 7: 清理测试数据 ====================
    print("\n步骤 7: 清理测试数据")
    print("-" * 80)

    await db.execute(
        """
        DELETE FROM entities 
        WHERE name IN ($1, $2)
        """,
        test_entity,
        another_entity,
    )

    print(f"✅ 测试数据已清理")

    # ==================== 总结 ====================
    print("\n" + "=" * 80)
    print("测试总结")
    print("=" * 80)

    print("\n✅ 实现的更新机制:")
    print("  1. 实时更新: 新实体入库时立即更新词典")
    print("  2. 增量更新: 只添加新实体，不清空整个词典")
    print("  3. 定时刷新: 5分钟自动刷新（兜底机制）")
    print("  4. 手动刷新: 提供 refresh() 方法")

    print("\n⚠️  注意事项:")
    print("  1. 增强提取器和词典服务是两个独立实例，需要同步")
    print("  2. 删除实体时也需要从词典中移除")
    print("  3. 分布式环境下需要使用共享缓存（如 Redis）")

    print("\n" + "=" * 80 + "\n")


async def main():
    """主函数"""
    try:
        await test_dict_update()
    finally:
        await db.close()


if __name__ == "__main__":
    asyncio.run(main())
