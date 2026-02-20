import asyncio
import json
import logging
from typing import Dict, Any, List, Optional
from openai import OpenAI
from app.core.config import settings

logger = logging.getLogger(__name__)

class ChatClient:
    def __init__(self):
        self.client = OpenAI(api_key=settings.OPENAI_API_KEY) if settings.OPENAI_API_KEY else None

    async def _chat(
        self,
        messages: List[dict],
        model: Optional[str] = None,
        max_tokens: int = 500,
        json_mode: bool = True,
    ) -> Dict[str, Any]:
        if not self.client:
            return {}
        try:
            kwargs = dict(
                model=model or settings.OPENAI_DEFAULT_MODEL,
                messages=messages,
                temperature=0.4,
                max_tokens=max_tokens,
            )
            if json_mode:
                kwargs["response_format"] = {"type": "json_object"}
            result = await asyncio.to_thread(
                self.client.chat.completions.create, **kwargs
            )
            content = result.choices[0].message.content
            return json.loads(content) if json_mode else {"text": content}
        except Exception as e:
            logger.error(f"ChatClient error: {e}")
            return {}

    # Reste du code inchangé - déjà compatible
    async def get_recommendations(
        self,
        user_history: List[Dict[str, Any]],
        query: str,
        preferences: Optional[dict] = None,
    ) -> Dict[str, Any]:
        if not user_history:
            return self._mock_recommendations()
        history_str = json.dumps(user_history[:10], ensure_ascii=False)
        prefs_str = json.dumps(preferences or {}, ensure_ascii=False)
        result = await self._chat(
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Tu es un expert en recommandations musicales et cinématographiques. "
                        "Analyse l'historique de l'utilisateur et génère des recommandations pertinentes. "
                        "Réponds UNIQUEMENT en JSON valide."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"Historique utilisateur: {history_str}\n"
                        f"Préférences: {prefs_str}\n"
                        f"Requête: {query}\n"
                        "Génère 10 recommandations sous format: "
                        '{"recommendations": [{"title": "", "type": "", "artist": "", '
                        '"reason": "", "confidence": 0.0}]}'
                    ),
                },
            ],
            model=settings.OPENAI_ADVANCED_MODEL,
            max_tokens=800,
        )
        return result if result else self._mock_recommendations()

    async def enrich_content(self, title: str, content_type: str) -> Dict[str, Any]:
        result = await self._chat(
            messages=[
                {
                    "role": "system",
                    "content": "Expert en métadonnées culturelles. JSON uniquement.",
                },
                {
                    "role": "user",
                    "content": (
                        f'Enrichis: titre="{title}", type="{content_type}". '
                        "Réponds: {description, genres, year, tags, similar_titles}"
                    ),
                },
            ],
            max_tokens=400,
        )
        return result

    def _mock_recommendations(self) -> Dict[str, Any]:
        return {
            "recommendations": [
                {"title": "Blinding Lights", "type": "music",
                 "artist": "The Weeknd", "reason": "Populaire en ce moment", "confidence": 0.9},
                {"title": "Shape of You", "type": "music",
                 "artist": "Ed Sheeran", "reason": "Correspondance style", "confidence": 0.85},
                {"title": "Interstellar", "type": "movie",
                 "artist": "Christopher Nolan", "reason": "Film très apprécié", "confidence": 0.8},
            ]
        }
