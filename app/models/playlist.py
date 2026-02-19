# models/playlist.py
from sqlalchemy import Column, Integer, String, ForeignKey, Boolean, Table, DateTime, JSON
from sqlalchemy.orm import relationship
from app.core.database import Base  # ← Changé !
from datetime import datetime

def utc_now():
    return datetime.utcnow()

# ===== TABLE D'ASSOCIATION PLAYLIST-CONTENT =====
playlist_contents = Table(
    'playlist_contents',
    Base.metadata,
    Column('playlist_id', Integer, ForeignKey('playlists.playlist_id', ondelete='CASCADE'), primary_key=True),
    Column('content_id', Integer, ForeignKey('contents.content_id', ondelete='CASCADE'), primary_key=True),
    Column('added_at', DateTime(timezone=True), default=utc_now, nullable=False),
    Column('position', Integer, default=0),           # Ordre dans la playlist
    Column('notes', String(500), nullable=True)      # Note personnelle
)


class Playlist(Base):
    """
    Modèle représentant une playlist de contenus
    """
    __tablename__ = 'playlists'
    
    playlist_id = Column(Integer, primary_key=True, index=True)
    playlist_name = Column(String(100), nullable=False)
    playlist_description = Column(String(500), nullable=True)
    playlist_image = Column(String(255), nullable=True)      # Image de couverture
    
    # Propriétaire
    user_id = Column(Integer, ForeignKey('users.user_id'), nullable=False)
    
    # Options
    is_public = Column(Boolean, default=False)               # Playlist visible par tous
    is_collaborative = Column(Boolean, default=False)        # Modifiable par d'autres
    
    # Statistiques dénormalisées (pour éviter les calculs)
    content_count = Column(Integer, default=0)                # Nombre de contenus
    
    # Métadonnées supplémentaires
    playlist_metadata = Column(JSON, nullable=True)                    # Infos supplémentaires
    
    # Dates
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)
    
    # Relations
    user = relationship("User", back_populates="playlists")
    contents = relationship("Content", secondary=playlist_contents, back_populates="playlists")
    
    def update_count(self):
        """Met à jour le compteur de contenus"""
        self.content_count = len(self.contents)