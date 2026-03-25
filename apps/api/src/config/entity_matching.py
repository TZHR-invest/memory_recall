"""
实体匹配配置
管理实体提取策略的配置
"""


class EntityMatchingConfig:
    """实体匹配配置"""

    # 匹配模式
    MODE_EXACT = "exact"  # 仅精确匹配
    MODE_KEYWORD = "keyword"  # 精确 + 关键词匹配
    MODE_ENHANCED = "enhanced"  # 精确 + 关键词 + 模糊匹配
    MODE_FULL = "full"  # 精确 + 关键词 + 模糊 + 语义匹配
    MODE_AUTO = "auto"  # 自动选择

    # 阈值配置
    FUZZY_THRESHOLD = 0.6  # 模糊匹配相似度阈值
    SEMANTIC_THRESHOLD = 0.75  # 语义匹配相似度阈值
    KEYWORD_OVERLAP_MIN = 2  # 最小关键词重叠数
    KEYWORD_OVERLAP_RATIO = 0.5  # 最小关键词重叠率

    # 性能配置
    MAX_ENTITIES_PER_QUERY = 20  # 每次查询最多返回的实体数
    CACHE_ENABLED = True  # 是否启用缓存
    CACHE_TTL = 3600  # 缓存过期时间（秒）

    # 默认模式
    DEFAULT_MODE = "keyword"  # 默认使用关键词匹配

    # 监控配置
    MONITORING_ENABLED = True  # 是否启用监控
    LOG_SLOW_QUERIES = True  # 是否记录慢查询
    SLOW_QUERY_THRESHOLD = 100  # 慢查询阈值（ms）


# 实体类型配置
ENTITY_TYPES = {
    "person": {
        "name": "人物",
        "priority": 1,  # 提取优先级
        "min_length": 2,
        "max_length": 10,
    },
    "location": {"name": "地点", "priority": 2, "min_length": 2, "max_length": 20},
    "event": {"name": "事件", "priority": 3, "min_length": 2, "max_length": 30},
    "topic": {"name": "主题", "priority": 4, "min_length": 2, "max_length": 30},
}


# 关系类型配置
RELATION_TYPES = {
    # 人物关系
    "friend": {
        "name": "朋友",
        "source_types": ["person"],
        "target_types": ["person"],
        "weight": 0.9,
    },
    "colleague": {
        "name": "同事",
        "source_types": ["person"],
        "target_types": ["person"],
        "weight": 0.8,
    },
    # 地点关系
    "at": {
        "name": "在...",
        "source_types": ["person"],
        "target_types": ["location"],
        "weight": 0.95,
    },
    "met_at": {
        "name": "在...遇到",
        "source_types": ["person"],
        "target_types": ["location"],
        "weight": 0.9,
    },
    # 归一化关系
    "same_as": {
        "name": "同义",
        "source_types": ["*"],
        "target_types": ["*"],
        "weight": 1.0,
    },
    "is_a": {
        "name": "属于",
        "source_types": ["*"],
        "target_types": ["*"],
        "weight": 0.9,
    },
}


# 停用词配置
STOPWORDS = {
    # 中文停用词
    "的",
    "了",
    "在",
    "是",
    "我",
    "有",
    "和",
    "就",
    "不",
    "人",
    "都",
    "一",
    "一个",
    "上",
    "也",
    "很",
    "到",
    "说",
    "要",
    "去",
    "你",
    "会",
    "什么",
    "怎么",
    "为什么",
    "哪",
    "哪个",
    "哪些",
    "这个",
    "那个",
    # 英文停用词
    "the",
    "a",
    "an",
    "is",
    "are",
    "was",
    "were",
    "be",
    "been",
    "being",
    "have",
    "has",
    "had",
    "do",
    "does",
    "did",
    "will",
    "would",
    "could",
    "should",
    "may",
    "might",
    "must",
    "can",
    "to",
    "of",
    "in",
    "for",
    "on",
    "with",
    "at",
    "by",
    "from",
    "as",
    "into",
    "through",
    "during",
}


# 性能基准
PERFORMANCE_BENCHMARKS = {
    "exact": {"expected_time_ms": 1, "max_time_ms": 5},
    "keyword": {"expected_time_ms": 10, "max_time_ms": 50},
    "fuzzy": {"expected_time_ms": 50, "max_time_ms": 200},
    "semantic": {"expected_time_ms": 200, "max_time_ms": 1000},
}


def get_config():
    """获取配置"""
    return EntityMatchingConfig


def get_entity_types():
    """获取实体类型配置"""
    return ENTITY_TYPES


def get_relation_types():
    """获取关系类型配置"""
    return RELATION_TYPES


def get_stopwords():
    """获取停用词列表"""
    return STOPWORDS
