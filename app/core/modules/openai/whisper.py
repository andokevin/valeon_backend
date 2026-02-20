import asyncio
import os
import logging
from typing import Optional, Dict, Any
from openai import OpenAI
from app.core.config import settings

logger = logging.getLogger(__name__)

class WhisperClient:
    def __init__(self):
        self.client = OpenAI(api_key=settings.OPENAI_API_KEY) if settings.OPENAI_API_KEY else None
        self.model = "whisper-1"

    async def transcribe(self, file_path: str) -> str:
        if not self.client or not os.path.exists(file_path):
            return self._mock_transcribe(file_path)
        try:
            with open(file_path, "rb") as f:
                result = await asyncio.to_thread(
                    self.client.audio.transcriptions.create,
                    model=self.model,
                    file=f,
                    response_format="text",
                )
            return result.strip() if result else ""
        except Exception as e:
            logger.error(f"Whisper transcription error: {e}")
            return self._mock_transcribe(file_path)

    async def transcribe_with_timestamps(self, file_path: str) -> Dict[str, Any]:
        if not self.client or not os.path.exists(file_path):
            return {"text": self._mock_transcribe(file_path), "segments": []}
        try:
            with open(file_path, "rb") as f:
                result = await asyncio.to_thread(
                    self.client.audio.transcriptions.create,
                    model=self.model,
                    file=f,
                    response_format="verbose_json",
                    timestamp_granularities=["segment"],
                )
            return {
                "text": result.text or "",
                "language": getattr(result, "language", "unknown"),
                "duration": getattr(result, "duration", 0),
                "segments": [
                    {
                        "start": s.get("start", 0),
                        "end": s.get("end", 0),
                        "text": s.get("text", ""),
                    }
                    for s in (getattr(result, "segments", []) or [])
                ],
            }
        except Exception as e:
            logger.error(f"Whisper timestamp error: {e}")
            return {"text": self._mock_transcribe(file_path), "segments": []}

    def _mock_transcribe(self, file_path: str) -> str:
        filename = os.path.basename(file_path).lower()
        if "music" in filename or ".mp3" in filename:
            return "This is a song with a melodic rhythm and beautiful lyrics about love."
        if "video" in filename or ".mp4" in filename:
            return "Scene from a movie with dramatic dialogue and background music."
        return "Audio content detected with speech and background sounds."
