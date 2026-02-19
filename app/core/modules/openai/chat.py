# app/core/modules/openai/chat.py
from openai import OpenAI
from typing import Dict, Any, Optional, List
import json
import logging
from app.core.config import settings

logger = logging.getLogger(__name__)

class ChatClient:
    """
    Client pour les conversations GPT (recommandations, chat).
    """
    
    def __init__(self):
        self.client = OpenAI(api_key=settings.OPENAI_API_KEY)
    
    async def get_recommendations(
        self,
        user_history: List[Dict],
        query: str,
        preferences: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """
        Obtient des recommandations personnalisées.
        """
        context = "Historique utilisateur:\n"
        for item in user_history[:10]:
            context += f"- {item.get('title')} ({item.get('type')})\n"
        
        if preferences:
            context += f"\nPréférences: {json.dumps(preferences, indent=2)}\n"
        
        try:
            response = self.client.chat.completions.create(
                model="gpt-4",
                messages=[
                    {"role": "system", "content": """Tu es un expert en recommandations de films, musiques et séries.
                    Analyse l'historique et la requête pour recommander des contenus pertinents.
                    Réponds en JSON avec une liste de recommandations contenant:
                    - title: titre
                    - type: film/musique/série
                    - artist/realisateur
                    - description courte
                    - raison: pourquoi ça pourrait plaire"""},
                    {"role": "user", "content": f"{context}\n\nRequête: {query}"}
                ],
                temperature=0.7,
                max_tokens=800,
                response_format={"type": "json_object"}
            )
            
            return json.loads(response.choices[0].message.content)
            
        except Exception as e:
            logger.error(f"Erreur recommandations: {e}")
            return {"recommendations": []}
    
    async def chat_completion(
        self,
        messages: List[Dict[str, str]],
        model: str = "gpt-3.5-turbo",
        temperature: float = 0.7,
        max_tokens: int = 500
    ) -> str:
        """
        Completion de chat générique.
        """
        try:
            response = self.client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens
            )
            
            return response.choices[0].message.content
            
        except Exception as e:
            logger.error(f"Erreur chat: {e}")
            return ""