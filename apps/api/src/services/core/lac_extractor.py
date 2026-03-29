"""
LAC (百度中文 NER) extractor for high-precision entity extraction.

LAC provides better accuracy for Chinese NER compared to jieba.
This module provides optional LAC integration with graceful fallback to jieba.

Installation: pip install lac
"""

from typing import List, Dict, Any, Optional
from dataclasses import dataclass

try:
    from LAC import LAC

    LAC_AVAILABLE = True
except ImportError:
    LAC_AVAILABLE = False


@dataclass
class LACEntity:
    text: str
    type: str
    start: int
    end: int
    confidence: float = 0.9


LAC_TO_GENERIC_MAPPING = {
    "PER": "person",
    "LOC": "location",
    "ORG": "organization",
    "TIME": "time",
    "nr": "person",
    "ns": "location",
    "nt": "organization",
    "t": "time",
    "nz": "organization",
    "nw": "organization",
}


class LACExtractor:
    def __init__(self):
        self.lac = None
        if LAC_AVAILABLE:
            try:
                self.lac = LAC(mode="lac")
            except Exception:
                pass

    def is_available(self) -> bool:
        return self.lac is not None

    def extract(self, text: str) -> List[LACEntity]:
        if not self.lac:
            return []

        try:
            result = self.lac.run(text)
            words = result[0]
            tags = result[1]

            entities = []
            offset = 0

            for word, tag in zip(words, tags):
                if tag in LAC_TO_GENERIC_MAPPING:
                    entities.append(
                        LACEntity(
                            text=word,
                            type=LAC_TO_GENERIC_MAPPING[tag],
                            start=offset,
                            end=offset + len(word),
                            confidence=0.95,
                        )
                    )
                offset += len(word)

            return entities
        except Exception:
            return []

    def extract_to_metadata(self, text: str) -> Dict[str, List[str]]:
        entities = self.extract(text)
        metadata: Dict[str, List[str]] = {}

        for entity in entities:
            if entity.type not in metadata:
                metadata[entity.type] = []
            if entity.text not in metadata[entity.type]:
                metadata[entity.type].append(entity.text)

        return metadata

    def extract_with_positions(
        self,
        text: str,
    ) -> List[Dict[str, Any]]:
        entities = self.extract(text)
        return [
            {
                "text": e.text,
                "type": e.type,
                "start": e.start,
                "end": e.end,
                "confidence": e.confidence,
            }
            for e in entities
        ]


lac_extractor = LACExtractor()
