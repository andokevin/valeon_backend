# app/core/orchestrator/video_orchestrator.py
import asyncio
import os
import tempfile
import logging
import json
import subprocess
from typing import Dict, Any, List, Optional
from datetime import datetime

from app.core.modules.gemini import GeminiClient
from app.core.modules.whisper_cpp import WhisperCppClient
from app.core.modules.acrcloud.client import ACRCloudClient
from app.core.modules.spotify.client import SpotifyClient
from app.core.modules.tmdb.client import TMDBClient
from app.core.modules.justwatch.client import JustWatchClient
from app.core.modules.youtube.client import YouTubeClient
from app.core.config import settings
from app.models import User

logger = logging.getLogger(__name__)

class VideoOrchestrator:
    """
    Orchestrateur intelligent pour l'analyse de vidéos.
    
    Stratégie multi-niveaux:
    1. Extraction de frames clés → analyse Gemini (identification visuelle)
    2. Extraction audio → transcription Whisper (analyse du dialogue)
    3. Extraction audio → ACR Cloud (identification musicale)
    4. Fusion intelligente des résultats
    """
    
    def __init__(self):
        self.gemini = GeminiClient()
        self.whisper = WhisperCppClient() if settings.WHISPER_CPP_ENABLED else None
        self.acrcloud = ACRCloudClient()
        self.spotify = SpotifyClient() if settings.SPOTIFY_ENABLED else None
        self.tmdb = TMDBClient() if settings.TMDB_ENABLED else None
        self.justwatch = JustWatchClient() if settings.JUSTWATCH_ENABLED else None
        self.youtube = YouTubeClient() if settings.YOUTUBE_ENABLED else None
        
        # Constantes
        self.MAX_FRAMES = 5  # Nombre max de frames à analyser
        self.FRAME_INTERVAL = 30  # Intervalle entre les frames (en frames)
        self.MIN_CONFIDENCE_ACR = 0.6
        self.ACR_SAMPLE_DURATION = 20  # Durée de l'échantillon audio pour ACR
        
    async def process_video(self, file_path: str, user: User, db) -> Dict[str, Any]:
        """
        Traite une vidéo avec analyse multi-niveaux.
        """
        logger.info(f"VideoOrchestrator: Traitement de {os.path.basename(file_path)}")
        
        temp_audio_path = None
        temp_frames = []
        results = {
            "type": "video",
            "detection_methods": [],
            "visual_analysis": {},
            "audio_transcript": "",
            "audio_music": None,
            "title": None,
            "artist": None,
            "director": None,
            "year": None,
            "description": None,
            "confidence": 0.0,
            "metadata": {}
        }
        
        try:
            # ===== ÉTAPE 1: EXTRAIRE L'AUDIO POUR ANALYSE =====
            logger.info("VideoOrchestrator: Extraction audio...")
            temp_audio_path = await self._extract_audio(file_path)
            
            if not temp_audio_path:
                logger.warning("VideoOrchestrator: Impossible d'extraire l'audio")
            
            # ===== ÉTAPE 2: ANALYSE AUDIO PAR ACR CLOUD (MUSIQUE) =====
            acr_result = None
            if temp_audio_path and self.acrcloud:
                logger.info("VideoOrchestrator: Analyse ACR Cloud de l'audio...")
                acr_result = await self.acrcloud.recognize(temp_audio_path)
                
                if acr_result and acr_result.get("title"):
                    confidence = acr_result.get("confidence", 0.0)
                    logger.info(f"VideoOrchestrator: ACR Cloud a trouvé '{acr_result.get('title')}' avec confiance {confidence}")
                    
                    if confidence >= self.MIN_CONFIDENCE_ACR:
                        results["audio_music"] = acr_result
                        results["detection_methods"].append("acr_cloud")
                        
                        # Si c'est clairement de la musique, on peut déjà avoir le titre
                        results["title"] = acr_result.get("title")
                        results["artist"] = acr_result.get("artist")
                        results["confidence"] = max(results["confidence"], confidence)
            
            # ===== ÉTAPE 3: TRANSCRIPTION AUDIO AVEC WHISPER =====
            transcript = ""
            if temp_audio_path and self.whisper:
                logger.info("VideoOrchestrator: Transcription audio avec Whisper...")
                transcript = await self.whisper.transcribe(temp_audio_path)
                results["audio_transcript"] = transcript
                logger.info(f"VideoOrchestrator: Transcription ({len(transcript)} caractères)")
            
            # ===== ÉTAPE 4: EXTRACTION ET ANALYSE DES FRAMES =====
            logger.info("VideoOrchestrator: Extraction des frames clés...")
            temp_frames = await self._extract_key_frames(file_path)
            
            if temp_frames:
                logger.info(f"VideoOrchestrator: {len(temp_frames)} frames extraites")
                
                # Analyser chaque frame avec Gemini
                frame_analyses = []
                for i, frame_path in enumerate(temp_frames):
                    logger.info(f"VideoOrchestrator: Analyse frame {i+1}/{len(temp_frames)} avec Gemini...")
                    frame_result = await self._analyze_frame(frame_path)
                    if frame_result:
                        frame_analyses.append(frame_result)
                
                # Fusionner les analyses des frames
                if frame_analyses:
                    visual_result = await self._merge_frame_analyses(frame_analyses, transcript, acr_result)
                    results["visual_analysis"] = visual_result
                    results["detection_methods"].append("gemini_vision")
                    
                    # Mettre à jour les résultats avec l'analyse visuelle
                    if visual_result.get("title") and not results["title"]:
                        results["title"] = visual_result.get("title")
                    if visual_result.get("artist") and not results["artist"]:
                        results["artist"] = visual_result.get("artist")
                    if visual_result.get("director"):
                        results["director"] = visual_result.get("director")
                    if visual_result.get("year"):
                        results["year"] = visual_result.get("year")
                    if visual_result.get("description"):
                        results["description"] = visual_result.get("description")
                    if visual_result.get("confidence", 0) > results["confidence"]:
                        results["confidence"] = visual_result.get("confidence", 0)
                    
                    results["metadata"]["frame_analysis"] = visual_result
            
            # ===== ÉTAPE 5: DÉTERMINER LE TYPE DE CONTENU =====
            content_type = await self._determine_content_type(results, transcript, acr_result)
            results["type"] = content_type
            
            # ===== ÉTAPE 6: ENRICHISSEMENT SELON LE TYPE =====
            
            # CAS 1: Film ou série
            if content_type in ["movie", "tv_show", "movie_scene", "tv_show_scene"]:
                await self._enrich_movie_content(results, transcript, frame_analyses if 'frame_analyses' in locals() else [])
            
            # CAS 2: Clip musical
            elif content_type in ["music_video", "concert"] or acr_result:
                await self._enrich_music_content(results, acr_result)
            
            # CAS 3: Autre (interview, documentaire, etc.)
            else:
                await self._enrich_other_content(results, transcript)
            
            # ===== ÉTAPE 7: NETTOYAGE =====
            logger.info(f"VideoOrchestrator: Analyse terminée - Type: {content_type}, Titre: {results.get('title')}")
            return results
            
        except Exception as e:
            logger.error(f"VideoOrchestrator: Erreur critique: {e}", exc_info=True)
            return {
                "type": "unknown",
                "title": None,
                "confidence": 0.0,
                "error": str(e),
                "detection": {"method": "failed", "error": str(e)}
            }
            
        finally:
            # Nettoyage des fichiers temporaires
            if temp_audio_path and os.path.exists(temp_audio_path):
                try:
                    os.unlink(temp_audio_path)
                except Exception as e:
                    logger.error(f"VideoOrchestrator: Erreur nettoyage audio: {e}")
            
            for frame_path in temp_frames:
                if os.path.exists(frame_path):
                    try:
                        os.unlink(frame_path)
                    except Exception as e:
                        logger.error(f"VideoOrchestrator: Erreur nettoyage frame: {e}")
    
    async def _extract_audio(self, video_path: str) -> Optional[str]:
        """
        Extrait la piste audio d'une vidéo au format MP3.
        """
        try:
            # Créer un fichier temporaire pour l'audio
            with tempfile.NamedTemporaryFile(suffix='.mp3', delete=False) as tmp_file:
                audio_path = tmp_file.name
            
            # Commande ffmpeg pour extraire l'audio
            cmd = [
                'ffmpeg',
                '-i', video_path,
                '-q:a', '0',
                '-map', 'a',
                '-y',
                audio_path
            ]
            
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            await process.communicate()
            
            if process.returncode == 0 and os.path.exists(audio_path) and os.path.getsize(audio_path) > 0:
                logger.info(f"VideoOrchestrator: Audio extrait: {audio_path}")
                return audio_path
            else:
                logger.error("VideoOrchestrator: Échec extraction audio")
                return None
                
        except Exception as e:
            logger.error(f"VideoOrchestrator: Erreur extraction audio: {e}")
            return None
    
    async def _extract_key_frames(self, video_path: str) -> List[str]:
        """
        Extrait des frames clés d'une vidéo à intervalles réguliers.
        Utilise OpenCV via subprocess.
        """
        frames = []
        try:
            # Obtenir la durée de la vidéo
            duration = await self._get_video_duration(video_path)
            if not duration:
                duration = 60  # Valeur par défaut
            
            # Calculer l'intervalle en secondes
            interval = max(1, duration / self.MAX_FRAMES)
            
            for i in range(self.MAX_FRAMES):
                # Calculer le timestamp
                timestamp = i * interval
                
                # Créer un fichier temporaire pour la frame
                with tempfile.NamedTemporaryFile(suffix='.jpg', delete=False) as tmp_file:
                    frame_path = tmp_file.name
                
                # Commande ffmpeg pour extraire la frame
                cmd = [
                    'ffmpeg',
                    '-ss', str(timestamp),
                    '-i', video_path,
                    '-frames:v', '1',
                    '-q:v', '2',
                    '-y',
                    frame_path
                ]
                
                process = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                await process.communicate()
                
                if process.returncode == 0 and os.path.exists(frame_path) and os.path.getsize(frame_path) > 0:
                    frames.append(frame_path)
                    logger.debug(f"VideoOrchestrator: Frame extraite à {timestamp}s")
                else:
                    logger.warning(f"VideoOrchestrator: Échec extraction frame à {timestamp}s")
            
            return frames
            
        except Exception as e:
            logger.error(f"VideoOrchestrator: Erreur extraction frames: {e}")
            return frames
    
    async def _get_video_duration(self, video_path: str) -> Optional[float]:
        """
        Récupère la durée de la vidéo avec ffprobe.
        """
        try:
            cmd = [
                'ffprobe',
                '-v', 'quiet',
                '-print_format', 'json',
                '-show_format',
                video_path
            ]
            
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, _ = await process.communicate()
            
            if process.returncode == 0:
                data = json.loads(stdout)
                return float(data.get('format', {}).get('duration', 0))
        except Exception as e:
            logger.error(f"VideoOrchestrator: Erreur récupération durée: {e}")
        return None
    
    async def _analyze_frame(self, frame_path: str) -> Optional[Dict[str, Any]]:
        """
        Analyse une frame avec Gemini Vision.
        Utilise un prompt spécial pour l'analyse vidéo.
        """
        prompt = """
        Tu es un expert en identification de contenus vidéo.
        Analyse cette image extraite d'une vidéo et identifie ce qu'elle représente.

        TYPES DE CONTENU POSSIBLES:
        - "movie_scene": Scène de film
        - "tv_show_scene": Scène de série TV
        - "music_video": Clip musical
        - "concert": Concert
        - "interview": Interview
        - "documentary": Documentaire
        - "sports": Événement sportif
        - "news": Journal télévisé
        - "other": Autre

        RÈGLES D'IDENTIFICATION:
        1. Identifie les personnes visibles (acteurs, chanteurs, présentateurs)
        2. Détecte le contexte (décor, costumes, époque)
        3. Si tu reconnais un film/série, donne le titre
        4. Si tu reconnais un artiste, donne son nom
        5. Détecte tout texte visible (titres, sous-titres, logos)

        Réponds UNIQUEMENT en JSON avec cette structure:
        {
            "content_type": "movie_scene/tv_show_scene/music_video/concert/interview/other",
            "celebrities": [
                {"name": "nom de la personne", "profession": "actor/singer/host/etc"}
            ],
            "title": "titre du film/série/chanson si identifiable",
            "artist": "nom de l'artiste (si musique)",
            "director": "nom du réalisateur (si film)",
            "show_name": "nom de l'émission (si interview/talk-show)",
            "year": "année probable",
            "description": "description de la scène",
            "text_detected": "texte visible à l'écran",
            "confidence": 0.0-1.0
        }
        """
        
        try:
            result = await self.gemini.generate_with_images(
                prompt=prompt,
                image_paths=[frame_path],
                max_tokens=800,
                json_mode=True
            )
            return result
        except Exception as e:
            logger.error(f"VideoOrchestrator: Erreur analyse frame: {e}")
            return None
    
    async def _merge_frame_analyses(self, 
                                   frame_analyses: List[Dict], 
                                   transcript: str,
                                   acr_result: Optional[Dict]) -> Dict[str, Any]:
        """
        Fusionne les analyses des différentes frames pour une conclusion cohérente.
        """
        if not frame_analyses:
            return {}
        
        # Compter les occurrences des types
        type_counts = {}
        title_counts = {}
        artist_counts = {}
        celebrity_counts = {}
        
        for analysis in frame_analyses:
            content_type = analysis.get("content_type")
            if content_type:
                type_counts[content_type] = type_counts.get(content_type, 0) + 1
            
            title = analysis.get("title")
            if title:
                title_counts[title] = title_counts.get(title, 0) + 1
            
            artist = analysis.get("artist")
            if artist:
                artist_counts[artist] = artist_counts.get(artist, 0) + 1
            
            celebrities = analysis.get("celebrities", [])
            for celeb in celebrities:
                name = celeb.get("name")
                if name:
                    celebrity_counts[name] = celebrity_counts.get(name, 0) + 1
        
        # Déterminer le type majoritaire
        content_type = max(type_counts, key=type_counts.get) if type_counts else "unknown"
        
        # Déterminer le titre majoritaire
        title = max(title_counts, key=title_counts.get) if title_counts else None
        
        # Déterminer l'artiste majoritaire
        artist = max(artist_counts, key=artist_counts.get) if artist_counts else None
        
        # Liste des célébrités
        celebrities = [{"name": name} for name, count in celebrity_counts.items() 
                      if count >= len(frame_analyses) / 2]  # Présent dans au moins 50% des frames
        
        # Calculer la confiance moyenne
        avg_confidence = sum(a.get("confidence", 0) for a in frame_analyses) / len(frame_analyses)
        
        return {
            "content_type": content_type,
            "title": title,
            "artist": artist,
            "celebrities": celebrities,
            "confidence": avg_confidence,
            "frame_count": len(frame_analyses)
        }
    
    async def _determine_content_type(self, 
                                     results: Dict, 
                                     transcript: str,
                                     acr_result: Optional[Dict]) -> str:
        """
        Détermine le type de contenu en combinant toutes les analyses.
        """
        visual_type = results.get("visual_analysis", {}).get("content_type")
        
        # Si ACR a détecté de la musique avec haute confiance
        if acr_result and acr_result.get("confidence", 0) >= 0.8:
            return "music_video"
        
        # Si la transcription contient des indices
        if transcript:
            transcript_lower = transcript.lower()
            if any(word in transcript_lower for word in ["film", "movie", "cinéma"]):
                return "movie_scene"
            elif any(word in transcript_lower for word in ["série", "episode", "tv show"]):
                return "tv_show_scene"
            elif any(word in transcript_lower for word in ["chanson", "song", "music"]):
                return "music_video"
            elif any(word in transcript_lower for word in ["interview", "talk show"]):
                return "interview"
        
        # Sinon, utiliser l'analyse visuelle
        return visual_type or "unknown"
    
    async def _enrich_movie_content(self, 
                                   results: Dict, 
                                   transcript: str,
                                   frame_analyses: List[Dict]) -> None:
        """
        Enrichit les résultats pour un contenu de type film/série.
        """
        search_terms = []
        
        # Utiliser le titre de l'analyse visuelle
        if results.get("title"):
            search_terms.append(results["title"])
        
        # Utiliser les noms des célébrités
        celebrities = results.get("visual_analysis", {}).get("celebrities", [])
        if celebrities:
            celeb_names = [c.get("name") for c in celebrities if c.get("name")]
            if celeb_names:
                search_terms.append(" ".join(celeb_names[:2]))
        
        # Utiliser la transcription
        if transcript and len(transcript) > 20:
            search_terms.append(transcript[:100])
        
        # Recherche TMDB
        if self.tmdb:
            for term in search_terms:
                if term:
                    logger.info(f"VideoOrchestrator: Recherche TMDB: '{term}'")
                    tmdb_result = await self.tmdb.search_movie(term, results.get("year"))
                    if tmdb_result:
                        results["tmdb"] = tmdb_result
                        results["title"] = tmdb_result.get("title")
                        results["director"] = tmdb_result.get("director")
                        results["year"] = tmdb_result.get("release_date", "")[:4] if tmdb_result.get("release_date") else None
                        results["description"] = tmdb_result.get("description")
                        results["image"] = tmdb_result.get("image")
                        
                        # Trailer YouTube
                        if self.youtube:
                            youtube_result = await self.youtube.search_trailer(
                                tmdb_result.get("title", ""),
                                results.get("year")
                            )
                            if youtube_result:
                                results["youtube"] = youtube_result
                                results.setdefault("external_links", {})
                                results["external_links"]["youtube"] = youtube_result.get("url")
                        
                        # Streaming JustWatch
                        if self.justwatch and tmdb_result.get("tmdb_id"):
                            streaming = await self.justwatch.search_by_tmdb_id(tmdb_result.get("tmdb_id"))
                            if streaming:
                                results["streaming"] = streaming.get("streaming", [])
                        break
    
    async def _enrich_music_content(self, results: Dict, acr_result: Optional[Dict]) -> None:
        """
        Enrichit les résultats pour un contenu de type musique.
        """
        # Utiliser ACR Cloud si disponible
        if acr_result:
            results["title"] = acr_result.get("title")
            results["artist"] = acr_result.get("artist")
            results["album"] = acr_result.get("album")
            results["year"] = acr_result.get("release_date", "")[:4] if acr_result.get("release_date") else None
            
            # Enrichissement Spotify
            if acr_result.get("spotify_id") and self.spotify:
                logger.info("VideoOrchestrator: Enrichissement Spotify...")
                spotify_result = await self.spotify.get_track(acr_result["spotify_id"])
                if spotify_result:
                    results["spotify"] = spotify_result
                    results["image"] = spotify_result.get("image") or results.get("image")
            
            # Recherche YouTube
            if acr_result.get("title") and acr_result.get("artist") and self.youtube:
                logger.info("VideoOrchestrator: Recherche YouTube...")
                youtube_result = await self.youtube.search_music_video(
                    acr_result.get("title", ""),
                    acr_result.get("artist", "")
                )
                if youtube_result:
                    results["youtube"] = youtube_result
                    results.setdefault("external_links", {})
                    results["external_links"]["youtube"] = youtube_result.get("url")
        
        # Sinon, utiliser l'analyse visuelle
        else:
            artist = results.get("visual_analysis", {}).get("artist")
            if artist and self.spotify:
                logger.info(f"VideoOrchestrator: Recherche Spotify pour '{artist}'")
                tracks = await self.spotify.search_track(artist, limit=3)
                if tracks:
                    results["spotify"] = tracks[0]
                    results["title"] = tracks[0].get("title")
                    results["artist"] = tracks[0].get("artist")
                    results["image"] = tracks[0].get("image")
    
    async def _enrich_other_content(self, results: Dict, transcript: str) -> None:
        """
        Enrichit les résultats pour d'autres types de contenu.
        """
        # Si on a une transcription, l'utiliser pour une recherche générale
        if transcript and len(transcript) > 50:
            search_term = transcript[:200]
            
            # Recherche YouTube
            if self.youtube:
                logger.info(f"VideoOrchestrator: Recherche YouTube: '{search_term[:50]}...'")
                youtube_results = await self.youtube.search_video(search_term, max_results=1)
                if youtube_results and len(youtube_results) > 0:
                    results["youtube"] = youtube_results[0]
                    results.setdefault("external_links", {})
                    results["external_links"]["youtube"] = youtube_results[0].get("url")
                    results["title"] = youtube_results[0].get("title")
                    results["description"] = youtube_results[0].get("description")
