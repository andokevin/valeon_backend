from pydantic_settings import BaseSettings
from typing import Optional, List
import os

class Settings(BaseSettings):
    # Application
    APP_NAME: str = "Valeon API"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False
    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    
    # Database
    DATABASE_URL: str
    REDIS_URL: str = "redis://localhost:6379/0"
    
    # OpenAI
    OPENAI_API_KEY: Optional[str] = None
    
    # Spotify
    SPOTIFY_CLIENT_ID: Optional[str] = "70379c43b7db4248ab2ee7709bbd4bf2"
    SPOTIFY_CLIENT_SECRET: Optional[str] = "3f89c675896f47c8b640b130261bff92"
    
    # TMDB
    TMDB_API_KEY: Optional[str] = None
    
    # AudD
    AUDD_API_KEY: Optional[str] = None
    AUDD_API_URL: str = "https://api.audd.io/"
    
    # YouTube
    YOUTUBE_API_KEY: Optional[str] = "AIzaSyAyKCr-8JIaJwIHrc8v_r0Hwi1ZYWO96A4"
    
    # File Upload
    MAX_UPLOAD_SIZE: int = 50 * 1024 * 1024  # 50MB
    UPLOAD_PATH: str = "uploads"
    ALLOWED_AUDIO_EXTENSIONS: List[str] = [".mp3", ".wav", ".m4a", ".flac"]
    ALLOWED_IMAGE_EXTENSIONS: List[str] = [".jpg", ".jpeg", ".png", ".gif"]
    ALLOWED_VIDEO_EXTENSIONS: List[str] = [".mp4", ".mov", ".avi", ".mkv"]
    
    # CORS
    CORS_ORIGINS: List[str] = ["http://localhost:3000", "http://localhost:8000"]
    
    class Config:
        env_file = ".env"
        case_sensitive = True

settings = Settings()