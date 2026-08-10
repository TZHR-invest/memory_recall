"""
配置管理模块
"""

from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    """应用配置"""

    # 应用配置
    APP_NAME: str = "Memory Recall API"
    APP_VERSION: str = "5.0.0"
    APP_ENV: str = "development"
    APP_DEBUG: bool = True
    LOG_LEVEL: str = "INFO"

    # 数据库配置
    DATABASE_URL: str = "postgresql://postgres:password@localhost:5432/memory_recall"
    DATABASE_HOST: str = "localhost"
    DATABASE_PORT: int = 5432
    DATABASE_NAME: str = "memory_recall"
    DATABASE_USER: str = "postgres"
    DATABASE_PASSWORD: str = "password"

    # 火山引擎 API 配置
    VOLC_API_KEY: Optional[str] = None
    VOLC_API_BASE: str = "https://ark.cn-beijing.volces.com/api/v3"

    # LLM 提供商：volcengine 或 deepseek
    LLM_PROVIDER: str = "volcengine"

    # LLM 模型配置（支持动态切换）
    VOLC_LLM_MODEL_PRO: str = "doubao-seed-2-0-pro-260215"
    VOLC_LLM_MODEL_MINI: str = "doubao-seed-2-0-mini"
    VOLC_LLM_MODEL: str = "doubao-seed-2-0-pro-260215"  # 默认使用 pro 模型

    # DeepSeek LLM 配置（LLM_PROVIDER=deepseek 时生效）
    DEEPSEEK_API_KEY: Optional[str] = None
    DEEPSEEK_API_BASE: str = "https://api.deepseek.com"
    DEEPSEEK_LLM_MODEL: str = "deepseek-v4-flash"

    VOLC_EMBEDDING_MODEL: str = "doubao-embedding-vision-251215"

    # 文件存储
    STORAGE_PATH: str = "/data/storage"

    # Function Calling 配置
    USE_FUNCTION_CALLING: bool = False  # 默认关闭，测试通过后开启

    # LLM 实体提取配置
    LLM_EXTRACTION_TIMEOUT: float = 300.0  # LLM提取超时时间（秒）
    USE_LLM_EXTRACTION: bool = True  # 默认使用LLM提取
    USE_LAC_EXTRACTOR: bool = False  # LAC提取器（可选）
    USE_DEFAULT_ENTITY_CONTEXT: bool = True  # 默认使用entity_context自动注入

    # Entity Graph 配置
    ENABLE_ENTITY_EXTRACTION: bool = True  # 启用实体提取
    ENABLE_ENTITY_RELATION_EXTRACTION: bool = True  # 启用实体关系提取
    ENTITY_EXTRACTION_CONFIDENCE_THRESHOLD: float = 0.7  # 实体提取置信度阈值

    # 实体过滤配置
    ENTITY_FILTER_MIN_LENGTH: int = 2  # 实体最小长度
    ENTITY_FILTER_MAX_LENGTH: int = 20  # 实体最大长度
    ENTITY_FILTER_SKIP_FILE_PATHS: bool = True  # 跳过文件路径格式
    ENTITY_FILTER_SKIP_NUMERIC: bool = True  # 跳过纯数值

    @property
    def ENTITY_FILTER_CONFIG(self) -> dict:
        return {
            "min_length": self.ENTITY_FILTER_MIN_LENGTH,
            "max_length": self.ENTITY_FILTER_MAX_LENGTH,
            "skip_file_paths": self.ENTITY_FILTER_SKIP_FILE_PATHS,
            "skip_numeric": self.ENTITY_FILTER_SKIP_NUMERIC,
        }

    # 批量关系检测配置
    USE_BATCH_RELATION_DETECTION: bool = True  # 默认使用批量关系检测
    BATCH_DETECTION_MAX_CANDIDATES: int = 10  # 批量检测最大候选数

    # 记忆合并配置
    MEMORY_MERGE_THRESHOLD: float = 0.95  # 记忆合并相似度阈值

    # Recall Trace 配置
    TRACE_ENABLED: bool = True  # 是否记录召回 Trace
    TRACE_SAMPLE_RATE: float = 1.0  # Trace 采样率 0~1（include_trace 请求不受采样影响）
    TRACE_RETENTION_DAYS: int = 7  # Trace 保留天数，由后台任务清理
    TRACE_CONTENT_MAX_LEN: int = 200  # Trace 中内容截断长度

    class Config:
        env_file = ".env"
        case_sensitive = True
        extra = "allow"  # 允许额外字段


# 全局配置实例
settings = Settings()
