from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.platform_routes import platform_router
from app.api.routes import router
from app.db.session import close_db_engine


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    yield
    await close_db_engine()


app = FastAPI(
    title="Data Quality Daemon",
    version="0.3.0",
    description=(
        "Data Quality Daemon with rule management (Atharv) "
        "and Platform Intelligence orchestration (Manjunath)."
    ),
    lifespan=lifespan,
)

# Atharv's rule management routes
app.include_router(router)

# Manjunath's platform intelligence routes (prefix: /platform)
app.include_router(platform_router)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
