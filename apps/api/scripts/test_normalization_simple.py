#!/usr/bin/env python3
"""
简化版实体归一化功能测试

直接测试图谱构建和召回，不依赖 memories 表
"""

import asyncio
import sys
import os

# 添加项目路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.services.graph_builder_service import get_graph_builder_service
from src.services.graph_recall_service import get_graph_recall_service
from src.database import db


async def test_location_normalization():
    """测试地点归一化"""
    print("\n" + "="*60)
    print("测试 1：地点归一化")
    print("="*60)
    
    builder = get_graph_builder_service()
    recall = get_graph_recall_service()
    
    user_id = "test_user_001"
    
    # 清理测试数据
    await db.execute("DELETE FROM entities WHERE user_id IN ($1, 'system')", user_id)
    await db.execute("DELETE FROM relations WHERE user_id IN ($1, 'system')", user_id)
    
    # 测试：输入"在星巴克见面"，应自动创建归一化关系
    print("\n输入: '昨天在星巴克和小李见面'")
    result = await builder.build_graph(
        content="昨天在星巴克和小李见面，聊了项目进展",
        user_id=user_id
    )
    
    print(f"✓ 提取实体: {result['entities']}")
    print(f"✓ 提取关系: {result['relations']}")
    print(f"✓ 状态: {result['status']}")
    
    # 验证归一化关系是否创建
    relations = await db.fetch(
        """
        SELECT 
            e1.name as source,
            r.relation_type,
            e2.name as target
        FROM relations r
        JOIN entities e1 ON r.from_entity_id = e1.id
        JOIN entities e2 ON r.to_entity_id = e2.id
        WHERE r.user_id = 'system'
        AND r.relation_type = 'is_a'
        """
    )
    
    print(f"\n系统归一化关系:")
    for r in relations:
        print(f"  - {r['source']} {r['relation_type']} {r['target']}")
    
    # 测试图谱召回
    print("\n测试查询 '咖啡店':")
    search_result = await recall.search_graph(
        query="咖啡店",
        user_id=user_id,
        limit=10
    )
    
    print(f"  - 关系数量: {len(search_result['relations'])}")
    print(f"  - 实体扩展: {[r['source'] for r in search_result['relations']]}")
    
    # 检查是否通过归一化关系找到了"星巴克"
    has_starbucks = any(
        '星巴克' in r['source'] or '星巴克' in r['destination']
        for r in search_result['relations']
    )
    
    if has_starbucks:
        print("✅ 地点归一化测试通过：查询'咖啡店'成功找到'星巴克'")
        return True
    else:
        print("❌ 地点归一化测试失败：未找到'星巴克'")
        return False


async def test_person_normalization():
    """测试人物归一化（智能询问）"""
    print("\n" + "="*60)
    print("测试 2：人物归一化（智能询问）")
    print("="*60)
    
    builder = get_graph_builder_service()
    
    user_id = "test_user_002"
    
    # 清理测试数据
    await db.execute("DELETE FROM entities WHERE user_id = $1", user_id)
    await db.execute("DELETE FROM relations WHERE user_id IN ($1, 'system')", user_id)
    
    # 第一步：创建"张三"实体
    print("\n第一步: 创建'张三'实体")
    result1 = await builder.build_graph(
        content="今天和张三吃饭，聊得很开心",
        user_id=user_id
    )
    print(f"✓ 提取实体: {result1['entities']}")
    
    # 第二步：创建"老张"实体（应触发智能询问）
    print("\n第二步: 创建'老张'实体（应触发智能询问）")
    result2 = await builder.build_graph(
        content="老张请客吃了顿大餐",
        user_id=user_id
    )
    
    print(f"✓ 返回状态: {result2.get('status')}")
    
    if result2.get('need_confirm'):
        print(f"✅ 智能询问触发:")
        print(f"  - 问题: {result2['question']}")
        print(f"  - 实体: {result2['entities']}")
        
        # 模拟用户确认
        await builder._create_normalization_relation(
            source_entity=result2['entities'][0],  # 老张
            target_entity=result2['entities'][1],  # 张三
            relation_type="same_as"
        )
        print(f"✓ 已确认归一化关系: 老张 same_as 张三")
        
        # 验证关系是否创建
        relations = await db.fetch(
            """
            SELECT 
                e1.name as source,
                r.relation_type,
                e2.name as target
            FROM relations r
            JOIN entities e1 ON r.from_entity_id = e1.id
            JOIN entities e2 ON r.to_entity_id = e2.id
            WHERE r.relation_type = 'same_as'
            """
        )
        
        print(f"\n归一化关系:")
        for r in relations:
            print(f"  - {r['source']} {r['relation_type']} {r['target']}")
        
        return True
    else:
        print("❌ 智能询问未触发")
        print(f"  提取实体: {result2.get('entities', [])}")
        return False


