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
        await self.sub_mgr.check_scan_permission(user, media_type, db)
        if media_type == "audio":
            result = await self.audio.process_audio(file_path, user, db)
        elif media_type == "image":
            result = await self.image.process_image(file_path, user, db)
        elif media_type == "video":
            result = await self.video.process_video(file_path, user, db)
        else:
            raise ValueError(f"Type inconnu: {media_type}")
        await self.sub_mgr.track_scan(user, media_type, db)
        return result
