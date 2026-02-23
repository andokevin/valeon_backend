import sys, os, asyncio, time, logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text
import openai

current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from app.core.config import settings
from app.core.database import engine, Base
from app.core.cache import cache
from app.core.rate_limiter import rate_limiter
from app.core.websocket.manager import manager
from app.api.routers import auth, scans, library, recommendations, streaming, websocket, admin

logging.basicConfig(
    level=logging.DEBUG if settings.DEBUG else logging.INFO,
    format="%(asctime)s | %(name)s | %(levelname)s | %(message)s",
)
logger = logging.getLogger(__name__)

async def periodic_cleanup():
    while True:
        await asyncio.sleep(3600)
        manager.cleanup_old_scans(24)
        logger.info("WS scan cleanup effectué")

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(f"🚀 Démarrage Valeon API ({settings.ENVIRONMENT})")
    for path in [settings.UPLOAD_PATH, f"{settings.UPLOAD_PATH}/audio",
                 f"{settings.UPLOAD_PATH}/images", f"{settings.UPLOAD_PATH}/videos"]:
        os.makedirs(path, exist_ok=True)
    asyncio.create_task(periodic_cleanup())
    yield
    logger.info("👋 Arrêt Valeon API")

app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="Valeon API – Know what you see, hear, and watch",
    docs_url="/api/docs" if settings.DEBUG else None,
    redoc_url=None,
    openapi_url="/api/openapi.json" if settings.DEBUG else None,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    return response

@app.middleware("http")
async def log_and_rate_limit(request: Request, call_next):
    start = time.time()
    try:
        rate_limiter.check(request)
    except Exception as e:
        return JSONResponse(status_code=429, content={"detail": str(e)})
    logger.info(f"➡ {request.method} {request.url.path}")
    response = await call_next(request)
    ms = (time.time() - start) * 1000
    logger.info(f"⬅ {response.status_code} {ms:.1f}ms")
    response.headers["X-Process-Time"] = f"{ms:.1f}ms"
    remaining, _ = rate_limiter.remaining(request)
    response.headers["X-Rate-Limit-Remaining"] = str(remaining)
    return response

@app.exception_handler(Exception)
async def global_error(request: Request, exc: Exception):
    logger.error(f"Unhandled error: {exc}", exc_info=True)
    return JSONResponse(status_code=500, content={"detail": "Erreur interne", "path": request.url.path})

app.include_router(auth.router,            prefix="/api")
app.include_router(scans.router,           prefix="/api")
app.include_router(library.router,         prefix="/api")
app.include_router(streaming.router,       prefix="/api")
app.include_router(recommendations.router, prefix="/api")
app.include_router(websocket.router)
app.include_router(admin.router,           prefix="/api")

app.mount("/uploads", StaticFiles(directory=settings.UPLOAD_PATH), name="uploads")

@app.get("/")
async def root():
    return {"name": settings.APP_NAME, "version": settings.APP_VERSION,
            "status": "operational", "docs": "/api/docs" if settings.DEBUG else None}

@app.get("/health")
async def health():
    services = {"api": "ok"}
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        services["database"] = "ok"
    except Exception:
        services["database"] = "error"
    services["redis"] = "ok" if (cache.enabled and cache.redis_client and cache.redis_client.ping()) else "disabled"
    services["ws_connections"] = manager.get_connection_count()
    ok = services["database"] == "ok"
    return {"status": "healthy" if ok else "degraded", "services": services, "version": settings.APP_VERSION}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=settings.DEBUG)
