"""
应用配置管理 — Pydantic Settings

从环境变量 / .env 文件读取所有配置项
"""

from pathlib import Path
from pydantic_settings import BaseSettings
from functools import lru_cache

# .env 文件绝对路径 — 确保无论从哪个目录启动都能正确加载
_ENV_FILE = str(Path(__file__).resolve().parent.parent / ".env")


class LLMSettings(BaseSettings):
    """DeepSeek LLM 配置"""
    DEEPSEEK_API_KEY: str = "sk-xxx"
    DEEPSEEK_BASE_URL: str = "https://api.deepseek.com/v1"
    DEEPSEEK_MODEL: str = "deepseek-chat"

    model_config = {"env_file": _ENV_FILE, "extra": "ignore"}


class EmbeddingSettings(BaseSettings):
    """BGE Embedding 配置"""
    EMBEDDING_MODEL: str = "BAAI/bge-large-zh-v1.5"
    EMBEDDING_DEVICE: str = "cpu"

    model_config = {"env_file": _ENV_FILE, "extra": "ignore"}


class RerankerSettings(BaseSettings):
    """BGE Reranker 配置"""
    RERANKER_MODEL: str = "BAAI/bge-reranker-v2-m3"

    model_config = {"env_file": _ENV_FILE, "extra": "ignore"}


class OpenSearchSettings(BaseSettings):
    """OpenSearch 配置"""
    OS_HOST: str = "http://opensearch:9200"
    OS_INDEX: str = "news_articles"

    model_config = {"env_file": _ENV_FILE, "extra": "ignore"}


class RedisSettings(BaseSettings):
    """Redis 配置"""
    REDIS_URL: str = "redis://redis:6379/0"

    model_config = {"env_file": _ENV_FILE, "extra": "ignore"}


class MySQLSettings(BaseSettings):
    """数据库配置 — 支持 MySQL 和 SQLite"""
    DATABASE_URL: str = ""  # 设置此项可覆盖下面的 MySQL 配置
    MYSQL_HOST: str = "mysql"
    MYSQL_PORT: int = 3306
    MYSQL_USER: str = "zhilan"
    MYSQL_PASSWORD: str = "zhilan_secret"
    MYSQL_DATABASE: str = "zhilan"

    @property
    def database_url(self) -> str:
        if self.DATABASE_URL:
            return self.DATABASE_URL
        return (
            f"mysql+pymysql://{self.MYSQL_USER}:{self.MYSQL_PASSWORD}"
            f"@{self.MYSQL_HOST}:{self.MYSQL_PORT}/{self.MYSQL_DATABASE}"
        )

    model_config = {"env_file": _ENV_FILE, "extra": "ignore"}


class CollectorSettings(BaseSettings):
    """数据采集配置"""
    NEWSAPI_KEY: str = "xxx"
    COLLECTION_INTERVAL_HOURS: int = 2
    BRIEF_GENERATION_TIME: str = "08:00"

    model_config = {"env_file": _ENV_FILE, "extra": "ignore"}


class AppSettings(BaseSettings):
    """应用全局配置"""
    APP_ENV: str = "development"
    LOG_LEVEL: str = "INFO"
    DEBUG: bool = True
    SECRET_KEY: str = "dev-secret-key-change-in-production"
    RESEARCH_MAX_CLUSTERS: int = 3  # 每次研报生成的簇数量上限

    model_config = {"env_file": _ENV_FILE, "extra": "ignore"}


class Settings:
    """聚合所有配置"""

    def __init__(self):
        self.llm = LLMSettings()
        self.embedding = EmbeddingSettings()
        self.reranker = RerankerSettings()
        self.os = OpenSearchSettings()
        self.redis = RedisSettings()
        self.mysql = MySQLSettings()
        self.collector = CollectorSettings()
        self.app = AppSettings()


@lru_cache()
def get_settings() -> Settings:
    """获取配置单例（带缓存）"""
    return Settings()
