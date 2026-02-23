import json
import logging
from typing import Dict, Any, Optional, List
from app.core.config import settings
from app.core.modules.gemini import GeminiClient

logger = logging.getLogger(__name__)

class DecisionEngine:
    def __init__(self):
        """Initialise le moteur de décision avec Gemini."""
        self.gemini = GeminiClient()
        logger.info("DecisionEngine: Initialisé avec Gemini")

    async def detect_content_type(self, file_info: Dict[str, Any]) -> Dict[str, Any]:
        """
        Détecte le type de contenu à partir des informations disponibles.
        C'est la première étape pour tout scan.
        """
        prompt = f"""Analyse ces informations et détermine le type de contenu.

Informations:
- Type de fichier: {file_info.get('file_type', 'inconnu')}
- Taille: {file_info.get('file_size', 0)} bytes
- Nom: {file_info.get('filename', '')}
- Métadonnées disponibles: {file_info.get('metadata', {})}

Objectif: Détecter précisément ce que contient ce fichier.

Réponds UNIQUEMENT en JSON avec cette structure:
{{
    "content_type": "music" ou "movie" ou "tv_show" ou "album_cover" ou "movie_poster" ou "speech" ou "podcast" ou "interview" ou "other",
    "confidence": 0.0-1.0,
    "should_use_acrcloud": true/false,  # Pour audio uniquement
    "should_use_tmdb": true/false,      # Pour contenu vidéo/film
    "should_use_spotify": true/false,   # Pour musique/album
    "possible_title": "titre si identifiable",
    "possible_artist": "artiste si identifiable",
    "reasoning": "explication courte"
}}"""
        
        result = await self.gemini.generate_text(prompt, json_mode=True)
        return result

    async def analyze_audio_transcript(self, transcript: str) -> Dict[str, Any]:
        """Analyse une transcription audio pour affiner le type."""
        default = {
            "content_type": "unknown",
            "confidence": 0.0,
            "should_use_acrcloud": True,
            "is_music": False,
            "is_speech": False,
            "possible_title": None,
            "possible_artist": None
        }
        
        if not transcript:
            return default
        
        prompt = f"""Analyse cette transcription audio. Détermine:

Transcription: "{transcript[:500]}"

Questions:
1. Est-ce de la musique (paroles de chanson) ?
2. Est-ce un dialogue de film/série ?
3. Est-ce un podcast ?
4. Est-ce un discours ?
5. Y a-t-il un titre identifiable ?
6. Y a-t-il un artiste/réalisateur identifiable ?

Réponds en JSON avec:
{{
    "content_type": "music" ou "movie_dialogue" ou "podcast" ou "speech" ou "other",
    "confidence": 0.0-1.0,
    "should_use_acrcloud": true/false,
    "is_music": true/false,
    "is_dialogue": true/false,
    "possible_title": "titre ou null",
    "possible_artist": "artiste ou null",
    "possible_movie": "nom du film si dialogue"
}}"""
        
        result = await self.gemini.generate_text(prompt, json_mode=True)
        return {**default, **result}

    async def analyze_image_content(self, vision_result: Dict[str, Any]) -> Dict[str, Any]:
        """Analyse une image pour déterminer son type."""
        default = {
            "content_type": "other",
            "confidence": 0.0,
            "should_enrich_with_tmdb": False,
            "should_enrich_with_spotify": False,
            "possible_title": None,
            "possible_artist": None,
            "possible_year": None
        }
        
        labels = vision_result.get("labels", [])
        text = vision_result.get("text", "")
        
        prompt = f"""Analyse cette description d'image pour identifier le contenu.

Labels détectés: {', '.join(labels[:10])}
Texte détecté: "{text[:200]}"

Questions:
1. Est-ce une pochette d'album ?
2. Est-ce une affiche de film/série ?
3. Est-ce une capture d'écran de film ?
4. Est-ce une photo d'artiste ?
5. Quel est le titre probable ?
6. Quel est l'artiste/réalisateur probable ?

Réponds en JSON avec:
{{
    "content_type": "album_cover" ou "movie_poster" ou "movie_screenshot" ou "artist_photo" ou "other",
    "confidence": 0.0-1.0,
    "should_enrich_with_tmdb": true/false,
    "should_enrich_with_spotify": true/false,
    "possible_title": "titre ou null",
    "possible_artist": "artiste ou null",
    "possible_year": "année ou null"
}}"""
        
        result = await self.gemini.generate_text(prompt, json_mode=True)
        return {**default, **result}

    async def analyze_video_frames(self, frame_results: List[Dict[str, Any]], audio_text: str) -> Dict[str, Any]:
        """Analyse des frames vidéo + audio pour identifier le contenu."""
        default = {
            "content_type": "unknown",
            "confidence": 0.0,
            "is_movie": False,
            "is_tv_show": False,
            "is_music_video": False,
            "possible_title": None,
            "possible_year": None,
            "possible_director": None
        }
        
        # Extraire les infos des frames
        all_labels = []
        all_text = []
        for frame in frame_results:
            all_labels.extend(frame.get("labels", []))
            if frame.get("text"):
                all_text.append(frame.get("text"))
        
        prompt = f"""Analyse ces informations vidéo pour identifier le contenu.

Texte audio: "{audio_text[:300]}"
Texte détecté dans les images: "{' '.join(all_text)[:300]}"
Labels fréquents: {', '.join(list(set(all_labels))[:15])}

Questions:
1. Est-ce un film ?
2. Est-ce un épisode de série TV ?
3. Est-ce un clip musical ?
4. Est-ce une bande-annonce ?
5. Quel est le titre probable ?
6. Quelle est l'année probable ?
7. Qui est le réalisateur/artiste ?

Réponds en JSON avec:
{{
    "content_type": "movie" ou "tv_show" ou "music_video" ou "trailer" ou "other",
    "confidence": 0.0-1.0,
    "is_movie": true/false,
    "is_tv_show": true/false,
    "is_music_video": true/false,
    "possible_title": "titre ou null",
    "possible_year": "année ou null",
    "possible_director": "réalisateur ou null",
    "possible_artist": "artiste ou null"
}}"""
        
        result = await self.gemini.generate_text(prompt, json_mode=True)
        return {**default, **result}

    async def merge_audio_results(
        self, 
        transcript: str, 
        acr_result: Optional[dict], 
        spotify_result: Optional[dict],
        content_type: str
    ) -> dict:
        """Fusionne les résultats audio selon le type détecté."""
        default = {
            "title": acr_result.get("title") if acr_result else None,
            "artist": acr_result.get("artist") if acr_result else None,
            "type": content_type,
            "confidence": acr_result.get("confidence", 0.5) if acr_result else 0.5,
            "metadata": acr_result or {},
            "external_links": {}
        }
        
        # Si ACR Cloud a trouvé, c'est probablement une musique
        if acr_result and acr_result.get("title"):
            return default
        
        # Sinon, analyser la transcription
        if transcript and len(transcript) > 50:
            prompt = f"""Analyse cette transcription pour identifier le contenu audio.
Type suspecté: {content_type}

Transcription: "{transcript[:500]}"

Réponds en JSON avec: title, artist, type, confidence, description."""
            
            result = await self.gemini.generate_text(prompt, json_mode=True)
            return {**default, **result}
        
        return default

    async def merge_video_results(
        self, 
        audio_text: str,
        frame_results: List[dict],
        tmdb_result: Optional[dict],
        content_type: str
    ) -> dict:
        """Fusionne les résultats vidéo selon le type détecté."""
        default = {
            "title": tmdb_result.get("title") if tmdb_result else None,
            "type": content_type,
            "confidence": 0.5,
            "description": tmdb_result.get("description") if tmdb_result else None,
            "metadata": tmdb_result or {}
        }
        
        # Si TMDB a trouvé, on l'utilise
        if tmdb_result:
            return default
        
        # Sinon, on analyse avec Gemini
        if audio_text or frame_results:
            prompt = f"""Identifie ce contenu vidéo.
Type suspecté: {content_type}

Audio: "{audio_text[:300]}"
Frames: {len(frame_results)} images analysées

Réponds en JSON avec: title, type, year, description, confidence."""
            
            result = await self.gemini.generate_text(prompt, json_mode=True)
            return {**default, **result}
        
        return default