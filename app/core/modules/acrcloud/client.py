# app/core/modules/acrcloud/client.py
import httpx
import base64
import hashlib
import hmac
import time
from typing import Optional, Dict, Any
from app.core.config import settings
import logging

logger = logging.getLogger(__name__)

class ACRCloudClient:
    """
    Client pour l'API ACRCloud (fingerprinting musical).
    """
    
    def __init__(self):
        self.host = settings.ACRCLOUD_HOST
        self.access_key = settings.ACRCLOUD_ACCESS_KEY
        self.secret_key = settings.ACRCLOUD_SECRET_KEY
        self.endpoint = f"https://{self.host}/v1/identify"
        
        if not all([self.host, self.access_key, self.secret_key]):
            logger.warning("ACRCloud non configuré - vérifier les variables d'environnement")
    
    def _generate_signature(self, timestamp: int) -> str:
        """Génère la signature HMAC-SHA1."""
        string_to_sign = f"POST\n/v1/identify\n{self.access_key}\naudio\n1\n{timestamp}"
        sign = hmac.new(
            self.secret_key.encode('utf-8'),
            string_to_sign.encode('utf-8'),
            hashlib.sha1
        )
        return base64.b64encode(sign.digest()).decode('utf-8')
    
    async def recognize(self, audio_path: str) -> Optional[Dict[str, Any]]:
        """
        Identifie une musique à partir d'un fichier audio.
        """
        try:
            # Lire le fichier audio
            with open(audio_path, 'rb') as f:
                audio_data = f.read()
            
            timestamp = int(time.time())
            signature = self._generate_signature(timestamp)
            
            # Préparer les données multipart
            files = {
                'sample': ('audio', audio_data, 'audio/mpeg')
            }
            data = {
                'access_key': self.access_key,
                'sample_bytes': len(audio_data),
                'timestamp': timestamp,
                'signature': signature,
                'data_type': 'audio',
                'signature_version': '1'
            }
            
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    self.endpoint,
                    files=files,
                    data=data
                )
                
                if response.status_code == 200:
                    result = response.json()
                    
                    if result.get('status', {}).get('code') == 0:
                        logger.info("ACRCloud: musique identifiée")
                        return self._parse_result(result)
                    else:
                        logger.warning(f"ACRCloud: {result.get('status', {}).get('msg')}")
                        return None
                        
        except Exception as e:
            logger.error(f"Erreur ACRCloud: {e}")
            return None
    
    def _parse_result(self, raw_result: Dict) -> Dict[str, Any]:
        """Parse le résultat ACRCloud en format standard."""
        metadata = raw_result.get('metadata', {})
        music = metadata.get('music', [{}])[0] if metadata.get('music') else {}
        
        return {
            'source': 'acrcloud',
            'title': music.get('title'),
            'artist': music.get('artists', [{}])[0].get('name') if music.get('artists') else None,
            'album': music.get('album', {}).get('name'),
            'release_date': music.get('release_date'),
            'label': music.get('label'),
            'acr_id': music.get('acrid'),
            'duration_ms': music.get('duration_ms'),
            'spotify_id': music.get('external_metadata', {}).get('spotify', {}).get('track', {}).get('id'),
            'youtube_id': music.get('external_metadata', {}).get('youtube', {}).get('vid'),
            'deezer_id': music.get('external_metadata', {}).get('deezer', {}).get('track', {}).get('id'),
            'isrc': music.get('external_ids', {}).get('isrc'),
            'confidence': 0.95
        }