from sqlalchemy.orm import Session
from datetime import datetime
from fastapi import HTTPException, status
from app.models import User, Subscription, Scan, UserActivity
import logging

logger = logging.getLogger(__name__)

class SubscriptionManager:
    async def check_scan_permission(self, user: User, media_type: str, db: Session):
        sub = db.query(Subscription).filter(Subscription.subscription_id == user.user_subscription_id).first()
        if not sub:
            raise HTTPException(403, "Abonnement invalide")
        if sub.subscription_name == "Free" and media_type != "audio":
            raise HTTPException(403, "Le plan Free autorise uniquement les scans audio")
        if sub.subscription_name == "Basic" and media_type == "video":
            raise HTTPException(403, "Le plan Basic n'inclut pas les scans vidéo")
        today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        month_start = datetime.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        scans_today = db.query(Scan).filter(Scan.scan_user == user.user_id, Scan.scan_date >= today).count()
        scans_month = db.query(Scan).filter(Scan.scan_user == user.user_id, Scan.scan_date >= month_start).count()
        if scans_today >= sub.max_scans_per_day:
            raise HTTPException(429, f"Limite journalière atteinte ({sub.max_scans_per_day}/jour)")
        if scans_month >= sub.max_scans_per_month:
            raise HTTPException(429, f"Limite mensuelle atteinte ({sub.max_scans_per_month}/mois)")
        return True

    async def track_scan(self, user: User, media_type: str, db: Session):
        db.add(UserActivity(user_id=user.user_id, activity_type="scan", metadata={"media_type": media_type}))
        db.commit()
        logger.info(f"Scan {media_type} tracké pour user {user.user_id}")

    async def track_token_usage(self, user_id: int, tokens: int, model: str, db: Session):
        db.add(UserActivity(user_id=user_id, activity_type="token_usage", metadata={"tokens": tokens, "model": model}))
        db.commit()
