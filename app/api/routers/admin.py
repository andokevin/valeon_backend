from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import Optional
from pydantic import BaseModel
from datetime import datetime, timedelta

from app.core.database import get_db
from app.models import User, Subscription, Scan, UserActivity
from app.api.dependencies.auth import get_current_user
from app.core.config import settings

router = APIRouter(prefix="/admin", tags=["Admin"])

async def require_admin(current_user: User = Depends(get_current_user)) -> User:
    if not current_user.preferences or current_user.preferences.get("role") != "admin":
        raise HTTPException(403, "Accès administrateur requis")
    return current_user

class SubscriptionCreate(BaseModel):
    subscription_name: str
    subscription_price: float
    subscription_duration: int
    max_scans_per_day: int
    max_scans_per_month: int
    is_premium: bool = False

@router.get("/users")
async def list_users(skip: int = 0, limit: int = Query(50, le=100),
                     search: Optional[str] = None,
                     db: Session = Depends(get_db), admin=Depends(require_admin)):
    q = db.query(User)
    if search:
        q = q.filter((User.user_email.contains(search)) | (User.user_full_name.contains(search)))
    return [{"user_id": u.user_id, "email": u.user_email, "full_name": u.user_full_name,
             "is_active": u.is_active, "subscription_id": u.user_subscription_id,
             "scans_count": db.query(Scan).filter(Scan.scan_user == u.user_id).count()}
            for u in q.offset(skip).limit(limit).all()]

@router.get("/stats/overview")
async def stats_overview(db: Session = Depends(get_db), admin=Depends(require_admin)):
    total_users = db.query(User).count()
    total_scans = db.query(Scan).count()
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    scans_today = db.query(Scan).filter(Scan.scan_date >= today).count()
    by_type = db.query(Scan.scan_type, func.count(Scan.scan_id)).group_by(Scan.scan_type).all()
    return {"total_users": total_users, "total_scans": total_scans, "scans_today": scans_today,
            "scans_by_type": {t: c for t, c in by_type}}

@router.get("/subscriptions")
async def list_subs(db: Session = Depends(get_db), admin=Depends(require_admin)):
    return db.query(Subscription).all()

@router.post("/subscriptions", status_code=201)
async def create_sub(data: SubscriptionCreate, db: Session = Depends(get_db), admin=Depends(require_admin)):
    s = Subscription(**data.dict()); db.add(s); db.commit()
    return {"message": "Créé", "id": s.subscription_id}
