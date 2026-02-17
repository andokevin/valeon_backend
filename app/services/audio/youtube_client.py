from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, BackgroundTasks, Query, status
from sqlalchemy.orm import Session
from sqlalchemy import desc, func
from typing import Optional, List
import shutil
import os
from datetime import datetime, timedelta
import aiofiles
import uuid
import asyncio
from pydantic import BaseModel

from app.core.config import settings
from app.core.database import get_db
from app.models import Scan, User, Content, RecognitionResult, Subscription, UserActivity, ExternalLink
from app.services.audio.recognizer import AudioRecognizer
from app.services.audio.spotify_client import SpotifyClient
from app.services.audio.youtube_client import YouTubeClient  # AJOUT
from app.services.vision.recognizer import VisionRecognizer
from app.services.vision.tmdb_client import TMDBClient
from app.services.vision.video_processor import VideoProcessor
from app.api.dependencies.auth import get_current_user
from app.services.websocket.manager import manager

router = APIRouter(prefix="/scans", tags=["Scans"])

# Initialiser les services
audio_recognizer = AudioRecognizer()
vision_recognizer = VisionRecognizer()
video_processor = VideoProcessor(vision_recognizer)
spotify_client = SpotifyClient()
tmdb_client = TMDBClient()
youtube_client = YouTubeClient()  # AJOUT

# Modèles Pydantic
class ScanResponse(BaseModel):
    scan_id: int
    scan_type: str
    input_source: str
    status: str
    progress: Optional[int] = None
    scan_date: datetime
    processing_time: Optional[float] = None
    
    class Config:
        from_attributes = True

class ScanDetailResponse(ScanResponse):
    recognition: Optional[dict] = None
    content: Optional[dict] = None
    file_url: Optional[str] = None

class ScanHistoryResponse(BaseModel):
    total: int
    scans: List[ScanResponse]

async def check_scan_limit(user: User, db: Session):
    """Vérifie si l'utilisateur a dépassé sa limite de scans"""
    subscription = db.query(Subscription).filter(
        Subscription.subscription_id == user.user_subscription_id
    ).first()
    
    if not subscription:
        return True
    
    # Compter les scans aujourd'hui
    today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    scans_today = db.query(Scan).filter(
        Scan.scan_user == user.user_id,
        Scan.scan_date >= today_start
    ).count()
    
    if scans_today >= subscription.max_scans_per_day:
        # Compter pour le mois aussi
        month_start = datetime.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        scans_month = db.query(Scan).filter(
            Scan.scan_user == user.user_id,
            Scan.scan_date >= month_start
        ).count()
        
        if scans_month >= subscription.max_scans_per_month:
            raise HTTPException(
                status_code=429,
                detail=f"Limite mensuelle de {subscription.max_scans_per_month} scans atteinte"
            )
    
    return True

async def save_upload_file(upload_file: UploadFile, subfolder: str) -> str:
    """Sauvegarde un fichier uploadé et retourne son chemin"""
    # Créer un nom de fichier unique
    file_extension = os.path.splitext(upload_file.filename)[1].lower()
    file_name = f"{uuid.uuid4()}{file_extension}"
    
    # Créer le dossier si nécessaire
    upload_dir = os.path.join(settings.UPLOAD_PATH, subfolder, datetime.now().strftime("%Y/%m/%d"))
    os.makedirs(upload_dir, exist_ok=True)
    
    file_path = os.path.join(upload_dir, file_name)
    
    # Sauvegarder le fichier
    async with aiofiles.open(file_path, 'wb') as out_file:
        content = await upload_file.read()
        await out_file.write(content)
    
    return file_path

