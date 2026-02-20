from sqlalchemy import Column, Integer, String, ForeignKey, Boolean, JSON, DateTime
from sqlalchemy.orm import relationship
from app.core.database import Base
from datetime import datetime

class User(Base):
    __tablename__ = "users"
    user_id              = Column(Integer, primary_key=True, index=True)
    user_full_name       = Column(String(100), nullable=False)
    user_email           = Column(String(100), unique=True, nullable=False, index=True)
    user_image           = Column(String(255), nullable=True)
    user_subscription_id = Column(Integer, ForeignKey("subscriptions.subscription_id"), nullable=False)
    is_active            = Column(Boolean, default=True)
    preferences          = Column(JSON, nullable=True)
    created_at           = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at           = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

class UserPassword(Base):
    __tablename__ = "user_passwords"
    password_id            = Column(Integer, primary_key=True, index=True)
    user_id                = Column(Integer, ForeignKey("users.user_id"), nullable=False, unique=True)
    password_hash          = Column(String(255), nullable=False)
    login_attempts         = Column(Integer, default=0)
    locked_until           = Column(DateTime, nullable=True)
    last_login             = Column(DateTime, nullable=True)
    password_reset_token   = Column(String(255), nullable=True)
    password_reset_expires = Column(DateTime, nullable=True)
    created_at             = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at             = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    user = relationship("User", back_populates="password")
