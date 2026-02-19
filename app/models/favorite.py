# models/favorite.py
from sqlalchemy import Column, Integer, ForeignKey, String, DateTime, UniqueConstraint
from sqlalchemy.orm import relationship
from app.core.database import Base  # ← Changé !
from datetime import datetime

def utc_now():
    return datetime.utcnow()

class Favorite(Base):
    """
    Modèle représentant un favori (contenu marqué par un utilisateur)
    """
    __tablename__ = 'favorites'
    
    favorite_id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey('users.user_id'), nullable=False)
    content_id = Column(Integer, ForeignKey('contents.content_id'), nullable=False)
    
    notes = Column(String(500), nullable=True)        # Notes personnelles sur ce favori
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)
    
    # Relations
    user = relationship("User", back_populates="favorites")
    content = relationship("Content", back_populates="favorites")
    
    # Contrainte : un utilisateur ne peut pas favoriser deux fois le même contenu
    __table_args__ = (UniqueConstraint('user_id', 'content_id', name='unique_user_favorite'),)