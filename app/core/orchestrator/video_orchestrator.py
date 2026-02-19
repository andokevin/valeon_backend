# app/core/orchestrator/video_orchestrator.py
import cv2
import tempfile
import os
from typing import Dict, Any, Optional, List
import asyncio
import logging
from app.core.modules.openai.whisper import WhisperClient
from app.core.modules.openai.vision import VisionClient
from app.core.modules.tmdb.client import TMDBClient
from app.core.modules.justwatch.client import JustWatchClient  # ← AJOUT IMPORTANT !
from app.core.orchestrator.decision_engine import DecisionEngine
from app.core.config import settings
from app.models import User

logger = logging.getLogger(__name__)

class VideoOrchestrator:
    """
    Orchestrateur vidéo intelligent.
    Extrait l'audio et les frames, puis fusionne les résultats.
    """
    
    def __init__(self):
        self.whisper = WhisperClient()
        self.vision = VisionClient()
        self.tmdb = TMDBClient() if settings.TMDB_ENABLED else None
        self.justwatch = JustWatchClient() if settings.JUSTWATCH_ENABLED else None  # ← AJOUT
        self.decision_engine = DecisionEngine()
        self.frame_interval = 30  # Une frame toutes les 30 frames
        self.max_frames = 5  # Maximum 5 frames à analyser
    
    async def process_video(self, file_path: str, user: User, db_session) -> Dict[str, Any]:
        """
        Traite une vidéo de façon intelligente.
        """
        logger.info(f"Début traitement vidéo: {file_path}")
        
        # Étape 1: Extraction audio
        audio_path = await self._extract_audio(file_path)
        
        # Étape 2: Transcription Whisper
        transcript = await self.whisper.transcribe_with_timestamps(audio_path) if audio_path else {"text": ""}
        
        # Étape 3: Extraction et analyse des frames clés
        frames = await self._extract_key_frames(file_path)
        vision_results = []
        
        for frame_path in frames:
            vision_result = await self.vision.analyze(frame_path)
            vision_results.append(vision_result)
            os.unlink(frame_path)  # Nettoyage
        
        # Étape 4: Recherche TMDB si titre probable
        tmdb_result = None
        if transcript.get("text") and len(transcript["text"]) > 20 and self.tmdb:
            search_query = transcript["text"][:100].split('.')[0]
            tmdb_result = await self.tmdb.search_movie(search_query)

        # Étape 5: Recherche JustWatch si film trouvé
        streaming_info = None
        if tmdb_result and self.justwatch:
            streaming_info = await self.justwatch.search_by_tmdb_id(tmdb_result.get("tmdb_id"))
        
        # Étape 6: Fusion multimodale avec GPT
        final_result = await self.decision_engine.merge_video_results(
            audio_transcript=transcript.get("text", ""),
            vision_results=vision_results,
            tmdb_result=tmdb_result
        )

        # Ajouter les infos de streaming
        if streaming_info:
            final_result["streaming"] = streaming_info.get("streaming")
        
        # Nettoyage
        if audio_path and os.path.exists(audio_path):
            os.unlink(audio_path)
        
        logger.info(f"Traitement vidéo terminé - type: {final_result.get('type')}")
        return final_result
    
    async def _extract_audio(self, video_path: str) -> Optional[str]:
        """Extrait l'audio d'une vidéo en utilisant ffmpeg."""
        try:
            import subprocess
            
            audio_path = tempfile.NamedTemporaryFile(suffix='.mp3', delete=False).name
            
            cmd = [
                'ffmpeg', '-i', video_path,
                '-q:a', '0', '-map', 'a',
                '-y', audio_path
            ]
            
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            await process.communicate()
            
            if process.returncode == 0:
                logger.info(f"Audio extrait avec succès: {audio_path}")
                return audio_path
            else:
                logger.error("Erreur extraction audio")
                return None
                
        except Exception as e:
            logger.error(f"Erreur extraction audio: {e}")
            return None
    
    async def _extract_key_frames(self, video_path: str) -> List[str]:
        """Extrait les frames clés d'une vidéo."""
        frames = []
        cap = cv2.VideoCapture(video_path)
        frame_count = 0
        
        try:
            while len(frames) < self.max_frames:
                ret, frame = cap.read()
                if not ret:
                    break
                
                if frame_count % self.frame_interval == 0:
                    with tempfile.NamedTemporaryFile(suffix='.jpg', delete=False) as tmp:
                        cv2.imwrite(tmp.name, frame)
                        frames.append(tmp.name)
                
                frame_count += 1
        finally:
            cap.release()
        
        logger.info(f"{len(frames)} frames extraites de la vidéo")
        return frames