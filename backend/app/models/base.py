"""
SQLAlchemy 数据库连接管理

支持 MySQL 和 SQLite，根据 database_url 自动适配
"""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase

from app.config import get_settings

settings = get_settings()
db_url = settings.mysql.database_url

# SQLite 不支持连接池参数，需区分处理
if "sqlite" in db_url:
    engine = create_engine(
        db_url,
        connect_args={"check_same_thread": False},
        echo=settings.app.DEBUG,
    )
else:
    engine = create_engine(
        db_url,
        pool_size=10,
        max_overflow=20,
        pool_pre_ping=True,
        echo=settings.app.DEBUG,
    )

# ---------- 会话工厂 ----------
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    """SQLAlchemy 声明式基类 — 所有模型继承此类"""
    pass


def get_db():
    """FastAPI 依赖注入：获取数据库会话"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
