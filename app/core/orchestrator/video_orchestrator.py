# app/core/orchestrator/video_orchestrator.py (CORRIGÉ - français)
import asyncio
import os
import tempfile
import logging
import subprocess
import json
from typing import Dict, Any, List, Optional

from app.core.modules.whisper_client import WhisperClient
from app.core.modules.gemini import GeminiClient
from app.core.modules.tmdb.client import TMDBClient
from app.core.modules.justwatch.client import JustWatchClient
from app.core.modules.youtube.client import YouTubeClient
from app.core.modules.spotify.client import SpotifyClient
from app.core.modules.acrcloud.client import ACRCloudClient
from app.core.orchestrator.image_orchestrator import ImageOrchestrator
from app.core.orchestrator.decision_engine import DecisionEngine
from app.core.config import settings
from app.models import User

logger = logging.getLogger(__name__)

class VideoOrchestrator:
    def __init__(self):
        self.whisper = WhisperClient(
            model_size=settings.WHISPER_MODEL_SIZE,
            language=settings.WHISPER_LANGUAGE
        ) if settings.WHISPER_ENABLED else None
        
        self.gemini = GeminiClient()
        self.image_orchestrator = ImageOrchestrator()
        self.acrcloud = ACRCloudClient()
        self.tmdb = TMDBClient() if settings.TMDB_ENABLED else None
        self.justwatch = JustWatchClient() if settings.JUSTWATCH_ENABLED else None
        self.youtube = YouTubeClient() if settings.YOUTUBE_ENABLED else None
        self.spotify = SpotifyClient() if settings.SPOTIFY_ENABLED else None
        self.engine = DecisionEngine()
        self.frame_interval = 30
        self.max_frames = 5
        self.MIN_TRANSCRIPT_LENGTH_FOR_SEARCH = 20
        self.MIN_CONFIDENCE_ACR = 0.3

    async def _search_by_transcript(self, transcript: str) -> Dict[str, Any]:
        """
        Recherche intelligente basée sur la transcription audio (en français).
        """
        if len(transcript) < self.MIN_TRANSCRIPT_LENGTH_FOR_SEARCH:
            return {}
        
        logger.info(f"VideoOrchestrator: Recherche par transcription ({len(transcript)} caractères)")
        logger.debug(f"Transcription: {transcript[:200]}...")
        
        prompt = f"""
        Tu es un expert en identification de contenus vidéo à partir de dialogues.

        **IMPORTANT: Tu dois TOUJOURS répondre en FRANÇAIS.**

        Voici une transcription audio extraite d'une vidéo:
        "{transcript}"

        Analyse ce texte et détermine en français:
        1. Le TYPE de contenu (movie, tv_show, music_video, interview, documentary, speech, other)
        2. Le TITRE possible (film, série, chanson, émission)
        3. L'ARTISTE/RÉALISATEUR/PRÉSENTATEUR
        4. Des MOTS-CLÉS pour la recherche

        Règles:
        - Si c'est un dialogue de film: cherche le titre du film
        - Si c'est un dialogue de série: cherche le titre de la série
        - Si c'est une chanson: cherche le titre ET l'artiste
        - Si c'est une interview: cherche la personne interviewée et l'émission
        - Si c'est un documentaire: cherche le sujet

        Réponds UNIQUEMENT en JSON avec cette structure:
        {{
            "content_type": "movie/tv_show/music_video/interview/documentary/speech/other",
            "title": "titre probable en français",
            "artist": "artiste/réalisateur/orateur",
            "keywords": ["mot1", "mot2", "mot3"],
            "possible_movie": "titre du film si dialogue",
            "possible_tv_show": "titre de la série si dialogue",
            "possible_song": "titre de la chanson si musique",
            "possible_interview": "nom de l'émission si interview",
            "confidence": 0.0-1.0,
            "reasoning": "explication en français"
        }}
        """
        
        try:
            result = await self.gemini.generate_text(
                prompt=prompt,
                max_tokens=500,
                json_mode=True,
                temperature=0.3
            )
            
            logger.info(f"VideoOrchestrator: Analyse transcription - Type: {result.get('content_type')}, Confiance: {result.get('confidence')}")
            return result
            
        except Exception as e:
            logger.error(f"VideoOrchestrator: Erreur analyse transcription: {e}")
            return {}

    async def _search_movie_by_dialogue(self, transcript: str, analysis: dict) -> Optional[Dict]:
        """Recherche un film à partir du dialogue."""
        if not self.tmdb:
            return None
        
        search_terms = []
        
        if analysis.get("possible_movie"):
            search_terms.append(analysis.get("possible_movie"))
        if analysis.get("keywords"):
            search_terms.extend(analysis.get("keywords")[:3])
        
        words = transcript.split()[:10]
        if words:
            search_terms.append(" ".join(words))
        
        for term in search_terms:
            if term and len(term) > 3:
                logger.info(f"VideoOrchestrator: Recherche TMDB par dialogue: '{term}'")
                movie = await self.tmdb.search_movie(term)
                if movie:
                    logger.info(f"✅ Film trouvé via dialogue: {movie.get('title')}")
                    return movie
        return None

    async def _search_tv_show_by_dialogue(self, transcript: str, analysis: dict) -> Optional[Dict]:
        """Recherche une série à partir du dialogue."""
        if not self.tmdb:
            return None
        
        search_terms = []
        
        if analysis.get("possible_tv_show"):
            search_terms.append(analysis.get("possible_tv_show"))
        if analysis.get("keywords"):
            search_terms.extend(analysis.get("keywords")[:3])
        
        for term in search_terms:
            if term and len(term) > 3:
                logger.info(f"VideoOrchestrator: Recherche TMDB série: '{term}'")
                tv_show = await self.tmdb.search_tv(term)
                if tv_show:
                    logger.info(f"✅ Série trouvée via dialogue: {tv_show.get('title')}")
                    return tv_show
        return None

    async def _search_music_by_audio(self, transcript: str, analysis: dict, acr_result: dict = None) -> Optional[Dict]:
        """Recherche une musique à partir de l'audio ou des paroles."""
        if not self.spotify:
            return None
        
        # Si ACR a déjà trouvé, on l'utilise
        if acr_result and acr_result.get("spotify_id"):
            track = await self.spotify.get_track(acr_result["spotify_id"])
            if track:
                return track
        
        # Sinon recherche par paroles
        search_terms = []
        if analysis.get("possible_song"):
            search_terms.append(analysis.get("possible_song"))
        if analysis.get("artist"):
            search_terms.append(analysis.get("artist"))
        if analysis.get("keywords"):
            search_terms.extend(analysis.get("keywords")[:3])
        
        words = transcript.split()[:7]
        if words:
            search_terms.append(" ".join(words))
        
        for term in search_terms:
            if term and len(term) > 3:
                logger.info(f"VideoOrchestrator: Recherche Spotify par paroles: '{term}'")
                tracks = await self.spotify.search_track(term, limit=3)
                if tracks and len(tracks) > 0:
                    logger.info(f"✅ Chanson trouvée via paroles: {tracks[0].get('title')}")
                    return tracks[0]
        return None

    async def process_video(self, file_path: str, user: User, db) -> Dict[str, Any]:
        logger.info(f"VideoOrchestrator: Traitement de {os.path.basename(file_path)}")
        
        # Étape 1: Extraction audio
        audio_path = None
        transcript = {"text": "", "segments": []}
        transcript_text = ""
        transcript_analysis = {}
        acr_result = None
        
        logger.info("VideoOrchestrator: Extraction audio...")
        audio_path = await self._extract_audio(file_path)
        
        if audio_path:
            # ===== PRIORITÉ ABSOLUE : ACR CLOUD =====
            if self.acrcloud:
                logger.info("VideoOrchestrator: Analyse ACR Cloud de l'audio...")
                acr_result = await self.acrcloud.recognize(audio_path)
                
                if acr_result and acr_result.get("title"):
                    confidence = acr_result.get("confidence", 0.0)
                    logger.info(f"VideoOrchestrator: ACR Cloud a trouvé '{acr_result.get('title')}' avec confiance {confidence}")
                    
                    # Construire le résultat (les titres sont déjà en français depuis ACR)
                    result = {
                        "title": acr_result.get("title"),
                        "artist": acr_result.get("artist"),
                        "album": acr_result.get("album"),
                        "year": acr_result.get("release_date", "")[:4] if acr_result.get("release_date") else None,
                        "genre": (acr_result.get("genres") or [""])[0] if acr_result.get("genres") else None,
                        "type": "music",
                        "confidence": confidence,
                        "metadata": acr_result,
                        "detection": {
                            "method": "acr_cloud",
                            "confidence": confidence,
                            "source": "audio_recognition"
                        }
                    }
                    
                    # Enrichir avec Spotify
                    if acr_result.get("spotify_id") and self.spotify:
                        try:
                            spotify_result = await self.spotify.get_track(acr_result["spotify_id"])
                            if spotify_result:
                                result["spotify"] = spotify_result
                                result["image"] = spotify_result.get("image") or result.get("image")
                        except Exception as e:
                            logger.error(f"Erreur Spotify: {e}")
                    
                    # Enrichir avec YouTube
                    if acr_result.get("youtube_id") and self.youtube:
                        try:
                            youtube_url = f"https://www.youtube.com/watch?v={acr_result.get('youtube_id')}"
                            result.setdefault("external_links", {})
                            result["external_links"]["youtube"] = youtube_url
                            result["youtube"] = {
                                "video_id": acr_result.get("youtube_id"),
                                "url": youtube_url,
                            }
                        except Exception as e:
                            logger.error(f"Erreur YouTube: {e}")
                    
                    if audio_path and os.path.exists(audio_path):
                        os.unlink(audio_path)
                    
                    logger.info(f"VideoOrchestrator: ✅ Résultat ACR direct - {result.get('title')}")
                    return result
                else:
                    logger.info("VideoOrchestrator: ACR Cloud n'a rien trouvé, passage aux autres méthodes...")
            
            # ===== SI ACR N'A RIEN TROUVÉ, TRANSCRIPTION =====
            if self.whisper:
                logger.info("VideoOrchestrator: Transcription audio...")
                try:
                    transcript_result = await self.whisper.transcribe_with_timestamps(audio_path)
                    transcript = transcript_result
                    transcript_text = transcript_result.get("text", "")
                except:
                    transcript_text = await self.whisper.transcribe(audio_path)
                    transcript = {"text": transcript_text, "segments": []}
                
                logger.info(f"VideoOrchestrator: Transcription ({len(transcript_text)} caractères)")
                
                if transcript_text:
                    logger.debug(f"Transcription extrait: {transcript_text[:200]}...")
                    
                    if len(transcript_text) >= self.MIN_TRANSCRIPT_LENGTH_FOR_SEARCH:
                        transcript_analysis = await self._search_by_transcript(transcript_text)

        # ===== SI ON ARRIVE ICI, ACR N'A RIEN TROUVÉ =====
        logger.info("VideoOrchestrator: Extraction des frames clés...")
        frames = await asyncio.to_thread(self._extract_frames_sync, file_path)
        vision_results = []
        
        for i, fp in enumerate(frames):
            logger.info(f"VideoOrchestrator: Analyse frame {i+1}/{len(frames)}...")
            try:
                vision_result = await self.image_orchestrator.process_image(fp, user, db)
                vision_results.append(vision_result)
            except Exception as e:
                logger.error(f"Erreur analyse frame: {e}")
                vision_results.append({"type": "unknown", "error": str(e)})
            finally:
                if os.path.exists(fp):
                    os.unlink(fp)

        # Détection du type de contenu
        file_info = {
            "file_type": "video",
            "file_size": os.path.getsize(file_path) if os.path.exists(file_path) else 0,
            "filename": os.path.basename(file_path),
            "duration": self._get_video_duration(file_path),
            "has_audio": audio_path is not None,
            "has_transcript": bool(transcript_text),
            "has_acr_result": acr_result is not None,
            "frame_count": len(vision_results)
        }
        
        content_detection = await self.engine.detect_content_type(file_info)
        content_type = content_detection.get("content_type", "unknown")
        confidence = content_detection.get("confidence", 0.0)
        
        logger.info(f"VideoOrchestrator: Type détecté = {content_type} (confiance: {confidence})")

        # Analyse approfondie des frames
        frame_analysis = await self.engine.analyze_video_frames(vision_results, transcript_text)

        # Initialisation des résultats
        tmdb_result = None
        spotify_result = None
        streaming = None
        youtube_result = None

        # Utilisation de la transcription
        if transcript_analysis:
            logger.info(f"VideoOrchestrator: Analyse transcription donne type: {transcript_analysis.get('content_type')}")
            if transcript_analysis.get("confidence", 0) > 0.7:
                content_type = transcript_analysis.get("content_type", content_type)
        
        # Stratégie selon le type
        if content_type in ["movie", "film", "trailer"] or frame_analysis.get("is_movie", False):
            logger.info("VideoOrchestrator: Contenu film détecté, recherche TMDB...")
            
            search_queries = []
            if transcript_analysis.get("possible_movie"):
                search_queries.append(transcript_analysis.get("possible_movie"))
            
            for frame in vision_results:
                if frame.get("title") and len(frame.get("title")) > 3:
                    search_queries.append(frame.get("title"))
            
            if transcript_text and len(transcript_text) > 50:
                search_queries.append(transcript_text[:100])
            
            if self.tmdb:
                for query in search_queries[:3]:
                    if query:
                        logger.info(f"VideoOrchestrator: Recherche TMDB: '{query[:50]}...'")
                        tmdb_result = await self.tmdb.search_movie(
                            query, 
                            transcript_analysis.get("year") or frame_analysis.get("possible_year")
                        )
                        if tmdb_result:
                            logger.info(f"✅ TMDB trouvé: {tmdb_result.get('title')}")
                            break
                
                if tmdb_result:
                    if self.justwatch:
                        streaming = await self.justwatch.search_by_tmdb_id(tmdb_result.get("tmdb_id"))
                    
                    if self.youtube:
                        youtube_result = await self.youtube.search_trailer(
                            tmdb_result.get("title", ""),
                            tmdb_result.get("release_date", "")[:4] if tmdb_result.get("release_date") else None
                        )

        elif content_type in ["tv_show", "episode"] or frame_analysis.get("is_tv_show", False):
            logger.info("VideoOrchestrator: Épisode de série détecté, recherche TMDB...")
            
            search_terms = []
            if transcript_analysis.get("possible_tv_show"):
                search_terms.append(transcript_analysis.get("possible_tv_show"))
            if transcript_text:
                search_terms.append(transcript_text[:100])
            
            if self.tmdb:
                for term in search_terms:
                    if term:
                        tmdb_result = await self.tmdb.search_tv(term)
                        if tmdb_result:
                            logger.info(f"✅ Série trouvée: {tmdb_result.get('title')}")
                            break
                
                if tmdb_result and self.justwatch:
                    streaming = await self.justwatch.search_by_tmdb_id(tmdb_result.get("tmdb_id"))

        elif content_type in ["music_video", "clip"] or frame_analysis.get("is_music_video", False) or acr_result:
            logger.info("VideoOrchestrator: Clip musical détecté")
            
            # Recherche musique via ACR + transcription
            spotify_result = await self._search_music_by_audio(transcript_text, transcript_analysis, acr_result)
            
            # Recherche YouTube
            if self.youtube:
                if acr_result and acr_result.get("title") and acr_result.get("artist"):
                    youtube_result = await self.youtube.search_music_video(
                        acr_result.get("title", ""),
                        acr_result.get("artist", "")
                    )
                elif transcript_analysis.get("possible_song") and transcript_analysis.get("artist"):
                    youtube_result = await self.youtube.search_music_video(
                        transcript_analysis.get("possible_song", ""),
                        transcript_analysis.get("artist", "")
                    )
                elif vision_results and len(vision_results) > 0 and vision_results[0].get("title"):
                    youtube_result = await self.youtube.search_music_video(
                        vision_results[0].get("title", ""),
                        vision_results[0].get("artist", "")
                    )

        # Étape 6: Fusion des résultats
        result = await self.engine.merge_video_results(
            audio_text=transcript_text,
            frame_results=vision_results,
            tmdb_result=tmdb_result,
            content_type=content_type
        )

        # Ajouter les métadonnées enrichies
        result["detection"] = {
            "method": "multi_modal",
            "confidence": confidence,
            "type_detected": content_type,
            "frame_analysis": frame_analysis,
            "transcript_analysis": transcript_analysis
        }

        if transcript_text:
            result["transcript"] = transcript_text[:1000]
            result["transcript_full"] = transcript_text if len(transcript_text) < 5000 else transcript_text[:5000] + "..."
        
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

        logger.info(f"VideoOrchestrator: Terminé - {result.get('title', 'inconnu')} (type: {result.get('type')})")
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
