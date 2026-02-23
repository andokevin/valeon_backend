from typing import Dict, Any
import logging
import os
from app.core.modules.gemini import GeminiClient
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
        self.gemini = GeminiClient()
        self.spotify = SpotifyClient() if settings.SPOTIFY_ENABLED else None
        self.tmdb = TMDBClient() if settings.TMDB_ENABLED else None
        self.justwatch = JustWatchClient() if settings.JUSTWATCH_ENABLED else None
        self.youtube = YouTubeClient() if settings.YOUTUBE_ENABLED else None
        self.engine = DecisionEngine()

    async def process_image(self, file_path: str, user: User, db) -> Dict[str, Any]:
        logger.info(f"ImageOrchestrator: Analyse de {os.path.basename(file_path)}")
        
        # Étape 1: Analyse avec Gemini Vision
        logger.info("ImageOrchestrator: Analyse Gemini Vision...")
        vision_result = await self.gemini.analyze_image(file_path)
        logger.info(f"ImageOrchestrator: Vision - type={vision_result.get('type', 'unknown')}")

        # Étape 2: Détection du type de contenu
        file_info = {
            "file_type": "image",
            "file_size": os.path.getsize(file_path) if os.path.exists(file_path) else 0,
            "filename": os.path.basename(file_path),
            "vision_type": vision_result.get("type"),
            "has_text": bool(vision_result.get("text")),
            "labels": vision_result.get("labels", [])[:5]
        }
        
        content_detection = await self.engine.detect_content_type(file_info)
        content_type = content_detection.get("content_type", vision_result.get("type", "unknown"))
        confidence = content_detection.get("confidence", vision_result.get("confidence", 0.5))
        
        logger.info(f"ImageOrchestrator: Type détecté = {content_type} (confiance: {confidence})")

        # Analyse approfondie avec DecisionEngine
        analysis = await self.engine.analyze_image_content(vision_result)
        
        # Initialisation des résultats
        enriched = None
        streaming = None
        youtube_result = None
        tmdb_result = None
        spotify_result = None

        # Étape 3: Enrichissement selon le type détecté
        possible_title = analysis.get("possible_title") or vision_result.get("title") or content_detection.get("possible_title")
        possible_artist = analysis.get("possible_artist") or vision_result.get("artist") or content_detection.get("possible_artist")
        possible_year = analysis.get("possible_year")

        # Cas 1: Pochette d'album
        if content_type in ["album_cover", "album"] or "album" in str(vision_result.get("labels", [])).lower():
            logger.info(f"ImageOrchestrator: Pochette d'album détectée - recherche Spotify...")
            if possible_title and self.spotify:
                spotify_result = await self.spotify.search_album(possible_title)
                enriched = spotify_result
                
                # Clip YouTube
                if possible_artist and self.youtube:
                    youtube_result = await self.youtube.search_music_video(possible_title, possible_artist)

        # Cas 2: Affiche de film
        elif content_type in ["movie_poster", "movie", "film"] or "poster" in str(vision_result.get("labels", [])).lower():
            logger.info(f"ImageOrchestrator: Affiche de film détectée - recherche TMDB...")
            if possible_title and self.tmdb:
                tmdb_result = await self.tmdb.search_movie(possible_title, possible_year)
                enriched = tmdb_result
                
                if tmdb_result:
                    # Streaming JustWatch
                    if self.justwatch:
                        streaming = await self.justwatch.search_by_tmdb_id(tmdb_result.get("tmdb_id"))
                    
                    # Trailer YouTube
                    if self.youtube:
                        youtube_result = await self.youtube.search_trailer(
                            tmdb_result.get("title", ""),
                            tmdb_result.get("release_date", "")[:4] if tmdb_result.get("release_date") else None
                        )

        # Cas 3: Capture d'écran de film
        elif content_type in ["movie_screenshot", "screenshot"] or "screenshot" in str(vision_result.get("labels", [])).lower():
            logger.info(f"ImageOrchestrator: Capture d'écran détectée - recherche TMDB...")
            # Chercher avec le texte OCR si disponible
            if vision_result.get("text") and self.tmdb:
                search_text = vision_result.get("text")[:100]
                tmdb_result = await self.tmdb.search_movie(search_text)
                enriched = tmdb_result
                
                if tmdb_result and self.youtube:
                    youtube_result = await self.youtube.search_trailer(
                        tmdb_result.get("title", "")
                    )

        # Cas 4: Photo d'artiste
        elif content_type in ["artist_photo", "portrait"] or "person" in str(vision_result.get("labels", [])).lower():
            logger.info(f"ImageOrchestrator: Photo d'artiste détectée")
            # On garde juste la description

        # Étape 4: Construction du résultat
        result = {
            "type": content_type,
            "title": possible_title or vision_result.get("title"),
            "artist": possible_artist,
            "year": possible_year,
            "confidence": confidence,
            "description": vision_result.get("description", ""),
            "labels": vision_result.get("labels", []),
            "text_detected": vision_result.get("text", ""),
            "detection": {
                "method": "gemini_vision",
                "confidence": confidence,
                "type_detected": content_type
            }
        }

        # Ajouter les enrichissements
        if enriched:
            result["enriched_data"] = enriched
        
        if streaming:
            result["streaming"] = streaming.get("streaming")
        
        if spotify_result:
            result["spotify"] = spotify_result
        
        if tmdb_result:
            result["tmdb"] = tmdb_result

        if youtube_result:
            result.setdefault("external_links", {})
            result["external_links"]["youtube"] = youtube_result.get("url")
            result["external_links"]["youtube_embed"] = youtube_result.get("embed_url")
            result["youtube"] = youtube_result

        logger.info(f"ImageOrchestrator: Terminé - {result.get('title', 'inconnu')}")
        return result