from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from app.api.routes import router
from app.api.llm_routes import router as llm_router
from app.db.session import close_db_engine


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    yield
    await close_db_engine()


app = FastAPI(
    title="Netra",
    description="**Netra** — Intelligent Data Quality Platform with LLM-assisted rule drafting and human-in-the-loop approval.",
    version="1.0.0",
    lifespan=lifespan,
    docs_url=None,   # disable default docs so we can serve custom ones
    redoc_url=None,
)

# Serve static files (logo, etc.)
app.mount("/static", StaticFiles(directory="app/static"), name="static")

app.include_router(router)
app.include_router(llm_router)


@app.get("/", include_in_schema=False)
async def root():
    return RedirectResponse(url="/docs")


@app.get("/docs", include_in_schema=False)
async def custom_swagger_ui() -> HTMLResponse:
    html = get_swagger_ui_html(
        openapi_url="/openapi.json",
        title="Netra — Data Quality Platform",
        swagger_favicon_url="/static/logo.png",
        swagger_ui_parameters={"defaultModelsExpandDepth": -1},
        swagger_js_url="https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui-bundle.js",
        swagger_css_url="https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui.css",
    )
    custom_css = """
    <style>
    .swagger-ui .topbar { display: none !important; }
    .swagger-ui .info a[href*="openapi.json"] { display: none !important; }
    .swagger-ui a.link { display: none !important; } /* catches the link if it has a class */
    .swagger-ui .info { margin-top: 30px; }
    .swagger-ui .info .title { 
        display: flex !important; 
        align-items: center; 
        gap: 15px; 
        margin: 0 !important;
    }
    .swagger-ui .info .title::before {
        content: '';
        display: inline-block;
        width: 100px;
        height: 70px;
        background-image: url('/static/logo.png');
        background-size: contain;
        background-repeat: no-repeat;
        background-position: center;
    }
    </style>
    """
    body = html.body.decode("utf-8")
    return HTMLResponse(body.replace("</head>", custom_css + "</head>"))


@app.get("/health", tags=["system"])
async def health() -> dict[str, str]:
    return {"status": "ok"}
