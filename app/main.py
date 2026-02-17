from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
import time
import logging

from app.core.config import settings
from app.core.database import engine, Base
from app.api.routers import auth, scans, library, recommendations, websocket

# Configuration des logs
logging.basicConfig(
    level=logging.INFO if not settings.DEBUG else logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Créer l'application FastAPI
app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="Valeon API - Know what you see, hear, and watch",
    docs_url="/api/docs" if settings.DEBUG else None,
    redoc_url="/api/redoc" if settings.DEBUG else None,
    openapi_url="/api/openapi.json" if settings.DEBUG else None
)

# Configuration CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Middleware pour logging des requêtes
@app.middleware("http")
async def log_requests(request: Request, call_next):
    start_time = time.time()
    
    # Log de la requête
    logger.info(f"Request: {request.method} {request.url.path}")
    
    response = await call_next(request)
    
    # Log de la réponse
    process_time = (time.time() - start_time) * 1000
    logger.info(f"Response: {response.status_code} - {process_time:.2f}ms")
    
    response.headers["X-Process-Time"] = str(process_time)
    return response

# Gestionnaire d'erreurs global
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled error: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={
            "detail": "Une erreur interne est survenue",
            "path": request.url.path
        }
    )

# Inclure les routers
app.include_router(auth.router, prefix="/api/auth", tags=["Authentication"])
app.include_router(scans.router, prefix="/api/scans", tags=["Scans"])
app.include_router(library.router, prefix="/api/library", tags=["Library"])
app.include_router(recommendations.router, prefix="/api/recommendations", tags=["Recommendations"])
app.include_router(websocket.router, prefix="", tags=["WebSocket"])

# Monter les fichiers statiques
os.makedirs(settings.UPLOAD_PATH, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=settings.UPLOAD_PATH), name="uploads")

@app.get("/")
async def root():
    """
    Racine de l'API
    """
    return {
        "message": "Bienvenue sur Valeon API",
        "version": settings.APP_VERSION,
        "status": "operational",
        "endpoints": {
            "docs": "/api/docs" if settings.DEBUG else None,
            "auth": "/api/auth",
            "scans": "/api/scans",
            "library": "/api/library",
            "recommendations": "/api/recommendations",
            "websocket": "/ws"
        }
    }

@app.get("/health")
async def health_check():
    """
    Vérification de la santé de l'API
    """
    # Vérifier la connexion à la base de données
    db_status = "disconnected"
    try:
        from app.core.database import SessionLocal
        db = SessionLocal()
        db.execute("SELECT 1")
        db.close()
        db_status = "connected"
    except Exception as e:
        logger.error(f"Database health check failed: {e}")
        db_status = "error"
    
    return {
        "status": "healthy" if db_status == "connected" else "degraded",
        "timestamp": time.time(),
        "services": {
            "database": db_status,
            "api": "operational"
        },
        "version": settings.APP_VERSION
    }

@app.on_event("startup")
async def startup_event():
    """
    Actions à exécuter au démarrage
    """
    logger.info("🚀 Démarrage de Valeon API...")
    
    # Créer les dossiers nécessaires
    os.makedirs(settings.UPLOAD_PATH, exist_ok=True)
    os.makedirs(os.path.join(settings.UPLOAD_PATH, "audio"), exist_ok=True)
    os.makedirs(os.path.join(settings.UPLOAD_PATH, "images"), exist_ok=True)
    os.makedirs(os.path.join(settings.UPLOAD_PATH, "videos"), exist_ok=True)
    
    logger.info(f"✅ Dossiers d'upload créés dans {settings.UPLOAD_PATH}")
    
    # Vérifier les clés API
    if not settings.OPENAI_API_KEY:
        logger.warning("⚠️  OPENAI_API_KEY non configurée")
    if not settings.SPOTIFY_CLIENT_ID:
        logger.warning("⚠️  SPOTIFY_CLIENT_ID non configurée")
    if not settings.TMDB_API_KEY:
        logger.warning("⚠️  TMDB_API_KEY non configurée")
    
    logger.info("✅ API prête!")

@app.on_event("shutdown")
async def shutdown_event():
    """
    Actions à exécuter à l'arrêt
    """
    logger.info("👋 Arrêt de Valeon API...")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.DEBUG,
        log_level="info"
    )