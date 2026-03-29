"""
ASMR 6-Dimension Entity Type Definitions.

Based on Supermemory's ASMR architecture for comprehensive knowledge extraction.
ASMR dimensions provide a structured way to categorize entities and facts.

Reference: https://supermemory.ai/blog/we-broke-the-frontier-in-agent-memory-introducing-99-sota-memory-system/
"""

from enum import Enum
from typing import Dict, List, Set, Optional
from dataclasses import dataclass, field


class ASMRDimension(Enum):
    """ASMR 6 Dimensions for entity classification."""

    PERSON = "person"
    """人物实体: 姓名、身份、角色、关系
    Examples: 张三是产品经理、李四向王五汇报
    """

    THING_CONCEPT = "thing_concept"
    """事物/概念实体: 项目、文档、组织、地点、产品、技术术语
    Examples: Alpha项目、北京总部、React框架
    """

    EVENT = "event"
    """事件实体: 会议、任务、活动、时间线节点
    Examples: 周一项目评审会、Q1销售目标
    """

    ATTRIBUTE_FACT = "attribute_fact"
    """属性/事实: 偏好、状态、规则、数值、时间戳
    Examples: 喜欢暗黑模式、项目状态=进行中
    """

    RELATION = "relation"
    """关系: Updates/Extends/Derives
    Examples: 信息更新、信息扩展、信息推断
    """

    META = "meta"
    """元数据: 来源、置信度、提取时间
    Examples: source=chat, confidence=0.9
    """


class RelationType(Enum):
    """Memory relation types for knowledge graph edges."""

    UPDATES = "updates"
    """信息更新: 新信息取代旧知识"""

    EXTENDS = "extends"
    """信息扩展: 丰富/补充现有信息"""

    DERIVES = "derives"
    """信息推断: 从模式推断新连接"""


@dataclass
class ASMREntityType:
    """Definition of an ASMR entity type."""

    dimension: ASMRDimension
    name: str
    description: str
    examples: List[str] = field(default_factory=list)
    patterns: List[str] = field(default_factory=list)
    sub_types: List[str] = field(default_factory=list)


# ASMR Entity Type Definitions
ASMR_ENTITY_TYPES: Dict[str, ASMREntityType] = {
    # Person Dimension
    "person_name": ASMREntityType(
        dimension=ASMRDimension.PERSON,
        name="person_name",
        description="人名",
        examples=["张三", "李四", "王五"],
        patterns=[
            r"我叫(.{1,10})",
            r"姓名是(.{1,10})",
            r"(.{1,10})说",
        ],
    ),
    "person_role": ASMREntityType(
        dimension=ASMRDimension.PERSON,
        name="person_role",
        description="角色/身份",
        examples=["产品经理", "工程师", "CEO"],
        patterns=[
            r"(.{1,10})是(.{1,10})(经理|工程师|总监|CEO)",
            r"担任(.{1,10})",
        ],
        sub_types=["职业", "职位", "头衔"],
    ),
    "person_relation": ASMREntityType(
        dimension=ASMRDimension.PERSON,
        name="person_relation",
        description="人物关系",
        examples=["妻子", "儿子", "父母", "同事"],
        patterns=[
            r"我的(.{1,10})(妻子|儿子|女儿|父母|同事)",
            r"和(.{1,10})是(.{1,10})关系",
        ],
        sub_types=["家庭关系", "工作关系", "社交关系"],
    ),
    # Thing/Concept Dimension
    "project": ASMREntityType(
        dimension=ASMRDimension.THING_CONCEPT,
        name="project",
        description="项目",
        examples=["Alpha项目", "认证迁移", "速率限制"],
        patterns=[
            r"(.{1,20})项目",
            r"在(.{1,20})项目",
        ],
    ),
    "organization": ASMREntityType(
        dimension=ASMRDimension.THING_CONCEPT,
        name="organization",
        description="组织/公司",
        examples=["字节跳动", "腾讯", "阿里巴巴"],
        patterns=[
            r"在(.{1,20})(公司|集团|企业)",
            r"(.{1,20})(公司|集团|企业)",
        ],
    ),
    "location": ASMREntityType(
        dimension=ASMRDimension.THING_CONCEPT,
        name="location",
        description="地点",
        examples=["北京", "上海", "深圳"],
        patterns=[
            r"在(.{1,10})(工作|居住|生活)",
            r"住在(.{1,10})",
            r"来自(.{1,10})",
        ],
    ),
    "technology": ASMREntityType(
        dimension=ASMRDimension.THING_CONCEPT,
        name="technology",
        description="技术/框架",
        examples=["React", "Python", "PostgreSQL"],
        patterns=[
            r"使用(.{1,20})(框架|技术|语言)",
            r"用(.{1,20})开发",
        ],
    ),
    # Event Dimension
    "meeting": ASMREntityType(
        dimension=ASMRDimension.EVENT,
        name="meeting",
        description="会议",
        examples=["项目评审会", "周会", "季度总结"],
        patterns=[
            r"(.{1,20})会议",
            r"参加(.{1,20})会",
        ],
    ),
    "task": ASMREntityType(
        dimension=ASMRDimension.EVENT,
        name="task",
        description="任务",
        examples=["完成登录功能", "修复Bug", "写文档"],
        patterns=[
            r"(.{1,30})任务",
            r"需要(.{1,30})",
            r"正在(.{1,30})",
        ],
    ),
    "activity": ASMREntityType(
        dimension=ASMRDimension.EVENT,
        name="activity",
        description="活动",
        examples=["团建", "培训", "面试"],
        patterns=[
            r"参加(.{1,20})活动",
            r"组织(.{1,20})",
        ],
    ),
    # Attribute/Fact Dimension
    "preference": ASMREntityType(
        dimension=ASMRDimension.ATTRIBUTE_FACT,
        name="preference",
        description="偏好",
        examples=["喜欢暗黑模式", "不吃辣", "偏好Python"],
        patterns=[
            r"(喜欢|偏好|偏爱)(.{1,20})",
            r"(不喜欢|讨厌)(.{1,20})",
        ],
    ),
    "skill": ASMREntityType(
        dimension=ASMRDimension.ATTRIBUTE_FACT,
        name="skill",
        description="技能",
        examples=["Python", "驾驶", "钢琴"],
        patterns=[
            r"会(.{1,20})",
            r"精通(.{1,20})",
            r"擅长(.{1,20})",
        ],
    ),
    "status": ASMREntityType(
        dimension=ASMRDimension.ATTRIBUTE_FACT,
        name="status",
        description="状态",
        examples=["进行中", "已完成", "待处理"],
        patterns=[
            r"状态(是|为)(.{1,10})",
            r"(.{1,10})(完成|进行中|待处理)",
        ],
    ),
    "education": ASMREntityType(
        dimension=ASMRDimension.ATTRIBUTE_FACT,
        name="education",
        description="学历",
        examples=["本科", "硕士", "博士"],
        patterns=[
            r"(本科|硕士|博士|MBA)学位",
            r"毕业于(.{1,30})",
        ],
    ),
    # Meta Dimension
    "source": ASMREntityType(
        dimension=ASMRDimension.META,
        name="source",
        description="来源",
        examples=["chat", "email", "document"],
    ),
    "confidence": ASMREntityType(
        dimension=ASMRDimension.META,
        name="confidence",
        description="置信度",
        examples=["0.9", "高", "中"],
    ),
}

