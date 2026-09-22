"""
配置管理模块
"""

from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    """应用配置"""

    # 应用配置
    APP_NAME: str = "Memory Recall API"
    APP_VERSION: str = "5.2.3"
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

    # LLM 提供商：volcengine / deepseek / opencodex
    LLM_PROVIDER: str = "volcengine"

    # LLM 模型配置（支持动态切换）
    VOLC_LLM_MODEL_PRO: str = "doubao-seed-2-0-pro-260215"
    VOLC_LLM_MODEL_MINI: str = "doubao-seed-2-0-mini"
    VOLC_LLM_MODEL: str = "doubao-seed-2-0-pro-260215"  # 默认使用 pro 模型

    # DeepSeek LLM 配置（LLM_PROVIDER=deepseek 时生效）
    DEEPSEEK_API_KEY: Optional[str] = None
    DEEPSEEK_API_BASE: str = "https://api.deepseek.com"
    DEEPSEEK_LLM_MODEL: str = "deepseek-v4-flash"

    # OpenCodeX 代理 LLM 配置（LLM_PROVIDER=opencodex 时生效）
    # 聚合商模型 id 是斜杠形态（commandcode/deepseek/deepseek-v4.1-flash），
    # 与官方直连的 deepseek-v4-flash 不是同一命名空间。
    # base 默认写局域网 IP 而非 127.0.0.1：容器内 127.0.0.1 是容器自身，
    # 只有宿主直跑 uvicorn 时两者等价（opencodex 监听 0.0.0.0:10100）。
    OPENCODEX_API_KEY: Optional[str] = None
    OPENCODEX_API_BASE: str = "http://192.168.0.206:10100/v1"
    OPENCODEX_LLM_MODEL: str = "commandcode/deepseek/deepseek-v4.1-flash"

    VOLC_EMBEDDING_MODEL: str = "doubao-embedding-vision-251215"

    # 文件存储
    STORAGE_PATH: str = "/data/storage"

    # Function Calling 配置
    USE_FUNCTION_CALLING: bool = False  # 默认关闭，测试通过后开启

    # LLM 实体提取配置
    LLM_EXTRACTION_TIMEOUT: float = 60.0  # LLM提取超时时间（秒）
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
    BATCH_DETECTION_MAX_CANDIDATES: int = 5  # 批量检测最大候选数

    # 记忆合并配置
    MEMORY_MERGE_THRESHOLD: float = 0.95  # 记忆合并相似度阈值（显式写入）
    # 自动捕获来源（metadata._capture=true）去重阈值（2026-08-16 膨胀治理）：
    # 捕获蒸馏条目与容器已有记忆相似度 ≥ 此值时丢弃，拦截同日主题碎片化冗余。
    # 实测依据：同一主题的不同表述（如同一地址两条变体）embedding 相似度约 0.81，
    # 阈值 0.85 拦不住该形态，故取 0.80；捕获路径误丢代价低（对话在 session 事件流，
    # dropped 可审计），宁丢勿存
    CAPTURE_DEDUP_THRESHOLD: float = 0.80

    # 异步处理"卡住"判定阈值（分钟）：memories.metadata._status 停在 processing 且
    # created_at 早于该阈值即视为卡死（stats/overview 的 anomalies.processing_stuck）。
    # 依据：思考型模型下后台单条处理实测 13~25s，10 分钟足够区分"在跑"与"丢了"。
    STUCK_PROCESSING_MINUTES: int = 10

    # crystal 对账 worker 开关（默认关）。
    # 背景（2026-09-22 实测）：生产库**没有 crystal schema**（0 张表 / 0 migration_state），
    # 但 main.py 原先无条件启动该 worker ⇒ 每 5 秒一条
    # `relation "crystal.evidence_processing" does not exist` 的 ERROR，
    # 把真实错误淹在噪音里（排查时全程要 grep -v 过滤它）。
    # 而文档（STATUS「crystal M1」条）声称 08-18 已在正式库落地 crystal.* 七表，
    # 且 git/文档/记忆里都查不到回退记录 ⇒ 文档与实况不符，待定夺。
    # 要恢复 crystal：跑 `python init_crystal_db.py`（建表）后把本开关置 True；
    # 要正式退役：保持 False 并清理 /api/v2 路由与 web/crystal。
    ENABLE_CRYSTAL_WORKER: bool = False

    # Recall Trace 配置
    TRACE_ENABLED: bool = True  # 是否记录召回 Trace
    TRACE_SAMPLE_RATE: float = 1.0  # Trace 采样率 0~1（include_trace 请求不受采样影响）
    TRACE_RETENTION_DAYS: int = 7  # Trace 保留天数，由后台任务清理
    TRACE_CONTENT_MAX_LEN: int = 200  # Trace 中内容截断长度
    TRACE_FULL_CANDIDATE_RATE: float = 0.0  # 采样率 0~1：命中时记录阈值前候选（SQL 阈值降低+limit 放大），默认 0 关闭

    class Config:
        env_file = ".env"
        case_sensitive = True
        extra = "allow"  # 允许额外字段


# 全局配置实例
settings = Settings()
