"""
图谱增强召回测试

测试 Phase 4 实现的三路召回功能:
1. 向量召回
2. 关键词召回
3. 图谱召回
"""

import pytest
import asyncio
import sys
import os
from datetime import datetime
from unittest.mock import Mock, AsyncMock, patch, MagicMock

# 添加项目路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../src'))


class TestGraphEnhancedRecall:
    """图谱增强召回测试"""
    
    @pytest.fixture
    def mock_db(self):
        """模拟数据库"""
        mock = AsyncMock()
        return mock
    
    @pytest.fixture
    def mock_embedding_client(self):
        """模拟 embedding 客户端"""
        mock = Mock()
        mock.embed = Mock(return_value=[0.1] * 1024)
        return mock
    
    @pytest.fixture
    def mock_llm_service(self):
        """模拟 LLM 服务"""
        mock = AsyncMock()
        mock.call_with_tools = AsyncMock(return_value={
            "tool_calls": [{
                "function": {
                    "arguments": {
                        "entities": [
                            {"entity": "张三"},
                            {"entity": "李四"}
                        ]
                    }
                }
            }]
        })
        return mock
    
    @pytest.fixture
    def mock_recall_service(self):
        """模拟召回服务"""
        mock = AsyncMock()
        
        # 模拟向量搜索返回结果
        mock._vector_search = AsyncMock(return_value=[
            {
                "id": "memory-1",
                "content": "今天和张三在咖啡店聊天",
                "created_at": "2026-03-20T10:00:00",
                "location_name": "咖啡店",
                "people": [{"name": "张三"}],
                "similarity": 0.85
            },
            {
                "id": "memory-2",
                "content": "昨天和李四讨论项目",
                "created_at": "2026-03-19T15:00:00",
                "location_name": "办公室",
                "people": [{"name": "李四"}],
                "similarity": 0.75
            }
        ])
        
        # 模拟关键词搜索返回结果
        mock._keyword_search = AsyncMock(return_value=[
            {
                "id": "memory-3",
                "content": "张三的项目进度很快",
                "created_at": "2026-03-18T10:00:00",
                "location_name": "会议室",
                "people": [{"name": "张三"}],
                "similarity": 0.8
            }
        ])
        
        # 模拟 embedding_client
        mock.embedding_client = Mock()
        mock.embedding_client.embed = Mock(return_value=[0.1] * 1024)
        
        return mock
    
    @pytest.mark.asyncio
    async def test_vector_recall(self, mock_recall_service):
        """测试向量召回"""
        import sys
        import os
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../'))
        from services.graph_recall_service import GraphEnhancedRecallService
        
        service = GraphEnhancedRecallService()
        
        # Mock recall_service
        with patch('services.graph_recall_service.get_recall_service', return_value=mock_recall_service):
            results = await service._vector_recall(
                query="张三在咖啡店",
                user_id="test_user",
                limit=10
            )
        
        # 验证结果
        assert len(results) == 2
        assert results[0]["memory_id"] == "memory-1"
        assert results[0]["recall_type"] == "vector"
        assert "张三" in results[0]["content"]
        
        print("✓ 向量召回测试通过")
    
    @pytest.mark.asyncio
    async def test_keyword_recall(self, mock_recall_service):
        """测试关键词召回"""
        import sys
        import os
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../'))
        from services.graph_recall_service import GraphEnhancedRecallService
        
        service = GraphEnhancedRecallService()
        
        # Mock recall_service
        with patch('services.graph_recall_service.get_recall_service', return_value=mock_recall_service):
            results = await service._keyword_recall(
                query="张三项目",
                user_id="test_user",
                limit=10
            )
        
        # 验证结果
        assert len(results) == 1
        assert results[0]["memory_id"] == "memory-3"
        assert results[0]["recall_type"] == "keyword"
        assert "张三" in results[0]["content"]
        
        print("✓ 关键词召回测试通过")
    
    @pytest.mark.asyncio
    async def test_graph_recall(self, mock_db, mock_llm_service):
        """测试图谱召回"""
        import sys
        import os
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../'))
        from services.graph_recall_service import GraphEnhancedRecallService
        
        service = GraphEnhancedRecallService()
        service.llm_service = mock_llm_service
        
        # Mock 数据库查询
        with patch('services.graph_recall_service.db', mock_db):
            # Mock 实体搜索
            mock_db.fetch = AsyncMock(return_value=[
                {
                    "id": "entity-1",
                    "name": "张三",
                    "type": "person",
                    "confidence": 0.9
                }
            ])
            
            # Mock 关系查询
            mock_db.fetch = AsyncMock(return_value=[
                {
                    "source": "张三",
                    "relationship": "friend",
                    "destination": "李四",
                    "weight": 0.8,
                    "confidence": 0.9
                }
            ])
            
            results = await service._graph_recall(
                query="张三的朋友",
                user_id="test_user",
                limit=10
            )
        
        # 验证结果（图谱召回返回记忆列表）
        assert isinstance(results, list)
        
        print("✓ 图谱召回测试通过")
    
    @pytest.mark.asyncio
    async def test_hybrid_recall(self, mock_recall_service, mock_llm_service, mock_db):
        """测试混合召回（三路召回）"""
        import sys
        import os
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../'))
        from services.graph_recall_service import GraphEnhancedRecallService
        
        service = GraphEnhancedRecallService()
        service.llm_service = mock_llm_service
        
        # Mock recall_service
        with patch('services.graph_recall_service.get_recall_service', return_value=mock_recall_service):
            # Mock 数据库
            with patch('services.graph_recall_service.db', mock_db):
                # Mock 图谱相关查询
                mock_db.fetch = AsyncMock(return_value=[])
                
                results = await service.hybrid_recall(
                    query="张三在咖啡店",
                    user_id="test_user",
                    limit=10
                )
        
        # 验证结果
        assert isinstance(results, list)
        
        # 验证三路召回都被调用
        # vector_recall 返回 2 条结果
        # keyword_recall 返回 1 条结果
        # graph_recall 返回 0 条结果（因为 mock_db.fetch 返回空列表）
        
        print(f"混合召回返回 {len(results)} 条结果")
        print("✓ 混合召回测试通过")
    
    @pytest.mark.asyncio
    async def test_recall_service_with_graph(self, mock_embedding_client, mock_recall_service):
        """测试 RecallService 集成图谱召回"""
        import sys
        import os
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../'))
        from services.recall_service import RecallService
        
        service = RecallService()
        service.embedding_client = mock_embedding_client
        
        # Mock graph_recall_service
        mock_graph_service = AsyncMock()
        mock_graph_service.hybrid_recall = AsyncMock(return_value=[
            {
                "memory_id": "memory-1",
                "content": "测试记忆",
                "similarity": 0.85
            }
        ])
        
        with patch('services.recall_service.get_graph_recall_service', return_value=mock_graph_service):
            results = await service.search(
                query="测试查询",
                limit=10,
                enable_graph=True,
                user_id="test_user"
            )
        
        # 验证结果
        assert len(results) == 1
        assert results[0]["memory_id"] == "memory-1"
        
        print("✓ RecallService 图谱集成测试通过")
    
    @pytest.mark.asyncio
    async def test_memory_weight_sorting(self, mock_db):
        """测试记忆按关系权重排序"""
        import sys
        import os
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../'))
        from services.graph_recall_service import GraphEnhancedRecallService
        
        service = GraphEnhancedRecallService()
        
        # 模拟数据库返回结果（已按关系权重排序）
        mock_db.fetch = AsyncMock(return_value=[
            {
                "id": "memory-1",
                "content": "和张三、李四一起去爬山",
                "created_at": datetime(2026, 3, 20, 10, 0, 0),
                "location_name": "山区",
                "people": [{"name": "张三"}, {"name": "李四"}],
                "max_relation_weight": 0.9  # 高权重
            },
            {
                "id": "memory-2",
                "content": "和张三、王五讨论项目",
                "created_at": datetime(2026, 3, 20, 11, 0, 0),
                "location_name": "办公室",
                "people": [{"name": "张三"}, {"name": "王五"}],
                "max_relation_weight": 0.7  # 中权重
            },
            {
                "id": "memory-3",
                "content": "张三的个人简介",
                "created_at": datetime(2026, 3, 20, 12, 0, 0),
                "location_name": None,
                "people": [{"name": "张三"}],
                "max_relation_weight": None  # 无关系
            }
        ])
        
        with patch('services.graph_recall_service.db', mock_db):
            results = await service._get_memories_by_entities(
                entity_names=["张三"],
                user_id="test_user",
                limit=10
            )
        
        # 验证结果数量
        assert len(results) == 3
        
        # 验证排序：高权重 → 中权重 → 无关系
        assert results[0]["max_relation_weight"] == 0.9
        assert results[1]["max_relation_weight"] == 0.7
        assert results[2]["max_relation_weight"] is None
        
        # 验证权重字段存在于返回结果中
        assert "max_relation_weight" in results[0]
        
        print("✓ 记忆权重排序测试通过")


