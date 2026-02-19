# models/base.py
from sqlalchemy import Column, DateTime
from sqlalchemy.ext.declarative import declarative_base
from datetime import datetime, timezone
import enum

# Base commune pour tous les modèles
Base = declarative_base()

# ===== ENUMS =====
class ScanType(str, enum.Enum):
    """Types de scans disponibles"""
    AUDIO = "audio"
    VIDEO = "video"
    IMAGE = "image"

class InputSource(str, enum.Enum):
    """Sources d'entrée pour les scans"""
    MICROPHONE = "microphone"
    CAMERA = "camera"
    FILE = "file"
    GALLERY = "gallery"

class ContentType(str, enum.Enum):
    """Types de contenu reconnus"""
    MUSIC = "music"
    MOVIE = "movie"
    TV_SHOW = "tv_show"
    ARTIST = "artist"
    IMAGE = "image"
    BOOK = "book"
    PRODUCT = "product"

class ActivityType(str, enum.Enum):
    """Types d'activités utilisateur"""
    SCAN = "scan"
    FAVORITE = "favorite"
    PLAYLIST_CREATE = "playlist_create"
    PLAYLIST_ADD = "playlist_add"
    SHARE = "share"
    VIEW = "view"
    RECOMMENDATION_VIEW = "recommendation_view"
    CHAT_QUERY = "chat_query"

# Fonction utilitaire pour les dates
def utc_now():
    """Retourne la date UTC actuelle"""
    return datetime.now(timezone.utc)