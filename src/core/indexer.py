"""
索引管理模块
管理时间、位置、人物、标签索引
"""

from typing import Dict, List, Any, Optional
from datetime import datetime
import json
import os


class MemoryIndexer:
    """记忆索引器"""
    
    def __init__(self, index_dir: str = "./index"):
        """
        初始化索引器
        
        Args:
            index_dir: 索引存储目录
        """
        self.index_dir = index_dir
        self.indices = {
            "time": {},      # {date_str: [memory_ids]}
            "location": {},  # {location_name: [memory_ids]}
            "people": {},    # {person_name: [memory_ids]}
            "tags": {},      # {tag: [memory_ids]}
        }
        
        # 创建索引目录
        os.makedirs(index_dir, exist_ok=True)
        
        # 加载已有索引
        self._load_indices()
    
    def _load_indices(self):
        """从文件加载索引"""
        for index_name in self.indices.keys():
            index_path = os.path.join(self.index_dir, f"{index_name}_index.json")
            if os.path.exists(index_path):
                with open(index_path, 'r', encoding='utf-8') as f:
                    self.indices[index_name] = json.load(f)
    
    def _save_indices(self):
        """保存索引到文件"""
        for index_name, index_data in self.indices.items():
            index_path = os.path.join(self.index_dir, f"{index_name}_index.json")
            with open(index_path, 'w', encoding='utf-8') as f:
                json.dump(index_data, f, ensure_ascii=False, indent=2)
    
    def add_memory(self, memory_id: str, memory_data: Dict[str, Any]):
        """
        添加记忆到索引
        
        Args:
            memory_id: 记忆 ID
            memory_data: 结构化记忆数据
        """
        # 时间索引
        time_value = memory_data.get("time", {}).get("value")
        if time_value:
            date_str = time_value.split("T")[0] if "T" in time_value else time_value
            if date_str not in self.indices["time"]:
                self.indices["time"][date_str] = []
            self.indices["time"][date_str].append(memory_id)
        
        # 位置索引
        location_name = memory_data.get("location", {}).get("name")
        if location_name:
            if location_name not in self.indices["location"]:
                self.indices["location"][location_name] = []
            self.indices["location"][location_name].append(memory_id)
        
        # 人物索引
        people = memory_data.get("people", [])
        for person in people:
            person_name = person.get("name")
            if person_name:
                if person_name not in self.indices["people"]:
                    self.indices["people"][person_name] = []
                self.indices["people"][person_name].append(memory_id)
        
        # 标签索引
        tags = memory_data.get("tags", [])
        for tag in tags:
            if tag not in self.indices["tags"]:
                self.indices["tags"][tag] = []
            self.indices["tags"][tag].append(memory_id)
        
        # 保存索引
        self._save_indices()
    
    def search_by_time(
        self,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None
    ) -> List[str]:
        """
        按时间范围查询
        
        Args:
            start_date: 开始日期（ISO 8601）
            end_date: 结束日期（ISO 8601）
        
        Returns:
            记忆 ID 列表
        """
        memory_ids = []
        
        for date_str, ids in self.indices["time"].items():
            if start_date and date_str < start_date:
                continue
            if end_date and date_str > end_date:
                continue
            memory_ids.extend(ids)
        
        return memory_ids
    
    def search_by_location(self, location_name: str) -> List[str]:
        """
        按位置查询
        
        Args:
            location_name: 位置名称
        
        Returns:
            记忆 ID 列表
        """
        return self.indices["location"].get(location_name, [])
    
    def search_by_person(self, person_name: str) -> List[str]:
        """
        按人物查询
        
        Args:
            person_name: 人物名称
        
        Returns:
            记忆 ID 列表
        """
        return self.indices["people"].get(person_name, [])
    
    def search_by_tags(self, tags: List[str]) -> List[str]:
        """
        按标签查询
        
        Args:
            tags: 标签列表
        
        Returns:
            记忆 ID 列表
        """
        memory_ids = []
        
        for tag in tags:
            if tag in self.indices["tags"]:
                memory_ids.extend(self.indices["tags"][tag])
        
        # 去重
        return list(set(memory_ids))
    
    def get_stats(self) -> Dict[str, int]:
        """
        获取索引统计
        
        Returns:
            索引统计信息
        """
        return {
            "time_entries": len(self.indices["time"]),
            "location_entries": len(self.indices["location"]),
            "people_entries": len(self.indices["people"]),
            "tags_entries": len(self.indices["tags"]),
        }
