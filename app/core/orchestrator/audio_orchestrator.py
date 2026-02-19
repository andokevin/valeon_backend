# app/core/orchestrator/audio_orchestrator.py
from typing import Dict, Any, Optional
import asyncio
import logging
from app.core.modules.openai.whisper import WhisperClient
from app.core.modules.acrcloud.client import ACRCloudClient
from app.core.modules.spotify.client import SpotifyClient
from app.core.orchestrator.decision_engine import DecisionEngine
from app.core.config import settings
from app.models import User

logger = logging.getLogger(__name__)

class AudioOrchestrator:
    """
    Orchestrateur audio intelligent.
    Décide dynamiquement quels appels API faire.
    """
    
    def __init__(self):
        self.whisper = WhisperClient()
        self.acrcloud = ACRCloudClient() if settings.ACRCLOUD_ENABLED else None
        self.spotify = SpotifyClient() if settings.SPOTIFY_ENABLED else None
        self.decision_engine = DecisionEngine()
    
    async def process_audio(self, file_path: str, user: User, db_session) -> Dict[str, Any]:
        """
        Traite un fichier audio de façon intelligente.
        """
        logger.info(f"Début traitement audio: {file_path}")
        
        # Étape 1: Transcription Whisper (cloud)
        transcript = await self.whisper.transcribe(file_path)
        
        # Étape 2: Analyse GPT de la transcription
        analysis = await self.decision_engine.analyze_audio_transcript(transcript)
        
        acr_result = None
        spotify_result = None
        
        # Étape 3: Appel conditionnel à ACRCloud
        if analysis.get("should_use_acrcloud", False) and self.acrcloud:
            logger.info("Musique détectée, appel à ACRCloud...")
            acr_result = await self.acrcloud.recognize(file_path)
            
            # Étape 4: Enrichissement Spotify si ACRCloud a réussi
            if acr_result and acr_result.get("spotify_id") and self.spotify:
                spotify_result = await self.spotify.get_track(acr_result["spotify_id"])
        
        # Étape 5: Si dialogue détecté
        elif analysis.get("is_dialogue", False):
            logger.info("Dialogue détecté, analyse sémantique...")
            # TODO: Logique pour détecter film/série/podcast
            pass
        
        # Étape 6: Fusion intelligente des résultats
        final_result = await self.decision_engine.merge_audio_results(
            transcript=transcript,
            acr_result=acr_result,
            spotify_result=spotify_result
        )
        
        # Ajouter la transcription pour référence
        final_result["transcript"] = transcript
        
        logger.info(f"Traitement audio terminé - type: {final_result.get('type')}")
        return final_result