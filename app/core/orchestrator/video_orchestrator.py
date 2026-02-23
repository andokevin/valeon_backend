import asyncio
import os
import tempfile
import logging
from typing import Dict, Any, List, Optional

from app.core.modules.whisper_cpp import WhisperCppClient
from app.core.modules.gemini import GeminiClient
from app.core.modules.tmdb.client import TMDBClient
from app.core.modules.justwatch.client import JustWatchClient
from app.core.modules.youtube.client import YouTubeClient
from app.core.modules.spotify.client import SpotifyClient
from app.core.modules.acrcloud.client import ACRCloudClient
from app.core.orchestrator.decision_engine import DecisionEngine
from app.core.config import settings
from app.models import User

logger = logging.getLogger(__name__)

class VideoOrchestrator:
    def __init__(self):
        self.whisper = WhisperCppClient() if settings.WHISPER_CPP_ENABLED else None
        self.gemini = GeminiClient()
        self.acrcloud = ACRCloudClient()  # Pour détecter la musique dans la vidéo
        self.tmdb = TMDBClient() if settings.TMDB_ENABLED else None
        self.justwatch = JustWatchClient() if settings.JUSTWATCH_ENABLED else None
        self.youtube = YouTubeClient() if settings.YOUTUBE_ENABLED else None
        self.spotify = SpotifyClient() if settings.SPOTIFY_ENABLED else None
        self.engine = DecisionEngine()
        self.frame_interval = 30
        self.max_frames = 5

    async def process_video(self, file_path: str, user: User, db) -> Dict[str, Any]:
        logger.info(f"VideoOrchestrator: Traitement de {os.path.basename(file_path)}")
        
        # Étape 1: Extraction audio pour analyse
        audio_path = None
        transcript = {"text": "", "segments": []}
        acr_result = None
        
        if self.whisper or self.acrcloud:
            logger.info("VideoOrchestrator: Extraction audio...")
            audio_path = await self._extract_audio(file_path)
            
            if audio_path:
                # Transcription Whisper
                if self.whisper:
                    logger.info("VideoOrchestrator: Transcription audio...")
                    transcript = await self.whisper.transcribe_with_timestamps(audio_path)
                    logger.info(f"VideoOrchestrator: Transcription ({len(transcript.get('text', ''))} caractères)")
                
                # ACR Cloud pour détecter musique de fond
                if self.acrcloud:
                    logger.info("VideoOrchestrator: Analyse ACR Cloud de l'audio...")
                    acr_result = await self.acrcloud.recognize(audio_path)
                    if acr_result and acr_result.get("title"):
                        logger.info(f"VideoOrchestrator: Musique détectée: {acr_result.get('title')}")

        # Étape 2: Extraction et analyse des frames
        logger.info("VideoOrchestrator: Extraction des frames clés...")
        frames = await asyncio.to_thread(self._extract_frames_sync, file_path)
        vision_results = []
        
        for i, fp in enumerate(frames):
            logger.info(f"VideoOrchestrator: Analyse frame {i+1}/{len(frames)} avec Gemini...")
            vision_result = await self.gemini.analyze_image(fp)
            vision_results.append(vision_result)
            os.unlink(fp)  # Nettoyage

        # Étape 3: Détection du type de contenu
        file_info = {
            "file_type": "video",
            "file_size": os.path.getsize(file_path) if os.path.exists(file_path) else 0,
            "filename": os.path.basename(file_path),
            "duration": self._get_video_duration(file_path),
            "has_audio": audio_path is not None,
            "has_transcript": bool(transcript.get("text")),
            "has_acr_result": acr_result is not None,
            "frame_count": len(vision_results)
        }
        
        content_detection = await self.engine.detect_content_type(file_info)
        content_type = content_detection.get("content_type", "unknown")
        confidence = content_detection.get("confidence", 0.0)
        
        logger.info(f"VideoOrchestrator: Type détecté = {content_type} (confiance: {confidence})")

        # Étape 4: Analyse approfondie des frames
        frame_analysis = await self.engine.analyze_video_frames(vision_results, transcript.get("text", ""))

        # Initialisation des résultats
        tmdb_result = None
        spotify_result = None
        streaming = None
        youtube_result = None

        # Étape 5: Stratégie selon le type détecté
        if content_type in ["movie", "film", "trailer"] or frame_analysis.get("is_movie", False):
            # C'est un film ou une bande-annonce → TMDB
            logger.info("VideoOrchestrator: Contenu film détecté, recherche TMDB...")
            
            search_queries = []
            
            # Priorité 1: Utiliser le texte des frames
            for frame in vision_results:
                if frame.get("text") and len(frame.get("text")) > 20:
                    search_queries.append(frame.get("text")[:100])
            
            # Priorité 2: Utiliser la transcription audio
            if transcript.get("text") and len(transcript.get("text")) > 50:
                search_queries.append(transcript.get("text")[:100])
            
            # Priorité 3: Utiliser le titre possible de l'analyse
            if frame_analysis.get("possible_title"):
                search_queries.append(frame_analysis.get("possible_title"))
            
            # Rechercher avec TMDB
            if self.tmdb:
                for query in search_queries[:3]:  # Essayer les 3 premières requêtes
                    if query:
                        logger.info(f"VideoOrchestrator: Recherche TMDB: '{query[:50]}...'")
                        tmdb_result = await self.tmdb.search_movie(
                            query, 
                            frame_analysis.get("possible_year")
                        )
                        if tmdb_result:
                            logger.info(f"VideoOrchestrator: TMDB a trouvé '{tmdb_result.get('title')}'")
                            break
                
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

        elif content_type in ["music_video", "clip"] or frame_analysis.get("is_music_video", False) or acr_result:
            # C'est un clip musical → Spotify + YouTube
            logger.info("VideoOrchestrator: Clip musical détecté")
            
            # Utiliser ACR Cloud si disponible
            if acr_result and acr_result.get("title"):
                logger.info(f"VideoOrchestrator: Musique identifiée: {acr_result.get('title')}")
                
                # Spotify
                if acr_result.get("spotify_id") and self.spotify:
                    spotify_result = await self.spotify.get_track(acr_result["spotify_id"])
                
                # YouTube
                if self.youtube:
                    youtube_result = await self.youtube.search_music_video(
                        acr_result.get("title", ""),
                        acr_result.get("artist", "")
                    )
            
            # Sinon, utiliser les frames
            elif self.youtube:
                for frame in vision_results:
                    if frame.get("text"):
                        youtube_result = await self.youtube.search_video(frame.get("text"), 1)
                        if youtube_result:
                            youtube_result = youtube_result[0]
                            break

        elif content_type in ["tv_show", "episode"] or frame_analysis.get("is_tv_show", False):
            # C'est un épisode de série → TMDB
            logger.info("VideoOrchestrator: Épisode de série détecté, recherche TMDB...")
            
            if self.tmdb and transcript.get("text"):
                # Chercher avec la transcription
                tmdb_result = await self.tmdb.search_tv(transcript.get("text")[:100])
                
                if tmdb_result and self.justwatch:
                    streaming = await self.justwatch.search_by_tmdb_id(tmdb_result.get("tmdb_id"))

        # Étape 6: Fusion des résultats
        result = await self.engine.merge_video_results(
            audio_text=transcript.get("text", ""),
            frame_results=vision_results,
            tmdb_result=tmdb_result,
            content_type=content_type
        )

        # Ajouter les métadonnées
        result["detection"] = {
            "method": "gemini_frames" if vision_results else "analysis",
            "confidence": confidence,
            "type_detected": content_type,
            "frame_analysis": frame_analysis
        }

        if transcript.get("text"):
            result["transcript"] = transcript.get("text")[:500]  # Limiter la taille
        
        if acr_result:
            result["audio_recognition"] = acr_result

        # Ajouter les enrichissements
        if tmdb_result:
            result["tmdb"] = tmdb_result
        
        if spotify_result:
            result["spotify"] = spotify_result
        
        if streaming:
            result["streaming"] = streaming.get("streaming")

        if youtube_result:
            result.setdefault("external_links", {})
            if isinstance(youtube_result, dict):
                result["external_links"]["youtube"] = youtube_result.get("url")
                result["external_links"]["youtube_embed"] = youtube_result.get("embed_url")
                result["youtube"] = youtube_result

        # Nettoyage
        if audio_path and os.path.exists(audio_path):
            os.unlink(audio_path)

        logger.info(f"VideoOrchestrator: Terminé - {result.get('title', 'inconnu')}")
        return result

    async def _extract_audio(self, video_path: str) -> Optional[str]:
        """Extrait la piste audio d'une vidéo avec ffmpeg."""
        try:
            audio_path = tempfile.NamedTemporaryFile(suffix=".mp3", delete=False).name
            
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
            
            if proc.returncode == 0 and os.path.exists(audio_path) and os.path.getsize(audio_path) > 0:
                return audio_path
            return None
            
        except Exception as e:
            logger.error(f"VideoOrchestrator: Erreur extraction audio: {e}")
            return None

    def _extract_frames_sync(self, video_path: str) -> List[str]:
        """Extrait des frames d'une vidéo (version synchrone)."""
        import cv2
        
        frames = []
        cap = cv2.VideoCapture(video_path)
        count = 0
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        
        # Adapter l'intervalle en fonction de la durée
        if total_frames > 0:
            self.frame_interval = max(1, total_frames // self.max_frames)
        
        try:
            while len(frames) < self.max_frames:
                ret, frame = cap.read()
                if not ret:
                    break
                    
                if count % self.frame_interval == 0:
                    with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
                        cv2.imwrite(tmp.name, frame)
                        frames.append(tmp.name)
                        
                count += 1
                
        finally:
            cap.release()
            
        logger.info(f"VideoOrchestrator: {len(frames)} frames extraites")
        return frames

    def _get_video_duration(self, video_path: str) -> Optional[float]:
        """Récupère la durée de la vidéo avec ffprobe."""
        try:
            import json
            proc = subprocess.run([
                "ffprobe", "-v", "quiet", "-print_format", "json", "-show_format",
                video_path
            ], capture_output=True, text=True)
            
            if proc.returncode == 0:
                data = json.loads(proc.stdout)
                return float(data.get("format", {}).get("duration", 0))
        except:
            pass
        return None