@router.post("/audio", response_model=ScanResponse, status_code=status.HTTP_202_ACCEPTED)
async def scan_audio(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    source: str = Form("file"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Scanner un fichier audio pour identifier la musique
    """
    # Vérifier la limite de scans
    await check_scan_limit(current_user, db)
    
    # Vérifier l'extension
    file_ext = os.path.splitext(file.filename)[1].lower()
    if file_ext not in settings.ALLOWED_AUDIO_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Format audio non supporté. Formats acceptés: {settings.ALLOWED_AUDIO_EXTENSIONS}"
        )
    
    # Vérifier la taille
    file_size = 0
    content = await file.read()
    file_size = len(content)
    await file.seek(0)
    
    if file_size > settings.MAX_UPLOAD_SIZE:
        raise HTTPException(
            status_code=400,
            detail=f"Fichier trop volumineux. Taille maximale: {settings.MAX_UPLOAD_SIZE / 1024 / 1024}MB"
        )
    
    # Sauvegarder le fichier
    file_path = await save_upload_file(file, "audio")
    
    # Créer l'enregistrement du scan
    scan = Scan(
        scan_type="audio",
        input_source=source,
        file_path=file_path,
        file_size=file_size,
        scan_user=current_user.user_id,
        status="processing"
    )
    db.add(scan)
    db.commit()
    db.refresh(scan)
    
    # Notifier via WebSocket
    await manager.send_personal_message({
        "type": "scan_started",
        "scan_id": scan.scan_id,
        "scan_type": "audio"
    }, current_user.user_id)
    
    # Lancer la reconnaissance en arrière-plan
    background_tasks.add_task(
        process_audio_scan,
        scan.scan_id,
        file_path,
        current_user.user_id,
        db
    )
    
    return {
        "scan_id": scan.scan_id,
        "scan_type": scan.scan_type,
        "input_source": scan.input_source,
        "status": scan.status,
        "scan_date": scan.scan_date
    }

async def process_audio_scan(scan_id: int, file_path: str, user_id: int, db: Session):
    """Traite un scan audio en arrière-plan avec AJOUT YOUTUBE"""
    start_time = datetime.now()
    scan = db.query(Scan).filter(Scan.scan_id == scan_id).first()
    
    try:
        # Mettre à jour la progression
        await update_scan_progress(scan_id, user_id, 10, "Analyse audio...")
        
        # Reconnaissance audio
        recognition_result = await audio_recognizer.recognize_from_file(file_path)
        
        await update_scan_progress(scan_id, user_id, 50, "Recherche sur Spotify et YouTube...")
        
        # Chercher sur Spotify
        content = None
        if recognition_result.get('artist') and recognition_result.get('title'):
            spotify_result = await spotify_client.search_track(
                recognition_result['title'],
                recognition_result['artist']
            )
            
            # AJOUT: Chercher sur YouTube
            youtube_videos = await youtube_client.search_music_video(
                recognition_result['title'],
                recognition_result['artist']
            )
            
            if spotify_result:
                # Vérifier si le contenu existe déjà
                content = db.query(Content).filter(
                    Content.spotify_id == spotify_result['spotify_id']
                ).first()
                
                if not content:
                    # Préparer les métadonnées YouTube
                    youtube_data = None
                    if youtube_videos:
                        youtube_data = {
                            'official': youtube_videos[0] if youtube_videos else None,
                            'count': len(youtube_videos)
                        }
                    
                    content = Content(
                        content_type="music",
                        content_title=spotify_result['title'],
                        content_artist=spotify_result['artist'],
                        content_description=f"Album: {spotify_result['album']}",
                        content_release_date=spotify_result['release_date'],
                        content_image=spotify_result['image'],
                        content_duration=spotify_result['duration_ms'] // 1000,
                        spotify_id=spotify_result['spotify_id'],
                        youtube_id=youtube_videos[0]['youtube_id'] if youtube_videos else None,  # AJOUT
                        metadata={
                            'popularity': spotify_result['popularity'],
                            'artists': spotify_result['artists'],
                            'youtube': youtube_data  # AJOUT
                        }
                    )
                    db.add(content)
                    db.flush()
                    
                    # AJOUT: Ajouter les liens YouTube
                    if youtube_videos:
                        for vid in youtube_videos[:3]:  # Limiter à 3 vidéos
                            external_link = ExternalLink(
                                content_id=content.content_id,
                                platform="youtube",
                                link_url=vid['url'],
                                embed_url=vid['embed_url']
                            )
                            db.add(external_link)
                
                scan.recognized_content_id = content.content_id
                
                # AJOUT: Ajouter les résultats YouTube au recognition_result
                if youtube_videos:
                    recognition_result['youtube'] = {
                        'videos': youtube_videos,
                        'primary': youtube_videos[0]
                    }
        
        await update_scan_progress(scan_id, user_id, 90, "Finalisation...")
        
        # Sauvegarder le résultat
        processing_time = (datetime.now() - start_time).total_seconds()
        result_db = RecognitionResult(
            scan_id=scan_id,
            raw_data=recognition_result,
            confidence=recognition_result.get('confidence', 0.5),
            processing_time=processing_time,
            model_used=recognition_result.get('source', 'merged')
        )
        db.add(result_db)
        
        scan.status = "completed"
        scan.processing_time = processing_time
        
        # Enregistrer l'activité
        activity = UserActivity(
            user_id=user_id,
            activity_type="scan",
            content_id=content.content_id if content else None,
            metadata={"scan_id": scan_id, "scan_type": "audio"}
        )
        db.add(activity)
        
        db.commit()
        
        # Notifier la complétion via WebSocket
        await manager.send_personal_message({
            "type": "scan_completed",
            "scan_id": scan_id,
            "result": {
                "recognition": recognition_result,
                "content_id": content.content_id if content else None,
                "youtube": recognition_result.get('youtube')  # AJOUT
            }
        }, user_id)
        
    except Exception as e:
        scan.status = "failed"
        error_result = RecognitionResult(
            scan_id=scan_id,
            raw_data={"error": str(e)},
            confidence=0
        )
        db.add(error_result)
        db.commit()
        
        # Notifier l'erreur via WebSocket
        await manager.send_personal_message({
            "type": "scan_failed",
            "scan_id": scan_id,
            "error": str(e)
        }, user_id)
        
        print(f"Erreur scan audio {scan_id}: {e}")

async def update_scan_progress(scan_id: int, user_id: int, progress: int, message: str):
    """Met à jour la progression d'un scan et notifie via WebSocket"""
    await manager.send_personal_message({
        "type": "scan_progress",
        "scan_id": scan_id,
        "progress": progress,
        "message": message
    }, user_id)

# [RESTE DU CODE IDENTIQUE - scan_image, scan_video, etc.]
# ... (les autres fonctions restent inchangées)