"""
配置管理模块
"""
from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    """应用配置"""
    
    # 应用配置
    APP_NAME: str = "Memory Recall API"
    APP_VERSION: str = "0.1.0"
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
    VOLC_LLM_MODEL: str = "doubao-seed-2-0-pro-260215"
    VOLC_EMBEDDING_MODEL: str = "doubao-embedding-vision-251215"
    
    # 文件存储
    STORAGE_PATH: str = "/data/storage"
    
    class Config:
        env_file = ".env"
        case_sensitive = True


# 全局配置实例
settings = Settings()
