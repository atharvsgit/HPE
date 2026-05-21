from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.platform_routes import platform_router
from app.api.routes import router
from app.api.ai_rules_routes import ai_rules_router
from app.db.session import close_db_engine


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    yield
    await close_db_engine()


app = FastAPI(
    title="Data Quality Daemon",
    version="0.3.0",
    description=(
        "Data Quality Daemon with rule management, scheduling, notifications, "
        "and platform intelligence endpoints."
    ),
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:5174",
        "http://127.0.0.1:5174",
        "http://localhost:5175",
        "http://127.0.0.1:5175",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)
app.include_router(platform_router)
app.include_router(ai_rules_router)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
