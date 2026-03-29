"""
Lightweight entity extraction using jieba and regex patterns.
"""

import re
from typing import List, Dict, Any, Set, Optional
from dataclasses import dataclass, field

try:
    import jieba
    import jieba.posseg as pseg

    JIEBA_AVAILABLE = True
except ImportError:
    JIEBA_AVAILABLE = False

from src.config import settings


@dataclass
class Entity:
    text: str
    type: str
    start: int
    end: int
    confidence: float = 0.8


ENTITY_PATTERNS = {
    "location": [
        r"在(.{1,10}?)(工作|居住|生活|上班)",
        r"住在(.{1,10}?)(，|。|$)",
        r"来自(.{1,10}?)(，|。|$)",
        r"(.{1,10}?)(市|省|区|县|镇|村)",
    ],
    "organization": [
        r"在(.{1,20}?)(公司|集团|企业|机构|学校|大学)",
        r"(.{1,20}?)(公司|集团|企业)",
        r"(.{1,30}?)(研究所|研究院)",
        r"毕业于(.{1,20}?)(大学|学院)",
        r"(.{2,15})(科技有限公司|信息技术有限公司|网络科技有限公司)",
        r"(.{2,15})(大学|学院|学校)",
        r"(.{2,15})(医院|银行|证券|保险)",
        r"在(.{2,20}?)(工作|任职|就职)",
    ],
    "person": [
        r"和(.{1,10}?)一起",
        r"跟(.{1,10}?)见面",
        r"给(.{1,10}?)打电话",
        r"(.{1,10}?)说",
    ],
    "time": [
        r"(\d{4}年\d{1,2}月\d{1,2}日)",
        r"(\d{1,2}月\d{1,2}日)",
        r"(昨天|今天|明天|上周|下周|本月|下月)",
        r"(\d{1,2}点\d{1,2}分)",
        r"农历(正月初一|正月十五|八月十五|腊月初八|腊月三十)",
        r"(立春|雨水|惊蛰|春分|清明|谷雨|立夏|小满|芒种|夏至|小暑|大暑|立秋|处暑|白露|秋分|寒露|霜降|立冬|小雪|大雪|冬至|小寒|大寒)",
        r"(春节|元宵节|清明节|端午节|中秋节|国庆节|元旦|劳动节)",
    ],
    "preference": [
        r"(不喜欢|不爱)(.{1,20}?)(，|。|$)",
        r"(喜欢|爱|偏好)(.{1,20}?)(，|。|$)",
        r"(.{1,10}?)是(素食主义者|肉食主义者)",
    ],
    "contact": [
        r"(1[3-9]\d{9})",
        r"([\w.-]+@[\w.-]+\.\w+)",
        r"微信号[：:]?\s*([a-zA-Z][a-zA-Z0-9_-]{5,19})",
        r"微信[是叫]([a-zA-Z][a-zA-Z0-9_-]{5,19})",
        r"加我微信[：:]?\s*([a-zA-Z][a-zA-Z0-9_-]{5,19})",
        r"QQ[号]?[：:]?\s*(\d{5,11})",
        r"加我QQ[：:]?\s*(\d{5,11})",
        r"我的QQ[是号为]*[：:]?\s*(\d{5,11})",
        r"电话[：:]?\s*(\d{3,4}[-\s]?\d{7,8})",
        r"座机[：:]?\s*(\d{3,4}[-\s]?\d{7,8})",
        r"(0\d{2,3}[-\s]?\d{7,8})",
    ],
    "occupation": [
        r"(.{1,10})是(.{1,10})(工程师|医生|老师|程序员|产品经理|设计师|经理|总监)",
        r"担任(.{1,20})",
        r"职位(是|为)(.{1,20})",
    ],
    "education": [
        r"(本科|硕士|博士|MBA|大专)学历",
        r"(本科|硕士|博士|MBA|大专)学位",
    ],
    "skill": [
        r"(会|精通|擅长)(.{1,20})",
        r"(.{1,20})技能",
    ],
    "hobby": [
        r"(爱好|业余)(.{1,20})",
    ],
    "family_relation": [
        r"我的(.{1,10})(妻子|儿子|女儿|父母|哥哥|姐姐|弟弟|妹妹)",
    ],
}

# Chinese type to Generic type mapping
CHINESE_TO_GENERIC_MAPPING = {
    "职业": "occupation",
    "学历": "education",
    "爱好": "preference",
    "技能": "skill",
    "家庭关系": "person",
}

# Generic type to ASMR dimension mapping
GENERIC_TO_ASMR_MAPPING = {
    "location": "thing_concept",
    "organization": "thing_concept",
    "person": "person",
    "time": "meta",
    "preference": "attribute_fact",
    "contact": "meta",
    "occupation": "person",
    "education": "attribute_fact",
    "skill": "attribute_fact",
    "hobby": "attribute_fact",
    "family_relation": "person",
    "activity": "event",
}

