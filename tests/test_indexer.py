"""
测试索引管理模块
"""

import pytest
import tempfile
import os
from src.core.indexer import MemoryIndexer


class TestMemoryIndexer:
    """MemoryIndexer 测试"""
    
    def setup_method(self):
        """每个测试方法前执行"""
        # 使用临时目录
        self.temp_dir = tempfile.mkdtemp()
        self.indexer = MemoryIndexer(self.temp_dir)
    
    def teardown_method(self):
        """每个测试方法后执行"""
        # 清理临时目录
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def test_add_memory(self):
        """测试添加记忆"""
        memory_id = "test-001"
        memory_data = {
            "time": {"value": "2026-03-19T15:00:00"},
            "location": {"name": "星巴克"},
            "people": [{"name": "张三"}],
            "tags": ["咖啡", "社交"]
        }
        
        self.indexer.add_memory(memory_id, memory_data)
        
        # 验证时间索引
        assert "2026-03-19" in self.indexer.indices["time"]
        assert memory_id in self.indexer.indices["time"]["2026-03-19"]
        
        # 验证位置索引
        assert "星巴克" in self.indexer.indices["location"]
        assert memory_id in self.indexer.indices["location"]["星巴克"]
        
        # 验证人物索引
        assert "张三" in self.indexer.indices["people"]
        assert memory_id in self.indexer.indices["people"]["张三"]
        
        # 验证标签索引
        assert "咖啡" in self.indexer.indices["tags"]
        assert memory_id in self.indexer.indices["tags"]["咖啡"]
    
    def test_search_by_time(self):
        """测试按时间查询"""
        # 添加测试数据
        self.indexer.add_memory("mem-1", {
            "time": {"value": "2026-03-18"},
            "location": {},
            "people": [],
            "tags": []
        })
        self.indexer.add_memory("mem-2", {
            "time": {"value": "2026-03-19"},
            "location": {},
            "people": [],
            "tags": []
        })
        self.indexer.add_memory("mem-3", {
            "time": {"value": "2026-03-20"},
            "location": {},
            "people": [],
            "tags": []
        })
        
        # 查询时间范围
        results = self.indexer.search_by_time("2026-03-18", "2026-03-19")
        assert len(results) == 2
        assert "mem-1" in results
        assert "mem-2" in results
        assert "mem-3" not in results
    
    def test_search_by_location(self):
        """测试按位置查询"""
        # 添加测试数据
        self.indexer.add_memory("mem-1", {
            "time": {},
            "location": {"name": "星巴克"},
            "people": [],
            "tags": []
        })
        self.indexer.add_memory("mem-2", {
            "time": {},
            "location": {"name": "星巴克"},
            "people": [],
            "tags": []
        })
        self.indexer.add_memory("mem-3", {
            "time": {},
            "location": {"name": "咖啡店"},
            "people": [],
            "tags": []
        })
        
        # 查询位置
        results = self.indexer.search_by_location("星巴克")
        assert len(results) == 2
        assert "mem-1" in results
        assert "mem-2" in results
        assert "mem-3" not in results
    
    def test_search_by_tags(self):
        """测试按标签查询"""
        # 添加测试数据
        self.indexer.add_memory("mem-1", {
            "time": {},
            "location": {},
            "people": [],
            "tags": ["咖啡", "社交"]
        })
        self.indexer.add_memory("mem-2", {
            "time": {},
            "location": {},
            "people": [],
            "tags": ["咖啡", "工作"]
        })
        self.indexer.add_memory("mem-3", {
            "time": {},
            "location": {},
            "people": [],
            "tags": ["运动"]
        })
        
        # 查询标签
        results = self.indexer.search_by_tags(["咖啡"])
        assert len(results) == 2
        assert "mem-1" in results
        assert "mem-2" in results
        assert "mem-3" not in results
    
    def test_get_stats(self):
        """测试索引统计"""
        # 添加测试数据
        self.indexer.add_memory("mem-1", {
            "time": {"value": "2026-03-19"},
            "location": {"name": "星巴克"},
            "people": [{"name": "张三"}],
            "tags": ["咖啡"]
        })
        
        stats = self.indexer.get_stats()
        assert stats["time_entries"] == 1
        assert stats["location_entries"] == 1
        assert stats["people_entries"] == 1
        assert stats["tags_entries"] == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
