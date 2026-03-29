"""
Chinese-specific entity type definitions and mappings.

Provides Chinese entity types with mappings to ASMR dimensions and generic types.
"""

from typing import Dict, List, Set, Tuple
from dataclasses import dataclass, field


@dataclass
class ChineseEntityType:
    """Chinese-specific entity type definition."""

    chinese_name: str
    english_name: str
    asmr_dimension: str
    generic_type: str
    examples: List[str] = field(default_factory=list)
    patterns: List[str] = field(default_factory=list)


CHINESE_ENTITY_TYPES: Dict[str, ChineseEntityType] = {
    "职业": ChineseEntityType(
        chinese_name="职业",
        english_name="occupation",
        asmr_dimension="person",
        generic_type="organization",
        examples=["工程师", "医生", "老师", "程序员", "产品经理", "设计师"],
        patterns=[
            r"(.{1,10})是(.{1,10})(工程师|医生|老师|程序员|产品经理|设计师)",
            r"担任(.{1,10})",
            r"工作(是|为)(.{1,10})",
        ],
    ),
    "学历": ChineseEntityType(
        chinese_name="学历",
        english_name="education",
        asmr_dimension="attribute_fact",
        generic_type="education",
        examples=["本科", "硕士", "博士", "MBA", "大专"],
        patterns=[
            r"(本科|硕士|博士|MBA|大专)学历",
            r"(本科|硕士|博士|MBA|大专)学位",
            r"毕业于(.{1,30})",
        ],
    ),
    "爱好": ChineseEntityType(
        chinese_name="爱好",
        english_name="hobby",
        asmr_dimension="attribute_fact",
        generic_type="preference",
        examples=["打篮球", "看书", "旅行", "摄影", "玩游戏", "听音乐"],
        patterns=[
            r"(喜欢|爱|爱好)(.{1,20})",
            r"业余(时间)?(.{1,20})",
        ],
    ),
    "技能": ChineseEntityType(
        chinese_name="技能",
        english_name="skill",
        asmr_dimension="attribute_fact",
        generic_type="skill",
        examples=["Python", "驾驶", "钢琴", "英语", "Excel"],
        patterns=[
            r"(会|精通|擅长)(.{1,20})",
            r"(.{1,20})技能",
        ],
    ),
    "家庭关系": ChineseEntityType(
        chinese_name="家庭关系",
        english_name="family_relation",
        asmr_dimension="person",
        generic_type="person",
        examples=["妻子", "儿子", "女儿", "父母", "兄弟姐妹"],
        patterns=[
            r"我的(.{1,10})(妻子|儿子|女儿|父母|哥哥|姐姐|弟弟|妹妹)",
            r"(妻子|儿子|女儿|父母)(是|叫)(.{1,10})",
        ],
    ),
    "微信": ChineseEntityType(
        chinese_name="微信",
        english_name="wechat",
        asmr_dimension="meta",
        generic_type="contact",
        examples=["微信号abc123", "我的微信是xyz789"],
        patterns=[
            r"微信号[：:]?\s*([a-zA-Z][a-zA-Z0-9_-]{5,19})",
            r"微信[是叫]([a-zA-Z][a-zA-Z0-9_-]{5,19})",
            r"加我微信[：:]?\s*([a-zA-Z][a-zA-Z0-9_-]{5,19})",
        ],
    ),
    "QQ": ChineseEntityType(
        chinese_name="QQ",
        english_name="qq",
        asmr_dimension="meta",
        generic_type="contact",
        examples=["QQ号123456789", "我的QQ是987654321"],
        patterns=[
            r"QQ[号]?[：:]?\s*(\d{5,11})",
            r"加我QQ[：:]?\s*(\d{5,11})",
        ],
    ),
    "手机": ChineseEntityType(
        chinese_name="手机",
        english_name="phone",
        asmr_dimension="meta",
        generic_type="contact",
        examples=["手机号13812345678", "电话010-12345678"],
        patterns=[
            r"手机[号码]?[：:]?\s*(1[3-9]\d{9})",
            r"电话[：:]?\s*(\d{3,4}[-\s]?\d{7,8})",
            r"(1[3-9]\d{9})",
        ],
    ),
    "农历日期": ChineseEntityType(
        chinese_name="农历日期",
        english_name="lunar_date",
        asmr_dimension="meta",
        generic_type="time",
        examples=["农历正月初一", "农历八月十五"],
        patterns=[
            r"农历(正月初一|正月十五|八月十五|腊月初八|腊月三十)",
            r"农历(.{1,10})",
        ],
    ),
    "节气": ChineseEntityType(
        chinese_name="节气",
        english_name="solar_term",
        asmr_dimension="meta",
        generic_type="time",
        examples=["立春", "清明", "冬至", "大寒"],
        patterns=[
            r"(立春|雨水|惊蛰|春分|清明|谷雨|立夏|小满|芒种|夏至|小暑|大暑|立秋|处暑|白露|秋分|寒露|霜降|立冬|小雪|大雪|冬至|小寒|大寒)",
        ],
    ),
    "节假日": ChineseEntityType(
        chinese_name="节假日",
        english_name="holiday",
        asmr_dimension="meta",
        generic_type="time",
        examples=["春节", "国庆节", "中秋节", "端午节"],
        patterns=[
            r"(春节|元宵节|清明节|端午节|中秋节|国庆节|元旦|劳动节)",
        ],
    ),
    "公司": ChineseEntityType(
        chinese_name="公司",
        english_name="company",
        asmr_dimension="thing_concept",
        generic_type="organization",
        examples=["字节跳动公司", "腾讯科技有限公司", "阿里巴巴集团"],
        patterns=[
            r"(.{1,20})(公司|集团|企业|科技)",
            r"在(.{1,20})(公司|集团|企业)",
        ],
    ),
    "大学": ChineseEntityType(
        chinese_name="大学",
        english_name="university",
        asmr_dimension="thing_concept",
        generic_type="organization",
        examples=["清华大学", "北京大学", "复旦大学", "浙江大学"],
        patterns=[
            r"(.{1,20})(大学|学院)",
            r"毕业于(.{1,20})(大学|学院)",
        ],
    ),
    "研究所": ChineseEntityType(
        chinese_name="研究所",
        english_name="institute",
        asmr_dimension="thing_concept",
        generic_type="organization",
        examples=["中科院软件研究所", "微软亚洲研究院"],
        patterns=[
            r"(.{1,30})(研究所|研究院)",
        ],
    ),
}