# ASMR dimension to Generic types mapping
ASMR_TO_GENERIC_MAPPING = {
    "person": {"person", "occupation", "family_relation"},
    "thing_concept": {"location", "organization", "project", "technology"},
    "event": {"activity", "meeting", "task"},
    "attribute_fact": {"preference", "skill", "education", "hobby", "status"},
    "relation": set(),
    "meta": {"time", "contact", "source", "confidence"},
}


CHINESE_POS_MAPPING = {
    "ns": "location",
    "nt": "organization",
    "nr": "person",
    "t": "time",
    "m": "number",
    "nz": "organization",
    "nw": "organization",
}


def map_chinese_to_generic(chinese_type: str) -> str:
    return CHINESE_TO_GENERIC_MAPPING.get(chinese_type, chinese_type)


def map_generic_to_asmr(generic_type: str) -> str:
    return GENERIC_TO_ASMR_MAPPING.get(generic_type, "meta")


def map_chinese_to_asmr(chinese_type: str) -> str:
    generic = map_chinese_to_generic(chinese_type)
    return map_generic_to_asmr(generic)


def get_generic_types_for_asmr(asmr_dimension: str) -> Set[str]:
    return ASMR_TO_GENERIC_MAPPING.get(asmr_dimension, set())


class EntityExtractor:
    def __init__(self, use_lac: Optional[bool] = None):
        self.patterns = ENTITY_PATTERNS
        self.use_lac = use_lac if use_lac is not None else settings.USE_LAC_EXTRACTOR
        self._lac_extractor = None
        self._init_jieba()

    def _init_jieba(self) -> None:
        if JIEBA_AVAILABLE:
            jieba.initialize()

    def _get_lac_extractor(self):
        if self._lac_extractor is None and self.use_lac:
            from src.services.core.lac_extractor import lac_extractor

            self._lac_extractor = lac_extractor
        return self._lac_extractor

    def extract(self, text: str) -> List[Entity]:
        entities = []
        extracted_texts: Set[str] = set()

        if self.use_lac:
            lac = self._get_lac_extractor()
            if lac and lac.is_available():
                lac_entities = self._extract_by_lac(text)
                for entity in lac_entities:
                    if entity.text not in extracted_texts:
                        entities.append(entity)
                        extracted_texts.add(entity.text)

        pattern_entities = self._extract_by_patterns(text)
        for entity in pattern_entities:
            if entity.text not in extracted_texts:
                entities.append(entity)
                extracted_texts.add(entity.text)

        if JIEBA_AVAILABLE:
            jieba_entities = self._extract_by_jieba(text)
            for entity in jieba_entities:
                if entity.text not in extracted_texts:
                    entities.append(entity)
                    extracted_texts.add(entity.text)

        return entities

    def _extract_by_lac(self, text: str) -> List[Entity]:
        lac = self._get_lac_extractor()
        if not lac or not lac.is_available():
            return []

        lac_result = lac.extract_with_positions(text)
        return [
            Entity(
                text=e["text"],
                type=e["type"],
                start=e["start"],
                end=e["end"],
                confidence=e.get("confidence", 0.95),
            )
            for e in lac_result
        ]

    def extract_to_metadata(self, text: str) -> Dict[str, List[str]]:
        entities = self.extract(text)
        metadata: Dict[str, List[str]] = {}

        for entity in entities:
            if entity.type not in metadata:
                metadata[entity.type] = []
            if entity.text not in metadata[entity.type]:
                metadata[entity.type].append(entity.text)

        return metadata

    def _extract_by_patterns(self, text: str) -> List[Entity]:
        entities = []

        for entity_type, patterns in self.patterns.items():
            for pattern in patterns:
                matches = re.finditer(pattern, text)
                for match in matches:
                    group = match.group(1) if match.groups() else match.group(0)
                    if group and len(group.strip()) > 0:
                        entities.append(
                            Entity(
                                text=group.strip(),
                                type=entity_type,
                                start=match.start(),
                                end=match.end(),
                                confidence=0.9,
                            )
                        )

        return entities

    def _extract_by_jieba(self, text: str) -> List[Entity]:
        entities = []

        if not JIEBA_AVAILABLE:
            return entities

        words = pseg.cut(text)
        offset = 0

        for word, flag in words:
            if flag in CHINESE_POS_MAPPING:
                entities.append(
                    Entity(
                        text=word,
                        type=CHINESE_POS_MAPPING[flag],
                        start=offset,
                        end=offset + len(word),
                        confidence=0.7,
                    )
                )
            offset += len(word)

        return entities


entity_extractor = EntityExtractor()
