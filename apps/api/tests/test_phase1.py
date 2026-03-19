"""
Phase 1 完成测试脚本
测试：
1. 数据库表创建
2. 工具定义格式
3. Prompt 模板
4. GraphBuilderService 初始化
"""
import asyncio
import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.database import db
from src.services.graph_tools import validate_all_tools, GRAPH_TOOLS
from src.services.graph_builder_service import GraphBuilderService
from src.services.prompts import (
    USER_MEMORY_EXTRACTION_PROMPT,
    ENTITY_EXTRACTION_PROMPT,
    RELATION_EXTRACTION_PROMPT
)


async def test_database_tables():
    """测试数据库表创建"""
    print("=" * 60)
    print("测试数据库表")
    print("=" * 60)
    
    await db.connect()
    
    try:
        # 测试 entities 表
        result = await db.fetchrow("""
            SELECT column_name, data_type 
            FROM information_schema.columns 
            WHERE table_name = 'entities'
            ORDER BY ordinal_position
        """)
        
        if result:
            print("✓ entities 表存在")
        else:
            print("✗ entities 表不存在")
            return False
        
        # 测试 relations 表
        result = await db.fetchrow("""
            SELECT column_name, data_type 
            FROM information_schema.columns 
            WHERE table_name = 'relations'
            ORDER BY ordinal_position
        """)
        
        if result:
            print("✓ relations 表存在")
        else:
            print("✗ relations 表不存在")
            return False
        
        # 测试 memory_entities 表
        result = await db.fetchrow("""
            SELECT column_name, data_type 
            FROM information_schema.columns 
            WHERE table_name = 'memory_entities'
            ORDER BY ordinal_position
        """)
        
        if result:
            print("✓ memory_entities 表存在")
        else:
            print("✗ memory_entities 表不存在")
            return False
        
        # 测试 pending_confirmations 表
        result = await db.fetchrow("""
            SELECT column_name, data_type 
            FROM information_schema.columns 
            WHERE table_name = 'pending_confirmations'
            ORDER BY ordinal_position
        """)
        
        if result:
            print("✓ pending_confirmations 表存在")
        else:
            print("✗ pending_confirmations 表不存在")
            return False
        
        # 测试插入数据
        test_entity_id = await db.fetchval("""
            INSERT INTO entities (name, type, user_id, confidence)
            VALUES ('测试实体', 'person', 'test_user', 0.9)
            RETURNING id
        """)
        
        if test_entity_id:
            print("✓ entities 表插入测试成功")
            
            # 清理测试数据
            await db.execute("DELETE FROM entities WHERE id = $1", test_entity_id)
            print("✓ 清理测试数据成功")
        
        return True
        
    except Exception as e:
        print(f"✗ 数据库测试失败: {e}")
        return False
    finally:
        await db.disconnect()


def test_tool_definitions():
    """测试工具定义"""
    print()
    print("=" * 60)
    print("测试工具定义")
    print("=" * 60)
    
    all_valid = validate_all_tools()
    
    print()
    if all_valid:
        print(f"✓ 所有 {len(GRAPH_TOOLS)} 个工具定义有效")
        return True
    else:
        print("✗ 部分工具定义无效")
        return False


def test_prompt_templates():
    """测试 Prompt 模板"""
    print()
    print("=" * 60)
    print("测试 Prompt 模板")
    print("=" * 60)
    
    try:
        # 测试用户记忆提取 Prompt
        assert len(USER_MEMORY_EXTRACTION_PROMPT) > 100
        assert "facts" in USER_MEMORY_EXTRACTION_PROMPT
        assert "JSON" in USER_MEMORY_EXTRACTION_PROMPT
        print("✓ USER_MEMORY_EXTRACTION_PROMPT 有效")
        
        # 测试实体提取 Prompt
        assert len(ENTITY_EXTRACTION_PROMPT) > 100
        assert "entities" in ENTITY_EXTRACTION_PROMPT
        assert "person" in ENTITY_EXTRACTION_PROMPT
        print("✓ ENTITY_EXTRACTION_PROMPT 有效")
        
        # 测试关系推理 Prompt
        assert len(RELATION_EXTRACTION_PROMPT) > 100
        assert "relations" in RELATION_EXTRACTION_PROMPT
        assert "relationship" in RELATION_EXTRACTION_PROMPT
        print("✓ RELATION_EXTRACTION_PROMPT 有效")
        
        return True
        
    except AssertionError as e:
        print(f"✗ Prompt 模板测试失败: {e}")
        return False


def test_graph_builder_service():
    """测试 GraphBuilderService 初始化"""
    print()
    print("=" * 60)
    print("测试 GraphBuilderService")
    print("=" * 60)
    
    try:
        service = GraphBuilderService()
        print("✓ GraphBuilderService 初始化成功")
        
        # 测试关键方法是否存在
        assert hasattr(service, 'build_graph')
        print("✓ build_graph 方法存在")
        
        assert hasattr(service, '_extract_entities')
        print("✓ _extract_entities 方法存在")
        
        assert hasattr(service, '_extract_relations')
        print("✓ _extract_relations 方法存在")
        
        assert hasattr(service, '_upsert_entity')
        print("✓ _upsert_entity 方法存在")
        
        assert hasattr(service, '_upsert_relation')
        print("✓ _upsert_relation 方法存在")
        
        return True
        
    except Exception as e:
        print(f"✗ GraphBuilderService 测试失败: {e}")
        return False


async def main():
    """主测试函数"""
    print()
    print("=" * 60)
    print("Phase 1 完成测试")
    print("=" * 60)
    print()
    
    results = {
        "数据库表": False,
        "工具定义": False,
        "Prompt 模板": False,
        "GraphBuilderService": False
    }
    
    # 1. 测试数据库表
    results["数据库表"] = await test_database_tables()
    
    # 2. 测试工具定义
    results["工具定义"] = test_tool_definitions()
    
    # 3. 测试 Prompt 模板
    results["Prompt 模板"] = test_prompt_templates()
    
    # 4. 测试 GraphBuilderService
    results["GraphBuilderService"] = test_graph_builder_service()
    
    # 输出总结
    print()
    print("=" * 60)
    print("测试总结")
    print("=" * 60)
    
    for name, passed in results.items():
        status = "✓ 通过" if passed else "✗ 失败"
        print(f"{name}: {status}")
    
    all_passed = all(results.values())
    
    print()
    if all_passed:
        print("=" * 60)
        print("🎉 Phase 1 所有测试通过！")
        print("=" * 60)
    else:
        print("=" * 60)
        print("❌ Phase 1 部分测试失败")
        print("=" * 60)
    
    return all_passed


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
