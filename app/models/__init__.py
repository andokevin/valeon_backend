from sqlalchemy import Column, DateTime, Integer, String, ForeignKey, Boolean, Text, Float, JSON, UniqueConstraint
from sqlalchemy.orm import relationship
from app.core.database import Base
from datetime import datetime, timezone
import enum

class ScanType(str, enum.Enum):
    AUDIO = "audio"
    VIDEO = "video"
    IMAGE = "image"

class InputSource(str, enum.Enum):
    MICROPHONE = "microphone"
    CAMERA = "camera"
    FILE = "file"
    GALLERY = "gallery"

class ContentType(str, enum.Enum):
    MUSIC = "music"
    MOVIE = "movie"
    TV_SHOW = "tv_show"
    ARTIST = "artist"
    IMAGE = "image"
    BOOK = "book"
    PRODUCT = "product"

class User(Base):
    __tablename__ = 'users'
    
    user_id = Column(Integer, primary_key=True, index=True)
    user_full_name = Column(String(100), nullable=False)
    user_email = Column(String(100), unique=True, nullable=False, index=True)
    user_image = Column(String(255), nullable=True)
    user_subscription_id = Column(Integer, ForeignKey('subscriptions.subscription_id'), nullable=False)
    is_active = Column(Boolean, default=True)
    preferences = Column(JSON, nullable=True)  # Stocker les préférences utilisateur
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)
    
    # Relations
    scans = relationship("Scan", back_populates="user")
    favorites = relationship("Favorite", back_populates="user")
    playlists = relationship("Playlist", back_populates="user")
    activities = relationship("UserActivity", back_populates="user")
    password = relationship("UserPassword", back_populates="user", uselist=False)

class Subscription(Base):
    __tablename__ = 'subscriptions'
    
    subscription_id = Column(Integer, primary_key=True, index=True)
    subscription_name = Column(String(50), nullable=False, unique=True)
    subscription_price = Column(Float, nullable=False)
    subscription_duration = Column(Integer, nullable=False)
    max_scans_per_day = Column(Integer, nullable=False)
    max_scans_per_month = Column(Integer, nullable=False)
    has_ads = Column(Boolean, default=True)
    offline_mode = Column(Boolean, default=False)
    hd_quality = Column(Boolean, default=False)
    priority_processing = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    
    # Relations
    users = relationship("User", back_populates="subscription")

class Scan(Base):
    __tablename__ = 'scans'
    
    scan_id = Column(Integer, primary_key=True, index=True)
    scan_type = Column(String(20), nullable=False)
    input_source = Column(String(20), nullable=False)
    file_path = Column(String(255), nullable=True)
    file_size = Column(Integer, nullable=True)
    processing_time = Column(Float, nullable=True)
    status = Column(String(20), default="pending")  # pending, processing, completed, failed
    scan_date = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    scan_user = Column(Integer, ForeignKey('users.user_id'), nullable=False, index=True)
    recognized_content_id = Column(Integer, ForeignKey('contents.content_id'), nullable=True)
    
    # Relations
    user = relationship("User", back_populates="scans")
    content = relationship("Content", back_populates="scans")
    recognition_result = relationship("RecognitionResult", back_populates="scan", uselist=False)

class Content(Base):
    __tablename__ = 'contents'
    
    content_id = Column(Integer, primary_key=True, index=True)
    content_type = Column(String(20), nullable=False)
    content_title = Column(String(200), nullable=False)
    content_original_title = Column(String(200), nullable=True)
    content_description = Column(Text, nullable=True)
    content_artist = Column(String(200), nullable=True)
    content_director = Column(String(200), nullable=True)
    content_cast = Column(JSON, nullable=True)
    content_image = Column(String(255), nullable=True)
    content_backdrop = Column(String(255), nullable=True)
    content_release_date = Column(String(20), nullable=True)
    content_duration = Column(Integer, nullable=True)  # en secondes
    content_rating = Column(Float, nullable=True)
    content_vote_count = Column(Integer, nullable=True)
    content_url = Column(String(255), nullable=True)
    content_date = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    
    # Identifiants externes
    spotify_id = Column(String(100), nullable=True, index=True)
    tmdb_id = Column(Integer, nullable=True, index=True)
    imdb_id = Column(String(20), nullable=True)
    audd_id = Column(String(100), nullable=True)
    youtube_id = Column(String(100), nullable=True, index=True)  # AJOUT
    justwatch_id = Column(Integer, nullable=True, index=True)  # AJOUT
    
    # Métadonnées
    metadata = Column(JSON, nullable=True)
    
    # Relations
    scans = relationship("Scan", back_populates="content")
    favorites = relationship("Favorite", back_populates="content")
    playlists = relationship("Playlist", secondary="playlist_contents", back_populates="contents")
    external_links = relationship("ExternalLink", back_populates="content")

class ExternalLink(Base):
    __tablename__ = 'external_links'
    
    link_id = Column(Integer, primary_key=True, index=True)
    content_id = Column(Integer, ForeignKey('contents.content_id'), nullable=False)
    platform = Column(String(50), nullable=False)
    link_url = Column(String(255), nullable=False)
    embed_url = Column(String(255), nullable=True)
    
    content = relationship("Content", back_populates="external_links")

class RecognitionResult(Base):
    __tablename__ = 'recognition_results'
    
    result_id = Column(Integer, primary_key=True, index=True)
    scan_id = Column(Integer, ForeignKey('scans.scan_id'), nullable=False, unique=True)
    raw_data = Column(JSON, nullable=True)
    confidence = Column(Float, nullable=True)
    processing_time = Column(Float, nullable=True)
    model_used = Column(String(50), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    
    scan = relationship("Scan", back_populates="recognition_result")

class Favorite(Base):
    __tablename__ = 'favorites'
    
    favorite_id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey('users.user_id'), nullable=False)
    content_id = Column(Integer, ForeignKey('contents.content_id'), nullable=False)
    notes = Column(String(500), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    
    user = relationship("User", back_populates="favorites")
    content = relationship("Content", back_populates="favorites")
    
    __table_args__ = (UniqueConstraint('user_id', 'content_id', name='unique_user_favorite'),)