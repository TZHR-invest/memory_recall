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

    # LLM 模型配置（支持动态切换）
    VOLC_LLM_MODEL_PRO: str = "doubao-seed-2-0-pro-260215"
    VOLC_LLM_MODEL_MINI: str = "doubao-seed-2-0-mini"
    VOLC_LLM_MODEL: str = "doubao-seed-2-0-pro-260215"  # 默认使用 pro 模型

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

    # 批量关系检测配置
    USE_BATCH_RELATION_DETECTION: bool = True  # 默认使用批量关系检测
    BATCH_DETECTION_MAX_CANDIDATES: int = 10  # 批量检测最大候选数

    # 记忆合并配置
    MEMORY_MERGE_THRESHOLD: float = 0.95  # 记忆合并相似度阈值

    # 实体字典配置
    USE_ENTITY_DICT: bool = True  # 启用实体字典
    ENTITY_DICT_LAZY_LOAD: bool = True  # 懒加载
    ENTITY_DICT_MAX_CONTAINERS: int = 1000  # 最大缓存容器数

    class Config:
        env_file = ".env"
        case_sensitive = True
        extra = "allow"  # 允许额外字段


# 全局配置实例
settings = Settings()
