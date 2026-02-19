# app/api/routers/scans.py
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, BackgroundTasks, Request, status
from sqlalchemy.orm import Session
from typing import Optional
import os
from datetime import datetime
import aiofiles
import uuid
import logging

from app.core.config import settings
from app.core.database import get_db
from app.models import Scan, User
from app.api.dependencies.auth import get_current_user
from app.core.orchestrator.main_orchestrator import MainOrchestrator
from app.core.cache import cache
from app.core.rate_limiter import rate_limiter

router = APIRouter(prefix="/scans", tags=["Scans"])
orchestrator = MainOrchestrator()
logger = logging.getLogger(__name__)

async def save_upload_file(upload_file: UploadFile, subfolder: str) -> str:
    """Sauvegarde un fichier uploadé."""
    file_extension = os.path.splitext(upload_file.filename)[1].lower()
    file_name = f"{uuid.uuid4()}{file_extension}"
    
    upload_dir = os.path.join(settings.UPLOAD_PATH, subfolder, datetime.now().strftime("%Y/%m/%d"))
    os.makedirs(upload_dir, exist_ok=True)
    
    file_path = os.path.join(upload_dir, file_name)
    
    async with aiofiles.open(file_path, 'wb') as out_file:
        content = await upload_file.read()
        await out_file.write(content)
    
    return file_path

@router.post("/audio", status_code=status.HTTP_202_ACCEPTED)
async def scan_audio(
    request: Request,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    source: str = Form("file"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Scanner un fichier audio."""
    # Rate limiting
    rate_limiter.check_rate_limit(request)
    
    # Vérifier extension
    file_ext = os.path.splitext(file.filename)[1].lower()
    if file_ext not in settings.ALLOWED_AUDIO_EXTENSIONS:
        raise HTTPException(400, "Format audio non supporté")
    
    # Sauvegarder
    file_path = await save_upload_file(file, "audio")
    
    # Créer le scan
    scan = Scan(
        scan_type="audio",
        input_source=source,
        file_path=file_path,
        scan_user=current_user.user_id,
        status="processing"
    )
    db.add(scan)
    db.commit()
    db.refresh(scan)
    
    # Notifier WebSocket
    await manager.send_personal_message({
        "type": "scan_started",
        "scan_id": scan.scan_id
    }, current_user.user_id)
    
    # Traiter en arrière-plan
    background_tasks.add_task(
        process_scan_task,
        scan.scan_id,
        file_path,
        "audio",
        current_user.user_id,
        db
    )
    
    return {"scan_id": scan.scan_id, "status": "processing"}

@router.post("/image", status_code=status.HTTP_202_ACCEPTED)
async def scan_image(
    request: Request,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    source: str = Form("file"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Scanner une image."""
    rate_limiter.check_rate_limit(request)
    
    file_ext = os.path.splitext(file.filename)[1].lower()
    if file_ext not in settings.ALLOWED_IMAGE_EXTENSIONS:
        raise HTTPException(400, "Format image non supporté")
    
    file_path = await save_upload_file(file, "images")
    
    scan = Scan(
        scan_type="image",
        input_source=source,
        file_path=file_path,
        scan_user=current_user.user_id,
        status="processing"
    )
    db.add(scan)
    db.commit()
    db.refresh(scan)
    
    await manager.send_personal_message({
        "type": "scan_started",
        "scan_id": scan.scan_id
    }, current_user.user_id)
    
    background_tasks.add_task(
        process_scan_task,
        scan.scan_id,
        file_path,
        "image",
        current_user.user_id,
        db
    )
    
    return {"scan_id": scan.scan_id, "status": "processing"}

@router.post("/video", status_code=status.HTTP_202_ACCEPTED)
async def scan_video(
    request: Request,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    source: str = Form("file"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Scanner une vidéo."""
    rate_limiter.check_rate_limit(request)
    
    file_ext = os.path.splitext(file.filename)[1].lower()
    if file_ext not in settings.ALLOWED_VIDEO_EXTENSIONS:
        raise HTTPException(400, "Format vidéo non supporté")
    
    file_path = await save_upload_file(file, "videos")
    
    scan = Scan(
        scan_type="video",
        input_source=source,
        file_path=file_path,
        scan_user=current_user.user_id,
        status="processing"
    )
    db.add(scan)
    db.commit()
    db.refresh(scan)
    
    await manager.send_personal_message({
        "type": "scan_started",
        "scan_id": scan.scan_id
    }, current_user.user_id)
    
    background_tasks.add_task(
        process_scan_task,
        scan.scan_id,
        file_path,
        "video",
        current_user.user_id,
        db
    )
    
    return {"scan_id": scan.scan_id, "status": "processing"}

async def process_scan_task(scan_id: int, file_path: str, media_type: str, user_id: int, db: Session):
    """Tâche asynchrone de traitement."""
    try:
        # Récupérer l'utilisateur
        user = db.query(User).filter(User.user_id == user_id).first()
        
        # Vérifier le cache (optionnel)
        cache_key = f"scan:{media_type}:{os.path.basename(file_path)}"
        cached_result = cache.get(cache_key)
        
        if cached_result:
            result = cached_result
            logger.info(f"Résultat trouvé en cache pour {file_path}")
        else:
            # Traiter avec l'orchestrateur
            result = await orchestrator.process_scan(file_path, media_type, user, db)
            # Mettre en cache (TTL plus court pour les scans)
            cache.set(cache_key, result, ttl=300)  # 5 minutes
        
        # Mettre à jour le scan
        scan = db.query(Scan).filter(Scan.scan_id == scan_id).first()
        scan.status = "completed"
        scan.result = result
        scan.processing_time = (datetime.utcnow() - scan.scan_date).total_seconds()
        db.commit()
        
        # Notifier WebSocket
        await manager.send_personal_message({
            "type": "scan_completed",
            "scan_id": scan_id,
            "result": result
        }, user_id)
        
    except Exception as e:
        logger.error(f"Erreur scan {scan_id}: {e}", exc_info=True)
        
        scan = db.query(Scan).filter(Scan.scan_id == scan_id).first()
        if scan:
            scan.status = "failed"
            scan.error = str(e)[:500]
            db.commit()
        
        await manager.send_personal_message({
            "type": "scan_failed",
            "scan_id": scan_id,
            "error": str(e)
        }, user_id)
    
    finally:
        # Nettoyer le fichier temporaire
        if os.path.exists(file_path):
            os.remove(file_path)

@router.get("/{scan_id}")
async def get_scan_result(
    scan_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Récupère le résultat d'un scan."""
    scan = db.query(Scan).filter(
        Scan.scan_id == scan_id,
        Scan.scan_user == current_user.user_id
    ).first()
    
    if not scan:
        raise HTTPException(404, "Scan non trouvé")
    
    return {
        "scan_id": scan.scan_id,
        "status": scan.status,
        "result": scan.result,
        "error": scan.error,
        "scan_date": scan.scan_date,
        "processing_time": scan.processing_time
    }