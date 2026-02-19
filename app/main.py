#!/usr/bin/env python3
import sys
import os

# === AJOUT DU DOSSIER RACINE AU PATH ===
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# === PATCH POUR L'ERREUR 'proxies' ===
print("⏳ Application des patches...")
try:
    import httpx
    original_httpx_client = httpx.Client
    
    class PatchedHttpxClient(original_httpx_client):
        def __init__(self, *args, **kwargs):
            if 'proxies' in kwargs:
                print(f"  ⚠️ Suppression du paramètre 'proxies'")
                del kwargs['proxies']
            super().__init__(*args, **kwargs)
    
    httpx.Client = PatchedHttpxClient
    print("  ✅ Patch httpx appliqué")
    
    import spotipy
    original_spotify = spotipy.Spotify
    
    class PatchedSpotify(original_spotify):
        def __init__(self, *args, **kwargs):
            if 'proxies' in kwargs:
                print(f"  ⚠️ Suppression du paramètre 'proxies' dans spotipy")
                del kwargs['proxies']
            super().__init__(*args, **kwargs)
    
    spotipy.Spotify = PatchedSpotify
    print("  ✅ Patch spotipy appliqué")
    
except Exception as e:
    print(f"  ❌ Erreur patches: {e}")

print("=" * 50)

# === IMPORTS ===
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
import time
import logging

from app.core.config import settings
from app.core.database import engine, Base
from app.api.routers import auth, scans, library, recommendations, streaming, websocket, admin
from app.core.cache import cache
from app.core.rate_limiter import rate_limiter

# === CONFIGURATION LOGS ===
logging.basicConfig(
    level=logging.INFO if not settings.DEBUG else logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# === CRÉATION DE L'APPLICATION ===
app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="Valeon API - Know what you see, hear, and watch",
    docs_url="/api/docs" if settings.DEBUG else None,
    redoc_url="/api/redoc" if settings.DEBUG else None,
    openapi_url="/api/openapi.json" if settings.DEBUG else None,
    contact={
        "name": "Valeon Support",
        "email": "support@valeon.com",
    },
    license_info={
        "name": "MIT",
    },
)

# === MIDDLEWARES ===
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.middleware("http")
async def log_requests(request: Request, call_next):
    """Middleware de logging des requêtes."""
    start_time = time.time()
    
    # Rate limiting
    try:
        rate_limiter.check_rate_limit(request)
    except Exception as e:
        return JSONResponse(
            status_code=429,
            content={"detail": str(e)}
        )
    
    # Log entrée
    logger.info(f"➡️ {request.method} {request.url.path}")
    
    response = await call_next(request)
    
    # Log sortie
    process_time = (time.time() - start_time) * 1000
    logger.info(f"⬅️ {response.status_code} - {process_time:.2f}ms")
    
    response.headers["X-Process-Time"] = str(process_time)
    response.headers["X-Rate-Limit-Remaining"] = str(rate_limiter.get_remaining(request)[0])
    
    return response

@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    """Ajoute des headers de sécurité."""
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    return response

# === GESTIONNAIRE D'ERREURS GLOBAL ===
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"❌ Erreur non gérée: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={
            "detail": "Une erreur interne est survenue",
            "path": request.url.path,
            "method": request.method
        }
    )

# === INCLUSION DES ROUTERS ===
app.include_router(auth.router, prefix="/api/auth", tags=["Authentication"])
app.include_router(scans.router, prefix="/api/scans", tags=["Scans"])
app.include_router(library.router, prefix="/api/library", tags=["Library"])
app.include_router(streaming.router, prefix="/api/streaming", tags=["Streaming"])
app.include_router(recommendations.router, prefix="/api/recommendations", tags=["Recommendations"])
app.include_router(websocket.router, tags=["WebSocket"])
app.include_router(admin.router, prefix="/api/admin", tags=["Admin"])

# === FICHIERS STATIQUES ===
os.makedirs(settings.UPLOAD_PATH, exist_ok=True)
os.makedirs(os.path.join(settings.UPLOAD_PATH, "audio"), exist_ok=True)
os.makedirs(os.path.join(settings.UPLOAD_PATH, "images"), exist_ok=True)
os.makedirs(os.path.join(settings.UPLOAD_PATH, "videos"), exist_ok=True)

app.mount("/uploads", StaticFiles(directory=settings.UPLOAD_PATH), name="uploads")

# === ENDPOINTS ===
@app.get("/")
async def root():
    """Racine de l'API."""
    return {
        "message": "Bienvenue sur Valeon API",
        "version": settings.APP_VERSION,
        "environment": settings.ENVIRONMENT,
        "status": "operational",
        "documentation": "/api/docs" if settings.DEBUG else None
    }

@app.get("/health")
async def health_check():
    """Vérification de la santé de l'API."""
    services = {
        "api": "operational"
    }
    
    # Vérifier la base de données
    try:
        from app.core.database import SessionLocal
        db = SessionLocal()
        db.execute("SELECT 1")
        db.close()
        services["database"] = "connected"
    except Exception as e:
        logger.error(f"Database health check failed: {e}")
        services["database"] = "error"
    
    # Vérifier Redis
    if cache.enabled:
        try:
            cache.redis_client.ping()
            services["redis"] = "connected"
        except:
            services["redis"] = "disconnected"
    else:
        services["redis"] = "disabled"
    
    status = "healthy" if services["database"] == "connected" else "degraded"
    
    return {
        "status": status,
        "timestamp": time.time(),
        "services": services,
        "version": settings.APP_VERSION
    }

# === ÉVÉNEMENTS DE CYCLE DE VIE ===
@app.on_event("startup")
async def startup_event():
    logger.info("🚀 Démarrage de Valeon API...")
    logger.info(f"📊 Configuration: {settings.ENVIRONMENT} mode")
    logger.info(f"✅ API prête!")

@app.on_event("shutdown")
async def shutdown_event():
    logger.info("👋 Arrêt de Valeon API...")

# === LANCEMENT ===
if __name__ == "__main__":
    import uvicorn
    print("=" * 50)
    print(f"🚀 DÉMARRAGE DU SERVEUR ({settings.ENVIRONMENT})")
    print(f"🌐 http://localhost:8000")
    print(f"📚 http://localhost:8000/api/docs")
    print("=" * 50)
    
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.DEBUG,
        log_level="info"
    )