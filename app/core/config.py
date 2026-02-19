# app/core/config.py
from pydantic_settings import BaseSettings
from typing import Optional, List
import os

class Settings(BaseSettings):
    # ===== APPLICATION =====
    APP_NAME: str = "Valeon API"
    APP_VERSION: str = "2.0.0"
    DEBUG: bool = False
    ENVIRONMENT: str = "development"  # development, staging, production
    SECRET_KEY: str = "ZcrC2_NRolBpdtvPnfdiiemnInJicjN7NWbUyFr0yXk"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    
    # ===== DATABASE =====
    DATABASE_URL: str = "mysql://root:ando05%40%24@127.0.0.1:3306/valeon"
    DATABASE_POOL_SIZE: int = 20
    DATABASE_MAX_OVERFLOW: int = 10
    
    # ===== REDIS (CACHE) =====
    REDIS_URL: str = "redis://localhost:6379/0"
    REDIS_ENABLED: bool = True
    CACHE_TTL_SECONDS: int = 3600  # 1 heure
    
    # ===== RATE LIMITING =====
    RATE_LIMIT_ENABLED: bool = True
    RATE_LIMIT_REQUESTS: int = 100  # Requêtes par minute
    RATE_LIMIT_PERIOD: int = 60  # secondes
    
    # ===== OPENAI =====
    OPENAI_API_KEY: Optional[str] = "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"
    OPENAI_ORGANIZATION: Optional[str] = None
    OPENAI_DEFAULT_MODEL: str = "gpt-3.5-turbo"
    OPENAI_ADVANCED_MODEL: str = "gpt-4"
    OPENAI_MAX_TOKENS_PER_MONTH: int = 1000000  # Limite mensuelle
    
    # ===== ACRCLOUD =====
    ACRCLOUD_ENABLED: bool = True
    ACRCLOUD_HOST: Optional[str] = None
    ACRCLOUD_ACCESS_KEY: Optional[str] = None
    ACRCLOUD_SECRET_KEY: Optional[str] = None
    ACRCLOUD_TIMEOUT: int = 30
    
    # ===== SPOTIFY =====
    SPOTIFY_CLIENT_ID: Optional[str] = "70379c43b7db4248ab2ee7709bbd4bf2"
    SPOTIFY_CLIENT_SECRET: Optional[str] = "3f89c675896f47c8b640b130261bff92"
    SPOTIFY_ENABLED: bool = True
    
    # ===== TMDB =====
    TMDB_API_KEY: Optional[str] = "8b5362c1220326f5ff0d07ea43e7a3e1"
    TMDB_ENABLED: bool = True
    TMDB_LANGUAGE: str = "fr-FR"
    
    # ===== YOUTUBE =====
    YOUTUBE_API_KEY: Optional[str] = "AIzaSyAyKCr-8JIaJwIHrc8v_r0Hwi1ZYWO96A4"
    YOUTUBE_ENABLED: bool = True
    
    # ===== JUSTWATCH =====
    JUSTWATCH_ENABLED: bool = True
    JUSTWATCH_COUNTRY: str = "FR"
    
    # ===== FILE UPLOAD =====
    MAX_UPLOAD_SIZE: int = 50 * 1024 * 1024  # 50MB
    UPLOAD_PATH: str = "uploads"
    ALLOWED_AUDIO_EXTENSIONS: List[str] = [".mp3", ".wav", ".m4a", ".flac", ".aac"]
    ALLOWED_IMAGE_EXTENSIONS: List[str] = [".jpg", ".jpeg", ".png", ".gif", ".webp"]
    ALLOWED_VIDEO_EXTENSIONS: List[str] = [".mp4", ".mov", ".avi", ".mkv", ".webm"]
    
    # ===== CORS =====
    CORS_ORIGINS: List[str] = ["http://localhost:3000", "http://localhost:8000", "https://valeon.app"]
    
    # ===== MODULE ACTIVATION =====
    ENABLE_ACRCLOUD: bool = True
    ENABLE_SPOTIFY: bool = True
    ENABLE_TMDB: bool = True
    ENABLE_YOUTUBE: bool = True
    ENABLE_JUSTWATCH: bool = True
    
    # ===== WEBHOOKS =====
    WEBHOOK_ENABLED: bool = False
    WEBHOOK_URL: Optional[str] = None
    WEBHOOK_SECRET: Optional[str] = None
    
    class Config:
        env_file = ".env"
        case_sensitive = True

settings = Settings()