# app/core/orchestrator/image_orchestrator.py (extrait modifié)
from typing import Dict, Any, Optional
import logging
from app.core.modules.openai.vision import VisionClient
from app.core.modules.spotify.client import SpotifyClient
from app.core.modules.tmdb.client import TMDBClient
from app.core.modules.justwatch.client import JustWatchClient  # NOUVEAU
from app.core.orchestrator.decision_engine import DecisionEngine
from app.core.config import settings
from app.models import User

logger = logging.getLogger(__name__)

class ImageOrchestrator:
    """
    Orchestrateur image intelligent.
    """
    
    def __init__(self):
        self.vision = VisionClient()
        self.spotify = SpotifyClient() if settings.SPOTIFY_ENABLED else None
        self.tmdb = TMDBClient() if settings.TMDB_ENABLED else None
        self.justwatch = JustWatchClient() if settings.JUSTWATCH_ENABLED else None  # NOUVEAU
        self.decision_engine = DecisionEngine()
    
    async def process_image(self, file_path: str, user: User, db_session) -> Dict[str, Any]:
        """
        Traite une image de façon intelligente.
        """
        logger.info(f"Début traitement image: {file_path}")
        
        # Étape 1: Analyse Vision
        vision_result = await self.vision.analyze(file_path)
        
        # Étape 2: Analyse GPT de la description
        analysis = await self.decision_engine.analyze_image_content(vision_result.get("description", ""))
        
        enriched_result = None
        streaming_info = None
        
        # Étape 3: Enrichissement conditionnel
        if analysis.get("should_enrich", False):
            content_type = analysis.get("content_type")
            
            if content_type == "album_cover" and analysis.get("possible_title") and self.spotify:
                logger.info("Pochette d'album détectée, recherche Spotify...")
                enriched_result = await self.spotify.search_album(analysis["possible_title"])
                
            elif content_type == "movie_poster" and analysis.get("possible_title") and self.tmdb:
                logger.info("Affiche de film détectée, recherche TMDB...")
                enriched_result = await self.tmdb.search_movie(
                    analysis["possible_title"],
                    analysis.get("possible_year")
                )
                
                # Étape 4: Ajouter les infos de streaming si film trouvé
                if enriched_result and self.justwatch:
                    streaming_info = await self.justwatch.search_by_tmdb_id(enriched_result.get("tmdb_id"))
        
        # Étape 5: Construction du résultat final
        final_result = {
            "type": analysis.get("content_type", "unknown"),
            "title": analysis.get("possible_title"),
            "year": analysis.get("possible_year"),
            "description": analysis.get("description_courte"),
            "confidence": analysis.get("confidence", 0.0),
            "vision_description": vision_result.get("description"),
            "enriched_data": enriched_result,
            "streaming": streaming_info.get("streaming") if streaming_info else None  # NOUVEAU
        }
        
        logger.info(f"Traitement image terminé - type: {final_result['type']}")
        return final_result