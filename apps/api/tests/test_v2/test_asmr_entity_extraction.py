import pytest
import sys
import os

sys.path.insert(
    0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)

from src.services.core.entity_extraction import (
    map_chinese_to_generic,
    map_generic_to_asmr,
    map_chinese_to_asmr,
    get_generic_types_for_asmr,
    ENTITY_PATTERNS,
)


class TestASMREntityTypes:
    def test_chinese_to_generic_mapping(self):
        assert map_chinese_to_generic("职业") == "occupation"
        assert map_chinese_to_generic("学历") == "education"
        assert map_chinese_to_generic("爱好") == "preference"
        assert map_chinese_to_generic("技能") == "skill"
        assert map_chinese_to_generic("家庭关系") == "person"
        assert map_chinese_to_generic("unknown") == "unknown"

    def test_generic_to_asmr_mapping(self):
        assert map_generic_to_asmr("location") == "thing_concept"
        assert map_generic_to_asmr("organization") == "thing_concept"
        assert map_generic_to_asmr("person") == "person"
        assert map_generic_to_asmr("time") == "meta"
        assert map_generic_to_asmr("preference") == "attribute_fact"
        assert map_generic_to_asmr("contact") == "meta"
        assert map_generic_to_asmr("occupation") == "person"
        assert map_generic_to_asmr("education") == "attribute_fact"
        assert map_generic_to_asmr("skill") == "attribute_fact"
        assert map_generic_to_asmr("hobby") == "attribute_fact"
        assert map_generic_to_asmr("family_relation") == "person"
        assert map_generic_to_asmr("activity") == "event"
        assert map_generic_to_asmr("unknown") == "meta"

    def test_chinese_to_asmr_mapping(self):
        assert map_chinese_to_asmr("职业") == "person"
        assert map_chinese_to_asmr("学历") == "attribute_fact"
        assert map_chinese_to_asmr("爱好") == "attribute_fact"
        assert map_chinese_to_asmr("技能") == "attribute_fact"
        assert map_chinese_to_asmr("家庭关系") == "person"

    def test_asmr_to_generic_mapping(self):
        person_types = get_generic_types_for_asmr("person")
        assert "person" in person_types
        assert "occupation" in person_types
        assert "family_relation" in person_types

        thing_types = get_generic_types_for_asmr("thing_concept")
        assert "location" in thing_types
        assert "organization" in thing_types

        attr_types = get_generic_types_for_asmr("attribute_fact")
        assert "preference" in attr_types
        assert "skill" in attr_types
        assert "education" in attr_types

        meta_types = get_generic_types_for_asmr("meta")
        assert "time" in meta_types
        assert "contact" in meta_types

    def test_entity_patterns_have_chinese_types(self):
        assert "occupation" in ENTITY_PATTERNS
        assert "education" in ENTITY_PATTERNS
        assert "skill" in ENTITY_PATTERNS
        assert "hobby" in ENTITY_PATTERNS
        assert "family_relation" in ENTITY_PATTERNS

    def test_entity_patterns_have_time_patterns(self):
        time_patterns = ENTITY_PATTERNS["time"]
        has_lunar = any("农历" in p for p in time_patterns)
        has_solar_terms = any("立春" in p or "冬至" in p for p in time_patterns)
        has_holidays = any("春节" in p or "国庆节" in p for p in time_patterns)

        assert has_lunar
        assert has_solar_terms
        assert has_holidays
