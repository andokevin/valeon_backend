from sqlalchemy import Column, Integer, String, Text, Float, JSON, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from app.core.database import Base
from datetime import datetime

class Content(Base):
    __tablename__ = "contents"
    content_id            = Column(Integer, primary_key=True, index=True)
    content_type          = Column(String(20), nullable=False)
    content_title         = Column(String(200), nullable=False)
    content_original_title= Column(String(200), nullable=True)
    content_description   = Column(Text, nullable=True)
    content_artist        = Column(String(200), nullable=True)
    content_director      = Column(String(200), nullable=True)
    content_cast          = Column(JSON, nullable=True)
    content_image         = Column(String(500), nullable=True)
    content_backdrop      = Column(String(500), nullable=True)
    content_release_date  = Column(String(20), nullable=True)
    content_duration      = Column(Integer, nullable=True)
    content_rating        = Column(Float, nullable=True)
    content_url           = Column(String(500), nullable=True)
    content_date          = Column(DateTime, default=datetime.utcnow, nullable=False)
    spotify_id            = Column(String(100), nullable=True, index=True)
    tmdb_id               = Column(Integer, nullable=True, index=True)
    imdb_id               = Column(String(20), nullable=True)
    youtube_id            = Column(String(100), nullable=True, index=True)
    justwatch_id          = Column(Integer, nullable=True, index=True)
    content_metadata      = Column(JSON, nullable=True)

class ExternalLink(Base):
    __tablename__ = "external_links"
    link_id     = Column(Integer, primary_key=True, index=True)
    content_id  = Column(Integer, ForeignKey("contents.content_id", ondelete="CASCADE"), nullable=False)
    platform    = Column(String(50), nullable=False)
    link_url    = Column(String(500), nullable=False)
    embed_url   = Column(String(500), nullable=True)
    content = relationship("Content", back_populates="external_links")
