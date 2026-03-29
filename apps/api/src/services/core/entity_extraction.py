"""
Lightweight entity extraction using jieba and regex patterns.
"""

import re
from typing import List, Dict, Any, Set
from dataclasses import dataclass, field

try:
    import jieba
    import jieba.posseg as pseg

    JIEBA_AVAILABLE = True
except ImportError:
    JIEBA_AVAILABLE = False


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
    ],
    "preference": [
        r"(不喜欢|不爱)(.{1,20}?)(，|。|$)",
        r"(喜欢|爱|偏好)(.{1,20}?)(，|。|$)",
        r"(.{1,10}?)是(素食主义者|肉食主义者)",
    ],
    "contact": [
        r"(\d{11})",  # phone
        r"([\w.-]+@[\w.-]+\.\w+)",  # email
        r"(微信号.{0,3}\w+)",
    ],
}


class EntityExtractor:
    def __init__(self):
        self.patterns = ENTITY_PATTERNS
        self._init_jieba()

    def _init_jieba(self) -> None:
        if JIEBA_AVAILABLE:
            jieba.initialize()

    def extract(self, text: str) -> List[Entity]:
        entities = []
        extracted_texts: Set[str] = set()

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

        pos_mapping = {
            "ns": "location",
            "nt": "organization",
            "nr": "person",
            "t": "time",
            "m": "number",
        }

        words = pseg.cut(text)
        offset = 0

        for word, flag in words:
            if flag in pos_mapping:
                entities.append(
                    Entity(
                        text=word,
                        type=pos_mapping[flag],
                        start=offset,
                        end=offset + len(word),
                        confidence=0.7,
                    )
                )
            offset += len(word)

        return entities


entity_extractor = EntityExtractor()
