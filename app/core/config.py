from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import List, Optional


class Settings(BaseSettings):

    # =========================
    # APP
    # =========================
    APP_NAME: str = "Valeon API"
    APP_VERSION: str = "2.0.0"
    DEBUG: bool = False
    ENVIRONMENT: str = "development"

    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # =========================
    # DATABASE
    # =========================
    DATABASE_URL: str
    DATABASE_POOL_SIZE: int = 20
    DATABASE_MAX_OVERFLOW: int = 10

    # =========================
    # REDIS / CACHE
    # =========================
    REDIS_URL: str = "redis://localhost:6379/0"
    REDIS_ENABLED: bool = True
    CACHE_TTL_SECONDS: int = 3600

    # =========================
    # RATE LIMIT
    # =========================
    RATE_LIMIT_ENABLED: bool = True
    RATE_LIMIT_REQUESTS: int = 100
    RATE_LIMIT_PERIOD: int = 60


    # =========================
    # ACRCLOUD
    # =========================
    ACRCLOUD_ENABLED: bool = True
    ACRCLOUD_HOST: Optional[str] = None  # Sera chargé depuis .env
    ACRCLOUD_ACCESS_KEY: Optional[str] = None  # Sera chargé depuis .env
    ACRCLOUD_SECRET_KEY: Optional[str] = None  # Sera chargé depuis .env

    # =========================
    # SPOTIFY
    # =========================
    SPOTIFY_CLIENT_ID: Optional[str] = None
    SPOTIFY_CLIENT_SECRET: Optional[str] = None
    SPOTIFY_ENABLED: bool = True

    # =========================
    # TMDB
    # =========================
    TMDB_API_KEY: Optional[str] = None
    TMDB_ENABLED: bool = True
    TMDB_LANGUAGE: str = "fr-FR"

    # =========================
    # YOUTUBE
    # =========================
    YOUTUBE_API_KEY: Optional[str] = None
    YOUTUBE_ENABLED: bool = True

    # =========================
    # JUSTWATCH
    # =========================
    JUSTWATCH_ENABLED: bool = True
    JUSTWATCH_COUNTRY: str = "FR"

    # =========================
    # WEBHOOK
    # =========================
    WEBHOOK_ENABLED: bool = False

    # =========================
    # FILE UPLOAD
    # =========================
    MAX_UPLOAD_SIZE: int = 50 * 1024 * 1024
    UPLOAD_PATH: str = "uploads"

    ALLOWED_AUDIO_EXTENSIONS: List[str] = [".mp3", ".wav", ".m4a", ".flac", ".aac"]
    ALLOWED_IMAGE_EXTENSIONS: List[str] = [".jpg", ".jpeg", ".png", ".gif", ".webp"]
    ALLOWED_VIDEO_EXTENSIONS: List[str] = [".mp4", ".mov", ".avi", ".mkv", ".webm"]

    # =========================
    # CORS
    # =========================
    CORS_ORIGINS: List[str] = [
        "http://localhost:3000",
        "http://localhost:8000"
    ]

    # =========================
    # SCAN LIMITS
    # =========================
    FREE_SCANS_PER_DAY: int = 500
    FREE_SCANS_PER_MONTH: int = 5000

    BASIC_SCANS_PER_DAY: int = 20000
    BASIC_SCANS_PER_MONTH: int = 2000

    PREMIUM_SCANS_PER_DAY: int = 999
    PREMIUM_SCANS_PER_MONTH: int = 9999

    # =========================
    # Pydantic v2 Config
    # =========================
    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=True,
        extra="ignore"
    )

   # GEMINI MODELS CONFIGURATION
    # =========================
    GEMINI_MODEL: str = "gemini-2.5-flash"  # Modèle principal
    GEMINI_FALLBACK_MODEL: str = "gemini-2.5-pro"  # Modèle de secours
    GEMINI_FALLBACK_ENABLED: bool = True  # Activer le fallback
    GEMINI_QUOTA_THRESHOLD: int = 5 

    # =========================
    # WHISPER.CPP
    WHISPER_ENABLED: bool = True
    WHISPER_MODEL_SIZE: str = "base"  # tiny, base, small, medium, large
    WHISPER_LANGUAGE: str = "fr"

    GEMINI_ENABLED: bool = True
    GEMINI_API_KEY: Optional[str] = None
    GEMINI_MODEL: str = "gemini-2.5-flash"


    # =========================
    # CLOUD VISION
    # =========================
    CLOUD_VISION_ENABLED: bool = True
    VISION_FALLBACK_TO_GEMINI: bool = True  # Fallback sur Gemini si Vision échoue
    VISION_CONFIDENCE_THRESHOLD: float = 0.7

    # Dans app/core/config.py

    # =========================
    # SCAN PERMISSIONS - CONFIGURABLE POUR BACK-OFFICE
    # =========================
    # ⚠️ IMPORTANT: Ces valeurs seront modifiables depuis le back-office
    # Ne pas modifier directement dans le code après déploiement
    # 
    # Types disponibles: "audio", "image", "video"
    # Format: Liste de strings

    # Configuration pour l'abonnement FREE
    FREE_ALLOWED_SCAN_TYPES: List[str] = ["audio", "image", "video"]  # ← Actuellement tout autorisé
    FREE_SCANS_PER_DAY: int = 5222
    FREE_SCANS_PER_MONTH: int = 20000

    # Configuration pour l'abonnement BASIC
    BASIC_ALLOWED_SCAN_TYPES: List[str] = ["audio", "image", "video"]
    BASIC_SCANS_PER_DAY: int = 20
    BASIC_SCANS_PER_MONTH: int = 200

    # Configuration pour l'abonnement PREMIUM
    PREMIUM_ALLOWED_SCAN_TYPES: List[str] = ["audio", "image", "video"]
    PREMIUM_SCANS_PER_DAY: int = 999
    PREMIUM_SCANS_PER_MONTH: int = 9999

     # Firebase
    FIREBASE_SERVICE_ACCOUNT_KEY: str = "./serviceAccountKey.json"
    FIREBASE_ENABLED: bool = True

settings = Settings()
