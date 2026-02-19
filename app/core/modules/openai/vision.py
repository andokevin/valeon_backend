# app/core/modules/openai/vision.py
import openai
from openai import OpenAI
import base64
from typing import Optional, Dict, Any
import logging
from app.core.config import settings

logger = logging.getLogger(__name__)

class VisionClient:
    """
    Client pour GPT-4 Vision (cloud uniquement).
    """
    
    def __init__(self):
        self.client = OpenAI(api_key=settings.OPENAI_API_KEY)
    
    async def analyze(self, image_path: str) -> Dict[str, Any]:
        """
        Analyse une image avec GPT-4 Vision.
        """
        try:
            with open(image_path, "rb") as image_file:
                base64_image = base64.b64encode(image_file.read()).decode('utf-8')
            
            response = self.client.chat.completions.create(
                model="gpt-4-vision-preview",
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": """Décris cette image en détail. 
                                Si c'est une affiche de film, donne le titre probable.
                                Si c'est une pochette d'album, donne l'artiste et l'album.
                                Si c'est une personne célèbre, donne son nom.
                                Si c'est un lieu célèbre, donne son nom."""
                            },
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/jpeg;base64,{base64_image}"
                                }
                            }
                        ]
                    }
                ],
                max_tokens=300
            )
            
            description = response.choices[0].message.content
            logger.info(f"Analyse vision réussie ({len(description)} caractères)")
            
            return {
                "description": description,
                "model": "gpt-4-vision"
            }
            
        except Exception as e:
            logger.error(f"Erreur analyse vision: {e}")
            return {"description": "", "model": "error"}