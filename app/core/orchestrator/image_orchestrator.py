from typing import Dict, Any
import logging
from app.core.modules.openai.vision import VisionClient
from app.core.modules.spotify.client import SpotifyClient
from app.core.modules.tmdb.client import TMDBClient
from app.core.modules.justwatch.client import JustWatchClient
from app.core.modules.youtube.client import YouTubeClient
from app.core.orchestrator.decision_engine import DecisionEngine
from app.core.config import settings
from app.models import User

logger = logging.getLogger(__name__)

class ImageOrchestrator:
    def __init__(self):
        self.vision = VisionClient()
        self.spotify = SpotifyClient() if settings.SPOTIFY_ENABLED else None
        self.tmdb = TMDBClient() if settings.TMDB_ENABLED else None
        self.justwatch = JustWatchClient() if settings.JUSTWATCH_ENABLED else None
        self.youtube = YouTubeClient() if settings.YOUTUBE_ENABLED else None
        self.engine = DecisionEngine()

    async def process_image(self, file_path: str, user: User, db) -> Dict[str, Any]:
        vision = await self.vision.analyze(file_path)
        analysis = await self.engine.analyze_image_content(
            vision.get("description", "")
        )

        enriched = streaming = youtube_result = None
        ct = analysis.get("content_type")
        possible_title = analysis.get("possible_title")
        possible_year = analysis.get("possible_year")
        possible_artist = analysis.get("possible_artist")

        if analysis.get("should_enrich"):
            if ct == "album_cover" and possible_title and self.spotify:
                enriched = await self.spotify.search_album(possible_title)
                # Clip YouTube pour l'album
                if self.youtube and possible_artist:
                    youtube_result = await self.youtube.search_music_video(
                        possible_title, possible_artist
                    )

            elif ct == "movie_poster" and possible_title and self.tmdb:
                enriched = await self.tmdb.search_movie(
                    possible_title, possible_year
                )
                if enriched:
                    if self.justwatch:
                        streaming = await self.justwatch.search_by_tmdb_id(
                            enriched.get("tmdb_id")
                        )
                    # Trailer YouTube pour le film
                    if self.youtube:
                        youtube_result = await self.youtube.search_trailer(
                            possible_title, possible_year
                        )

        result = {
            "type": ct or "unknown",
            "title": possible_title,
            "year": possible_year,
            "confidence": analysis.get("confidence", 0.0),
            "vision_description": vision.get("description"),
            "enriched_data": enriched,
            "streaming": streaming.get("streaming") if streaming else None,
        }

        if youtube_result:
            result["external_links"] = {
                "youtube": youtube_result.get("url"),
                "youtube_embed": youtube_result.get("embed_url"),
            }
            result["youtube"] = youtube_result

        return result
