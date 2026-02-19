# app/api/routers/admin.py
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from pydantic import BaseModel
from datetime import datetime, timedelta

from app.core.database import get_db
from app.models import User, Subscription, Scan, UserActivity
from app.api.dependencies.auth import get_current_user
from app.core.config import settings

router = APIRouter(prefix="/admin", tags=["Admin"])

# Modèles Pydantic
class UserUpdate(BaseModel):
    user_full_name: Optional[str] = None
    user_email: Optional[str] = None
    is_active: Optional[bool] = None
    subscription_id: Optional[int] = None
    preferences: Optional[dict] = None

class SubscriptionCreate(BaseModel):
    subscription_name: str
    subscription_price: float
    subscription_duration: int
    max_scans_per_day: int
    max_scans_per_month: int

class ModuleConfig(BaseModel):
    enable_acrcloud: bool
    enable_spotify: bool
    enable_tmdb: bool
    enable_youtube: bool
    enable_justwatch: bool 

# Dépendance pour vérifier les droits admin
async def get_admin_user(
    current_user: User = Depends(get_current_user)
) -> User:
    if current_user.preferences.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Accès réservé aux administrateurs")
    return current_user

# ===== GESTION UTILISATEURS =====

@router.get("/users")
async def get_users(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    search: Optional[str] = None,
    db: Session = Depends(get_db),
    admin: User = Depends(get_admin_user)
):
    """Liste tous les utilisateurs."""
    query = db.query(User)
    
    if search:
        query = query.filter(
            (User.user_email.contains(search)) |
            (User.user_full_name.contains(search))
        )
    
    users = query.offset(skip).limit(limit).all()
    
    return [
        {
            "user_id": u.user_id,
            "full_name": u.user_full_name,
            "email": u.user_email,
            "is_active": u.is_active,
            "subscription_id": u.user_subscription_id,
            "preferences": u.preferences,
            "created_at": u.created_at,
            "scans_count": db.query(Scan).filter(Scan.scan_user == u.user_id).count()
        }
        for u in users
    ]

@router.get("/users/{user_id}")
async def get_user_details(
    user_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(get_admin_user)
):
    """Détails d'un utilisateur."""
    user = db.query(User).filter(User.user_id == user_id).first()
    if not user:
        raise HTTPException(404, "Utilisateur non trouvé")
    
    scans = db.query(Scan).filter(Scan.scan_user == user_id).order_by(Scan.scan_date.desc()).limit(20).all()
    
    return {
        "user": {
            "user_id": user.user_id,
            "full_name": user.user_full_name,
            "email": user.user_email,
            "is_active": user.is_active,
            "subscription_id": user.user_subscription_id,
            "preferences": user.preferences,
            "created_at": user.created_at
        },
        "recent_scans": [
            {
                "scan_id": s.scan_id,
                "type": s.scan_type,
                "status": s.status,
                "date": s.scan_date
            }
            for s in scans
        ]
    }

@router.put("/users/{user_id}")
async def update_user(
    user_id: int,
    user_data: UserUpdate,
    db: Session = Depends(get_db),
    admin: User = Depends(get_admin_user)
):
    """Modifier un utilisateur."""
    user = db.query(User).filter(User.user_id == user_id).first()
    if not user:
        raise HTTPException(404, "Utilisateur non trouvé")
    
    if user_data.user_full_name is not None:
        user.user_full_name = user_data.user_full_name
    if user_data.user_email is not None:
        user.user_email = user_data.user_email
    if user_data.is_active is not None:
        user.is_active = user_data.is_active
    if user_data.subscription_id is not None:
        user.user_subscription_id = user_data.subscription_id
    if user_data.preferences is not None:
        user.preferences = user_data.preferences
    
    db.commit()
    
    return {"message": "Utilisateur mis à jour"}

@router.delete("/users/{user_id}")
async def delete_user(
    user_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(get_admin_user)
):
    """Supprimer un utilisateur."""
    user = db.query(User).filter(User.user_id == user_id).first()
    if not user:
        raise HTTPException(404, "Utilisateur non trouvé")
    
    db.delete(user)
    db.commit()
    
    return {"message": "Utilisateur supprimé"}

# ===== GESTION ABONNEMENTS =====

@router.get("/subscriptions")
async def get_subscriptions(
    db: Session = Depends(get_db),
    admin: User = Depends(get_admin_user)
):
    """Liste tous les abonnements."""
    subs = db.query(Subscription).all()
    return subs

@router.post("/subscriptions")
async def create_subscription(
    sub_data: SubscriptionCreate,
    db: Session = Depends(get_db),
    admin: User = Depends(get_admin_user)
):
    """Créer un nouvel abonnement."""
    sub = Subscription(
        subscription_name=sub_data.subscription_name,
        subscription_price=sub_data.subscription_price,
        subscription_duration=sub_data.subscription_duration,
        max_scans_per_day=sub_data.max_scans_per_day,
        max_scans_per_month=sub_data.max_scans_per_month
    )
    db.add(sub)
    db.commit()
    
    return {"message": "Abonnement créé", "id": sub.subscription_id}

