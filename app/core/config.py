from pydantic_settings import BaseSettings
from typing import List, Optional

class Settings(BaseSettings):
    APP_NAME: str = "Valeon API"
    APP_VERSION: str = "2.0.0"
    DEBUG: bool = False
    ENVIRONMENT: str = "development"
    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    DATABASE_URL: str
    DATABASE_POOL_SIZE: int = 20
    DATABASE_MAX_OVERFLOW: int = 10

    REDIS_URL: str = "redis://localhost:6379/0"
    REDIS_ENABLED: bool = True
    CACHE_TTL_SECONDS: int = 3600

    RATE_LIMIT_ENABLED: bool = True
    RATE_LIMIT_REQUESTS: int = 100
    RATE_LIMIT_PERIOD: int = 60

    OPENAI_API_KEY: Optional[str] = None
    OPENAI_DEFAULT_MODEL: str = "gpt-3.5-turbo"
    OPENAI_ADVANCED_MODEL: str = "gpt-4"
    OPENAI_MAX_TOKENS_PER_MONTH: int = 1_000_000

    ACRCLOUD_ENABLED: bool = True
    ACRCLOUD_HOST: Optional[str] = None
    ACRCLOUD_ACCESS_KEY: Optional[str] = None
    ACRCLOUD_SECRET_KEY: Optional[str] = None

    SPOTIFY_CLIENT_ID: Optional[str] = None
    SPOTIFY_CLIENT_SECRET: Optional[str] = None
    SPOTIFY_ENABLED: bool = True

    TMDB_API_KEY: Optional[str] = None
    TMDB_ENABLED: bool = True
    TMDB_LANGUAGE: str = "fr-FR"

    YOUTUBE_API_KEY: Optional[str] = None
    YOUTUBE_ENABLED: bool = True

    JUSTWATCH_ENABLED: bool = True
    JUSTWATCH_COUNTRY: str = "FR"

    MAX_UPLOAD_SIZE: int = 50 * 1024 * 1024
    UPLOAD_PATH: str = "uploads"
    ALLOWED_AUDIO_EXTENSIONS: List[str] = [".mp3", ".wav", ".m4a", ".flac", ".aac"]
    ALLOWED_IMAGE_EXTENSIONS: List[str] = [".jpg", ".jpeg", ".png", ".gif", ".webp"]
    ALLOWED_VIDEO_EXTENSIONS: List[str] = [".mp4", ".mov", ".avi", ".mkv", ".webm"]

    CORS_ORIGINS: List[str] = ["http://localhost:3000", "http://localhost:8000"]

    FREE_SCANS_PER_DAY: int = 5
    FREE_SCANS_PER_MONTH: int = 50
    BASIC_SCANS_PER_DAY: int = 20
    BASIC_SCANS_PER_MONTH: int = 200
    PREMIUM_SCANS_PER_DAY: int = 999
    PREMIUM_SCANS_PER_MONTH: int = 9999

    class Config:
        env_file = ".env"
        case_sensitive = True

settings = Settings()
