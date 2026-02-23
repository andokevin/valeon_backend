from sqlalchemy import Column, Integer, String, ForeignKey, JSON, DateTime
from sqlalchemy.orm import relationship
from app.core.database import Base
from datetime import datetime

class UserActivity(Base):
    __tablename__ = "user_activities"
    activity_id   = Column(Integer, primary_key=True, index=True)
    user_id       = Column(Integer, ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False)
    activity_type = Column(String(50), nullable=False)
    content_id    = Column(Integer, ForeignKey("contents.content_id"), nullable=True)
    activity_metadata      = Column(JSON, nullable=True)
    ip_address    = Column(String(50), nullable=True)
    created_at    = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    user    = relationship("User", back_populates="activities")
    content = relationship("Content", foreign_keys=[content_id])
