from app.core.database import Base
from .subscription import Subscription
from .user import User, UserPassword
from .content import Content, ExternalLink
from .playlist import Playlist, playlist_contents
from .scan import Scan, RecognitionResult
from .favorite import Favorite
from .activity import UserActivity
from sqlalchemy.orm import relationship
from datetime import datetime

def utc_now():
    return datetime.utcnow()

User.subscription = relationship("Subscription", back_populates="users", foreign_keys="User.user_subscription_id")
User.scans = relationship("Scan", back_populates="user", foreign_keys="Scan.scan_user")
User.favorites = relationship("Favorite", back_populates="user")
User.playlists = relationship("Playlist", back_populates="user")
User.activities = relationship("UserActivity", back_populates="user")
User.password = relationship("UserPassword", back_populates="user", uselist=False)

Content.scans = relationship("Scan", back_populates="content", foreign_keys="Scan.recognized_content_id")
Content.favorites = relationship("Favorite", back_populates="content")
Content.external_links = relationship("ExternalLink", back_populates="content")
Content.playlists = relationship("Playlist", secondary=playlist_contents, back_populates="contents")

__all__ = [
    "Base", "Subscription", "User", "UserPassword",
    "Content", "ExternalLink", "Playlist", "playlist_contents",
    "Scan", "RecognitionResult", "Favorite", "UserActivity",
]
