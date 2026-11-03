# app/core/orchestrator/main_orchestrator.py
from typing import Dict, Any
import logging
from app.core.orchestrator.audio_orchestrator import AudioOrchestrator
from app.core.subscription.manager import SubscriptionManager
from app.models import User

logger = logging.getLogger(__name__)

class MainOrchestrator:
    """Valeon ne reconnaît que l'audio (musique, dialogues de films, interviews)."""

    def __init__(self):
        self.audio = AudioOrchestrator()
        self.sub_mgr = SubscriptionManager()

    async def process_scan(self, file_path: str, media_type: str, user: User, db) -> Dict[str, Any]:
        """
        Traite un scan audio. Les permissions d'abonnement sont vérifiées par la route
        avant l'upload (check_scan_permission), pour répondre 403/429 immédiatement.
        """
        if media_type != "audio":
            error_msg = f"Type de média non pris en charge: {media_type}"
            logger.error(error_msg)
            raise ValueError(error_msg)

        logger.info(f"MainOrchestrator: Scan audio pour user {user.user_id}")
        result = await self.audio.process_audio(file_path, user, db)

        # Tracker le scan pour les quotas
        await self.sub_mgr.track_scan(user, media_type, db)

        logger.info(f"MainOrchestrator: Scan audio terminé pour user {user.user_id}")
        return result
