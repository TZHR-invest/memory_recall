import pytest
import sys
import os

sys.path.insert(
    0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)

from src.services.core.entity_extraction import EntityExtractor, Entity


class TestChineseEntityExtraction:
    def setup_method(self):
        self.extractor = EntityExtractor(use_lac=False)

    def test_extract_chinese_occupation(self):
        entities = self.extractor.extract("我是一名软件工程师")
        occupation_entities = [e for e in entities if e.type == "occupation"]
        assert len(occupation_entities) > 0

    def test_extract_chinese_education(self):
        entities = self.extractor.extract("我有计算机科学硕士学位")
        education_entities = [e for e in entities if e.type == "education"]
        assert len(education_entities) > 0

    def test_extract_chinese_hobby(self):
        entities = self.extractor.extract("我喜欢打篮球和看书")
        preference_entities = [e for e in entities if e.type == "preference"]
        assert len(preference_entities) > 0

    def test_extract_chinese_time_lunar(self):
        entities = self.extractor.extract("我的生日是农历八月十五")
        time_entities = [e for e in entities if e.type == "time"]
        assert len(time_entities) > 0
        assert any("农历" in e.text or "八月十五" in e.text for e in time_entities)

    def test_extract_chinese_time_holiday(self):
        entities = self.extractor.extract("春节我回了老家")
        time_entities = [e for e in entities if e.type == "time"]
        assert len(time_entities) > 0
        assert any("春节" in e.text for e in time_entities)

    def test_extract_chinese_time_solar_term(self):
        entities = self.extractor.extract("立春那天天气很好")
        time_entities = [e for e in entities if e.type == "time"]
        assert len(time_entities) > 0

    def test_extract_wechat_id(self):
        entities = self.extractor.extract("我的微信号是abc123")
        contact_entities = [e for e in entities if e.type == "contact"]
        assert len(contact_entities) > 0
        assert any("abc123" in e.text for e in contact_entities)

    def test_extract_qq_number(self):
        entities = self.extractor.extract("加我QQ：123456789")
        contact_entities = [e for e in entities if e.type == "contact"]
        assert len(contact_entities) > 0
        assert any("123456789" in e.text for e in contact_entities)

    def test_extract_chinese_phone(self):
        entities = self.extractor.extract("我的手机号是13812345678")
        contact_entities = [e for e in entities if e.type == "contact"]
        assert len(contact_entities) > 0
        assert any("13812345678" in e.text for e in contact_entities)

    def test_extract_chinese_landline(self):
        entities = self.extractor.extract("座机：010-12345678")
        contact_entities = [e for e in entities if e.type == "contact"]
        assert len(contact_entities) > 0

    def test_extract_chinese_organization(self):
        entities = self.extractor.extract("我在字节跳动科技有限公司工作")
        org_entities = [e for e in entities if e.type == "organization"]
        assert len(org_entities) > 0

    def test_extract_chinese_university(self):
        entities = self.extractor.extract("我毕业于清华大学")
        org_entities = [e for e in entities if e.type == "organization"]
        assert len(org_entities) > 0

    def test_extract_family_relation(self):
        entities = self.extractor.extract("我的妻子也是工程师")
        family_entities = [e for e in entities if e.type == "family_relation"]
        assert len(family_entities) > 0

    def test_extract_to_metadata(self):
        metadata = self.extractor.extract_to_metadata(
            "我是软件工程师，喜欢打篮球，手机号13812345678"
        )
        assert isinstance(metadata, dict)
        assert len(metadata) > 0

    def test_multiple_entities_in_text(self):
        entities = self.extractor.extract(
            "我毕业于清华大学，现在在字节跳动工作，喜欢喝咖啡"
        )
        assert len(entities) >= 2

    def test_entity_confidence_scores(self):
        entities = self.extractor.extract("我在北京工作")
        for entity in entities:
            assert 0.0 <= entity.confidence <= 1.0
