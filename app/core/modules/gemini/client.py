# app/core/modules/gemini/client.py
import asyncio
import json
import logging
import re
from typing import Dict, Any, List, Optional
from google import genai
from google.genai import types
from app.core.config import settings

logger = logging.getLogger(__name__)

class GeminiClient:
    def __init__(self):
        """Initialise le client Gemini avec fallback automatique."""
        self.api_key = settings.GEMINI_API_KEY
        self.primary_model = settings.GEMINI_MODEL
        self.fallback_model = settings.GEMINI_FALLBACK_MODEL
        self.fallback_enabled = settings.GEMINI_FALLBACK_ENABLED
        self.enabled = settings.GEMINI_ENABLED
        
        # Compteurs pour suivre l'utilisation
        self.primary_requests = 0
        self.fallback_requests = 0
        self.quota_threshold = settings.GEMINI_QUOTA_THRESHOLD
        
        if self.enabled and self.api_key:
            try:
                self.client = genai.Client(api_key=self.api_key)
                logger.info(f"GeminiClient: Initialisé avec modèle principal {self.primary_model}")
                if self.fallback_enabled:
                    logger.info(f"GeminiClient: Fallback activé vers {self.fallback_model}")
            except Exception as e:
                logger.error(f"GeminiClient: Erreur initialisation: {e}")
                self.client = None
                self.enabled = False
        else:
            logger.warning("GeminiClient: Non configuré, mode mock")
            self.client = None

    async def _call_with_model(self, model: str, contents: Any, config: dict) -> Any:
        """Appelle Gemini avec un modèle spécifique."""
        try:
            logger.debug(f"GeminiClient: Appel du modèle {model}")
            response = await asyncio.to_thread(
                self.client.models.generate_content,
                model=model,
                contents=contents,
                config=config
            )
            return response
        except Exception as e:
            error_str = str(e).lower()
            
            # Détection des erreurs de quota
            if "429" in error_str or "quota" in error_str or "resource exhausted" in error_str:
                logger.warning(f"GeminiClient: Quota épuisé pour {model}: {e}")
                return type('QuotaError', (), {'error': 'quota_exceeded', 'status_code': 429})()
            
            # Autres erreurs
            logger.error(f"GeminiClient: Erreur avec {model}: {e}")
            raise

    async def generate_text(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        max_tokens: int = 500,
        json_mode: bool = False,
        force_fallback: bool = False,
        **kwargs  # ← CORRECTION: accepter tous les arguments supplémentaires
    ) -> Dict[str, Any]:
        """Génère du texte avec Gemini, avec fallback automatique."""
        if not self.enabled or not self.client:
            return self._mock_response(prompt)

        # Construire le contenu
        contents = []
        if system_prompt:
            contents.append(system_prompt)
        contents.append(prompt)
        
        # Configuration avec kwargs
        config = {
            "max_output_tokens": max_tokens,
            "temperature": kwargs.get('temperature', 0.4),  # ← CORRECTION
            "top_p": kwargs.get('top_p', 0.95),
            "top_k": kwargs.get('top_k', 40),
        }
        
        if json_mode:
            config["response_mime_type"] = "application/json"
        
        # Déterminer quel modèle utiliser
        model_to_use = self.fallback_model if force_fallback else self.primary_model
        
        try:
            # Premier appel
            response = await self._call_with_model(
                model_to_use,
                "\n\n".join(contents),
                config
            )
            
            # Vérifier si c'est une erreur de quota
            if hasattr(response, 'error') and response.error == 'quota_exceeded':
                if self.fallback_enabled and model_to_use == self.primary_model:
                    logger.info(f"GeminiClient: Quota {self.primary_model} épuisé, fallback vers {self.fallback_model}")
                    self.primary_requests += 1
                    
                    # Réessayer avec le fallback
                    response = await self._call_with_model(
                        self.fallback_model,
                        "\n\n".join(contents),
                        config
                    )
                    
                    if hasattr(response, 'error'):
                        logger.error("GeminiClient: Fallback également épuisé")
                        return self._mock_response(prompt)
                    
                    self.fallback_requests += 1
                    logger.info(f"GeminiClient: Fallback réussi avec {self.fallback_model}")
                else:
                    logger.error("GeminiClient: Quota épuisé et fallback désactivé")
                    return self._mock_response(prompt)
            
            # Compter les requêtes réussies
            if model_to_use == self.primary_model:
                self.primary_requests += 1
            else:
                self.fallback_requests += 1
            
            # Traiter la réponse
            if json_mode:
                return self._parse_json_response(response.text)
            
            return {"text": response.text}
            
        except Exception as e:
            logger.error(f"GeminiClient: Erreur generate_text: {e}")
            return self._mock_response(prompt)

    async def generate_with_images(
        self,
        prompt: str,
        image_paths: List[str],
        max_tokens: int = 500,
        json_mode: bool = False,
        force_fallback: bool = False,
        **kwargs  # ← CORRECTION: ajout de **kwargs pour cohérence
    ) -> Dict[str, Any]:
        """Génère du texte avec images (vision), avec fallback automatique."""
        if not self.enabled or not self.client:
            return self._mock_response(prompt)

        try:
            # Construire les parties (texte + images)
            parts = [prompt]
            
            for path in image_paths:
                try:
                    with open(path, "rb") as f:
                        img_data = f.read()
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
                "temperature": kwargs.get('temperature', 0.4),  # ← CORRECTION
                "top_p": kwargs.get('top_p', 0.95),
                "top_k": kwargs.get('top_k', 40),
            }
            
            if json_mode:
                config["response_mime_type"] = "application/json"

            # Déterminer quel modèle utiliser
            model_to_use = self.fallback_model if force_fallback else self.primary_model
            
            try:
                # Premier appel
                response = await self._call_with_model(
                    model_to_use,
                    parts,
                    config
                )
                
                # Vérifier si c'est une erreur de quota
                if hasattr(response, 'error') and response.error == 'quota_exceeded':
                    if self.fallback_enabled and model_to_use == self.primary_model:
                        logger.info(f"GeminiClient: Quota {self.primary_model} épuisé pour vision, fallback vers {self.fallback_model}")
                        self.primary_requests += 1
                        
                        # Réessayer avec le fallback
                        response = await self._call_with_model(
                            self.fallback_model,
                            parts,
                            config
                        )
                        
                        if hasattr(response, 'error'):
                            logger.error("GeminiClient: Fallback également épuisé pour vision")
                            return self._mock_response(prompt)
                        
                        self.fallback_requests += 1
                        logger.info(f"GeminiClient: Fallback réussi avec {self.fallback_model} pour vision")
                    else:
                        logger.error("GeminiClient: Quota épuisé et fallback désactivé pour vision")
                        return self._mock_response(prompt)
                
                # Compter les requêtes réussies
                if model_to_use == self.primary_model:
                    self.primary_requests += 1
                else:
                    self.fallback_requests += 1
                
                # Traiter la réponse
                if json_mode:
                    return self._parse_json_response(response.text)
                
                return {"text": response.text}
                
            except Exception as e:
                logger.error(f"GeminiClient: Erreur generate_with_images: {e}")
                return self._mock_response(prompt)
            
        except Exception as e:
            logger.error(f"GeminiClient: Erreur generate_with_images: {e}")
            return self._mock_response(prompt)

    def _parse_json_response(self, text: str) -> Dict[str, Any]:
        """
        Parse une réponse JSON de Gemini de manière robuste.
        Gère les cas où le JSON est mal formé ou entouré de texte.
        """
        if not text:
            logger.warning("GeminiClient: Réponse vide")
            return {"error": "empty_response"}
        
        try:
            # Nettoyer la réponse
            text = text.strip()
            
            # Enlever les blocs de code markdown
            if text.startswith('```json'):
                text = text.replace('```json', '').replace('```', '')
            elif text.startswith('```'):
                text = text.replace('```', '')
            
            # Nettoyer les espaces et retours à la ligne
            text = text.strip()
            
            # Essayer de trouver le premier { et le dernier }
            start_idx = text.find('{')
            end_idx = text.rfind('}')
            
            if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
                json_str = text[start_idx:end_idx + 1]
                logger.debug(f"GeminiClient: JSON extrait: {json_str[:200]}...")
            else:
                json_str = text
            
            # Essayer de parser normalement
            try:
                return json.loads(json_str)
            except json.JSONDecodeError as e:
                logger.debug(f"GeminiClient: Échec du parsing normal, tentative de correction: {e}")
                
                # Correction des guillemets simples
                # Remplacer les guillemets simples par des doubles, mais pas à l'intérieur des mots
                corrected = re.sub(r"(?<!\w)'(?!\w)", '"', json_str)
                
                # Correction des virgules en trop avant }
                corrected = re.sub(r',\s*}', '}', corrected)
                
                # Correction des virgules en trop avant ]
                corrected = re.sub(r',\s*\]', ']', corrected)
                
                # Essayer de parser après correction
                try:
                    return json.loads(corrected)
                except json.JSONDecodeError as e2:
                    logger.error(f"GeminiClient: Échec après correction: {e2}")
                    
                    # Dernier recours : extraction manuelle des champs
                    return self._extract_fields_manually(text)
                    
        except Exception as e:
            logger.error(f"GeminiClient: Erreur inattendue lors du parsing: {e}")
            return {"text": text, "error": str(e)}

    def _extract_fields_manually(self, text: str) -> Dict[str, Any]:
        """
        Extrait manuellement les champs importants du texte quand le JSON est invalide.
        """
        result = {}
        
        try:
            # Chercher content_type
            match = re.search(r'content_type["\s:]+([^",}\s]+)', text)
            if match:
                result["content_type"] = match.group(1).strip('"\'')
            
            # Chercher title
            match = re.search(r'title["\s:]+([^",}\s]+)', text)
            if match:
                result["title"] = match.group(1).strip('"\'')
            
            # Chercher artist
            match = re.search(r'artist["\s:]+([^",}\s]+)', text)
            if match:
                result["artist"] = match.group(1).strip('"\'')
            
            # Chercher director
            match = re.search(r'director["\s:]+([^",}\s]+)', text)
            if match:
                result["director"] = match.group(1).strip('"\'')
            
            # Chercher year
            match = re.search(r'year["\s:]+([0-9]{4})', text)
            if match:
                result["year"] = match.group(1)
            
            # Chercher genre
            match = re.search(r'genre["\s:]+([^",}\s]+)', text)
            if match:
                result["genre"] = match.group(1).strip('"\'')
            
            # Chercher confidence
            match = re.search(r'confidence["\s:]+([0-9.]+)', text)
            if match:
                try:
                    result["confidence"] = float(match.group(1))
                except:
                    result["confidence"] = 0.5
            
            # Chercher action_needed
            match = re.search(r'action_needed["\s:]+([^",}\s]+)', text)
            if match:
                result["action_needed"] = match.group(1).strip('"\'')
            
            # Chercher des acteurs (format array)
            actors_match = re.search(r'actors["\s:]+\[(.*?)\]', text, re.DOTALL)
            if actors_match:
                actors_text = actors_match.group(1)
                actors = re.findall(r'"([^"]+)"', actors_text)
                if actors:
                    result["actors"] = actors
            
            logger.info(f"GeminiClient: Extraction manuelle réussie: {result}")
            
        except Exception as e:
            logger.error(f"GeminiClient: Erreur extraction manuelle: {e}")
        
        return result

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

            response = await self._call_with_model(
                self.primary_model,
                "\n".join(conversation_parts),
                {
                    "max_output_tokens": max_tokens,
                    "temperature": 0.7,
                }
            )
            
            if hasattr(response, 'error') and response.error == 'quota_exceeded':
                if self.fallback_enabled:
                    logger.info("GeminiClient: Fallback pour chat")
                    response = await self._call_with_model(
                        self.fallback_model,
                        "\n".join(conversation_parts),
                        {
                            "max_output_tokens": max_tokens,
                            "temperature": 0.7,
                        }
                    )
            
            return {"text": response.text}
            
        except Exception as e:
            logger.error(f"GeminiClient: Erreur chat: {e}")
            return {"text": "Désolé, une erreur est survenue."}

    def get_stats(self) -> Dict[str, Any]:
        """Retourne les statistiques d'utilisation."""
        return {
            "primary_model": self.primary_model,
            "primary_requests": self.primary_requests,
            "fallback_model": self.fallback_model,
            "fallback_requests": self.fallback_requests,
            "fallback_enabled": self.fallback_enabled,
            "total_requests": self.primary_requests + self.fallback_requests
        }

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