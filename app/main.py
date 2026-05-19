from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from app.api.ingestion_routes import router as ingestion_router
from app.api.llm_routes import router as llm_router
from app.api.platform_routes import platform_router
from app.api.routes import router
from app.db.session import close_db_engine


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    yield
    await close_db_engine()


app = FastAPI(
    title="NETRA Data Quality Platform",
    version="1.0.0",
    description=(
        "NETRA data quality platform with validation rules, ingestion, "
        "LLM-assisted rule drafts, notifications, and Platform Intelligence orchestration."
    ),
    lifespan=lifespan,
    docs_url=None,
    redoc_url=None,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory="app/static"), name="static")

app.include_router(router)
app.include_router(ingestion_router)
app.include_router(llm_router)
app.include_router(platform_router)


@app.get("/docs", include_in_schema=False)
async def custom_swagger_ui_html() -> HTMLResponse:
    html = """
    <!DOCTYPE html>
    <html>
    <head>
    <title>NETRA - Swagger UI</title>
    <link href="https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui.css" rel="stylesheet">
    <style>
        body { background-color: #020617; margin: 0; padding: 0; font-family: sans-serif; }
        .swagger-ui { filter: invert(88%) hue-rotate(180deg); }
        .swagger-ui .wrapper { max-width: 1200px; margin: 0 auto; padding: 20px; }
        .topbar { display: none; }
        .netra-header { background: #0f172a; padding: 1rem 2rem; display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid #1e293b; }
        .netra-header h1 { margin: 0; color: #f8fafc; font-size: 1.5rem; font-weight: bold; display: flex; align-items: center; gap: 15px; }
        .netra-header img { height: 32px; filter: drop-shadow(0 0 5px rgba(34, 211, 238, 0.4)); }
        .netra-header a { color: #0ea5e9; text-decoration: none; font-weight: bold; border: 1px solid #0ea5e9; padding: 0.5rem 1rem; border-radius: 0.5rem; transition: all 0.2s; }
        .netra-header a:hover { background: #0ea5e9; color: white; }
    </style>
    </head>
    <body>
    <div class="netra-header">
        <h1><img src="/logo.png" alt="NETRA Logo"> NETRA - API Docs</h1>
        <a href="/ui">&larr; Back to Portal</a>
    </div>
    <div id="swagger-ui"></div>
    <script src="https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui-bundle.js"></script>
    <script>
    window.onload = () => {
        window.ui = SwaggerUIBundle({
            url: '/openapi.json',
            dom_id: '#swagger-ui',
            presets: [SwaggerUIBundle.presets.apis, SwaggerUIBundle.SwaggerUIStandalonePreset],
            layout: "BaseLayout",
            deepLinking: true
        });
    };
    </script>
    </body>
    </html>
    """
    return HTMLResponse(html)


@app.get("/redoc", include_in_schema=False)
async def redoc_html() -> HTMLResponse:
    html = """
    <!DOCTYPE html>
    <html>
    <head>
    <title>NETRA - ReDoc</title>
    <style>
        body { margin: 0; padding: 0; background-color: #020617; font-family: sans-serif; }
        .netra-header { background: #0f172a; padding: 1rem 2rem; display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid #1e293b; }
        .netra-header h1 { margin: 0; color: #f8fafc; font-size: 1.5rem; font-weight: bold; display: flex; align-items: center; gap: 15px; }
        .netra-header img { height: 32px; filter: drop-shadow(0 0 5px rgba(34, 211, 238, 0.4)); }
        .netra-header a { color: #0ea5e9; text-decoration: none; font-weight: bold; border: 1px solid #0ea5e9; padding: 0.5rem 1rem; border-radius: 0.5rem; transition: all 0.2s; }
        .netra-header a:hover { background: #0ea5e9; color: white; }
        .redoc-container { background-color: #ffffff; padding: 20px; border-radius: 8px; margin: 20px; }
    </style>
    </head>
    <body>
    <div class="netra-header">
        <h1><img src="/logo.png" alt="NETRA Logo"> NETRA - ReDoc</h1>
        <a href="/ui">&larr; Back to Portal</a>
    </div>
    <div class="redoc-container">
        <redoc spec-url="/openapi.json"></redoc>
    </div>
    <script src="https://cdn.jsdelivr.net/npm/redoc@next/bundles/redoc.standalone.js"></script>
    </body>
    </html>
    """
    return HTMLResponse(html)


@app.get("/health", tags=["system"])
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/", include_in_schema=False)
async def root() -> RedirectResponse:
    """Redirect root to the bundled ingestion portal."""
    return RedirectResponse(url="/ui")


@app.get("/ui", include_in_schema=False)
async def serve_ui() -> FileResponse:
    """Serve the basic frontend UI for CSV ingestion."""
    return FileResponse("frontend/index.html")


@app.get("/logo.png", include_in_schema=False)
async def serve_logo() -> FileResponse:
    """Serve the NETRA platform logo."""
    return FileResponse("frontend/logo.png")
