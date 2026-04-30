from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import get_settings

_settings = get_settings()

# statement_cache_size=0 lets the same engine work against Supabase Supavisor
# pooler in either session or transaction mode without surprises.
engine = create_async_engine(
    _settings.DATABASE_URL,
    pool_pre_ping=True,
    connect_args={"statement_cache_size": 0},
)

SessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


async def get_db() -> AsyncIterator[AsyncSession]:
    async with SessionLocal() as session:
        yield session
