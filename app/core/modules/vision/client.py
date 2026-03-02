import asyncio
import logging
from typing import Dict, Any, Optional, List
from google.cloud import vision
import io
import os
from app.core.config import settings

logger = logging.getLogger(__name__)

class CloudVisionClient:
    """
    Client pour Google Cloud Vision API
    Utilise le chemin du fichier JSON depuis settings.GOOGLE_APPLICATION_CREDENTIALS
    """
    
    def __init__(self):
        self.enabled = settings.CLOUD_VISION_ENABLED
        self.max_results = 10
        self.confidence_threshold = settings.VISION_CONFIDENCE_THRESHOLD
        self.creds_path = settings.GOOGLE_APPLICATION_CREDENTIALS
        
        if self.enabled:
            # Vérifier que le fichier existe
            if not self.creds_path or not os.path.exists(self.creds_path):
                logger.warning(f"CloudVisionClient: Fichier de credentials non trouvé: {self.creds_path}")
                self.enabled = False
            else:
                try:
                    # Définir la variable d'environnement pour google-cloud-vision
                    os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = self.creds_path
                    
                    # Initialiser le client Vision
                    self.client = vision.ImageAnnotatorClient()
                    logger.info(f"CloudVisionClient: Initialisé avec {self.creds_path}")
                except Exception as e:
                    logger.error(f"CloudVisionClient: Erreur d'initialisation: {e}")
                    self.enabled = False
        else:
            logger.info("CloudVisionClient: Désactivé")

    async def analyze_image(self, image_path: str) -> Dict[str, Any]:
        """
        Analyse une image avec Cloud Vision API
        """
        if not self.enabled:
            return self._mock_response(image_path)
        
        try:
            # Lire l'image
            with io.open(image_path, 'rb') as image_file:
                content = image_file.read()
            
            image = vision.Image(content=content)
            
            # Exécuter en parallèle
            loop = asyncio.get_event_loop()
            
            tasks = [
                loop.run_in_executor(None, lambda: self.client.label_detection(image=image, max_results=self.max_results)),
                loop.run_in_executor(None, lambda: self.client.text_detection(image=image)),
                loop.run_in_executor(None, lambda: self.client.logo_detection(image=image, max_results=self.max_results)),
                loop.run_in_executor(None, lambda: self.client.web_detection(image=image, max_results=self.max_results)),
                loop.run_in_executor(None, lambda: self.client.image_properties(image=image))
            ]
            
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            return self._parse_results(results)
            
        except Exception as e:
            logger.error(f"CloudVisionClient: Erreur: {e}")
            return {"error": str(e), "fallback": True}

    def _parse_results(self, results: List) -> Dict[str, Any]:
        """Parse les résultats"""
        result = {
            "labels": [],
            "text": None,
            "logos": [],
            "web": {},
            "colors": [],
            "confidence": 0.0
        }
        
        try:
            # Labels
            if results[0] and not isinstance(results[0], Exception):
                for label in results[0].label_annotations:
                    result["labels"].append({
                        "description": label.description,
                        "score": label.score
                    })
                    result["confidence"] = max(result["confidence"], label.score)
            
            # Texte
            if results[1] and not isinstance(results[1], Exception):
                if results[1].text_annotations:
                    result["text"] = results[1].text_annotations[0].description
            
            # Logos
            if results[2] and not isinstance(results[2], Exception):
                for logo in results[2].logo_annotations:
                    result["logos"].append({
                        "description": logo.description,
                        "score": logo.score
                    })
            
            # Web
            if results[3] and not isinstance(results[3], Exception):
                if results[3].web_detection:
                    web = results[3].web_detection
                    result["web"] = {
                        "best_guess": web.best_guess_labels[0].label if web.best_guess_labels else None,
                        "pages": [p.url for p in web.pages_with_matching_images[:5]],
                        "similar": [i.url for i in web.visually_similar_images[:5]]
                    }
            
            # Couleurs
            if results[4] and not isinstance(results[4], Exception):
                if results[4].image_properties_annotation:
                    colors = []
                    for c in results[4].image_properties_annotation.dominant_colors.colors[:5]:
                        colors.append({
                            "color": {
                                "red": c.color.red,
                                "green": c.color.green,
                                "blue": c.color.blue
                            },
                            "score": c.score
                        })
                    result["colors"] = colors
            
        except Exception as e:
            logger.error(f"CloudVisionClient: Erreur parsing: {e}")
        
        return result

    def _mock_response(self, image_path: str) -> Dict[str, Any]:
        """Réponse mock"""
        return {
            "labels": [
                {"description": "album cover", "score": 0.95},
                {"description": "music", "score": 0.90}
            ],
            "text": "Listen",
            "logos": [],
            "web": {"best_guess": "Listen album cover"},
            "colors": [],
            "confidence": 0.95
        }