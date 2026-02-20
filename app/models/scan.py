from sqlalchemy import Column, Integer, String, ForeignKey, DateTime, Float, JSON
from sqlalchemy.orm import relationship
from app.core.database import Base
from datetime import datetime

class Scan(Base):
    __tablename__ = "scans"
    scan_id               = Column(Integer, primary_key=True, index=True)
    scan_type             = Column(String(20), nullable=False)
    input_source          = Column(String(20), nullable=False, default="file")
    file_path             = Column(String(500), nullable=True)
    file_size             = Column(Integer, nullable=True)
    processing_time       = Column(Float, nullable=True)
    status                = Column(String(20), default="pending")
    error                 = Column(String(500), nullable=True)
    result                = Column(JSON, nullable=True)
    scan_date             = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    scan_user             = Column(Integer, ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False, index=True)
    recognized_content_id = Column(Integer, ForeignKey("contents.content_id"), nullable=True)
    user    = relationship("User", back_populates="scans", foreign_keys=[scan_user])
    content = relationship("Content", back_populates="scans", foreign_keys=[recognized_content_id])
    recognition_result = relationship("RecognitionResult", back_populates="scan", uselist=False, cascade="all, delete-orphan")

class RecognitionResult(Base):
    __tablename__ = "recognition_results"
    result_id       = Column(Integer, primary_key=True, index=True)
    scan_id         = Column(Integer, ForeignKey("scans.scan_id", ondelete="CASCADE"), nullable=False, unique=True)
    raw_data        = Column(JSON, nullable=True)
    confidence      = Column(Float, nullable=True)
    processing_time = Column(Float, nullable=True)
    model_used      = Column(String(50), nullable=True)
    created_at      = Column(DateTime, default=datetime.utcnow, nullable=False)
    scan = relationship("Scan", back_populates="recognition_result")
