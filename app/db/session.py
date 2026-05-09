from sqlalchemy.ext.asyncio import create_async_engine

from app.settings import get_settings

settings = get_settings()


def _create_engine(database_url: str):
    return create_async_engine(
        database_url,
        pool_size=settings.pool_size,
        max_overflow=settings.max_overflow,
        pool_timeout=settings.pool_timeout,
        pool_recycle=settings.pool_recycle,
        pool_pre_ping=True,
    )


executor_engine = _create_engine(settings.database_url)
metadata_engine = _create_engine(settings.metadata_database_url)

# Backward-compatible alias used by the executor tests and Milestone 1 code.
engine = executor_engine


async def close_db_engine() -> None:
    await executor_engine.dispose()
    await metadata_engine.dispose()