# Mapping from Chinese type to ASMR dimension
CHINESE_TO_ASMR: Dict[str, str] = {
    name: et.asmr_dimension for name, et in CHINESE_ENTITY_TYPES.items()
}

# Mapping from Chinese type to Generic type
CHINESE_TO_GENERIC: Dict[str, str] = {
    name: et.generic_type for name, et in CHINESE_ENTITY_TYPES.items()
}

# Reverse mapping: Generic to Chinese types
GENERIC_TO_CHINESE: Dict[str, Set[str]] = {}
for chinese_name, et in CHINESE_ENTITY_TYPES.items():
    if et.generic_type not in GENERIC_TO_CHINESE:
        GENERIC_TO_CHINESE[et.generic_type] = set()
    GENERIC_TO_CHINESE[et.generic_type].add(chinese_name)

# Chinese Semantic Markers for Relation Detection
CHINESE_UPDATE_MARKERS = [
    "现在",
    "改",
    "换成",
    "不再",
    "已经",
    "更新",
    "原来是",
    "以前是",
    "之前在",
    "刚换",
]

CHINESE_EXTEND_MARKERS = [
    "而且",
    "另外",
    "还有",
    "同时",
    "顺便",
    "具体来说",
    "比如说",
    "特别是",
    "另外还有",
]

CHINESE_DERIVE_MARKERS = [
    "所以",
    "因此",
    "可以推断",
    "由此可见",
    "这说明",
    "这意味着",
    "因为",
    "由于",
]

# Chinese Contradiction Patterns
CHINESE_CONTRADICTION_PATTERNS = [
    # Occupation contradiction
    (r"在(.{1,20})公司工作", r"在(.{1,20})公司工作"),
    # Location contradiction
    (r"住在(.{1,10})", r"住在(.{1,10})"),
    # Status contradiction
    (r"是单身", r"结婚"),
    (r"结婚", r"离婚"),
    # Preference contradiction
    (r"喜欢(.{1,20})", r"不喜欢(.{1,20})"),
]


def get_chinese_type(name: str) -> ChineseEntityType | None:
    return CHINESE_ENTITY_TYPES.get(name)


def map_to_asmr_dimension(chinese_type: str) -> str:
    return CHINESE_TO_ASMR.get(chinese_type, "meta")


def map_to_generic_type(chinese_type: str) -> str:
    return CHINESE_TO_GENERIC.get(chinese_type, "unknown")


def get_chinese_types_for_generic(generic_type: str) -> Set[str]:
    return GENERIC_TO_CHINESE.get(generic_type, set())


def has_update_marker(text: str) -> bool:
    return any(marker in text for marker in CHINESE_UPDATE_MARKERS)


def has_extend_marker(text: str) -> bool:
    return any(marker in text for marker in CHINESE_EXTEND_MARKERS)


def has_derive_marker(text: str) -> bool:
    return any(marker in text for marker in CHINESE_DERIVE_MARKERS)