async def test_graph_expansion():
    """测试图谱关系扩展"""
    print("\n" + "="*60)
    print("测试 3：图谱关系扩展")
    print("="*60)
    
    recall = get_graph_recall_service()
    
    user_id = "test_user_003"
    
    # 清理测试数据
    await db.execute("DELETE FROM entities WHERE user_id IN ($1, 'system')", user_id)
    await db.execute("DELETE FROM relations WHERE user_id IN ($1, 'system')", user_id)
    
    # 手动创建测试数据
    # 创建实体
    entity1_id = await db.fetchval(
        """
        INSERT INTO entities (name, type, user_id, confidence)
        VALUES ('老婆', 'person', $1, 0.9)
        RETURNING id
        """,
        user_id
    )
    
    entity2_id = await db.fetchval(
        """
        INSERT INTO entities (name, type, user_id, confidence)
        VALUES ('孩子', 'person', $1, 0.9)
        RETURNING id
        """,
        user_id
    )
    
    # 创建关系
    await db.execute(
        """
        INSERT INTO relations (from_entity_id, to_entity_id, relation_type, weight, confidence, user_id)
        VALUES ($1, $2, 'family', 0.8, 0.9, $3)
        """,
        str(entity1_id), str(entity2_id), user_id
    )
    
    print(f"✓ 创建测试实体: 老婆, 孩子")
    print(f"✓ 创建测试关系: 老婆 - family -> 孩子")
    
    # 测试关系扩展
    relations = await recall._get_entity_relations([str(entity1_id)], user_id)
    
    print(f"\n查询'老婆'的关系:")
    for r in relations:
        print(f"  - {r['source']} {r['relationship']} {r['destination']}")
    
    if relations:
        print("✅ 关系扩展测试通过")
        return True
    else:
        print("❌ 关系扩展测试失败")
        return False


async def main():
    """运行所有测试"""
    print("\n" + "="*60)
    print("开始测试实体归一化功能（简化版）")
    print("="*60)
    
    try:
        # 测试 1：地点归一化
        test1_passed = await test_location_normalization()
        
        # 测试 2：人物归一化
        test2_passed = await test_person_normalization()
        
        # 测试 3：关系扩展
        test3_passed = await test_graph_expansion()
        
        # 总结
        print("\n" + "="*60)
        print("测试总结")
        print("="*60)
        print(f"测试 1 (地点归一化): {'✅ 通过' if test1_passed else '❌ 失败'}")
        print(f"测试 2 (人物归一化): {'✅ 通过' if test2_passed else '❌ 失败'}")
        print(f"测试 3 (关系扩展): {'✅ 通过' if test3_passed else '❌ 失败'}")
        
        all_passed = test1_passed and test2_passed and test3_passed
        print(f"\n总结果: {'✅ 全部通过' if all_passed else '❌ 部分失败'}")
        
        return all_passed
        
    except Exception as e:
        print(f"\n❌ 测试出错: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    result = asyncio.run(main())
    sys.exit(0 if result else 1)
