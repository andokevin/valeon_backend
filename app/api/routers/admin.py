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

# app/api/routers/admin.py - Ajoutez cet endpoint

@router.put("/subscription-config/{subscription_name}")
async def update_subscription_config(
    subscription_name: str,
    config: dict,
    db: Session = Depends(get_db),
    admin=Depends(require_admin)
):
    """
    Endpoint pour le back-office permettant de modifier
    la configuration des abonnements en temps réel
    """
    # Vérifier que l'abonnement existe
    sub = db.query(Subscription).filter(Subscription.subscription_name == subscription_name).first()
    if not sub:
        raise HTTPException(404, "Abonnement non trouvé")
    
    # Mettre à jour la configuration en mémoire
    from app.core.subscription.manager import SubscriptionManager
    manager = SubscriptionManager()
    manager.update_subscription_config(subscription_name, config)
    
    # Optionnel: Sauvegarder dans la base de données pour persistance
    if "allowed_types" in config:
        # Vous pouvez ajouter une colonne allowed_scan_types à la table subscriptions
        # sub.allowed_scan_types = ",".join(config["allowed_types"])
        pass
    
    if "daily_limit" in config:
        sub.max_scans_per_day = config["daily_limit"]
    
    if "monthly_limit" in config:
        sub.max_scans_per_month = config["monthly_limit"]
    
    db.commit()
    
    return {
        "message": f"Configuration mise à jour pour {subscription_name}",
        "config": config
    }