@router.put("/subscriptions/{sub_id}")
async def update_subscription(
    sub_id: int,
    sub_data: SubscriptionCreate,
    db: Session = Depends(get_db),
    admin: User = Depends(get_admin_user)
):
    """Modifier un abonnement."""
    sub = db.query(Subscription).filter(Subscription.subscription_id == sub_id).first()
    if not sub:
        raise HTTPException(404, "Abonnement non trouvé")
    
    sub.subscription_name = sub_data.subscription_name
    sub.subscription_price = sub_data.subscription_price
    sub.subscription_duration = sub_data.subscription_duration
    sub.max_scans_per_day = sub_data.max_scans_per_day
    sub.max_scans_per_month = sub_data.max_scans_per_month
    
    db.commit()
    
    return {"message": "Abonnement mis à jour"}

@router.delete("/subscriptions/{sub_id}")
async def delete_subscription(
    sub_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(get_admin_user)
):
    """Supprimer un abonnement."""
    sub = db.query(Subscription).filter(Subscription.subscription_id == sub_id).first()
    if not sub:
        raise HTTPException(404, "Abonnement non trouvé")
    
    db.delete(sub)
    db.commit()
    
    return {"message": "Abonnement supprimé"}

# ===== STATISTIQUES =====

@router.get("/stats/overview")
async def get_stats_overview(
    db: Session = Depends(get_db),
    admin: User = Depends(get_admin_user)
):
    """Statistiques générales."""
    total_users = db.query(User).count()
    total_scans = db.query(Scan).count()
    scans_today = db.query(Scan).filter(
        Scan.scan_date >= datetime.now().replace(hour=0, minute=0, second=0)
    ).count()
    
    # Scans par type
    scans_by_type = db.query(
        Scan.scan_type,
        func.count(Scan.scan_id).label('count')
    ).group_by(Scan.scan_type).all()
    
    # Utilisateurs par abonnement
    users_by_sub = db.query(
        Subscription.subscription_name,
        func.count(User.user_id).label('count')
    ).join(User).group_by(Subscription.subscription_name).all()
    
    return {
        "total_users": total_users,
        "total_scans": total_scans,
        "scans_today": scans_today,
        "scans_by_type": {t: c for t, c in scans_by_type},
        "users_by_subscription": {s: c for s, c in users_by_sub}
    }

@router.get("/stats/token-usage")
async def get_token_usage(
    days: int = Query(7, ge=1, le=30),
    db: Session = Depends(get_db),
    admin: User = Depends(get_admin_user)
):
    """Consommation de tokens OpenAI."""
    start_date = datetime.now() - timedelta(days=days)
    
    usage = db.query(
        func.date(UserActivity.created_at).label('date'),
        func.sum(UserActivity.metadata['tokens'].astext.cast(Integer)).label('tokens')
    ).filter(
        UserActivity.activity_type == "token_usage",
        UserActivity.created_at >= start_date
    ).group_by(
        func.date(UserActivity.created_at)
    ).all()
    
    return {
        "period": f"{days} jours",
        "daily_usage": {str(u[0]): u[1] for u in usage}
    }

# ===== CONFIGURATION MODULES =====

@router.get("/config/modules")
async def get_module_config(
    admin: User = Depends(get_admin_user)
):
    """Récupère la configuration des modules."""
    return {
        "acrcloud": {
            "enabled": settings.ENABLE_ACRCLOUD,
            "configured": all([settings.ACRCLOUD_HOST, settings.ACRCLOUD_ACCESS_KEY])
        },
        "spotify": {
            "enabled": settings.ENABLE_SPOTIFY,
            "configured": all([settings.SPOTIFY_CLIENT_ID, settings.SPOTIFY_CLIENT_SECRET])
        },
        "tmdb": {
            "enabled": settings.ENABLE_TMDB,
            "configured": bool(settings.TMDB_API_KEY)
        },
        "youtube": {
            "enabled": settings.ENABLE_YOUTUBE,
            "configured": bool(settings.YOUTUBE_API_KEY)
        },
        "justwatch": {  # NOUVEAU
            "enabled": settings.ENABLE_JUSTWATCH,
            "configured": True  # Pas de clé nécessaire
        }   
    }

@router.post("/config/modules")
async def update_module_config(
    config: ModuleConfig,
    admin: User = Depends(get_admin_user)
):
    """
    Met à jour la configuration des modules.
    Note: Nécessite un redémarrage pour être effectif.
    """
    # Ici on pourrait sauvegarder en DB, mais pour l'instant on simule
    return {
        "message": "Configuration mise à jour. Redémarrage nécessaire.",
        "new_config": config.dict()
    }