from typing import Dict, Any
import logging
from app.core.modules.openai.whisper import WhisperClient
from app.core.modules.acrcloud.client import ACRCloudClient
from app.core.modules.spotify.client import SpotifyClient
from app.core.modules.youtube.client import YouTubeClient
from app.core.orchestrator.decision_engine import DecisionEngine
from app.core.config import settings
from app.models import User

logger = logging.getLogger(__name__)

class AudioOrchestrator:
    def __init__(self):
        self.whisper = WhisperClient()
        self.acrcloud = ACRCloudClient() if settings.ACRCLOUD_ENABLED else None
        self.spotify = SpotifyClient() if settings.SPOTIFY_ENABLED else None
        self.youtube = YouTubeClient() if settings.YOUTUBE_ENABLED else None
        self.engine = DecisionEngine()

    async def process_audio(self, file_path: str, user: User, db) -> Dict[str, Any]:
        transcript = await self.whisper.transcribe(file_path)
        analysis = await self.engine.analyze_audio_transcript(transcript)

        acr_result = spotify_result = youtube_result = None

        if analysis.get("should_use_acrcloud") and self.acrcloud:
            acr_result = await self.acrcloud.recognize(file_path)

            if acr_result:
                # Enrichissement Spotify
                if acr_result.get("spotify_id") and self.spotify:
                    spotify_result = await self.spotify.get_track(
                        acr_result["spotify_id"]
                    )
                # Enrichissement YouTube (clip officiel)
                if self.youtube:
                    title = acr_result.get("title", "")
                    artist = acr_result.get("artist", "")
                    if title and artist:
                        youtube_result = await self.youtube.search_music_video(
                            title, artist
                        )
                    elif acr_result.get("youtube_id"):
                        youtube_result = await self.youtube.get_video_by_id(
                            acr_result["youtube_id"]
                        )

        result = await self.engine.merge_audio_results(
            transcript, acr_result, spotify_result
        )
        result["transcript"] = transcript

        # Injection liens YouTube
        if youtube_result:
            result.setdefault("external_links", {})
            result["external_links"]["youtube"] = youtube_result.get("url")
            result["external_links"]["youtube_embed"] = youtube_result.get("embed_url")
            result["youtube"] = youtube_result

        return result
