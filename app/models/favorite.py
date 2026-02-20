from sqlalchemy import Column, Integer, ForeignKey, String, DateTime, UniqueConstraint
from sqlalchemy.orm import relationship
from app.core.database import Base
from datetime import datetime

class Favorite(Base):
    __tablename__ = "favorites"
    favorite_id = Column(Integer, primary_key=True, index=True)
    user_id     = Column(Integer, ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False)
    content_id  = Column(Integer, ForeignKey("contents.content_id", ondelete="CASCADE"), nullable=False)
    notes       = Column(String(500), nullable=True)
    created_at  = Column(DateTime, default=datetime.utcnow, nullable=False)
    user    = relationship("User", back_populates="favorites")
    content = relationship("Content", back_populates="favorites")
    __table_args__ = (UniqueConstraint("user_id", "content_id", name="uq_user_favorite"),)
