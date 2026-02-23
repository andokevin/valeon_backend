from typing import Dict, Any
import logging
import os
from app.core.modules.whisper_cpp import WhisperCppClient
from app.core.modules.acrcloud.client import ACRCloudClient
from app.core.modules.spotify.client import SpotifyClient
from app.core.modules.tmdb.client import TMDBClient
from app.core.modules.youtube.client import YouTubeClient
from app.core.orchestrator.decision_engine import DecisionEngine
from app.core.config import settings
from app.models import User

logger = logging.getLogger(__name__)

class AudioOrchestrator:
    def __init__(self):
        self.whisper = WhisperCppClient() if settings.WHISPER_CPP_ENABLED else None
        self.acrcloud = ACRCloudClient()
        self.spotify = SpotifyClient() if settings.SPOTIFY_ENABLED else None
        self.tmdb = TMDBClient() if settings.TMDB_ENABLED else None
        self.youtube = YouTubeClient() if settings.YOUTUBE_ENABLED else None
        self.engine = DecisionEngine()

    async def process_audio(self, file_path: str, user: User, db) -> Dict[str, Any]:
        logger.info(f"AudioOrchestrator: Traitement de {os.path.basename(file_path)}")
        
        # Étape 1: Transcription Whisper (pour analyse)
        transcript = ""
        if self.whisper:
            logger.info("AudioOrchestrator: Transcription Whisper...")
            transcript = await self.whisper.transcribe(file_path)
            logger.info(f"AudioOrchestrator: Transcription ({len(transcript)} caractères)")

        # Étape 2: Détection du type de contenu
        file_info = {
            "file_type": "audio",
            "file_size": os.path.getsize(file_path) if os.path.exists(file_path) else 0,
            "filename": os.path.basename(file_path),
            "has_transcript": bool(transcript)
        }
        
        content_detection = await self.engine.detect_content_type(file_info)
        content_type = content_detection.get("content_type", "unknown")
        confidence = content_detection.get("confidence", 0.0)
        
        logger.info(f"AudioOrchestrator: Type détecté = {content_type} (confiance: {confidence})")

        # Initialisation des résultats
        acr_result = None
        spotify_result = None
        tmdb_result = None
        youtube_result = None

        # Étape 3: Stratégie selon le type détecté
        if content_type in ["music", "song"] or content_detection.get("should_use_acrcloud", False):
            # C'est probablement une musique → ACR Cloud
            logger.info("AudioOrchestrator: Recherche ACR Cloud...")
            acr_result = await self.acrcloud.recognize(file_path)
            
            if acr_result and acr_result.get("title"):
                logger.info(f"AudioOrchestrator: ACR Cloud a trouvé '{acr_result.get('title')}'")
                
                # Enrichissement Spotify
                if acr_result.get("spotify_id") and self.spotify:
                    logger.info("AudioOrchestrator: Enrichissement Spotify...")
                    spotify_result = await self.spotify.get_track(acr_result["spotify_id"])
                
                # Recherche YouTube
                if self.youtube:
                    title = acr_result.get("title", "")
                    artist = acr_result.get("artist", "")
                    if title and artist:
                        logger.info("AudioOrchestrator: Recherche YouTube...")
                        youtube_result = await self.youtube.search_music_video(title, artist)

        elif content_type in ["movie_dialogue", "tv_show_dialogue"]:
            # C'est un extrait de film/série → TMDB
            logger.info("AudioOrchestrator: Contenu dialogué détecté, recherche TMDB...")
            
            # Utiliser la transcription pour chercher
            if transcript and len(transcript) > 50 and self.tmdb:
                # Prendre la première phrase significative
                search_query = transcript[:100].split('.')[0]
                tmdb_result = await self.tmdb.search_movie(search_query)
                
                if tmdb_result:
                    logger.info(f"AudioOrchestrator: TMDB a trouvé '{tmdb_result.get('title')}'")
                    
                    # Trailer YouTube
                    if self.youtube:
                        youtube_result = await self.youtube.search_trailer(
                            tmdb_result.get("title", ""),
                            tmdb_result.get("release_date", "")[:4] if tmdb_result.get("release_date") else None
                        )

        elif content_type in ["podcast", "speech", "interview"]:
            # Contenu parlé → on garde juste la transcription
            logger.info("AudioOrchestrator: Contenu parlé détecté")

        # Étape 4: Fusion des résultats avec l'engine
        result = await self.engine.merge_audio_results(
            transcript=transcript,
            acr_result=acr_result,
            spotify_result=spotify_result,
            content_type=content_type
        )

        # Ajouter les métadonnées supplémentaires
        result["transcript"] = transcript if transcript else None
        result["detection"] = {
            "method": "acr_cloud" if acr_result else "analysis",
            "confidence": confidence,
            "type_detected": content_type
        }

        # Ajouter les liens YouTube/TMDB
        if youtube_result:
            result.setdefault("external_links", {})
            result["external_links"]["youtube"] = youtube_result.get("url")
            result["external_links"]["youtube_embed"] = youtube_result.get("embed_url")
            result["youtube"] = youtube_result

        if tmdb_result:
            result["tmdb"] = tmdb_result
            result.setdefault("external_links", {})
            if tmdb_result.get("imdb_id"):
                result["external_links"]["imdb"] = f"https://www.imdb.com/title/{tmdb_result['imdb_id']}"

        logger.info(f"AudioOrchestrator: Terminé - {result.get('title', 'inconnu')}")
        return result