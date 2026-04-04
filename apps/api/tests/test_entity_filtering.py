"""
实体过滤功能单元测试
"""

import pytest
from src.services.core.llm_entity_extraction import (
    should_skip_entity,
    MEANINGLESS_ENTITIES,
    LLMEntityExtractor,
)


class TestShouldSkipEntity:
    """测试 should_skip_entity 函数"""

    def test_empty_name(self):
        """空名称应该被跳过"""
        assert should_skip_entity("", "person") is True
        assert should_skip_entity(None, "person") is True

    def test_too_short_name(self):
        """过短名称应该被跳过"""
        assert should_skip_entity("A", "thing") is True
        assert should_skip_entity("我", "person") is True

    def test_too_long_name(self):
        """过长名称应该被跳过"""
        long_name = "这是一个非常非常非常非常非常非常非常长的实体名称啊"
        assert len(long_name) > 20
        assert should_skip_entity(long_name, "thing") is True

    def test_numeric_name(self):
        """纯数值名称应该被跳过"""
        assert should_skip_entity("0.85", "thing") is True
        assert should_skip_entity("100", "thing") is True
        assert should_skip_entity("3.14", "thing") is True
        assert should_skip_entity("8888", "thing") is True

    def test_file_path_name(self):
        """文件路径格式名称应该被跳过"""
        assert should_skip_entity("apps/api/src/services/", "thing") is True
        assert should_skip_entity("document_store.py", "thing") is True
        assert should_skip_entity("main.ts", "thing") is True

    def test_code_location_name(self):
        """代码位置格式名称应该被跳过"""
        assert should_skip_entity("document_store.py:82", "event") is True
        assert should_skip_entity("main.ts:100-120", "thing") is True

    def test_valid_entity_name(self):
        """有效实体名称应该保留"""
        assert should_skip_entity("张三", "person") is False
        assert should_skip_entity("字节跳动", "organization") is False
        assert should_skip_entity("北京", "location") is False
        assert should_skip_entity("Python", "thing") is False


class TestMeaninglessEntities:
    """测试黑名单实体"""

    def test_blacklist_contains_pronouns(self):
        """黑名单应包含代词"""
        pronouns = ["我", "你", "他", "她", "我们", "你们", "他们", "用户", "说话者"]
        for word in pronouns:
            assert word in MEANINGLESS_ENTITIES, f"'{word}' 应在黑名单中"

    def test_blacklist_contains_generic_nouns(self):
        """黑名单应包含泛指名词"""
        generic_nouns = [
            "代码",
            "技术",
            "日志",
            "数据库",
            "系统",
            "项目",
            "功能",
            "服务",
        ]
        for word in generic_nouns:
            assert word in MEANINGLESS_ENTITIES, f"'{word}' 应在黑名单中"

    def test_blacklist_contains_language_names(self):
        """黑名单应包含语言名称"""
        languages = ["中文", "英文", "EN", "CN"]
        for word in languages:
            assert word in MEANINGLESS_ENTITIES, f"'{word}' 应在黑名单中"

    def test_blacklist_contains_verbs_states(self):
        """黑名单应包含动词/状态"""
        verbs = ["中断", "新建", "关联", "修正", "延后", "完成"]
        for word in verbs:
            assert word in MEANINGLESS_ENTITIES, f"'{word}' 应在黑名单中"


class TestFilterEntitiesWithTypes:
    """测试 _filter_entities_with_types 方法"""

    def setup_method(self):
        self.extractor = LLMEntityExtractor()

    def test_filter_blacklist_entities(self):
        """黑名单实体应该被过滤"""
        entities = [
            {"name": "用户", "type": "person"},
            {"name": "代码", "type": "thing"},
            {"name": "中文", "type": "organization"},
        ]
        filtered = self.extractor._filter_entities_with_types(entities)
        assert len(filtered) == 0

    def test_filter_file_path_entities(self):
        """文件路径实体应该被过滤"""
        entities = [
            {"name": "apps/api/src/", "type": "thing"},
            {"name": "document_store.py", "type": "thing"},
        ]
        filtered = self.extractor._filter_entities_with_types(entities)
        assert len(filtered) == 0

    def test_filter_numeric_entities(self):
        """纯数值实体应该被过滤"""
        entities = [
            {"name": "0.85", "type": "thing"},
            {"name": "100", "type": "thing"},
        ]
        filtered = self.extractor._filter_entities_with_types(entities)
        assert len(filtered) == 0

    def test_filter_length_invalid_entities(self):
        """长度异常实体应该被过滤"""
        entities = [
            {"name": "A", "type": "thing"},
            {"name": "这是一个非常非常非常非常非常长的实体名称啊", "type": "thing"},
        ]
        filtered = self.extractor._filter_entities_with_types(entities)
        assert len(filtered) == 0

    def test_keep_valid_entities(self):
        """有效实体应该保留"""
        entities = [
            {"name": "张三", "type": "person"},
            {"name": "字节跳动", "type": "organization"},
            {"name": "北京", "type": "location"},
        ]
        filtered = self.extractor._filter_entities_with_types(entities)
        assert len(filtered) == 3

    def test_mixed_entities(self):
        """混合实体应该正确过滤"""
        entities = [
            {"name": "张三", "type": "person"},
            {"name": "用户", "type": "person"},
            {"name": "字节跳动", "type": "organization"},
            {"name": "代码", "type": "thing"},
            {"name": "0.85", "type": "thing"},
        ]
        filtered = self.extractor._filter_entities_with_types(entities)
        assert len(filtered) == 2
        names = [e["name"] for e in filtered]
        assert "张三" in names
        assert "字节跳动" in names

    def test_normalize_entity_type(self):
        """非标准实体类型应该映射到 thing"""
        entities = [
            {"name": "张三", "type": "unknown_type"},
        ]
        filtered = self.extractor._filter_entities_with_types(entities)
        assert len(filtered) == 1
        assert filtered[0]["type"] == "thing"


class TestFilterIntegration:
    """集成测试：过滤函数与黑名单配合"""

    def test_case_insensitive_blacklist(self):
        """黑名单应该大小写不敏感"""
        extractor = LLMEntityExtractor()

        entities = [
            {"name": "ai", "type": "thing"},
            {"name": "AI", "type": "thing"},
            {"name": "app", "type": "thing"},
            {"name": "APP", "type": "thing"},
        ]

        filtered = extractor._filter_entities_with_types(entities)
        assert len(filtered) == 0

    def test_whitespace_handling(self):
        """应该正确处理前后空格"""
        assert should_skip_entity("  张三  ", "person") is False
        assert should_skip_entity("  代码  ", "thing") is False
