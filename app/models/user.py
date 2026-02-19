# models/user.py
# models/user.py
from sqlalchemy import Column, Integer, String, ForeignKey, Boolean, JSON, DateTime
from sqlalchemy.orm import relationship
from app.core.database import Base  # ← Changé !
from datetime import datetime

def utc_now():
    return datetime.utcnow()

class User(Base):
    """
    Modèle représentant un utilisateur de l'application
    """
    __tablename__ = 'users'
    
    # Identifiants
    user_id = Column(Integer, primary_key=True, index=True)
    user_full_name = Column(String(100), nullable=False)
    user_email = Column(String(100), unique=True, nullable=False, index=True)
    user_image = Column(String(255), nullable=True)
    
    # Abonnement
    user_subscription_id = Column(Integer, ForeignKey('subscriptions.subscription_id'), nullable=False)
    
    # Statut
    is_active = Column(Boolean, default=True)
    preferences = Column(JSON, nullable=True)  # Stocke les préférences utilisateur (langue, thème, etc.)
    
    # Dates
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)
    
    # ===== RELATIONS =====
    # Ces relations seront définies après l'import des autres modèles
    # Elles sont commentées ici pour éviter les imports circulaires
    scans = relationship("Scan", back_populates="user")
    favorites = relationship("Favorite", back_populates="user")
    playlists = relationship("Playlist", back_populates="user")
    activities = relationship("UserActivity", back_populates="user")
    password = relationship("UserPassword", back_populates="user", uselist=False)
    subscription = relationship("Subscription", back_populates="users")


class UserPassword(Base):
    """
    Modèle pour stocker les mots de passe de façon sécurisée (séparé de User)
    """
    __tablename__ = 'user_passwords'
    
    password_id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey('users.user_id'), nullable=False, unique=True)
    
    # Données sensibles
    password_hash = Column(String(255), nullable=False)
    
    # Sécurité
    login_attempts = Column(Integer, default=0)           # Tentatives échouées
    locked_until = Column(DateTime(timezone=True), nullable=True)  # Verrouillage temporaire
    last_login = Column(DateTime(timezone=True), nullable=True)
    
    # Réinitialisation de mot de passe
    password_reset_token = Column(String(255), nullable=True)
    password_reset_expires = Column(DateTime(timezone=True), nullable=True)
    
    # Dates
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)
    
    # Relations
    user = relationship("User", back_populates="password")