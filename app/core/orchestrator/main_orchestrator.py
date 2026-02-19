# app/core/orchestrator/main_orchestrator.py
from typing import Dict, Any, Optional
import logging
from app.core.orchestrator.audio_orchestrator import AudioOrchestrator
from app.core.orchestrator.image_orchestrator import ImageOrchestrator
from app.core.orchestrator.video_orchestrator import VideoOrchestrator
from app.core.subscription.manager import SubscriptionManager
from app.models import User

logger = logging.getLogger(__name__)

class MainOrchestrator:
    """
    Orchestrateur principal - Point d'entrée unique pour tous les scans.
    Décide quel sous-orchestrateur utiliser en fonction du type de média.
    """
    
    def __init__(self):
        self.audio_orchestrator = AudioOrchestrator()
        self.image_orchestrator = ImageOrchestrator()
        self.video_orchestrator = VideoOrchestrator()
        self.subscription_manager = SubscriptionManager()
    
    async def process_scan(
        self,
        file_path: str,
        media_type: str,  # 'audio', 'image', 'video'
        user: User,
        db_session
    ) -> Dict[str, Any]:
        """
        Point d'entrée unique pour tous les scans.
        """
        logger.info(f"Traitement {media_type} pour utilisateur {user.user_id}")
        
        # 1. Vérifier les droits d'abonnement
        await self.subscription_manager.check_scan_permission(user, media_type, db_session)
        
        # 2. Router vers le bon orchestrateur
        if media_type == 'audio':
            result = await self.audio_orchestrator.process_audio(file_path, user, db_session)
        elif media_type == 'image':
            result = await self.image_orchestrator.process_image(file_path, user, db_session)
        elif media_type == 'video':
            result = await self.video_orchestrator.process_video(file_path, user, db_session)
        else:
            raise ValueError(f"Type de média inconnu: {media_type}")
        
        # 3. Tracker la consommation
        await self.subscription_manager.track_scan(user, media_type, db_session)
        
        return result