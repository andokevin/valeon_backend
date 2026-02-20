import asyncio
import base64
import os
import logging
import json
from typing import Dict, Any, List, Optional
from openai import OpenAI
from app.core.config import settings

logger = logging.getLogger(__name__)

class VisionClient:
    def __init__(self):
        self.client = OpenAI(api_key=settings.OPENAI_API_KEY) if settings.OPENAI_API_KEY else None
        self.model = settings.OPENAI_DEFAULT_MODEL

    async def analyze(self, file_path: str) -> Dict[str, Any]:
        if not self.client or not os.path.exists(file_path):
            return self._mock_analyze(file_path)
        try:
            with open(file_path, "rb") as f:
                image_data = base64.b64encode(f.read()).decode("utf-8")
            ext = os.path.splitext(file_path)[1].lower().replace(".", "")
            mime = {"jpg": "jpeg", "jpeg": "jpeg", "png": "png",
                    "gif": "gif", "webp": "webp"}.get(ext, "jpeg")

            result = await asyncio.to_thread(
                self.client.chat.completions.create,
                model=settings.OPENAI_ADVANCED_MODEL,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/{mime};base64,{image_data}",
                                    "detail": "high",
                                },
                            },
                            {
                                "type": "text",
                                "text": (
                                    "Analyse cette image et identifie précisément: "
                                    "1) Est-ce une pochette d'album, affiche de film/série, "
                                    "capture d'écran, ou autre visuel médiatique? "
                                    "2) Titre du contenu si visible. "
                                    "3) Artiste/réalisateur si identifiable. "
                                    "4) Année si visible. "
                                    "Réponds en JSON: {type, title, artist, year, description, confidence}"
                                ),
                            },
                        ],
                    }
                ],
                max_tokens=400,
                response_format={"type": "json_object"},
            )
            # PATCH: Import json déplacé en haut + gestion d'erreur
            content = result.choices[0].message.content
            try:
                return json.loads(content)
            except json.JSONDecodeError:
                logger.warning("JSON decode failed, returning raw content")
                return {"raw_content": content, "parsed": False}
        except Exception as e:
            logger.error(f"Vision analysis error: {e}")
            return self._mock_analyze(file_path)

    async def analyze_multiple(self, file_paths: List[str]) -> List[Dict[str, Any]]:
        tasks = [self.analyze(fp) for fp in file_paths]
        return await asyncio.gather(*tasks)

    def _mock_analyze(self, file_path: str) -> Dict[str, Any]:
        filename = os.path.basename(file_path).lower()
        if any(x in filename for x in ["cover", "album", "music"]):
            return {
                "type": "album_cover",
                "title": "Unknown Album",
                "artist": "Unknown Artist",
                "year": None,
                "description": "Album cover artwork with artistic design",
                "confidence": 0.6,
            }
        if any(x in filename for x in ["poster", "movie", "film"]):
            return {
                "type": "movie_poster",
                "title": "Unknown Film",
                "artist": None,
                "year": None,
                "description": "Movie promotional poster",
                "confidence": 0.5,
            }
        return {
            "type": "other",
            "title": None,
            "artist": None,
            "year": None,
            "description": "Image with visual content",
            "confidence": 0.3,
        }
