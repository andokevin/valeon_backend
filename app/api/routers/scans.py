import os, uuid, logging, asyncio
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, BackgroundTasks, Request, status
from sqlalchemy.orm import Session
import aiofiles

from app.core.config import settings
from app.core.database import get_db, SessionLocal
from app.models import Scan, User, Content
from app.api.dependencies.auth import get_current_user
from app.core.orchestrator.main_orchestrator import MainOrchestrator
from app.core.websocket.manager import manager

router = APIRouter(prefix="/scans", tags=["Scans"])
orchestrator = MainOrchestrator()
logger = logging.getLogger(__name__)

UPLOAD_CHUNK_SIZE = 1024 * 1024

async def _save_file(upload: UploadFile, subfolder: str) -> str:
    ext = os.path.splitext(upload.filename)[1].lower()
    name = f"{uuid.uuid4()}{ext}"
    directory = os.path.join(settings.UPLOAD_PATH, subfolder, datetime.now().strftime("%Y/%m/%d"))
    os.makedirs(directory, exist_ok=True)
    path = os.path.join(directory, name)
    size = 0
    async with aiofiles.open(path, "wb") as f:
        while chunk := await upload.read(UPLOAD_CHUNK_SIZE):
            size += len(chunk)
            if size > settings.MAX_UPLOAD_SIZE:
                await f.close()
                os.remove(path)
                raise HTTPException(413, f"Fichier trop volumineux (max {settings.MAX_UPLOAD_SIZE // (1024 * 1024)} Mo)")
            await f.write(chunk)
    return path

async def _create_scan(db: Session, scan_type: str, source: str, file_path: str, user_id: int) -> Scan:
    scan = Scan(scan_type=scan_type, input_source=source, file_path=file_path,
                file_size=os.path.getsize(file_path), scan_user=user_id, status="processing")
    db.add(scan); db.commit(); db.refresh(scan)
    return scan

async def _process(scan_id: int, file_path: str, media_type: str, user_id: int):
    # Session dédiée : celle de la requête est fermée quand la tâche de fond s'exécute
    db = SessionLocal()
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
                    db.rollback()

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
        db.rollback()
        scan = db.query(Scan).filter(Scan.scan_id == scan_id).first()
        if scan:
            scan.status = "failed"; scan.error = str(e)[:500]; db.commit()
        await manager.send_personal_message({"type": "scan_failed", "scan_id": scan_id, "error": str(e)}, user_id)
    finally:
        db.close()
        if os.path.exists(file_path):
            os.remove(file_path)

async def _start_scan(media_type: str, subfolder: str, allowed_extensions, label: str,
                      file: UploadFile, source: str, background_tasks: BackgroundTasks,
                      db: Session, current_user: User) -> dict:
    # Le rate limit global est déjà appliqué par le middleware de main.py
    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in allowed_extensions:
        raise HTTPException(400, f"Format {label} non supporté")
    # Quotas d'abonnement vérifiés avant l'upload : réponse 403/429 immédiate
    await orchestrator.sub_mgr.check_scan_permission(current_user, media_type, db)
    path = await _save_file(file, subfolder)
    scan = await _create_scan(db, media_type, source, path, current_user.user_id)
    background_tasks.add_task(_process, scan.scan_id, path, media_type, current_user.user_id)
    return {"scan_id": scan.scan_id, "status": "processing"}

@router.post("/audio", status_code=202)
async def scan_audio(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...), source: str = Form("file"),
    db: Session = Depends(get_db), current_user: User = Depends(get_current_user),
):
    return await _start_scan("audio", "audio", settings.ALLOWED_AUDIO_EXTENSIONS, "audio",
                             file, source, background_tasks, db, current_user)

@router.post("/image", status_code=202)
async def scan_image(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...), source: str = Form("file"),
    db: Session = Depends(get_db), current_user: User = Depends(get_current_user),
):
    return await _start_scan("image", "images", settings.ALLOWED_IMAGE_EXTENSIONS, "image",
                             file, source, background_tasks, db, current_user)

@router.post("/video", status_code=202)
async def scan_video(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...), source: str = Form("file"),
    db: Session = Depends(get_db), current_user: User = Depends(get_current_user),
):
    return await _start_scan("video", "videos", settings.ALLOWED_VIDEO_EXTENSIONS, "vidéo",
                             file, source, background_tasks, db, current_user)

@router.get("/{scan_id}")
async def get_scan(scan_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    scan = db.query(Scan).filter(Scan.scan_id == scan_id, Scan.scan_user == current_user.user_id).first()
    if not scan:
        raise HTTPException(404, "Scan non trouvé")
    return {"scan_id": scan.scan_id, "status": scan.status, "result": scan.result,
            "error": scan.error, "scan_date": scan.scan_date, "processing_time": scan.processing_time}
