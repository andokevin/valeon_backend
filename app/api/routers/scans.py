import os, uuid, logging, asyncio
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, BackgroundTasks, Request, status
from sqlalchemy.orm import Session
import aiofiles

from app.core.config import settings
from app.core.database import get_db
from app.core.rate_limiter import rate_limiter
from app.models import Scan, User
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
        scan = db.query(Scan).filter(Scan.scan_id == scan_id).first()
        scan.status = "completed"; scan.result = result
        scan.processing_time = (datetime.utcnow() - scan.scan_date).total_seconds()
        db.commit()
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
