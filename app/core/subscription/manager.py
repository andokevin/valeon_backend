# app/core/subscription/manager.py
from sqlalchemy.orm import Session
from datetime import datetime
from fastapi import HTTPException, status
from app.models import User, Subscription, Scan, UserActivity
from app.core.config import settings
import logging

logger = logging.getLogger(__name__)

class SubscriptionManager:
    
    # Mapping des noms d'abonnement vers les clés de configuration
    _SUBSCRIPTION_CONFIG_MAP = {
        "Free": {
            "allowed_types": settings.FREE_ALLOWED_SCAN_TYPES,
            "daily_limit": settings.FREE_SCANS_PER_DAY,
            "monthly_limit": settings.FREE_SCANS_PER_MONTH
        },
        "Basic": {
            "allowed_types": settings.BASIC_ALLOWED_SCAN_TYPES,
            "daily_limit": settings.BASIC_SCANS_PER_DAY,
            "monthly_limit": settings.BASIC_SCANS_PER_MONTH
        },
        "Premium": {
            "allowed_types": settings.PREMIUM_ALLOWED_SCAN_TYPES,
            "daily_limit": settings.PREMIUM_SCANS_PER_DAY,
            "monthly_limit": settings.PREMIUM_SCANS_PER_MONTH
        }
    }

    async def check_scan_permission(self, user: User, media_type: str, db: Session):
        # Récupérer l'abonnement de l'utilisateur
        sub = db.query(Subscription).filter(Subscription.subscription_id == user.user_subscription_id).first()
        if not sub:
            raise HTTPException(403, "Abonnement invalide")
        
        # Récupérer la configuration pour cet abonnement
        sub_config = self._SUBSCRIPTION_CONFIG_MAP.get(sub.subscription_name)
        
        if not sub_config:
            logger.warning(f"Configuration non trouvée pour {sub.subscription_name}, utilisation des valeurs par défaut")
            # Fallback: autoriser tous les types
            allowed_types = ["audio", "image", "video"]
            daily_limit = 1000
            monthly_limit = 1000
        else:
            allowed_types = sub_config["allowed_types"]
            daily_limit = sub_config["daily_limit"]
            monthly_limit = sub_config["monthly_limit"]
        
        # Vérifier si le type de scan est autorisé
        if media_type not in allowed_types:
            raise HTTPException(
                403, 
                f"Le plan {sub.subscription_name} n'autorise pas les scans {media_type}. "
                f"Types autorisés: {', '.join(allowed_types)}"
            )
        
        # Vérifier les quotas
        today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        month_start = datetime.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        
        scans_today = db.query(Scan).filter(
            Scan.scan_user == user.user_id, 
            Scan.scan_date >= today
        ).count()
        
        scans_month = db.query(Scan).filter(
            Scan.scan_user == user.user_id, 
            Scan.scan_date >= month_start
        ).count()
        
        if scans_today >= daily_limit:
            raise HTTPException(429, f"Limite journalière atteinte ({daily_limit} scans/jour)")
        
        if scans_month >= monthly_limit:
            raise HTTPException(429, f"Limite mensuelle atteinte ({monthly_limit} scans/mois)")
        
        logger.info(f"✅ Scan {media_type} autorisé pour user {user.user_id} (plan: {sub.subscription_name})")
        return True

    async def track_scan(self, user: User, media_type: str, db: Session):
        db.add(UserActivity(
            user_id=user.user_id, 
            activity_type="scan", 
            metadata={"media_type": media_type}
        ))
        db.commit()
        logger.info(f"Scan {media_type} tracké pour user {user.user_id}")

    async def track_token_usage(self, user_id: int, tokens: int, model: str, db: Session):
        db.add(UserActivity(
            user_id=user_id, 
            activity_type="token_usage", 
            metadata={"tokens": tokens, "model": model}
        ))
        db.commit()

    # Méthode pour le futur back-office (mise à jour dynamique)
    def update_subscription_config(self, subscription_name: str, config: dict):
        """
        Méthode qui sera appelée par le back-office pour mettre à jour
        la configuration des abonnements sans redémarrer le serveur
        """
        if subscription_name in self._SUBSCRIPTION_CONFIG_MAP:
            self._SUBSCRIPTION_CONFIG_MAP[subscription_name].update(config)
            logger.info(f"Configuration mise à jour pour {subscription_name}: {config}")
        else:
            logger.error(f"Abonnement {subscription_name} non trouvé")