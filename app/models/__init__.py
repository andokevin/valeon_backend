# models/__init__.py
from sqlalchemy.orm import relationship
from app.core.database import Base  # ← Changé !
import enum
# Définir utc_now ici si besoin
from datetime import datetime
utc_now = datetime.utcnow

# Enums (garder les mêmes)
class ScanType(str, enum.Enum):
    AUDIO = "audio"
    VIDEO = "video"
    IMAGE = "image"

# ... (garde tous tes enums inchangés)

# Importer les modèles
from .subscription import Subscription
from .user import User, UserPassword
from .content import Content, ExternalLink
from .playlist import Playlist, playlist_contents
from .scan import Scan, RecognitionResult
from .favorite import Favorite
from .activity import UserActivity

# Relations (inchangées)
User.subscription = relationship("Subscription", back_populates="users")
User.scans = relationship("Scan", back_populates="user")
User.favorites = relationship("Favorite", back_populates="user")
User.playlists = relationship("Playlist", back_populates="user")
User.activities = relationship("UserActivity", back_populates="user")
User.password = relationship("UserPassword", back_populates="user", uselist=False)

Content.scans = relationship("Scan", back_populates="content")
Content.favorites = relationship("Favorite", back_populates="content")
Content.playlists = relationship("Playlist", secondary="playlist_contents", back_populates="contents")
Content.external_links = relationship("ExternalLink", back_populates="content")

# Export (inchangé)
__all__ = [
    'Base',
    'ScanType',
    'InputSource',
    'ContentType',
    'ActivityType',
    'utc_now',
    'Subscription',
    'User',
    'UserPassword',
    'Content',
    'ExternalLink',
    'Playlist',
    'playlist_contents',
    'Scan',
    'RecognitionResult',
    'Favorite',
    'UserActivity',
]