# app/core/orchestrator/decision_engine.py
from openai import OpenAI
from typing import Dict, Any, Optional, List
import json
import logging
from app.core.config import settings

logger = logging.getLogger(__name__)

class DecisionEngine:
    """
    Moteur de décision basé sur GPT.
    C'est le cerveau qui analyse et décide quoi faire.
    """
    
    def __init__(self):
        self.client = OpenAI(api_key=settings.OPENAI_API_KEY)
    
    async def analyze_audio_transcript(self, transcript: str) -> Dict[str, Any]:
        """
        Analyse une transcription audio pour décider de quoi il s'agit.
        """
        prompt = f"""
        Analyse cette transcription audio et détermine son contenu:
        
        TRANSCRIPTION: "{transcript}"
        
        Réponds UNIQUEMENT en JSON avec cette structure exacte:
        {{
            "content_type": "music" ou "speech" ou "noise" ou "unknown" ou "film" ou "series" ou "podcast",
            "confidence": 0.0 à 1.0,
            "should_use_acrcloud": true/false (true si musique probable),
            "possible_title": "titre probable si musique",
            "possible_artist": "artiste probable si musique",
            "is_dialogue": true/false,
            "is_podcast_likely": true/false,
            "summary": "résumé court si dialogue"
        }}
        """
        
        try:
            response = self.client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": "Tu es un expert en analyse audio. Réponds uniquement en JSON."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.3,
                max_tokens=300,
                response_format={"type": "json_object"}
            )
            
            result = json.loads(response.choices[0].message.content)
            logger.info(f"Analyse audio: {result.get('content_type')} (confiance: {result.get('confidence')})")
            return result
            
        except Exception as e:
            logger.error(f"Erreur analyse audio: {e}")
            return {
                "content_type": "unknown",
                "confidence": 0.0,
                "should_use_acrcloud": False,
                "possible_title": None,
                "possible_artist": None,
                "is_dialogue": False,
                "is_podcast_likely": False,
                "summary": None
            }
    
    async def analyze_image_content(self, vision_description: str) -> Dict[str, Any]:
        """
        Analyse la description d'une image pour décider de quoi il s'agit.
        """
        prompt = f"""
        Analyse cette description d'image et détermine son contenu:
        
        DESCRIPTION: "{vision_description}"
        
        Réponds UNIQUEMENT en JSON avec cette structure:
        {{
            "content_type": "movie_poster" ou "album_cover" ou "video_screenshot" ou "person" ou "place" ou "music" ou "other",
            "confidence": 0.0 à 1.0,
            "should_enrich": true/false (si on doit chercher sur TMDB/Spotify),
            "possible_title": "titre probable",
            "possible_artist": "artiste probable (si album)",
            "possible_year": année probable (nombre entier),
            "description_courte": "description courte"
        }}
        """
        
        try:
            response = self.client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": "Tu es un expert en analyse d'images. Réponds uniquement en JSON."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.3,
                max_tokens=300,
                response_format={"type": "json_object"}
            )
            
            return json.loads(response.choices[0].message.content)
            
        except Exception as e:
            logger.error(f"Erreur analyse image: {e}")
            return {
                "content_type": "other",
                "confidence": 0.0,
                "should_enrich": False,
                "possible_title": None,
                "possible_artist": None,
                "possible_year": None,
                "description_courte": vision_description[:200]
            }
    
    async def merge_audio_results(
        self,
        transcript: str,
        acr_result: Optional[Dict],
        spotify_result: Optional[Dict]
    ) -> Dict[str, Any]:
        """
        Fusionne intelligemment les résultats audio.
        """
        prompt = f"""
        Voici trois sources d'information sur un contenu audio:
        
        TRANSCRIPTION WHISPER: "{transcript}"
        
        ACRCLOUD: {json.dumps(acr_result) if acr_result else "Non disponible"}
        
        SPOTIFY: {json.dumps(spotify_result) if spotify_result else "Non disponible"}
        
        Fusionne ces informations en un seul objet JSON cohérent avec:
        - title: le titre
        - artist: l'artiste (si musique)
        - type: "music" ou "podcast" ou "movie_dialogue" ou "other"
        - confidence: 0.0 à 1.0
        - metadata: toutes les infos utiles (album, release_date, etc.)
        - external_links: liens Spotify, YouTube, etc.
        - summary: résumé si dialogue/podcast
        """
        
        try:
            response = self.client.chat.completions.create(
                model="gpt-4",  # GPT-4 pour la fusion complexe
                messages=[
                    {"role": "system", "content": "Tu es un expert en fusion de données multimédia."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.2,
                max_tokens=500,
                response_format={"type": "json_object"}
            )
            
            return json.loads(response.choices[0].message.content)
            
        except Exception as e:
            logger.error(f"Erreur fusion audio: {e}")
            return {
                "title": acr_result.get("title") if acr_result else None,
                "artist": acr_result.get("artist") if acr_result else None,
                "type": "unknown",
                "confidence": 0.0,
                "metadata": {},
                "external_links": {},
                "summary": transcript[:200]
            }
    
    async def merge_video_results(
        self,
        audio_transcript: str,
        vision_results: List[Dict],
        tmdb_result: Optional[Dict]
    ) -> Dict[str, Any]:
        """
        Fusionne les résultats audio et vision pour une vidéo.
        """
        prompt = f"""
        Voici les résultats d'analyse d'une vidéo:
        
        TRANSCRIPTION AUDIO: "{audio_transcript}"
        
        ANALYSES DES IMAGES CLÉS: {json.dumps(vision_results)}
        
        TMDB: {json.dumps(tmdb_result) if tmdb_result else "Non disponible"}
        
        Détermine de quoi il s'agit et réponds en JSON avec:
        - title: le titre (film, série, etc.)
        - type: "movie" ou "tv_show" ou "music_video" ou "other"
        - year: année
        - description: description courte
        - confidence: 0.0 à 1.0
        - metadata: infos supplémentaires
        - external_links: liens TMDB, etc.
        """
        
        try:
            response = self.client.chat.completions.create(
                model="gpt-4",
                messages=[
                    {"role": "system", "content": "Tu es un expert en analyse vidéo."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.2,
                max_tokens=500,
                response_format={"type": "json_object"}
            )
            
            return json.loads(response.choices[0].message.content)
            
        except Exception as e:
            logger.error(f"Erreur fusion vidéo: {e}")
            return {
                "title": None,
                "type": "unknown",
                "year": None,
                "description": None,
                "confidence": 0.0,
                "metadata": {},
                "external_links": {}
            }