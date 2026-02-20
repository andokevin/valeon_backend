from sqlalchemy import Column, Integer, String, ForeignKey, Boolean, Table, DateTime, JSON
from sqlalchemy.orm import relationship
from app.core.database import Base
from datetime import datetime

playlist_contents = Table(
    "playlist_contents", Base.metadata,
    Column("playlist_id", Integer, ForeignKey("playlists.playlist_id", ondelete="CASCADE"), primary_key=True),
    Column("content_id",  Integer, ForeignKey("contents.content_id",  ondelete="CASCADE"), primary_key=True),
    Column("added_at",    DateTime, default=datetime.utcnow, nullable=False),
    Column("position",    Integer, default=0),
)

class Playlist(Base):
    __tablename__ = "playlists"
    playlist_id          = Column(Integer, primary_key=True, index=True)
    playlist_name        = Column(String(100), nullable=False)
    playlist_description = Column(String(500), nullable=True)
    playlist_image       = Column(String(500), nullable=True)
    user_id              = Column(Integer, ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False)
    is_public            = Column(Boolean, default=False)
    is_collaborative     = Column(Boolean, default=False)
    content_count        = Column(Integer, default=0)
    playlist_metadata    = Column(JSON, nullable=True)
    created_at           = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at           = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    user     = relationship("User", back_populates="playlists")
    contents = relationship("Content", secondary=playlist_contents, back_populates="playlists")
