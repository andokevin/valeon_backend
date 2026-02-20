from sqlalchemy import Column, Integer, String, Float, DateTime, Boolean
from sqlalchemy.orm import relationship
from app.core.database import Base
from datetime import datetime

class Subscription(Base):
    __tablename__ = "subscriptions"
    subscription_id   = Column(Integer, primary_key=True, index=True)
    subscription_name = Column(String(50), nullable=False, unique=True)
    subscription_price    = Column(Float, nullable=False, default=0.0)
    subscription_duration = Column(Integer, nullable=False, default=0)
    max_scans_per_day     = Column(Integer, nullable=False, default=5)
    max_scans_per_month   = Column(Integer, nullable=False, default=50)
    is_premium            = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    users = relationship("User", back_populates="subscription")
