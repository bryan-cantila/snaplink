"""SnapLink API — a hand-built URL shortener.

Created by devuvo (https://www.devuvo.com).
Design: Cyberpunk / HUD · Palette: Prompt Blue #0B132B + AI Green #39FF88
"""
from fastapi import FastAPI
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.responses import HTMLResponse
from sqlalchemy import text

from . import cache
from .config import settings
from .db import engine
from .ratelimit import limiter
from .routers import auth as auth_router
from .routers import links as links_router
from .routers import redirect as redirect_router
from .schemas import HealthOut

# --- Cyberpunk / HUD docs theme (Prompt Blue + AI Green) -------------------
# Injected into the Swagger UI page. Style: Cyberpunk / HUD.
# Palette: #11 Prompt Blue 0B132B + AI Green 39FF88.
DOCS_CSS = """<style>
body, .swagger-ui { background: #0B132B !important; }
.swagger-ui .topbar { background: #0B132B !important; border-bottom: 2px solid #39FF88; }
.swagger-ui .topbar .download-url-wrapper .select-label { color: #39FF88 !important; }
.swagger-ui .info .title, .swagger-ui .info h1, .swagger-ui .info h2,
.swagger-ui .info h3, .swagger-ui .info h4 { color: #39FF88 !important; font-family: ui-monospace, monospace; }
.swagger-ui .info .description, .swagger-ui .info p, .swagger-ui .info li { color: #c9d4e8 !important; }
.swagger-ui .info a { color: #39FF88 !important; }
.swagger-ui .scheme-container { background: #0B132B !important; box-shadow: 0 0 0 1px #39FF88; }
.swagger-ui .btn.authorize { background: transparent !important; color: #39FF88 !important; border: 1px solid #39FF88 !important; }
.swagger-ui .btn.authorize svg { fill: #39FF88 !important; }
.swagger-ui .opblock-tag { color: #39FF88 !important; font-family: ui-monospace, monospace; }
.swagger-ui .opblock { background: rgba(57,255,136,0.04) !important; border-color: #39FF88 !important; }
.swagger-ui .opblock .opblock-summary-method { font-family: ui-monospace, monospace; }
.swagger-ui .opblock .opblock-summary-path, .swagger-ui .opblock .opblock-summary-description { color: #e6edf7 !important; }
.swagger-ui table thead tr td, .swagger-ui table thead tr th { color: #39FF88 !important; }
.swagger-ui .parameter__name, .swagger-ui .parameter__type { color: #c9d4e8 !important; }
.swagger-ui input, .swagger-ui select, .swagger-ui textarea { background: #060b1a !important; color: #e6edf7 !important; border: 1px solid #39FF88 !important; }
.swagger-ui .model, .swagger-ui .model-title, .swagger-ui section.models h4 { color: #c9d4e8 !important; }
.swagger-ui .prop-type { color: #39FF88 !important; }
</style>"""

app = FastAPI(
    title="SnapLink API",
    description=(
        "A production-style URL shortener built by hand with FastAPI + PostgreSQL. "
        "Created by devuvo (https://www.devuvo.com)."
    ),
    version="1.0.0",
    docs_url=None,  # custom themed docs below
    redoc_url=None,
)


@app.get("/docs", include_in_schema=False)
async def themed_docs() -> HTMLResponse:
    """Swagger UI with the Cyberpunk / HUD theme (Prompt Blue + AI Green)."""
    html = get_swagger_ui_html(openapi_url=app.openapi_url, title="SnapLink API")
    body = html.body.decode("utf-8").replace("</head>", DOCS_CSS + "</head>")
    return HTMLResponse(body)


if settings.RATE_LIMIT_ENABLED:
    from slowapi.errors import RateLimitExceeded
    from slowapi import _rate_limit_exceeded_handler

    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)


@app.get("/health", response_model=HealthOut, tags=["ops"])
async def health():
    db_status = "up"
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception:
        db_status = "down"
    return HealthOut(
        status="ok" if db_status == "up" else "degraded",
        db=db_status,
        redis=await cache.ping(),
    )


app.include_router(auth_router.router)
app.include_router(links_router.router)
# public redirect must be last: GET /{code} must not shadow /docs, /health,
# /api/* or /auth/*
app.include_router(redirect_router.router)
