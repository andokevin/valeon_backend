import openai
from openai import OpenAI
import base64
from typing import Dict, Any, Optional, List
import tempfile
import os
from PIL import Image
import io
import torch
import torchvision.transforms as transforms
from transformers import AutoImageProcessor, AutoModelForImageClassification
import numpy as np
from app.services.vision.justwatch_client import JustWatchClient  # AJOUT

class VisionRecognizer:
    def __init__(self):
        self.openai_client = OpenAI(api_key=settings.OPENAI_API_KEY)
        self.tmdb_client = None  # Sera initialisé séparément
        self.justwatch_client = JustWatchClient()  # AJOUT
        
        # Charger un modèle de classification d'images léger
        self._load_vision_models()
    
    def _load_vision_models(self):
        """Charge les modèles de vision"""
        try:
            # Modèle de classification d'images
            self.classification_processor = AutoImageProcessor.from_pretrained(
                "google/vit-base-patch16-224"
            )
            self.classification_model = AutoModelForImageClassification.from_pretrained(
                "google/vit-base-patch16-224"
            )
            self.classification_model.eval()
        except Exception as e:
            print(f"Erreur chargement modèle vision: {e}")
            self.classification_model = None
    
    async def recognize_from_image(self, image_path: str) -> Dict[str, Any]:
        """
        Reconnaît le contenu d'une image en utilisant plusieurs méthodes
        """
        results = {}
        
        # Méthode 1: GPT-4 Vision
        gpt_result = await self._analyze_with_gpt4(image_path)
        if gpt_result:
            results['gpt4'] = gpt_result
        
        # Méthode 2: Classification locale
        local_result = await self._classify_image_local(image_path)
        if local_result:
            results['classification'] = local_result
        
        # Fusionner les résultats
        final_result = await self._merge_vision_results(results, image_path)
        
        return final_result
    
    async def _analyze_with_gpt4(self, image_path: str) -> Optional[Dict]:
        """Analyse l'image avec GPT-4 Vision"""
        try:
            with open(image_path, "rb") as image_file:
                base64_image = base64.b64encode(image_file.read()).decode('utf-8')
            
            response = self.openai_client.chat.completions.create(
                model="gpt-4-vision-preview",
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": """Analyse cette image en profondeur. Identifie:
                                1. Si c'est une scène de film/série: donne le titre probable, année, réalisateur
                                2. Si c'est un album/artiste: donne le nom de l'artiste, titre de l'album
                                3. Si c'est une personne célèbre: donne son nom et pourquoi elle est célèbre
                                4. Si c'est un lieu: donne le nom du lieu et sa localisation
                                5. Si c'est une œuvre d'art: donne le titre, l'artiste, l'année
                                6. Si c'est un produit: donne la marque, le modèle
                                
                                Réponds en JSON avec les champs: type, title, description, details, year"""
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
                max_tokens=500,
                response_format={"type": "json_object"}
            )
            
            return eval(response.choices[0].message.content)
        except Exception as e:
            print(f"Erreur GPT-4 Vision: {e}")
        return None
    
    async def _classify_image_local(self, image_path: str) -> Optional[Dict]:
        """Classification locale de l'image"""
        if not self.classification_model:
            return None
        
        try:
            image = Image.open(image_path).convert('RGB')
            inputs = self.classification_processor(images=image, return_tensors="pt")
            
            with torch.no_grad():
                outputs = self.classification_model(**inputs)
                predictions = torch.nn.functional.softmax(outputs.logits, dim=-1)
            
            # Obtenir les top 5 prédictions
            top5_prob, top5_idx = torch.topk(predictions[0], 5)
            
            results = []
            for i in range(5):
                results.append({
                    'label': self.classification_model.config.id2label[top5_idx[i].item()],
                    'confidence': float(top5_prob[i].item())
                })
            
            return {
                'predictions': results,
                'model': 'vit-base-patch16-224'
            }
        except Exception as e:
            print(f"Erreur classification locale: {e}")
        return None
    
    async def _merge_vision_results(self, results: Dict, image_path: str) -> Dict:
        """Fusionne les résultats des différentes méthodes avec AJOUT JUSTWATCH"""
        final = {
            'source': 'merged',
            'confidence': 0,
            'type': 'unknown',
            'title': None,
            'description': None,
            'metadata': {},
            'streaming': None  # AJOUT
        }
        
        # Priorité à GPT-4 pour l'analyse détaillée
        if 'gpt4' in results and results['gpt4']:
            final.update(results['gpt4'])
            final['confidence'] = 0.9
            
            # AJOUT: Si c'est un film, chercher les infos de streaming
            if final.get('type') in ['movie', 'film', 'tv_show', 'série']:
                if final.get('title'):
                    # Chercher d'abord avec JustWatch
                    justwatch_result = await self.justwatch_client.search_movie(
                        final['title'],
                        final.get('year')
                    )
                    
                    if justwatch_result:
                        final['streaming'] = justwatch_result.get('streaming')
                        final['justwatch_id'] = justwatch_result.get('justwatch_id')
                        final['metadata']['justwatch'] = justwatch_result
                        
                        # Mettre à jour avec les infos JustWatch
                        if justwatch_result.get('poster'):
                            final['image'] = justwatch_result['poster']
                        if justwatch_result.get('genres'):
                            final['metadata']['genres'] = justwatch_result['genres']
        
        elif 'classification' in results and results['classification']:
            final['description'] = f"Image classifiée comme: {results['classification']['predictions'][0]['label']}"
            final['metadata']['classifications'] = results['classification']['predictions']
            final['confidence'] = results['classification']['predictions'][0]['confidence']
        
        return final