# Dimension to Entity Types mapping
DIMENSION_ENTITY_MAP: Dict[ASMRDimension, Set[str]] = {
    ASMRDimension.PERSON: {"person_name", "person_role", "person_relation"},
    ASMRDimension.THING_CONCEPT: {"project", "organization", "location", "technology"},
    ASMRDimension.EVENT: {"meeting", "task", "activity"},
    ASMRDimension.ATTRIBUTE_FACT: {"preference", "skill", "status", "education"},
    ASMRDimension.RELATION: set(),  # Relations are stored separately
    ASMRDimension.META: {"source", "confidence"},
}

# Chinese Static Indicators (永久特征)
CHINESE_STATIC_INDICATORS = [
    "是",
    "叫",
    "姓",
    "职业是",
    "工作是",
    "职位是",
    "喜欢",
    "不喜欢",
    "偏好",
    "过敏",
    "信仰",
    "学历是",
    "毕业",
    "专业是",
    "技能是",
    "擅长",
]

# Chinese Dynamic Indicators (临时活动)
CHINESE_DYNAMIC_INDICATORS = [
    "今天",
    "昨天",
    "明天",
    "本周",
    "上周",
    "下周",
    "正在",
    "最近",
    "目前",
    "暂时",
    "现在",
    "计划",
    "准备",
    "打算",
]


def get_entity_type_by_name(name: str) -> Optional[ASMREntityType]:
    """Get ASMR entity type definition by name."""
    return ASMR_ENTITY_TYPES.get(name)


def get_entities_by_dimension(dimension: ASMRDimension) -> Set[str]:
    """Get all entity types for a given ASMR dimension."""
    return DIMENSION_ENTITY_MAP.get(dimension, set())


def is_static_indicator(text: str) -> bool:
    """Check if text contains static fact indicators."""
    text_lower = text.lower()
    return any(indicator in text_lower for indicator in CHINESE_STATIC_INDICATORS)


def is_dynamic_indicator(text: str) -> bool:
    """Check if text contains dynamic fact indicators."""
    text_lower = text.lower()
    return any(indicator in text_lower for indicator in CHINESE_DYNAMIC_INDICATORS)


def detect_is_static(content: str) -> bool:
    """
    Detect if content represents a static (permanent) fact.

    Returns True if content appears to be a permanent trait,
    False if it appears to be a temporary activity.
    """
    has_static = is_static_indicator(content)
    has_dynamic = is_dynamic_indicator(content)

    # If only static indicators, it's static
    if has_static and not has_dynamic:
        return True

    # If only dynamic indicators, it's dynamic
    if has_dynamic and not has_static:
        return False

    # If both or neither, default to dynamic (safer assumption)
    return has_static and not has_dynamic
