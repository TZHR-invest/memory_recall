"""
测试召回机制模块
"""

import pytest
from src.core.recall import MemoryRecall
from src.core.indexer import MemoryIndexer


class TestMemoryRecall:
    """MemoryRecall 测试"""
    
    def setup_method(self):
        """每个测试方法前执行"""
        self.indexer = MemoryIndexer("./test_index")
        self.recall = MemoryRecall(self.indexer)
    
    def teardown_method(self):
        """每个测试方法后执行"""
        import shutil
        shutil.rmtree("./test_index", ignore_errors=True)
    
    def test_simple_recall(self):
        """测试简单召回"""
        # 添加测试数据
        self.indexer.add_memory("mem-1", {
            "time": {"value": "2026-03-19T15:00:00"},
            "location": {"name": "星巴克"},
            "people": [],
            "tags": ["咖啡"]
        })
        
        # 召回
        results = self.recall.recall("咖啡", limit=10)
        assert isinstance(results, list)
    
    def test_recall_with_filters(self):
        """测试带过滤条件的召回"""
        # 添加测试数据
        self.indexer.add_memory("mem-1", {
            "time": {"value": "2026-03-19"},
            "location": {},
            "people": [],
            "tags": []
        })
        
        # 召回（带时间过滤）
        results = self.recall.recall(
            "测试",
            filters={"start_date": "2026-03-19"},
            limit=10
        )
        assert isinstance(results, list)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
