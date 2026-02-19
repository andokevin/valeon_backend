# app/core/modules/openai/whisper.py
import openai
from openai import OpenAI
from typing import Optional, Dict, Any
import logging
from app.core.config import settings

logger = logging.getLogger(__name__)

class WhisperClient:
    """
    Client pour l'API Whisper d'OpenAI (cloud uniquement).
    """
    
    def __init__(self):
        self.client = OpenAI(api_key=settings.OPENAI_API_KEY)
    
    async def transcribe(self, audio_path: str) -> str:
        """
        Transcrit un fichier audio en texte.
        """
        try:
            with open(audio_path, "rb") as audio_file:
                response = self.client.audio.transcriptions.create(
                    model="whisper-1",
                    file=audio_file,
                    response_format="text"
                )
            
            logger.info(f"Transcription réussie ({len(response)} caractères)")
            return response
            
        except Exception as e:
            logger.error(f"Erreur transcription Whisper: {e}")
            return ""
    
    async def transcribe_with_timestamps(self, audio_path: str) -> Dict[str, Any]:
        """
        Transcrit avec timestamps (pour vidéo).
        """
        try:
            with open(audio_path, "rb") as audio_file:
                response = self.client.audio.transcriptions.create(
                    model="whisper-1",
                    file=audio_file,
                    response_format="verbose_json",
                    timestamp_granularities=["segment"]
                )
            
            return {
                "text": response.text,
                "language": response.language,
                "segments": [
                    {
                        "text": seg.text,
                        "start": seg.start,
                        "end": seg.end
                    }
                    for seg in response.segments
                ]
            }
            
        except Exception as e:
            logger.error(f"Erreur transcription Whisper: {e}")
            return {"text": "", "language": "unknown", "segments": []}