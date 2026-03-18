"""
测试结构化提取模块
"""

import pytest
from datetime import datetime
from src.core.extractor import MemoryExtractor


class TestMemoryExtractor:
    """MemoryExtractor 测试"""
    
    def setup_method(self):
        """每个测试方法前执行"""
        self.extractor = MemoryExtractor()
        self.current_time = datetime(2026, 3, 19, 15, 0, 0)
    
    def test_extract_complete_info(self):
        """测试完整信息提取"""
        text = "今天下午3点在星巴克遇到了老同学张三，聊得很开心"
        result = self.extractor.extract_from_text(text, self.current_time)
        
        # 验证时间
        assert result["time"]["value"] is not None
        assert result["time"]["source"] == "extracted"
        
        # 验证地点
        assert result["location"]["name"] == "星巴克"
        assert result["location"]["need_confirm"] is False
        
        # 验证人物
        assert len(result["people"]) > 0
        assert any(p["name"] == "张三" for p in result["people"])
        
        # 验证情绪
        assert result["emotion"]["value"] == "开心"
        
        # 验证标签
        assert "咖啡店" in result["tags"] or "社交" in result["tags"]
    
    def test_extract_fuzzy_info(self):
        """测试模糊信息提取"""
        text = "昨天遇到一个有趣的人"
        result = self.extractor.extract_from_text(text, self.current_time)
        
        # 验证时间（相对时间）
        assert result["time"]["value"] is not None
        
        # 验证人物（需要确认）
        assert len(result["people"]) > 0
        assert result["people"][0]["need_confirm"] is True
        
        # 验证询问
        assert len(result["need_questions"]) > 0
    
    def test_extract_mood_only(self):
        """测试纯心情记录"""
        text = "今天心情不错"
        result = self.extractor.extract_from_text(text, self.current_time)
        
        # 验证时间
        assert result["time"]["value"] is not None
        
        # 验证情绪
        assert result["emotion"]["value"] == "开心"
        
        # 验证不询问
        assert len(result["need_questions"]) == 0
    
    def test_extract_time_patterns(self):
        """测试时间提取"""
        # 今天
        result = self.extractor.extract_from_text("今天", self.current_time)
        assert "2026-03-19" in result["time"]["value"]
        
        # 昨天
        result = self.extractor.extract_from_text("昨天", self.current_time)
        assert "2026-03-18" in result["time"]["value"]
        
        # 推断时间
        result = self.extractor.extract_from_text("下班后", self.current_time)
        assert result["time"]["source"] == "inferred"
    
    def test_extract_location_patterns(self):
        """测试地点提取"""
        # 明确地点
        result = self.extractor.extract_from_text("在星巴克三里屯店", self.current_time)
        assert result["location"]["name"] is not None
        assert result["location"]["need_confirm"] is False
        
        # 泛指地点
        result = self.extractor.extract_from_text("在咖啡店", self.current_time)
        assert result["location"]["name"] == "咖啡店"
    
    def test_extract_emotion_patterns(self):
        """测试情绪提取"""
        # 开心
        result = self.extractor.extract_from_text("今天很开心", self.current_time)
        assert result["emotion"]["value"] == "开心"
        
        # 难过
        result = self.extractor.extract_from_text("有点难过", self.current_time)
        assert result["emotion"]["value"] == "难过"
        
        # 焦虑
        result = self.extractor.extract_from_text("很焦虑", self.current_time)
        assert result["emotion"]["value"] == "焦虑"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
