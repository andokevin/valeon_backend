# app/core/orchestrator/main_orchestrator.py
from typing import Dict, Any
import logging
from app.core.orchestrator.audio_orchestrator import AudioOrchestrator
from app.core.orchestrator.image_orchestrator import ImageOrchestrator
from app.core.orchestrator.video_orchestrator import VideoOrchestrator
from app.core.subscription.manager import SubscriptionManager
from app.models import User

logger = logging.getLogger(__name__)

class MainOrchestrator:
    def __init__(self):
        self.audio = AudioOrchestrator()
        self.image = ImageOrchestrator()
        self.video = VideoOrchestrator()
        self.sub_mgr = SubscriptionManager()

    async def process_scan(self, file_path: str, media_type: str, user: User, db) -> Dict[str, Any]:
        """
        Traite un scan en fonction de son type (audio, image, video).
        Vérifie d'abord les permissions d'abonnement, puis dirige vers l'orchestrateur approprié.
        """
        # Vérifier les permissions d'abonnement
        await self.sub_mgr.check_scan_permission(user, media_type, db)
        
        # Traitement selon le type de média
        if media_type == "audio":
            logger.info(f"MainOrchestrator: Scan audio pour user {user.user_id}")
            result = await self.audio.process_audio(file_path, user, db)
            
        elif media_type == "image":
            logger.info(f"MainOrchestrator: Scan image pour user {user.user_id}")
            result = await self.image.process_image(file_path, user, db)
            
        elif media_type == "video":
            logger.info(f"MainOrchestrator: Scan vidéo pour user {user.user_id}")
            result = await self.video.process_video(file_path, user, db)
            
        else:
            error_msg = f"Type de média inconnu: {media_type}"
            logger.error(error_msg)
            raise ValueError(error_msg)
        
        # Tracker le scan pour les quotas
        await self.sub_mgr.track_scan(user, media_type, db)
        
        logger.info(f"MainOrchestrator: Scan {media_type} terminé pour user {user.user_id}")
        return result
