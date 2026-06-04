import pytest


@pytest.fixture(autouse=True)
async def close_shared_db_engines_after_test():
    yield

    from app.db.session import close_db_engine

    await close_db_engine()
