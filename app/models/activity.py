# models/activity.py
from sqlalchemy import Column, Integer, String, ForeignKey, JSON, DateTime
from sqlalchemy.orm import relationship
from app.core.database import Base  # ← Changé !
from datetime import datetime

def utc_now():
    return datetime.utcnow()

class UserActivity(Base):
    """
    Modèle pour tracer toutes les actions des utilisateurs
    """
    __tablename__ = 'user_activities'
    
    activity_id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey('users.user_id'), nullable=False)
    
    # Type d'activité (scan, favorite, playlist_create, etc.)
    activity_type = Column(String(50), nullable=False)   # Utilise ActivityType enum
    
    # Références optionnelles
    content_id = Column(Integer, ForeignKey('contents.content_id'), nullable=True)
    playlist_id = Column(Integer, ForeignKey('playlists.playlist_id'), nullable=True)
    
    # Données supplémentaires
    activity_metadata = Column(JSON, nullable=True)               # Infos contextuelles
    
    # Informations de requête
    ip_address = Column(String(50), nullable=True)
    user_agent = Column(String(200), nullable=True)
    
    # Date
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)
    
    # Relations
    user = relationship("User", back_populates="activities")
    content = relationship("Content", foreign_keys=[content_id])
    playlist = relationship("Playlist", foreign_keys=[playlist_id])