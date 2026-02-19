# models/subscription.py
from sqlalchemy import Column, Integer, String, Float, DateTime
from sqlalchemy.orm import relationship
from app.core.database import Base  # ← Changé !
from datetime import datetime

def utc_now():
    return datetime.utcnow()

class Subscription(Base):
    """
    Modèle représentant les différents plans d'abonnement
    """
    __tablename__ = 'subscriptions'
    
    subscription_id = Column(Integer, primary_key=True, index=True)
    subscription_name = Column(String(50), nullable=False, unique=True)  # Free, Premium, Pro
    
    # Tarification
    subscription_price = Column(Float, nullable=False)        # Prix en euros
    subscription_duration = Column(Integer, nullable=False)    # Durée en jours
    
    # Limites
    max_scans_per_day = Column(Integer, nullable=False)
    max_scans_per_month = Column(Integer, nullable=False)
    
    # Date de création
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)
    
    # Relations
    users = relationship("User", back_populates="subscription")