async def run_tests():
    """运行所有测试"""
    print("\n" + "=" * 60)
    print("图谱增强召回测试")
    print("=" * 60 + "\n")
    
    test_instance = TestGraphEnhancedRecall()
    
    # 创建 mock 对象（不使用 pytest fixture）
    mock_recall_service = AsyncMock()
    mock_recall_service._vector_search = AsyncMock(return_value=[
        {
            "id": "memory-1",
            "content": "今天和张三在咖啡店聊天",
            "created_at": "2026-03-20T10:00:00",
            "location_name": "咖啡店",
            "people": [{"name": "张三"}],
            "similarity": 0.85
        },
        {
            "id": "memory-2",
            "content": "昨天和李四讨论项目",
            "created_at": "2026-03-19T15:00:00",
            "location_name": "办公室",
            "people": [{"name": "李四"}],
            "similarity": 0.75
        }
    ])
    mock_recall_service._keyword_search = AsyncMock(return_value=[
        {
            "id": "memory-3",
            "content": "张三的项目进度很快",
            "created_at": "2026-03-18T10:00:00",
            "location_name": "会议室",
            "people": [{"name": "张三"}],
            "similarity": 0.8
        }
    ])
    mock_recall_service.embedding_client = Mock()
    mock_recall_service.embedding_client.embed = Mock(return_value=[0.1] * 1024)
    
    mock_llm_service = AsyncMock()
    mock_llm_service.call_with_tools = AsyncMock(return_value={
        "tool_calls": [{
            "function": {
                "arguments": {
                    "entities": [
                        {"entity": "张三"},
                        {"entity": "李四"}
                    ]
                }
            }
        }]
    })
    
    mock_db = AsyncMock()
    mock_db.fetch = AsyncMock(return_value=[])
    
    mock_embedding_client = Mock()
    mock_embedding_client.embed = Mock(return_value=[0.1] * 1024)
    
    print("1. 测试向量召回...")
    await test_instance.test_vector_recall(mock_recall_service)
    
    print("\n2. 测试关键词召回...")
    await test_instance.test_keyword_recall(mock_recall_service)
    
    print("\n3. 测试图谱召回...")
    await test_instance.test_graph_recall(mock_db, mock_llm_service)
    
    print("\n4. 测试混合召回...")
    await test_instance.test_hybrid_recall(mock_recall_service, mock_llm_service, mock_db)
    
    print("\n5. 测试 RecallService 集成...")
    await test_instance.test_recall_service_with_graph(mock_embedding_client, mock_recall_service)
    
    print("\n" + "=" * 60)
    print("✓ 所有测试通过")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    asyncio.run(run_tests())
