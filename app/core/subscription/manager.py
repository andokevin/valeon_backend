# app/core/subscription/manager.py
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
from fastapi import HTTPException, status
from app.models import User, Subscription, Scan
import logging

logger = logging.getLogger(__name__)

class SubscriptionManager:
    """
    Gestionnaire des abonnements et quotas.
    """
    
    async def check_scan_permission(self, user: User, media_type: str, db: Session):
        """
        Vérifie si l'utilisateur peut scanner ce type de média.
        """
        subscription = db.query(Subscription).filter(
            Subscription.subscription_id == user.user_subscription_id
        ).first()
        
        if not subscription:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Abonnement invalide"
            )
        
        # Vérifier les droits par type
        if subscription.subscription_name == "Free" and media_type != "audio":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Le plan Free permet uniquement les scans audio"
            )
        
        if subscription.subscription_name == "Basic" and media_type == "video":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Le plan Basic ne permet pas les scans vidéo"
            )
        
        # Vérifier le quota mensuel
        month_start = datetime.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        scans_month = db.query(Scan).filter(
            Scan.scan_user == user.user_id,
            Scan.scan_date >= month_start
        ).count()
        
        if scans_month >= subscription.max_scans_per_month:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Limite mensuelle atteinte ({subscription.max_scans_per_month})"
            )
        
        return True
    
    async def track_scan(self, user: User, media_type: str, db: Session):
        """
        Enregistre un scan et tracke la consommation.
        """
        # Le scan est déjà créé ailleurs, on peut juste logger
        logger.info(f"Scan {media_type} enregistré pour user {user.user_id}")
    
    async def track_token_usage(self, user_id: int, tokens: int, db: Session):
        """
        Track la consommation de tokens OpenAI.
        """
        from app.models import UserActivity
        
        activity = UserActivity(
            user_id=user_id,
            activity_type="token_usage",
            metadata={"tokens": tokens}
        )
        db.add(activity)
        db.commit()