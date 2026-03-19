"""
数据库优化脚本
添加索引以提升查询性能
"""
import asyncio
import sys
import os
from pathlib import Path

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 加载 .env 文件
from dotenv import load_dotenv
env_path = Path(__file__).parent.parent / ".env"
load_dotenv(env_path)

from src.database import db


async def create_indexes():
    """创建数据库索引"""
    print("=" * 60)
    print("🔧 数据库索引优化")
    print("=" * 60)
    
    try:
        await db.connect()
        print("✅ 数据库连接成功")
        
        # 索引定义
        indexes = [
            # 主表索引
            {
                "name": "idx_memories_status",
                "table": "memories",
                "columns": "status",
                "description": "状态过滤索引"
            },
            {
                "name": "idx_memories_created_at",
                "table": "memories",
                "columns": "created_at DESC",
                "description": "创建时间排序索引"
            },
            {
                "name": "idx_memories_time_value",
                "table": "memories",
                "columns": "time_value",
                "description": "时间值过滤索引"
            },
            {
                "name": "idx_memories_time_range",
                "table": "memories",
                "columns": "time_value, status",
                "description": "时间范围查询复合索引"
            },
            {
                "name": "idx_memories_location",
                "table": "memories",
                "columns": "location_name",
                "description": "地点过滤索引"
            },
            {
                "name": "idx_memories_tags",
                "table": "memories",
                "columns": "tags",
                "using": "GIN",
                "description": "标签数组索引（GIN）"
            },
            {
                "name": "idx_memories_people",
                "table": "memories",
                "columns": "people",
                "using": "GIN",
                "description": "人物 JSONB 索引（GIN）"
            },
            {
                "name": "idx_memories_content_fts",
                "table": "memories",
                "columns": "to_tsvector('simple', content)",
                "description": "内容全文检索索引"
            },
            {
                "name": "idx_memories_location_fts",
                "table": "memories",
                "columns": "to_tsvector('simple', location_name)",
                "description": "地点全文检索索引"
            },
            # 向量索引（IVFFlat）
            {
                "name": "idx_memories_embedding",
                "table": "memories",
                "columns": "embedding",
                "using": "ivfflat",
                "opclass": "vector_cosine_ops",
                "description": "向量相似度索引（IVFFlat）",
                "options": "WITH (lists = 100)"
            }
        ]
        
        # 创建索引
        print("\n创建索引:")
        for idx in indexes:
            try:
                # 检查索引是否已存在
                exists = await db.fetchval("""
                    SELECT 1 FROM pg_indexes 
                    WHERE indexname = $1
                """, idx["name"])
                
                if exists:
                    print(f"  ⏭️  {idx['name']}: 已存在")
                    continue
                
                # 构建 CREATE INDEX 语句
                using = idx.get("using", "btree")
                opclass = idx.get("opclass", "")
                options = idx.get("options", "")
                
                sql = f"""
                    CREATE INDEX {idx['name']}
                    ON {idx['table']}
                    USING {using} ({idx['columns']}{' ' + opclass if opclass else ''})
                    {options}
                """
                
                await db.execute(sql)
                print(f"  ✅ {idx['name']}: {idx['description']}")
                
            except Exception as e:
                print(f"  ❌ {idx['name']}: {e}")
        
        # 分析表统计信息
        print("\n更新表统计信息...")
        await db.execute("ANALYZE memories")
        print("  ✅ 完成")
        
        # 显示索引列表
        print("\n当前索引:")
        rows = await db.fetch("""
            SELECT indexname, indexdef
            FROM pg_indexes
            WHERE tablename = 'memories'
            ORDER BY indexname
        """)
        
        for row in rows:
            print(f"  - {row['indexname']}")
        
        print("\n" + "=" * 60)
        print("✅ 数据库索引优化完成")
        print("=" * 60)
        
    except Exception as e:
        print(f"\n❌ 错误: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await db.disconnect()


if __name__ == "__main__":
    asyncio.run(create_indexes())
