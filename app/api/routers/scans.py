import os, uuid, logging, asyncio
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, BackgroundTasks, Request, status
from sqlalchemy.orm import Session
import aiofiles

from app.core.config import settings
from app.core.database import get_db
from app.core.rate_limiter import rate_limiter
from app.models import Scan, User, Content  
from app.api.dependencies.auth import get_current_user
from app.core.orchestrator.main_orchestrator import MainOrchestrator
from app.core.websocket.manager import manager

router = APIRouter(prefix="/scans", tags=["Scans"])
orchestrator = MainOrchestrator()
logger = logging.getLogger(__name__)

async def _save_file(upload: UploadFile, subfolder: str) -> str:
    ext = os.path.splitext(upload.filename)[1].lower()
    name = f"{uuid.uuid4()}{ext}"
    directory = os.path.join(settings.UPLOAD_PATH, subfolder, datetime.now().strftime("%Y/%m/%d"))
    os.makedirs(directory, exist_ok=True)
    path = os.path.join(directory, name)
    async with aiofiles.open(path, "wb") as f:
        await f.write(await upload.read())
    return path

async def _create_scan(db: Session, scan_type: str, source: str, file_path: str, user_id: int) -> Scan:
    scan = Scan(scan_type=scan_type, input_source=source, file_path=file_path,
                scan_user=user_id, status="processing")
    db.add(scan); db.commit(); db.refresh(scan)
    return scan

async def _process(scan_id: int, file_path: str, media_type: str, user_id: int, db: Session):
    try:
        user = db.query(User).filter(User.user_id == user_id).first()
        result = await orchestrator.process_scan(file_path, media_type, user, db)
        
        # ===== AJOUT: CRÉER OU RÉCUPÉRER LE CONTENU =====
        content_id = None
        if result and result.get("title"):
            # Chercher si le contenu existe déjà par spotify_id ou titre+artiste
            existing_content = None
            spotify_id = result.get("spotify_id") or (result.get("spotify", {}).get("spotify_id") if result.get("spotify") else None)
            youtube_id = result.get("youtube_id") or (result.get("youtube", {}).get("video_id") if result.get("youtube") else None)
            
            if spotify_id:
                existing_content = db.query(Content).filter(Content.spotify_id == spotify_id).first()
            elif result.get("title") and result.get("artist"):
                existing_content = db.query(Content).filter(
                    Content.content_title == result.get("title"),
                    Content.content_artist == result.get("artist")
                ).first()
            
            if existing_content:
                content_id = existing_content.content_id
                result["content_id"] = content_id
                logger.info(f"✅ Contenu existant trouvé avec ID: {content_id}")
            else:
                # Créer un nouveau contenu
                try:
                    new_content = Content(
                        content_type=result.get("type", "music"),
                        content_title=result.get("title", "Inconnu"),
                        content_artist=result.get("artist"),
                        content_image=result.get("image"),
                        content_description=result.get("description"),
                        content_release_date=result.get("year"),
                        spotify_id=spotify_id,
                        youtube_id=youtube_id,
                    )
                    db.add(new_content)
                    db.flush()  # Pour obtenir l'ID sans commit final
                    content_id = new_content.content_id
                    result["content_id"] = content_id
                    logger.info(f"✅ Nouveau contenu créé avec ID: {content_id}")
                except Exception as e:
                    logger.error(f"❌ Erreur création contenu: {e}")
        
        scan = db.query(Scan).filter(Scan.scan_id == scan_id).first()
        scan.status = "completed"
        scan.result = result
        scan.recognized_content_id = content_id  # Lier le scan au contenu
        scan.processing_time = (datetime.utcnow() - scan.scan_date).total_seconds()
        db.commit()
        
        logger.info(f"📤 Scan {scan_id} terminé avec content_id: {content_id}")
        await manager.send_personal_message({"type": "scan_completed", "scan_id": scan_id, "result": result}, user_id)
        
    except Exception as e:
        logger.error(f"Scan {scan_id} failed: {e}", exc_info=True)
        scan = db.query(Scan).filter(Scan.scan_id == scan_id).first()
        if scan:
            scan.status = "failed"; scan.error = str(e)[:500]; db.commit()
        await manager.send_personal_message({"type": "scan_failed", "scan_id": scan_id, "error": str(e)}, user_id)
    finally:
        if os.path.exists(file_path):
            os.remove(file_path)

@router.post("/audio", status_code=202)
async def scan_audio(
    request: Request, background_tasks: BackgroundTasks,
    file: UploadFile = File(...), source: str = Form("file"),
    db: Session = Depends(get_db), current_user: User = Depends(get_current_user),
):
    rate_limiter.check(request)
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in settings.ALLOWED_AUDIO_EXTENSIONS:
        raise HTTPException(400, "Format audio non supporté")
    path = await _save_file(file, "audio")
    scan = await _create_scan(db, "audio", source, path, current_user.user_id)
    background_tasks.add_task(_process, scan.scan_id, path, "audio", current_user.user_id, db)
    return {"scan_id": scan.scan_id, "status": "processing"}

@router.post("/image", status_code=202)
async def scan_image(
    request: Request, background_tasks: BackgroundTasks,
    file: UploadFile = File(...), source: str = Form("file"),
    db: Session = Depends(get_db), current_user: User = Depends(get_current_user),
):
    rate_limiter.check(request)
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in settings.ALLOWED_IMAGE_EXTENSIONS:
        raise HTTPException(400, "Format image non supporté")
    path = await _save_file(file, "images")
    scan = await _create_scan(db, "image", source, path, current_user.user_id)
    background_tasks.add_task(_process, scan.scan_id, path, "image", current_user.user_id, db)
    return {"scan_id": scan.scan_id, "status": "processing"}

@router.post("/video", status_code=202)
async def scan_video(
    request: Request, background_tasks: BackgroundTasks,
    file: UploadFile = File(...), source: str = Form("file"),
    db: Session = Depends(get_db), current_user: User = Depends(get_current_user),
):
    rate_limiter.check(request)
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in settings.ALLOWED_VIDEO_EXTENSIONS:
        raise HTTPException(400, "Format vidéo non supporté")
    path = await _save_file(file, "videos")
    scan = await _create_scan(db, "video", source, path, current_user.user_id)
    background_tasks.add_task(_process, scan.scan_id, path, "video", current_user.user_id, db)
    return {"scan_id": scan.scan_id, "status": "processing"}

@router.get("/{scan_id}")
async def get_scan(scan_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    scan = db.query(Scan).filter(Scan.scan_id == scan_id, Scan.scan_user == current_user.user_id).first()
    if not scan:
        raise HTTPException(404, "Scan non trouvé")
    return {"scan_id": scan.scan_id, "status": scan.status, "result": scan.result,
            "error": scan.error, "scan_date": scan.scan_date, "processing_time": scan.processing_time}
