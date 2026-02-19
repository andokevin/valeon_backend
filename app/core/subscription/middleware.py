# app/core/subscription/middleware.py
from fastapi import Request, HTTPException, status
from sqlalchemy.orm import Session
from functools import wraps
from app.core.database import get_db
from app.models import User, Subscription
import logging

logger = logging.getLogger(__name__)

class SubscriptionMiddleware:
    """
    Middleware pour vérifier les droits d'abonnement.
    """
    
    @staticmethod
    async def verify_scan_access(request: Request, call_next):
        """
        Middleware à ajouter sur les endpoints de scan.
        """
        # Récupérer l'utilisateur depuis le token
        user = request.state.user if hasattr(request.state, 'user') else None
        
        if not user:
            return await call_next(request)
        
        # Déterminer le type de scan depuis le path
        path = request.url.path
        if '/audio' in path:
            media_type = 'audio'
        elif '/image' in path:
            media_type = 'image'
        elif '/video' in path:
            media_type = 'video'
        else:
            return await call_next(request)
        
        # Vérifier les droits
        db = next(get_db())
        try:
            subscription = db.query(Subscription).filter(
                Subscription.subscription_id == user.user_subscription_id
            ).first()
            
            if not subscription:
                raise HTTPException(403, "Abonnement invalide")
            
            # Vérifier les droits par type
            if subscription.subscription_name == "Free" and media_type != "audio":
                raise HTTPException(403, "Le plan Free permet uniquement les scans audio")
            
            if subscription.subscription_name == "Basic" and media_type == "video":
                raise HTTPException(403, "Le plan Basic ne permet pas les scans vidéo")
            
        finally:
            db.close()
        
        return await call_next(request)