import asyncio, json, logging
from typing import Dict, Any, Optional, List
from openai import OpenAI
from app.core.config import settings

logger = logging.getLogger(__name__)

class DecisionEngine:
    def __init__(self):
        self.client = OpenAI(api_key=settings.OPENAI_API_KEY) if settings.OPENAI_API_KEY else None

    async def _chat(self, messages: list, model: str = None, max_tokens: int = 300) -> dict:
        if not self.client:
            return {}
        model = model or settings.OPENAI_DEFAULT_MODEL
        try:
            resp = await asyncio.to_thread(
                self.client.chat.completions.create,
                model=model, messages=messages, temperature=0.3,
                max_tokens=max_tokens, response_format={"type": "json_object"},
            )
            return json.loads(resp.choices[0].message.content)
        except Exception as e:
            logger.error(f"DecisionEngine error: {e}")
            return {}

    async def analyze_audio_transcript(self, transcript: str) -> Dict[str, Any]:
        default = {"content_type": "unknown", "confidence": 0.0, "should_use_acrcloud": False,
                   "is_dialogue": False, "possible_title": None, "possible_artist": None}
        if not transcript:
            return default
        result = await self._chat([
            {"role": "system", "content": "Expert audio. JSON uniquement."},
            {"role": "user", "content": f'Analyse: "{transcript[:500]}"\nRéponds avec content_type, confidence, should_use_acrcloud, is_dialogue, possible_title, possible_artist'},
        ])
        return {**default, **result}

    async def analyze_image_content(self, description: str) -> Dict[str, Any]:
        default = {"content_type": "other", "confidence": 0.0, "should_enrich": False,
                   "possible_title": None, "possible_artist": None, "possible_year": None}
        if not description:
            return default
        result = await self._chat([
            {"role": "system", "content": "Expert image. JSON uniquement."},
            {"role": "user", "content": f'Analyse: "{description[:500]}"\nRéponds avec content_type, confidence, should_enrich, possible_title, possible_artist, possible_year'},
        ])
        return {**default, **result}

    async def merge_audio_results(self, transcript: str, acr_result: Optional[dict], spotify_result: Optional[dict]) -> dict:
        default = {"title": acr_result.get("title") if acr_result else None,
                   "artist": acr_result.get("artist") if acr_result else None,
                   "type": "music" if acr_result else "unknown", "confidence": 0.5,
                   "metadata": acr_result or {}, "external_links": {}}
        if not self.client:
            return default
        result = await self._chat([
            {"role": "system", "content": "Expert fusion données. JSON uniquement."},
            {"role": "user", "content": f"Transcription: {transcript[:200]}\nACR: {json.dumps(acr_result)}\nSpotify: {json.dumps(spotify_result)}\nFusionne en: title, artist, type, confidence, metadata, external_links"},
        ], model=settings.OPENAI_ADVANCED_MODEL, max_tokens=500)
        return {**default, **result}

    async def merge_video_results(self, audio_transcript: str, vision_results: List[dict], tmdb_result: Optional[dict]) -> dict:
        default = {"title": tmdb_result.get("title") if tmdb_result else None,
                   "type": "movie" if tmdb_result else "unknown", "confidence": 0.5,
                   "description": tmdb_result.get("description") if tmdb_result else None,
                   "metadata": tmdb_result or {}}
        if not self.client:
            return default
        result = await self._chat([
            {"role": "system", "content": "Expert vidéo. JSON uniquement."},
            {"role": "user", "content": f"Audio: {audio_transcript[:200]}\nVision: {json.dumps(vision_results[:2])}\nTMDB: {json.dumps(tmdb_result)}\nDonne: title, type, year, description, confidence, metadata"},
        ], model=settings.OPENAI_ADVANCED_MODEL, max_tokens=500)
        return {**default, **result}
