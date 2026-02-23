import asyncio
import json
import logging
from typing import Dict, Any, List, Optional
from google import genai  # ✅ Nouvelle API uniquement
from app.core.config import settings

logger = logging.getLogger(__name__)

class GeminiClient:
    def __init__(self):
        """Initialise le client Gemini avec la nouvelle API."""
        self.api_key = settings.GEMINI_API_KEY
        self.model_name = settings.GEMINI_MODEL or "gemini-2.5-flash"
        self.enabled = settings.GEMINI_ENABLED
        
        if self.enabled and self.api_key:
            try:
                # ✅ NOUVEAU : Client au lieu de configure()
                self.client = genai.Client(api_key=self.api_key)
                logger.info(f"GeminiClient: Initialisé avec modèle {self.model_name}")
            except Exception as e:
                logger.error(f"GeminiClient: Erreur initialisation: {e}")
                self.client = None
                self.enabled = False
        else:
            logger.warning("GeminiClient: Non configuré, mode mock")
            self.client = None

    async def generate_text(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        max_tokens: int = 500,
        json_mode: bool = False
    ) -> Dict[str, Any]:
        """Génère du texte avec Gemini."""
        if not self.enabled or not self.client:
            return self._mock_response(prompt)

        try:
            # Construire le contenu
            contents = []
            if system_prompt:
                contents.append(system_prompt)
            contents.append(prompt)
            
            # Configuration
            config = {
                "max_output_tokens": max_tokens,
                "temperature": 0.4,
            }
            
            if json_mode:
                config["response_mime_type"] = "application/json"
            
            # ✅ NOUVEAU : Appel via client.models
            response = await asyncio.to_thread(
                self.client.models.generate_content,
                model=self.model_name,
                contents="\n\n".join(contents),
                config=config
            )
            
            if json_mode:
                try:
                    return json.loads(response.text)
                except json.JSONDecodeError:
                    return {"text": response.text, "error": "Invalid JSON"}
            
            return {"text": response.text}
            
        except Exception as e:
            logger.error(f"GeminiClient: Erreur generate_text: {e}")
            return self._mock_response(prompt)

    async def generate_with_images(
        self,
        prompt: str,
        image_paths: List[str],
        max_tokens: int = 500,
        json_mode: bool = False
    ) -> Dict[str, Any]:
        """Génère du texte avec images (vision)."""
        if not self.enabled or not self.client:
            return self._mock_response(prompt)

        try:
            # Construire les parties (texte + images)
            from google.genai import types
            parts = [prompt]
            
            for path in image_paths:
                try:
                    with open(path, "rb") as f:
                        img_data = f.read()
                    # ✅ NOUVEAU : Création de partie image
                    parts.append(
                        types.Part.from_bytes(
                            data=img_data,
                            mime_type="image/jpeg"
                        )
                    )
                except Exception as e:
                    logger.error(f"GeminiClient: Erreur chargement image {path}: {e}")

            config = {
                "max_output_tokens": max_tokens,
                "temperature": 0.4,
            }
            
            if json_mode:
                config["response_mime_type"] = "application/json"

            response = await asyncio.to_thread(
                self.client.models.generate_content,
                model=self.model_name,
                contents=parts,
                config=config
            )
            
            if json_mode:
                try:
                    return json.loads(response.text)
                except json.JSONDecodeError:
                    return {"text": response.text}
            
            return {"text": response.text}
            
        except Exception as e:
            logger.error(f"GeminiClient: Erreur generate_with_images: {e}")
            return self._mock_response(prompt)

    async def analyze_image(
        self,
        file_path: str,
        prompt: str = "Décris cette image en détail. Identifie le type de contenu (album cover, movie poster, etc.), le titre si visible, l'artiste si connu."
    ) -> Dict[str, Any]:
        """Analyse une image avec Gemini Vision."""
        result = await self.generate_with_images(prompt, [file_path])
        
        # Essayer de parser le résultat JSON
        try:
            text = result.get("text", "")
            if "{" in text:
                import re
                json_match = re.search(r'\{.*\}', text, re.DOTALL)
                if json_match:
                    return json.loads(json_match.group())
        except:
            pass
        
        return {
            "type": "unknown",
            "title": None,
            "artist": None,
            "year": None,
            "description": result.get("text", ""),
            "confidence": 0.5
        }

    async def generate_recommendations(
        self,
        user_history: List[Dict[str, Any]],
        query: str,
        preferences: Optional[dict] = None
    ) -> Dict[str, Any]:
        """Génère des recommandations basées sur l'historique."""
        system_prompt = (
            "Tu es un expert en recommandations musicales et cinématographiques. "
            "Analyse l'historique de l'utilisateur et génère des recommandations pertinentes. "
            "Réponds UNIQUEMENT en JSON valide."
        )

        history_str = json.dumps(user_history[:15], ensure_ascii=False, default=str)
        prefs_str = json.dumps(preferences or {}, ensure_ascii=False, default=str)

        user_prompt = (
            f"Historique utilisateur: {history_str}\n"
            f"Préférences: {prefs_str}\n"
            f"Requête: {query}\n"
            "Génère 8-10 recommandations au format JSON avec la structure: "
            '{"recommendations": [{"title": "", "type": "", "artist": "", "reason": "", "confidence": 0.0}]}'
        )

        return await self.generate_text(
            prompt=user_prompt,
            system_prompt=system_prompt,
            max_tokens=800,
            json_mode=True
        )

    async def chat(
        self,
        messages: List[Dict[str, str]],
        max_tokens: int = 500
    ) -> Dict[str, Any]:
        """Version chat avec historique."""
        if not self.enabled or not self.client:
            return {"text": "Service non disponible"}

        try:
            # Construire la conversation
            conversation_parts = []
            for msg in messages:
                role = msg.get("role", "user")
                content = msg.get("content", "")
                if role == "system":
                    conversation_parts.insert(0, f"[System] {content}")
                elif role == "user":
                    conversation_parts.append(f"User: {content}")
                elif role == "assistant":
                    conversation_parts.append(f"Assistant: {content}")
            
            conversation_parts.append("Assistant:")

            response = await asyncio.to_thread(
                self.client.models.generate_content,
                model=self.model_name,
                contents="\n".join(conversation_parts),
                config={
                    "max_output_tokens": max_tokens,
                    "temperature": 0.7,
                }
            )
            
            return {"text": response.text}
            
        except Exception as e:
            logger.error(f"GeminiClient: Erreur chat: {e}")
            return {"text": "Désolé, une erreur est survenue."}

    def _mock_response(self, prompt: str) -> Dict[str, Any]:
        """Réponse mock quand Gemini n'est pas disponible."""
        return {
            "text": "Mode démo - Gemini non configuré",
            "recommendations": [
                {
                    "title": "Blinding Lights",
                    "type": "music",
                    "artist": "The Weeknd",
                    "reason": "Tendance actuelle",
                    "confidence": 0.9
                }
            ]
        }