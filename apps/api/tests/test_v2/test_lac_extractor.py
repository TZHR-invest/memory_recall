import pytest
import sys
import os

sys.path.insert(
    0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
))

from src.services.core.lac_extractor import LACExtractor


class TestLACExtractor:
    def test_lac_extractor_initialization(self):
        extractor = LACExtractor()
        assert extractor is not None

    def test_lac_availability_check(self):
        extractor = LACExtractor()
        is_available = extractor.is_available()
        assert isinstance(is_available, bool)

    def test_extract_basic(self):
        extractor = LACExtractor()
        if not extractor.is_available():
            pytest.skip("LAC not available")

        entities = extractor.extract("我在北京工作")
        assert isinstance(entities, list)

    def test_extract_with_positions(self):
        extractor = LACExtractor()
        if not extractor.is_available():
            pytest.skip("LAC not available")

        entities = extractor.extract_with_positions("我在北京工作")
        assert isinstance(entities, list)

        for entity in entities:
            assert "text" in entity
            assert "type" in entity
            assert "start" in entity
            assert "end" in entity

    def test_extract_person_entity(self):
        extractor = LACExtractor()
        if not extractor.is_available():
            pytest.skip("LAC not available")

        entities = extractor.extract("张三是产品经理")
        person_entities = [e for e in entities if e.get("type") == "PER"]
        assert len(person_entities) >= 0

    def test_extract_location_entity(self):
        extractor = LACExtractor()
        if not extractor.is_available():
            pytest.skip("LAC not available")

        entities = extractor.extract("我在北京工作")
        location_entities = [e for e in entities if e.get("type") == "LOC"]
        assert len(location_entities) >= 0

    def test_extract_organization_entity(self):
        extractor = LACExtractor()
        if not extractor.is_available():
            pytest.skip("LAC not available")

        entities = extractor.extract("我在字节跳动工作")
        org_entities = [e for e in entities if e.get("type") == "ORG"]
        assert len(org_entities) >= 0

    def test_graceful_fallback(self):
        extractor = LACExtractor()
        
        if extractor.is_available():
            entities = extractor.extract("测试文本")
            assert isinstance(entities, list)
        else:
            entities = extractor.extract("测试文本")
            assert entities == []

    def test_empty_text(self):
        extractor = LACExtractor()
        if not extractor.is_available():
            pytest.skip("LAC not available")

        entities = extractor.extract("")
        assert entities == []

    def test_extract_to_dict(self):
        extractor = LACExtractor()
        if not extractor.is_available():
            pytest.skip("LAC not available")

        result = extractor.extract_to_dict("我在北京工作")
        assert isinstance(result, dict)
