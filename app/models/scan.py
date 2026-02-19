# app/models/scan.py
from sqlalchemy import Column, Integer, String, ForeignKey, DateTime, Float, JSON
from sqlalchemy.orm import relationship
from app.core.database import Base
from datetime import datetime

def utc_now():
    return datetime.utcnow()

class Scan(Base):
    """
    Modèle représentant un scan effectué par un utilisateur
    """
    __tablename__ = 'scans'
    
    scan_id = Column(Integer, primary_key=True, index=True)
    
    # Métadonnées du scan
    scan_type = Column(String(20), nullable=False)        # audio, video, image
    input_source = Column(String(20), nullable=False)     # microphone, camera, file, gallery
    
    # Fichier
    file_path = Column(String(255), nullable=True)        # Chemin du fichier sur le serveur
    file_size = Column(Integer, nullable=True)            # Taille en bytes
    
    # Traitement
    processing_time = Column(Float, nullable=True)        # Temps de traitement en secondes
    status = Column(String(20), default="pending")        # pending, processing, completed, failed
    error = Column(String(500), nullable=True)            # Message d'erreur si échec
    
    # Résultat (NOUVEAU)
    result = Column(JSON, nullable=True)                  # Résultat structuré du scan
    
    # Dates
    scan_date = Column(DateTime(timezone=True), default=utc_now, nullable=False)
    
    # Clés étrangères
    scan_user = Column(Integer, ForeignKey('users.user_id'), nullable=False, index=True)
    recognized_content_id = Column(Integer, ForeignKey('contents.content_id'), nullable=True)
    
    # Relations
    user = relationship("User", back_populates="scans")
    content = relationship("Content", back_populates="scans")
    recognition_result = relationship("RecognitionResult", back_populates="scan", uselist=False, cascade="all, delete-orphan")


class RecognitionResult(Base):
    """
    Résultat détaillé de la reconnaissance (données brutes des API)
    """
    __tablename__ = 'recognition_results'
    
    result_id = Column(Integer, primary_key=True, index=True)
    scan_id = Column(Integer, ForeignKey('scans.scan_id'), nullable=False, unique=True)
    
    # Données de reconnaissance
    raw_data = Column(JSON, nullable=True)                # Réponse JSON brute de l'API
    confidence = Column(Float, nullable=True)             # Niveau de confiance (0-1)
    processing_time = Column(Float, nullable=True)        # Temps de traitement spécifique
    model_used = Column(String(50), nullable=True)        # acrcloud, whisper, gpt4-vision, etc.
    
    # Date
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)
    
    # Relations
    scan = relationship("Scan", back_populates="recognition_result")