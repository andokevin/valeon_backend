import asyncio
import os
import tempfile
import logging
from typing import Dict, Any, List, Optional

from app.core.modules.openai.whisper import WhisperClient
from app.core.modules.openai.vision import VisionClient
from app.core.modules.tmdb.client import TMDBClient
from app.core.modules.justwatch.client import JustWatchClient
from app.core.modules.youtube.client import YouTubeClient
from app.core.orchestrator.decision_engine import DecisionEngine
from app.core.config import settings
from app.models import User

logger = logging.getLogger(__name__)


class VideoOrchestrator:
    def __init__(self):
        self.whisper = WhisperClient()
        self.vision = VisionClient()
        self.tmdb = TMDBClient() if settings.TMDB_ENABLED else None
        self.justwatch = JustWatchClient() if settings.JUSTWATCH_ENABLED else None
        self.youtube = YouTubeClient() if settings.YOUTUBE_ENABLED else None
        self.engine = DecisionEngine()
        self.frame_interval = 30
        self.max_frames = 5

    async def process_video(self, file_path: str, user: User, db) -> Dict[str, Any]:
        # 1. Extraction audio
        audio_path = await self._extract_audio(file_path)
        transcript = {}
        if audio_path:
            transcript = await self.whisper.transcribe_with_timestamps(audio_path)

        # 2. Extraction frames + analyse vision
        frames = await asyncio.to_thread(self._extract_frames_sync, file_path)
        vision_results = []
        for fp in frames:
            vision_results.append(await self.vision.analyze(fp))
            os.unlink(fp)

        # 3. Identification TMDB
        tmdb_result = None
        text = transcript.get("text", "")
        if text and len(text) > 20 and self.tmdb:
            tmdb_result = await self.tmdb.search_movie(
                text[:100].split(".")[0]
            )

        # 4. Streaming JustWatch
        streaming = None
        if tmdb_result and self.justwatch:
            streaming = await self.justwatch.search_by_tmdb_id(
                tmdb_result.get("tmdb_id")
            )

        # 5. Trailer YouTube
        youtube_result = None
        if self.youtube and tmdb_result:
            youtube_result = await self.youtube.search_trailer(
                tmdb_result.get("title", ""),
                tmdb_result.get("release_date", "")[:4]
                if tmdb_result.get("release_date")
                else None,
            )

        # 6. Fusion résultat final (appelé UNE seule fois)
        result = await self.engine.merge_video_results(
            text, vision_results, tmdb_result
        )

        # 7. Injection enrichissements
        if streaming:
            result["streaming"] = streaming.get("streaming")

        if youtube_result:
            result["external_links"] = {
                "youtube": youtube_result.get("url"),
                "youtube_embed": youtube_result.get("embed_url"),
            }
            result["youtube"] = youtube_result

        # 8. Nettoyage fichier audio temporaire
        if audio_path and os.path.exists(audio_path):
            os.unlink(audio_path)

        return result

    async def _extract_audio(self, video_path: str) -> Optional[str]:
        try:
            audio_path = tempfile.NamedTemporaryFile(
                suffix=".mp3", delete=False
            ).name
            proc = await asyncio.create_subprocess_exec(
                "ffmpeg",
                "-i", video_path,
                "-q:a", "0",
                "-map", "a",
                "-y", audio_path,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            await proc.communicate()
            return audio_path if proc.returncode == 0 else None
        except Exception as e:
            logger.error(f"Audio extraction error: {e}")
            return None

    def _extract_frames_sync(self, video_path: str) -> List[str]:
        import cv2
        frames = []
        cap = cv2.VideoCapture(video_path)
        count = 0
        try:
            while len(frames) < self.max_frames:
                ret, frame = cap.read()
                if not ret:
                    break
                if count % self.frame_interval == 0:
                    with tempfile.NamedTemporaryFile(
                        suffix=".jpg", delete=False
                    ) as tmp:
                        cv2.imwrite(tmp.name, frame)
                        frames.append(tmp.name)
                count += 1
        finally:
            cap.release()
        return frames
