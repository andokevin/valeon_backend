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
from app.services.vision.justwatch_client import JustWatchClient  # AJOUT
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
justwatch_client = JustWatchClient()  # AJOUT

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

async def update_scan_progress(scan_id: int, user_id: int, progress: int, message: str):
    """Met à jour la progression d'un scan et notifie via WebSocket"""
    await manager.send_personal_message({
        "type": "scan_progress",
        "scan_id": scan_id,
        "progress": progress,
        "message": message
    }, user_id)

# ==================== SCAN AUDIO ====================

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
    """Traite un scan audio en arrière-plan avec YouTube"""
    start_time = datetime.now()
    scan = db.query(Scan).filter(Scan.scan_id == scan_id).first()
    
    try:
        # Mettre à jour la progression
        await update_scan_progress(scan_id, user_id, 10, "Analyse audio...")
        
        # Reconnaissance audio
        recognition_result = await audio_recognizer.recognize_from_file(file_path)
        
        await update_scan_progress(scan_id, user_id, 50, "Recherche sur Spotify et YouTube...")
        
        # Chercher sur Spotify et YouTube
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
                        youtube_id=youtube_videos[0]['youtube_id'] if youtube_videos else None,
                        metadata={
                            'popularity': spotify_result['popularity'],
                            'artists': spotify_result['artists'],
                            'youtube': youtube_data
                        }
                    )
                    db.add(content)
                    db.flush()
                    
                    # AJOUT: Ajouter les liens YouTube
                    if youtube_videos:
                        for vid in youtube_videos[:3]:
                            external_link = ExternalLink(
                                content_id=content.content_id,
                                platform="youtube",
                                link_url=vid['url'],
                                embed_url=vid['embed_url'],
                                metadata={
                                    'title': vid['title'],
                                    'thumbnail': vid['thumbnail'],
                                    'view_count': vid['view_count']
                                }
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
                "youtube": recognition_result.get('youtube')
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

# ==================== SCAN IMAGE ====================

@router.post("/image", response_model=ScanResponse, status_code=status.HTTP_202_ACCEPTED)
async def scan_image(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    source: str = Form("file"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Scanner une image pour identifier son contenu
    """
    await check_scan_limit(current_user, db)
    
    file_ext = os.path.splitext(file.filename)[1].lower()
    if file_ext not in settings.ALLOWED_IMAGE_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Format image non supporté. Formats acceptés: {settings.ALLOWED_IMAGE_EXTENSIONS}"
        )
    
    content = await file.read()
    file_size = len(content)
    await file.seek(0)
    
    if file_size > settings.MAX_UPLOAD_SIZE:
        raise HTTPException(
            status_code=400,
            detail=f"Fichier trop volumineux. Taille maximale: {settings.MAX_UPLOAD_SIZE / 1024 / 1024}MB"
        )
    
    file_path = await save_upload_file(file, "images")
    
    scan = Scan(
        scan_type="image",
        input_source=source,
        file_path=file_path,
        file_size=file_size,
        scan_user=current_user.user_id,
        status="processing"
    )
    db.add(scan)
    db.commit()
    db.refresh(scan)
    
    await manager.send_personal_message({
        "type": "scan_started",
        "scan_id": scan.scan_id,
        "scan_type": "image"
    }, current_user.user_id)
    
    background_tasks.add_task(
        process_image_scan,
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

async def process_image_scan(scan_id: int, file_path: str, user_id: int, db: Session):
    """Traite un scan image en arrière-plan avec JustWatch"""
    start_time = datetime.now()
    scan = db.query(Scan).filter(Scan.scan_id == scan_id).first()
    
    try:
        await update_scan_progress(scan_id, user_id, 10, "Analyse de l'image...")
        
        recognition_result = await vision_recognizer.recognize_from_image(file_path)
        
        await update_scan_progress(scan_id, user_id, 50, "Recherche sur TMDB et JustWatch...")
        
        content = None
        if recognition_result.get('title'):
            # Chercher sur TMDB
            tmdb_result = await tmdb_client.search_movie(recognition_result['title'])
            
            # AJOUT: Chercher sur JustWatch pour la disponibilité streaming
            justwatch_result = None
            if tmdb_result:
                justwatch_result = await justwatch_client.search_by_tmdb_id(tmdb_result['tmdb_id'])
            else:
                justwatch_result = await justwatch_client.search_movie(
                    recognition_result['title'],
                    recognition_result.get('year')
                )
            
            if tmdb_result or justwatch_result:
                # Vérifier si le contenu existe déjà
                if tmdb_result:
                    content = db.query(Content).filter(
                        Content.tmdb_id == tmdb_result['tmdb_id']
                    ).first()
                elif justwatch_result:
                    content = db.query(Content).filter(
                        Content.justwatch_id == justwatch_result['justwatch_id']
                    ).first()
                
                if not content:
                    # Fusionner les données TMDB et JustWatch
                    content_data = {
                        "content_type": "movie",
                        "content_title": tmdb_result['title'] if tmdb_result else recognition_result['title'],
                        "content_original_title": tmdb_result.get('original_title') if tmdb_result else None,
                        "content_description": tmdb_result.get('description') if tmdb_result else recognition_result.get('description'),
                        "content_release_date": tmdb_result.get('release_date') if tmdb_result else str(recognition_result.get('year')),
                        "content_image": tmdb_result.get('poster_path') if tmdb_result else (justwatch_result.get('poster') if justwatch_result else None),
                        "content_backdrop": tmdb_result.get('backdrop_path') if tmdb_result else None,
                        "content_rating": tmdb_result.get('vote_average') if tmdb_result else None,
                        "content_vote_count": tmdb_result.get('vote_count') if tmdb_result else None,
                        "tmdb_id": tmdb_result['tmdb_id'] if tmdb_result else None,
                        "justwatch_id": justwatch_result['justwatch_id'] if justwatch_result else None,
                        "metadata": {
                            'genres': tmdb_result.get('genres', []) if tmdb_result else (justwatch_result.get('genres', []) if justwatch_result else []),
                            'cast': tmdb_result.get('cast', []) if tmdb_result else None,
                            'director': tmdb_result.get('director') if tmdb_result else None,
                            'runtime': tmdb_result.get('runtime') if tmdb_result else justwatch_result.get('runtime'),
                            'streaming': justwatch_result.get('streaming') if justwatch_result else None
                        }
                    }
                    
                    content = Content(**content_data)
                    db.add(content)
                    db.flush()
                    
                    # AJOUT: Ajouter les liens vers les plateformes de streaming
                    if justwatch_result and justwatch_result.get('streaming'):
                        streaming_data = justwatch_result['streaming']
                        
                        # Ajouter les liens streaming (abonnement)
                        for provider in streaming_data.get('streaming', []):
                            if provider.get('url'):
                                external_link = ExternalLink(
                                    content_id=content.content_id,
                                    platform=provider['provider'].lower().replace(' ', '_'),
                                    link_url=provider['url'],
                                    metadata={
                                        'type': 'streaming',
                                        'provider': provider['provider'],
                                        'icon': provider.get('icon'),
                                        'quality': provider.get('presentation_type')
                                    }
                                )
                                db.add(external_link)
                        
                        # Ajouter les liens location
                        for provider in streaming_data.get('rent', []):
                            if provider.get('url'):
                                external_link = ExternalLink(
                                    content_id=content.content_id,
                                    platform=f"{provider['provider'].lower().replace(' ', '_')}_rent",
                                    link_url=provider['url'],
                                    metadata={
                                        'type': 'rent',
                                        'provider': provider['provider'],
                                        'price': provider.get('price'),
                                        'currency': provider.get('currency')
                                    }
                                )
                                db.add(external_link)
                        
                        # Ajouter les liens achat
                        for provider in streaming_data.get('buy', []):
                            if provider.get('url'):
                                external_link = ExternalLink(
                                    content_id=content.content_id,
                                    platform=f"{provider['provider'].lower().replace(' ', '_')}_buy",
                                    link_url=provider['url'],
                                    metadata={
                                        'type': 'buy',
                                        'provider': provider['provider'],
                                        'price': provider.get('price'),
                                        'currency': provider.get('currency')
                                    }
                                )
                                db.add(external_link)
                
                scan.recognized_content_id = content.content_id
                
                # AJOUT: Ajouter les infos streaming au recognition_result
                if justwatch_result:
                    recognition_result['streaming'] = justwatch_result.get('streaming')
                    recognition_result['justwatch'] = {
                        'id': justwatch_result.get('justwatch_id'),
                        'available_on': list(justwatch_result.get('streaming', {}).keys())
                    }
        
        await update_scan_progress(scan_id, user_id, 90, "Finalisation...")
        
        processing_time = (datetime.now() - start_time).total_seconds()
        result_db = RecognitionResult(
            scan_id=scan_id,
            raw_data=recognition_result,
            confidence=recognition_result.get('confidence', 0.8),
            processing_time=processing_time,
            model_used=recognition_result.get('source', 'merged')
        )
        db.add(result_db)
        
        scan.status = "completed"
        scan.processing_time = processing_time
        
        activity = UserActivity(
            user_id=user_id,
            activity_type="scan",
            content_id=content.content_id if content else None,
            metadata={"scan_id": scan_id, "scan_type": "image"}
        )
        db.add(activity)
        
        db.commit()
        
        await manager.send_personal_message({
            "type": "scan_completed",
            "scan_id": scan_id,
            "result": {
                "recognition": recognition_result,
                "content_id": content.content_id if content else None,
                "streaming": recognition_result.get('streaming')
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
        
        await manager.send_personal_message({
            "type": "scan_failed",
            "scan_id": scan_id,
            "error": str(e)
        }, user_id)
        
        print(f"Erreur scan image {scan_id}: {e}")

# ==================== SCAN VIDEO ====================

@router.post("/video", response_model=ScanResponse, status_code=status.HTTP_202_ACCEPTED)
async def scan_video(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    source: str = Form("file"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Scanner une vidéo pour identifier son contenu
    """
    await check_scan_limit(current_user, db)
    
    file_ext = os.path.splitext(file.filename)[1].lower()
    if file_ext not in settings.ALLOWED_VIDEO_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Format vidéo non supporté. Formats acceptés: {settings.ALLOWED_VIDEO_EXTENSIONS}"
        )
    
    content = await file.read()
    file_size = len(content)
    await file.seek(0)
    
    if file_size > settings.MAX_UPLOAD_SIZE:
        raise HTTPException(
            status_code=400,
            detail=f"Fichier trop volumineux. Taille maximale: {settings.MAX_UPLOAD_SIZE / 1024 / 1024}MB"
        )
    
    file_path = await save_upload_file(file, "videos")
    
    scan = Scan(
        scan_type="video",
        input_source=source,
        file_path=file_path,
        file_size=file_size,
        scan_user=current_user.user_id,
        status="processing"
    )
    db.add(scan)
    db.commit()
    db.refresh(scan)
    
    await manager.send_personal_message({
        "type": "scan_started",
        "scan_id": scan.scan_id,
        "scan_type": "video"
    }, current_user.user_id)
    
    background_tasks.add_task(
        process_video_scan,
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

async def process_video_scan(scan_id: int, file_path: str, user_id: int, db: Session):
    """Traite un scan vidéo en arrière-plan avec JustWatch"""
    start_time = datetime.now()
    scan = db.query(Scan).filter(Scan.scan_id == scan_id).first()
    
    try:
        await update_scan_progress(scan_id, user_id, 5, "Extraction des frames...")
        
        recognition_result = await video_processor.recognize_video(file_path)
        
        await update_scan_progress(scan_id, user_id, 60, "Recherche sur TMDB et JustWatch...")
        
        content = None
        if recognition_result.get('title'):
            # Chercher sur TMDB
            tmdb_result = await tmdb_client.search_movie(recognition_result['title'])
            
            # AJOUT: Chercher sur JustWatch
            justwatch_result = None
            if tmdb_result:
                justwatch_result = await justwatch_client.search_by_tmdb_id(tmdb_result['tmdb_id'])
            else:
                justwatch_result = await justwatch_client.search_movie(
                    recognition_result['title'],
                    recognition_result.get('year')
                )
            
            if tmdb_result or justwatch_result:
                # Vérifier si le contenu existe déjà
                if tmdb_result:
                    content = db.query(Content).filter(
                        Content.tmdb_id == tmdb_result['tmdb_id']
                    ).first()
                elif justwatch_result:
                    content = db.query(Content).filter(
                        Content.justwatch_id == justwatch_result['justwatch_id']
                    ).first()
                
                if not content:
                    content = Content(
                        content_type="movie",
                        content_title=tmdb_result['title'] if tmdb_result else recognition_result['title'],
                        content_original_title=tmdb_result.get('original_title') if tmdb_result else None,
                        content_description=tmdb_result.get('description') if tmdb_result else recognition_result.get('description'),
                        content_release_date=tmdb_result.get('release_date') if tmdb_result else str(recognition_result.get('year')),
                        content_image=tmdb_result.get('poster_path') if tmdb_result else (justwatch_result.get('poster') if justwatch_result else None),
                        content_backdrop=tmdb_result.get('backdrop_path') if tmdb_result else None,
                        content_rating=tmdb_result.get('vote_average') if tmdb_result else None,
                        tmdb_id=tmdb_result['tmdb_id'] if tmdb_result else None,
                        justwatch_id=justwatch_result['justwatch_id'] if justwatch_result else None,
                        metadata={
                            'genres': tmdb_result.get('genres', []) if tmdb_result else (justwatch_result.get('genres', []) if justwatch_result else []),
                            'cast': tmdb_result.get('cast', []) if tmdb_result else None,
                            'director': tmdb_result.get('director') if tmdb_result else None,
                            'runtime': tmdb_result.get('runtime') if tmdb_result else justwatch_result.get('runtime'),
                            'streaming': justwatch_result.get('streaming') if justwatch_result else None
                        }
                    )
                    db.add(content)
                    db.flush()
                
                scan.recognized_content_id = content.content_id
                
                if justwatch_result:
                    recognition_result['streaming'] = justwatch_result.get('streaming')
        
        await update_scan_progress(scan_id, user_id, 90, "Finalisation...")
        
        processing_time = (datetime.now() - start_time).total_seconds()
        result_db = RecognitionResult(
            scan_id=scan_id,
            raw_data=recognition_result,
            confidence=0.8,
            processing_time=processing_time,
            model_used="video_processor"
        )
        db.add(result_db)
        
        scan.status = "completed"
        scan.processing_time = processing_time
        
        activity = UserActivity(
            user_id=user_id,
            activity_type="scan",
            content_id=content.content_id if content else None,
            metadata={"scan_id": scan_id, "scan_type": "video"}
        )
        db.add(activity)
        
        db.commit()
        
        await manager.send_personal_message({
            "type": "scan_completed",
            "scan_id": scan_id,
            "result": {
                "recognition": recognition_result,
                "content_id": content.content_id if content else None,
                "streaming": recognition_result.get('streaming')
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
        
        await manager.send_personal_message({
            "type": "scan_failed",
            "scan_id": scan_id,
            "error": str(e)
        }, user_id)
        
        print(f"Erreur scan vidéo {scan_id}: {e}")

# ==================== ENDPOINTS DE RÉCUPÉRATION ====================

@router.get("/{scan_id}", response_model=ScanDetailResponse)
async def get_scan_result(
    scan_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Récupère le résultat d'un scan
    """
    scan = db.query(Scan).filter(
        Scan.scan_id == scan_id,
        Scan.scan_user == current_user.user_id
    ).first()
    
    if not scan:
        raise HTTPException(status_code=404, detail="Scan non trouvé")
    
    result = {
        "scan_id": scan.scan_id,
        "scan_type": scan.scan_type,
        "input_source": scan.input_source,
        "status": scan.status,
        "scan_date": scan.scan_date,
        "processing_time": scan.processing_time
    }
    
    if scan.recognition_result:
        result["recognition"] = scan.recognition_result.raw_data
    
    if scan.content:
        result["content"] = {
            "content_id": scan.content.content_id,
            "title": scan.content.content_title,
            "type": scan.content.content_type,
            "artist": scan.content.content_artist,
            "description": scan.content.content_description,
            "image": scan.content.content_image,
            "release_date": scan.content.content_release_date,
            "metadata": scan.content.metadata  # Inclut streaming pour les films
        }
    
    if scan.file_path:
        # Générer une URL pour le fichier
        file_url = f"/uploads/{os.path.relpath(scan.file_path, settings.UPLOAD_PATH)}"
        result["file_url"] = file_url
    
    return result

@router.get("/", response_model=ScanHistoryResponse)
async def get_scan_history(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    scan_type: Optional[str] = Query(None, regex="^(audio|image|video)$"),
    status: Optional[str] = Query(None, regex="^(pending|processing|completed|failed)$"),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    sort_by: str = Query("date", regex="^(date|processing_time)$"),
    order: str = Query("desc", regex="^(asc|desc)$")
):
    """
    Récupère l'historique des scans de l'utilisateur
    """
    query = db.query(Scan).filter(Scan.scan_user == current_user.user_id)
    
    if scan_type:
        query = query.filter(Scan.scan_type == scan_type)
    
    if status:
        query = query.filter(Scan.status == status)
    
    # Tri
    if sort_by == "date":
        order_column = Scan.scan_date
    else:
        order_column = Scan.processing_time
    
    if order == "desc":
        query = query.order_by(desc(order_column))
    else:
        query = query.order_by(order_column)
    
    total = query.count()
    scans = query.offset(skip).limit(limit).all()
    
    return {
        "total": total,
        "scans": [
            {
                "scan_id": s.scan_id,
                "scan_type": s.scan_type,
                "input_source": s.input_source,
                "status": s.status,
                "scan_date": s.scan_date,
                "processing_time": s.processing_time
            }
            for s in scans
        ]
    }

@router.get("/stats/daily")
async def get_daily_scan_stats(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    days: int = Query(7, ge=1, le=30)
):
    """
    Récupère les statistiques quotidiennes des scans
    """
    start_date = datetime.now() - timedelta(days=days)
    
    # Récupérer les scans des derniers jours
    scans = db.query(
        func.date(Scan.scan_date).label('date'),
        Scan.scan_type,
        func.count().label('count')
    ).filter(
        Scan.scan_user == current_user.user_id,
        Scan.scan_date >= start_date
    ).group_by(
        func.date(Scan.scan_date),
        Scan.scan_type
    ).all()
    
    # Organiser les données
    stats = {}
    for scan_date, scan_type, count in scans:
        date_str = scan_date.strftime("%Y-%m-%d")
        if date_str not in stats:
            stats[date_str] = {}
        stats[date_str][scan_type] = count
    
    return {
        "period": f"{days} days",
        "stats": stats
    }

@router.delete("/{scan_id}")
async def delete_scan(
    scan_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Supprime un scan de l'historique
    """
    scan = db.query(Scan).filter(
        Scan.scan_id == scan_id,
        Scan.scan_user == current_user.user_id
    ).first()
    
    if not scan:
        raise HTTPException(status_code=404, detail="Scan non trouvé")
    
    # Supprimer le fichier associé
    if scan.file_path and os.path.exists(scan.file_path):
        os.remove(scan.file_path)
    
    db.delete(scan)
    db.commit()
    
    return {"message": "Scan supprimé avec succès"}