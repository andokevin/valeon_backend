from sqlalchemy import Column, Integer, String, ForeignKey, Boolean, Table, DateTime, JSON
from sqlalchemy.orm import relationship
from app.core.database import Base
from datetime import datetime, timezone

playlist_contents = Table(
    'playlist_contents',
    Base.metadata,
    Column('playlist_id', Integer, ForeignKey('playlists.playlist_id'), primary_key=True),
    Column('content_id', Integer, ForeignKey('contents.content_id'), primary_key=True),
    Column('added_at', DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)),
    Column('order', Integer, default=0)
)

class Playlist(Base):
    __tablename__ = 'playlists'
    
    playlist_id = Column(Integer, primary_key=True, index=True)
    playlist_name = Column(String(100), nullable=False)
    playlist_description = Column(String(500), nullable=True)
    playlist_image = Column(String(255), nullable=True)
    user_id = Column(Integer, ForeignKey('users.user_id'), nullable=False)
    is_public = Column(Boolean, default=False)
    is_collaborative = Column(Boolean, default=False)
    track_count = Column(Integer, default=0)
    metadata = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)
    
    # Relations
    user = relationship("User", back_populates="playlists")
    contents = relationship("Content", secondary=playlist_contents, back_populates="playlists")

class UserActivity(Base):
    __tablename__ = 'user_activities'
    
    activity_id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey('users.user_id'), nullable=False)
    activity_type = Column(String(50), nullable=False)  # scan, favorite, share, playlist_add, view
    content_id = Column(Integer, ForeignKey('contents.content_id'), nullable=True)
    metadata = Column(JSON, nullable=True)
    ip_address = Column(String(50), nullable=True)
    user_agent = Column(String(200), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    
    user = relationship("User", back_populates="activities")
    content = relationship("Content", backref="activities")