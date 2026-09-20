import os
from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from app.database.models.base import Base

def get_database_url() -> str:
    url = os.getenv("DATABASE_URL", "postgresql+psycopg://postgres:postgres@localhost:5432/telegram_ai_bot")
    # Convert standard postgresql:// to postgresql+psycopg:// if needed
    if url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+psycopg://", 1)
    elif url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql+psycopg://", 1)
    return url

DATABASE_URL = get_database_url()

# Disable pool for sqlite memory/file during testing
is_sqlite = DATABASE_URL.startswith("sqlite")
engine_kwargs = {} if is_sqlite else {"pool_size": 10, "max_overflow": 20, "pool_pre_ping": True}

async_engine = create_async_engine(DATABASE_URL, echo=False, **engine_kwargs)

AsyncSessionLocal = async_sessionmaker(
    bind=async_engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False
)

async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()

async def init_db():
    async with async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
