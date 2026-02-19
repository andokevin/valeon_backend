# app/models/content.py
from sqlalchemy import Column, Integer, String, Text, Float, JSON, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from app.core.database import Base
from datetime import datetime

def utc_now():
    return datetime.utcnow()

class Content(Base):
    """
    Modèle représentant un contenu reconnu (musique, film, etc.)
    """
    __tablename__ = 'contents'
    
    content_id = Column(Integer, primary_key=True, index=True)
    content_type = Column(String(20), nullable=False)     # music, movie, tv_show, etc.
    
    # Informations générales
    content_title = Column(String(200), nullable=False)
    content_original_title = Column(String(200), nullable=True)
    content_description = Column(Text, nullable=True)
    
    # Artistes et équipe
    content_artist = Column(String(200), nullable=True)   # Pour la musique
    content_director = Column(String(200), nullable=True) # Pour les films
    content_cast = Column(JSON, nullable=True)            # Liste des acteurs
    
    # Médias
    content_image = Column(String(255), nullable=True)    # URL de l'image/pochette
    content_backdrop = Column(String(255), nullable=True) # Image de fond
    
    # Métadonnées
    content_release_date = Column(String(20), nullable=True)  # Format: YYYY-MM-DD ou YYYY
    content_duration = Column(Integer, nullable=True)         # Durée en secondes
    content_rating = Column(Float, nullable=True)             # Note moyenne
    content_url = Column(String(255), nullable=True)          # URL officielle
    
    # Date d'ajout dans notre base
    content_date = Column(DateTime(timezone=True), default=utc_now, nullable=False)
    
    # ===== IDENTIFIANTS EXTERNES =====
    # AUDD_ID SUPPRIMÉ !
    spotify_id = Column(String(100), nullable=True, index=True)
    tmdb_id = Column(Integer, nullable=True, index=True)
    imdb_id = Column(String(20), nullable=True)
    youtube_id = Column(String(100), nullable=True, index=True)
    justwatch_id = Column(Integer, nullable=True, index=True)
    
    # Métadonnées supplémentaires (flexibles)
    content_metadata = Column(JSON, nullable=True)
    
    # ===== RELATIONS =====
    scans = relationship("Scan", back_populates="content")
    favorites = relationship("Favorite", back_populates="content")
    playlists = relationship("Playlist", secondary="playlist_contents", back_populates="contents")
    external_links = relationship("ExternalLink", back_populates="content")


class ExternalLink(Base):
    """
    Liens vers les plateformes externes (YouTube, Spotify, Netflix, etc.)
    """
    __tablename__ = 'external_links'
    
    link_id = Column(Integer, primary_key=True, index=True)
    content_id = Column(Integer, ForeignKey('contents.content_id'), nullable=False)
    
    # Informations du lien
    platform = Column(String(50), nullable=False)         # youtube, spotify, netflix, etc.
    link_url = Column(String(255), nullable=False)        # URL de visionnage
    embed_url = Column(String(255), nullable=True)        # URL pour intégration (iframe)
    
    # Relations
    content = relationship("Content", back_populates="external_links")