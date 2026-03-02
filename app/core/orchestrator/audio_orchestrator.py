# app/core/orchestrator/audio_orchestrator.py
from typing import Dict, Any, Optional
import logging
import os
import tempfile
import asyncio
import json
from app.core.modules.whisper_client import WhisperClient
from app.core.modules.acrcloud.client import ACRCloudClient
from app.core.modules.spotify.client import SpotifyClient
from app.core.modules.tmdb.client import TMDBClient
from app.core.modules.youtube.client import YouTubeClient
from app.core.modules.gemini import GeminiClient
from app.core.orchestrator.decision_engine import DecisionEngine
from app.core.config import settings
from app.models import User

logger = logging.getLogger(__name__)

class AudioOrchestrator:
    def __init__(self):
        self.whisper = WhisperClient(
            model_size=settings.WHISPER_MODEL_SIZE,
            language=settings.WHISPER_LANGUAGE
        ) if settings.WHISPER_ENABLED else None
        
        self.acrcloud = ACRCloudClient()
        self.spotify = SpotifyClient() if settings.SPOTIFY_ENABLED else None
        self.tmdb = TMDBClient() if settings.TMDB_ENABLED else None
        self.youtube = YouTubeClient() if settings.YOUTUBE_ENABLED else None
        self.gemini = GeminiClient()
        self.engine = DecisionEngine()
        
        # Constantes
        self.ACR_MAX_DURATION_SECONDS = 60
        self.ACR_SAMPLE_DURATION = 20
        self.MIN_CONFIDENCE_ACR = 0.6
        self.MIN_TRANSCRIPT_LENGTH_FOR_SEARCH = 20

    async def _prepare_audio_for_acr(self, file_path: str) -> Optional[str]:
        """Prépare un fichier audio pour ACR Cloud."""
        duration = await self._get_audio_duration(file_path)
        
        if duration is None:
            logger.warning(f"AudioOrchestrator: Impossible de déterminer la durée de {os.path.basename(file_path)}")
            return file_path
        
        logger.info(f"AudioOrchestrator: Durée du fichier = {duration:.1f}s")
        
        if duration > self.ACR_MAX_DURATION_SECONDS:
            logger.info(f"AudioOrchestrator: Fichier trop long ({duration:.1f}s) - Extraction d'un échantillon de {self.ACR_SAMPLE_DURATION}s")
            
            try:
                with tempfile.NamedTemporaryFile(suffix='.mp3', delete=False) as tmp_file:
                    sample_path = tmp_file.name
                
                start_time = max(0, (duration - self.ACR_SAMPLE_DURATION) / 2)
                
                cmd = [
                    'ffmpeg',
                    '-i', file_path,
                    '-ss', str(start_time),
                    '-t', str(self.ACR_SAMPLE_DURATION),
                    '-y',
                    '-acodec', 'libmp3lame',
                    '-ar', '16000',
                    '-ac', '1',
                    '-b:a', '64k',
                    sample_path
                ]
                
                process = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                
                try:
                    await asyncio.wait_for(process.communicate(), timeout=30)
                except asyncio.TimeoutError:
                    logger.error("AudioOrchestrator: Timeout extraction échantillon")
                    process.kill()
                    return file_path
                
                if process.returncode == 0 and os.path.exists(sample_path):
                    logger.info(f"AudioOrchestrator: Échantillon extrait avec succès: {sample_path}")
                    return sample_path
                else:
                    logger.error("AudioOrchestrator: Échec de l'extraction d'échantillon")
                    return file_path
                    
            except Exception as e:
                logger.error(f"AudioOrchestrator: Erreur extraction échantillon: {e}")
                return file_path
        
        return file_path

    async def _get_audio_duration(self, file_path: str) -> Optional[float]:
        try:
            import json
            process = await asyncio.create_subprocess_exec(
                'ffprobe',
                '-v', 'quiet',
                '-print_format', 'json',
                '-show_format',
                file_path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, _ = await process.communicate()
            
            if process.returncode == 0:
                data = json.loads(stdout)
                return float(data.get('format', {}).get('duration', 0))
        except Exception as e:
            logger.error(f"AudioOrchestrator: Erreur récupération durée: {e}")
        return None

    async def _enrich_with_spotify_youtube(self, acr_result: dict) -> dict:
        """Enrichit un résultat ACR avec Spotify et YouTube."""
        enriched = acr_result.copy()
        
        if acr_result.get("spotify_id") and self.spotify:
            logger.info("AudioOrchestrator: Enrichissement Spotify...")
            spotify_result = await self.spotify.get_track(acr_result["spotify_id"])
            if spotify_result:
                enriched["spotify"] = spotify_result
                
                if spotify_result.get("title") != "Mock Track" and spotify_result.get("album") != "Mock Album":
                    enriched["image"] = spotify_result.get("image") or enriched.get("image")
                    enriched["writers"] = spotify_result.get("artists")
                    enriched["album"] = spotify_result.get("album") or enriched.get("album")
                    enriched["album_id"] = spotify_result.get("album_id")
                    enriched["label"] = spotify_result.get("label")
                    enriched["duration"] = spotify_result.get("duration")
                    enriched["popularity"] = spotify_result.get("popularity")
                    enriched["genre"] = spotify_result.get("genre") or acr_result.get("genres", [""])[0]
                    
                    if spotify_result.get("album") and acr_result.get("artist"):
                        enriched["description"] = f"Chanson de {acr_result.get('artist')} extraite de l'album '{spotify_result.get('album')}'"
                else:
                    logger.info("AudioOrchestrator: Spotify en mode mock, conservation des données ACR")
                    enriched["album"] = acr_result.get("album") or enriched.get("album")
                    if acr_result.get("artist") and acr_result.get("album"):
                        enriched["description"] = f"Chanson de {acr_result.get('artist')} extraite de l'album '{acr_result.get('album')}'"
        
        if self.youtube and acr_result.get("title") and acr_result.get("artist"):
            logger.info("AudioOrchestrator: Recherche YouTube...")
            youtube_result = await self.youtube.search_music_video(
                acr_result.get("title", ""),
                acr_result.get("artist", "")
            )
            if youtube_result:
                enriched.setdefault("external_links", {})
                
                if youtube_result.get("video_id") != "mock_video_id":
                    enriched["external_links"]["youtube"] = youtube_result.get("url")
                    enriched["external_links"]["youtube_embed"] = youtube_result.get("embed_url")
                    enriched["youtube"] = youtube_result
                else:
                    if acr_result.get("youtube_id"):
                        youtube_url = f"https://www.youtube.com/watch?v={acr_result.get('youtube_id')}"
                        enriched["external_links"]["youtube"] = youtube_url
                        enriched["external_links"]["youtube_embed"] = f"https://www.youtube.com/embed/{acr_result.get('youtube_id')}"
                        enriched["youtube"] = {
                            "video_id": acr_result.get("youtube_id"),
                            "url": youtube_url,
                            "embed_url": f"https://www.youtube.com/embed/{acr_result.get('youtube_id')}"
                        }
        
        return enriched

    async def _search_by_transcript(self, transcript: str) -> Dict[str, Any]:
        if len(transcript) < self.MIN_TRANSCRIPT_LENGTH_FOR_SEARCH:
            return {}
        
        logger.info(f"AudioOrchestrator: Recherche par transcription ({len(transcript)} caractères)")
        logger.debug(f"Transcription: {transcript[:200]}...")
        
        prompt = f"""
        Tu es un expert en identification de contenus audio (musique, films, interviews, podcasts).
        
        Voici une transcription audio:
        "{transcript}"
        
        Analyse ce texte et détermine:
        1. Le TYPE de contenu (music, movie_dialogue, interview, podcast, speech, other)
        2. Le TITRE possible (chanson, film, émission)
        3. L'ARTISTE/RÉALISATEUR/PRÉSENTATEUR
        4. Des MOTS-CLÉS pour la recherche
        
        Règles:
        - Si c'est une chanson: cherche le titre ET l'artiste
        - Si c'est un dialogue de film: cherche le titre du film
        - Si c'est une interview: cherche la personne interviewée et l'émission
        - Si c'est un discours: cherche l'orateur et l'événement
        
        Réponds UNIQUEMENT en JSON avec cette structure:
        {{
            "content_type": "music/movie_dialogue/interview/podcast/speech/other",
            "title": "titre probable",
            "artist": "artiste/réalisateur/orateur",
            "keywords": ["mot1", "mot2", "mot3"],
            "possible_movie": "titre du film si dialogue",
            "possible_song": "titre de la chanson si musique",
            "possible_show": "nom de l'émission si interview",
            "confidence": 0.0-1.0,
            "reasoning": "explication rapide"
        }}
        """
        
        try:
            result = await self.gemini.generate_text(
                prompt=prompt,
                max_tokens=500,
                json_mode=True,
                temperature=0.3
            )
            
            logger.info(f"AudioOrchestrator: Analyse transcription - Type: {result.get('content_type')}, Confiance: {result.get('confidence')}")
            return result
            
        except Exception as e:
            logger.error(f"AudioOrchestrator: Erreur analyse transcription: {e}")
            return {}

    async def _search_movie_by_dialogue(self, transcript: str, analysis: dict) -> Optional[Dict]:
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
                logger.info(f"AudioOrchestrator: Recherche TMDB par dialogue: '{term}'")
                movie = await self.tmdb.search_movie(term)
                if movie:
                    logger.info(f"✅ Film trouvé via dialogue: {movie.get('title')}")
                    return movie
        
        return None

    async def _search_music_by_lyrics(self, transcript: str, analysis: dict) -> Optional[Dict]:
        if not self.spotify:
            return None
        
        search_terms = []
        
        if analysis.get("possible_song"):
            search_terms.append(analysis.get("possible_song"))
        if analysis.get("artist") and analysis.get("title"):
            search_terms.append(f"{analysis.get('artist')} {analysis.get('title')}")
        if analysis.get("keywords"):
            search_terms.extend(analysis.get("keywords")[:3])
        
        words = transcript.split()[:7]
        if words:
            search_terms.append(" ".join(words))
        
        for term in search_terms:
            if term and len(term) > 3:
                logger.info(f"AudioOrchestrator: Recherche Spotify par paroles: '{term}'")
                tracks = await self.spotify.search_track(term, limit=3)
                if tracks and len(tracks) > 0:
                    logger.info(f"✅ Chanson trouvée via paroles: {tracks[0].get('title')}")
                    return tracks[0]
        
        return None

    async def _search_interview_by_transcript(self, transcript: str, analysis: dict) -> Optional[Dict]:
        if not self.youtube:
            return None
        
        search_term = ""
        
        if analysis.get("possible_show"):
            search_term = analysis.get("possible_show")
        elif analysis.get("artist"):
            search_term = f"{analysis.get('artist')} interview"
        elif analysis.get("keywords"):
            search_term = " ".join(analysis.get("keywords")[:2]) + " interview"
        
        if search_term:
            logger.info(f"AudioOrchestrator: Recherche YouTube interview: '{search_term}'")
            videos = await self.youtube.search_video(search_term, max_results=1)
            if videos and len(videos) > 0:
                logger.info(f"✅ Interview trouvée: {videos[0].get('title')}")
                return videos[0]
        
        return None

    async def process_audio(self, file_path: str, user: User, db) -> Dict[str, Any]:
        logger.info(f"AudioOrchestrator: Traitement de {os.path.basename(file_path)}")
        
        temp_sample_path = None
        transcript = ""
        transcript_analysis = {}
        
        try:
            # Préparation pour ACR
            acr_input_path = await self._prepare_audio_for_acr(file_path)
            if acr_input_path != file_path:
                temp_sample_path = acr_input_path
            
            # ACR Cloud en priorité
            logger.info(f"AudioOrchestrator: Recherche ACR Cloud...")
            acr_result = await self.acrcloud.recognize(acr_input_path)
            
            # Si ACR a trouvé avec bonne confiance
            if acr_result and acr_result.get("title") and acr_result.get("confidence", 0) >= self.MIN_CONFIDENCE_ACR:
                logger.info(f"AudioOrchestrator: ACR Cloud a trouvé '{acr_result.get('title')}' avec bonne confiance")
                
                enriched_result = await self._enrich_with_spotify_youtube(acr_result)
                
                album_name = enriched_result.get("album") or acr_result.get("album")
                
                description = enriched_result.get("description") or (
                    f"Chanson {acr_result.get('title')} de {acr_result.get('artist')}"
                    f"{' extraite de l\'album ' + album_name if album_name else ''}"
                    f"{' sortie en ' + acr_result.get('release_date')[:4] if acr_result.get('release_date') else ''}"
                )
                
                # S'assurer que spotify_id et youtube_id sont au bon endroit
                spotify_id = acr_result.get("spotify_id")
                youtube_id = acr_result.get("youtube_id")
                
                result = {
                    "title": acr_result.get("title"),
                    "artist": acr_result.get("artist"),
                    "album": album_name,
                    "year": acr_result.get("release_date", "")[:4] if acr_result.get("release_date") else 
                           (enriched_result.get("release_date", "")[:4] if enriched_result.get("release_date") else None),
                    "genre": enriched_result.get("genre") or (acr_result.get("genres", [""])[0] if acr_result.get("genres") else None),
                    "description": description,
                    "type": "music",
                    "writers": enriched_result.get("writers"),
                    "label": enriched_result.get("label") or acr_result.get("label"),
                    "image": enriched_result.get("image") or acr_result.get("image"),
                    "duration": enriched_result.get("duration") or acr_result.get("duration"),
                    "popularity": enriched_result.get("popularity"),
                    "confidence": acr_result.get("confidence", 0.0),
                    "spotify_id": spotify_id,  # ← AJOUT
                    "youtube_id": youtube_id,  # ← AJOUT
                    "metadata": acr_result,
                    "detection": {
                        "method": "acr_cloud",
                        "confidence": acr_result.get("confidence", 0.0),
                        "sample_used": acr_input_path != file_path
                    }
                }
                
                if "spotify" in enriched_result:
                    result["spotify"] = enriched_result["spotify"]
                if "youtube" in enriched_result:
                    result["youtube"] = enriched_result["youtube"]
                if "external_links" in enriched_result:
                    result["external_links"] = enriched_result["external_links"]
                
                # ===== LOGS POUR DÉBOGUER =====
                logger.info(f"🔍 RÉSULTAT FINAL - Titre: {result.get('title')}")
                logger.info(f"🔍 RÉSULTAT FINAL - Artiste: {result.get('artist')}")
                logger.info(f"🔍 RÉSULTAT FINAL - Spotify ID: {result.get('spotify_id')}")
                logger.info(f"🔍 RÉSULTAT FINAL - YouTube ID: {result.get('youtube_id')}")
                logger.info(f"🔍 RÉSULTAT FINAL - Clés disponibles: {list(result.keys())}")
                
                return result
            
            # ===== SI ACR N'A PAS TROUVÉ, TRANSCRIPTION =====
            if self.whisper:
                logger.info("AudioOrchestrator: Transcription Whisper...")
                transcript = await self.whisper.transcribe(file_path)
                logger.info(f"AudioOrchestrator: Transcription obtenue ({len(transcript)} caractères)")
                
                if transcript:
                    logger.debug(f"Transcription extrait: {transcript[:200]}...")
                    
                    if len(transcript) >= self.MIN_TRANSCRIPT_LENGTH_FOR_SEARCH:
                        transcript_analysis = await self._search_by_transcript(transcript)
            
            if not transcript or len(transcript.strip()) == 0:
                return {
                    "title": None,
                    "type": "unknown",
                    "confidence": 0.0,
                    "error": "Impossible de transcrire l'audio",
                    "detection": {"method": "failed"}
                }
            
            content_type = transcript_analysis.get("content_type", "unknown")
            logger.info(f"AudioOrchestrator: Type détecté par transcription: {content_type}")
            
            result = {
                "title": transcript_analysis.get("title"),
                "artist": transcript_analysis.get("artist"),
                "type": content_type,
                "description": f"Transcription audio: {transcript[:200]}...",
                "confidence": transcript_analysis.get("confidence", 0.5),
                "transcript": transcript[:1000],
                "transcript_analysis": transcript_analysis,
                "detection": {
                    "method": "whisper+gemini",
                    "content_type": content_type,
                    "confidence": transcript_analysis.get("confidence", 0.5)
                }
            }
            
            # Recherches spécifiques selon le type
            if content_type == "movie_dialogue" and self.tmdb:
                movie = await self._search_movie_by_dialogue(transcript, transcript_analysis)
                if movie:
                    result["tmdb"] = movie
                    result["title"] = movie.get("title")
                    result["director"] = movie.get("director")
                    result["cast"] = movie.get("cast")
                    result["description"] = movie.get("description")
                    result["year"] = movie.get("release_date", "")[:4] if movie.get("release_date") else None
                    result["type"] = "movie"
                    
                    if self.youtube:
                        trailer = await self.youtube.search_trailer(movie.get("title", ""))
                        if trailer:
                            result.setdefault("external_links", {})
                            result["external_links"]["youtube"] = trailer.get("url")
                            result["youtube"] = trailer
            
            elif content_type == "music" and self.spotify:
                song = await self._search_music_by_lyrics(transcript, transcript_analysis)
                if song:
                    result["spotify"] = song
                    result["title"] = song.get("title")
                    result["artist"] = song.get("artist")
                    result["album"] = song.get("album")
                    result["image"] = song.get("image")
                    result["year"] = song.get("release_date", "")[:4] if song.get("release_date") else None
                    
                    if self.youtube and result.get("artist"):
                        video = await self.youtube.search_music_video(
                            result.get("title", ""),
                            result.get("artist", "")
                        )
                        if video:
                            result["youtube"] = video
                            result.setdefault("external_links", {})
                            result["external_links"]["youtube"] = video.get("url")
            
            elif content_type == "interview" and self.youtube:
                interview = await self._search_interview_by_transcript(transcript, transcript_analysis)
                if interview:
                    result["youtube"] = interview
                    result.setdefault("external_links", {})
                    result["external_links"]["youtube"] = interview.get("url")
                    result["title"] = interview.get("title")
                    result["description"] = interview.get("description")
            
            elif content_type == "speech" and self.youtube:
                search_term = transcript_analysis.get("title") or " ".join(transcript_analysis.get("keywords", [])[:3])
                if search_term:
                    logger.info(f"AudioOrchestrator: Recherche YouTube discours: '{search_term}'")
                    videos = await self.youtube.search_video(search_term, max_results=1)
                    if videos and len(videos) > 0:
                        result["youtube"] = videos[0]
                        result.setdefault("external_links", {})
                        result["external_links"]["youtube"] = videos[0].get("url")
                        result["title"] = videos[0].get("title")
            
            logger.info(f"AudioOrchestrator: Terminé (via transcription) - {result.get('title', 'inconnu')}")
            return result
            
        finally:
            if temp_sample_path and os.path.exists(temp_sample_path):
                try:
                    os.unlink(temp_sample_path)
                except Exception as e:
                    logger.error(f"AudioOrchestrator: Erreur nettoyage: {e}")
