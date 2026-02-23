import asyncio
import base64
import hashlib
import hmac
import os
import time
import logging
import json
import subprocess
import tempfile
from typing import Optional, Dict, Any
import aiohttp
from app.core.config import settings

logger = logging.getLogger(__name__)

class ACRCloudClient:
    def __init__(self):
        self.enabled = settings.ACRCLOUD_ENABLED
        self.host = settings.ACRCLOUD_HOST
        self.access_key = settings.ACRCLOUD_ACCESS_KEY
        self.secret_key = settings.ACRCLOUD_SECRET_KEY
        
        # Logs de configuration
        logger.info(f"ACRCloudClient: enabled={self.enabled}")
        logger.info(f"ACRCloudClient: host={'***' if self.host else 'NON'}")
        logger.info(f"ACRCloudClient: access_key={'***' if self.access_key else 'NON'}")
        logger.info(f"ACRCloudClient: secret_key={'***' if self.secret_key else 'NON'}")

    def _build_signature(self, timestamp: str) -> str:
        string_to_sign = "\n".join(["POST", "/v1/identify", self.access_key, "audio", "1", timestamp])
        return base64.b64encode(
            hmac.new(
                self.secret_key.encode("utf-8"),
                string_to_sign.encode("utf-8"),
                digestmod=hashlib.sha1,
            ).digest()
        ).decode("utf-8")

    async def _extract_audio_sample(self, file_path: str, duration: int = 20) -> Optional[str]:
        """
        Extrait un échantillon audio de 'duration' secondes au format MP3.
        Utilise ffmpeg pour couper le fichier.
        """
        try:
            # Créer un fichier temporaire pour l'échantillon
            with tempfile.NamedTemporaryFile(suffix='.mp3', delete=False) as tmp_file:
                sample_path = tmp_file.name
            
            logger.info(f"ACRCloudClient: Extraction d'un échantillon de {duration}s de {os.path.basename(file_path)}")
            
            # Commande ffmpeg pour extraire les premières 'duration' secondes
            cmd = [
                'ffmpeg',
                '-i', file_path,           # Fichier d'entrée
                '-t', str(duration),        # Durée à extraire
                '-y',                        # Forcer l'écrasement
                '-acodec', 'libmp3lame',    # Codec audio MP3
                '-ar', '44100',              # Fréquence d'échantillonnage
                '-ac', '2',                   # Stéréo
                '-b:a', '128k',               # Bitrate
                sample_path
            ]
            
            # Exécuter ffmpeg
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await process.communicate()
            
            if process.returncode != 0:
                logger.error(f"ACRCloudClient: Erreur ffmpeg: {stderr.decode()}")
                os.unlink(sample_path)
                return None
            
            # Vérifier la taille du fichier extrait
            size = os.path.getsize(sample_path)
            logger.info(f"ACRCloudClient: Échantillon extrait: {size} bytes")
            
            return sample_path
            
        except Exception as e:
            logger.error(f"ACRCloudClient: Erreur extraction échantillon: {e}")
            if 'sample_path' in locals() and os.path.exists(sample_path):
                os.unlink(sample_path)
            return None

    async def recognize(self, file_path: str) -> Optional[Dict[str, Any]]:
        # Vérification détaillée de la configuration
        if not self.enabled:
            logger.warning("ACRCloudClient: Service désactivé (enabled=False)")
            return self._mock_recognize(file_path)
            
        if not self.host:
            logger.warning("ACRCloudClient: Host non configuré")
            return self._mock_recognize(file_path)
            
        if not self.access_key or not self.secret_key:
            logger.warning("ACRCloudClient: Clés API non configurées")
            return self._mock_recognize(file_path)
        
        logger.info(f"ACRCloudClient: Appel API pour {os.path.basename(file_path)}")
        
        # Extraire un échantillon de 20 secondes
        sample_path = await self._extract_audio_sample(file_path, duration=20)
        if not sample_path:
            logger.error("ACRCloudClient: Impossible d'extraire l'échantillon audio")
            return self._mock_recognize(file_path)
        
        try:
            timestamp = str(int(time.time()))
            signature = self._build_signature(timestamp)
            logger.debug(f"ACRCloudClient: Signature générée, timestamp={timestamp}")

            # Lecture du fichier audio (l'échantillon)
            with open(sample_path, "rb") as f:
                audio_data = f.read()
            
            logger.info(f"ACRCloudClient: Échantillon lu, taille={len(audio_data)} bytes")

            # Préparation de la requête multipart
            form_data = aiohttp.FormData()
            form_data.add_field("sample", audio_data,
                                filename=os.path.basename(sample_path),
                                content_type="audio/mpeg")
            form_data.add_field("access_key", self.access_key)
            form_data.add_field("data_type", "audio")
            form_data.add_field("signature_version", "1")
            form_data.add_field("signature", signature)
            form_data.add_field("sample_bytes", str(len(audio_data)))
            form_data.add_field("timestamp", timestamp)

            url = f"https://{self.host}/v1/identify"
            logger.info(f"ACRCloudClient: Envoi requête à {url}")
            
            async with aiohttp.ClientSession() as session:
                async with session.post(url, data=form_data, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                    logger.info(f"ACRCloudClient: Réponse reçue, status={resp.status}")
                    
                    # Lire le contenu brut d'abord
                    response_text = await resp.text()
                    logger.debug(f"ACRCloudClient: Réponse brute (premiers 200 caractères): {response_text[:200]}")
                    
                    if resp.status == 200:
                        try:
                            # Essayer de parser en JSON
                            data = json.loads(response_text)
                            logger.debug("ACRCloudClient: JSON parsé avec succès")
                            
                            # Vérifier le code de statut dans la réponse
                            status_code = data.get("status", {}).get("code")
                            if status_code != 0:
                                logger.warning(f"ACRCloudClient: Status code {status_code}: {data.get('status', {}).get('msg', '')}")
                                
                                # Gestion spécifique des codes d'erreur
                                if status_code == 3016:
                                    logger.error("ACRCloudClient: Fichier trop long - l'extraction automatique a échoué")
                                elif status_code == 1001:
                                    logger.info("ACRCloudClient: Aucun résultat trouvé")
                                return None
                            
                            result = self._parse_response(data)
                            if result:
                                logger.info(f"ACRCloudClient: SUCCÈS - '{result.get('title')}' par '{result.get('artist')}'")
                            else:
                                logger.warning("ACRCloudClient: Aucun résultat trouvé dans la réponse")
                            return result
                            
                        except json.JSONDecodeError as e:
                            logger.error(f"ACRCloudClient: Erreur de parsing JSON: {e}")
                            return self._mock_recognize(file_path)
                    else:
                        logger.error(f"ACRCloudClient: Erreur HTTP {resp.status}: {response_text[:500]}")
                        return self._mock_recognize(file_path)
                        
        except asyncio.TimeoutError:
            logger.error("ACRCloudClient: Timeout de la requête")
            return self._mock_recognize(file_path)
        except aiohttp.ClientError as e:
            logger.error(f"ACRCloudClient: Erreur de connexion: {e}")
            return self._mock_recognize(file_path)
        except Exception as e:
            logger.error(f"ACRCloudClient: Erreur inattendue: {e}", exc_info=True)
            return self._mock_recognize(file_path)
        finally:
            # Nettoyer le fichier temporaire
            if os.path.exists(sample_path):
                os.unlink(sample_path)
                logger.debug("ACRCloudClient: Fichier temporaire supprimé")

    def _parse_response(self, data: dict) -> Optional[Dict[str, Any]]:
        """Parse la réponse JSON d'ACRCloud."""
        try:
            metadata = data.get("metadata", {})
            music_list = metadata.get("music", [])
            
            if not music_list:
                logger.debug("ACRCloudClient: Aucune musique dans la réponse")
                return None
            
            # Prendre le premier résultat (le plus pertinent)
            music = music_list[0]

            artists = music.get("artists", [])
            artist_name = artists[0].get("name", "") if artists else ""
            
            album = music.get("album", {})
            external = music.get("external_ids", {})
            external_meta = music.get("external_metadata", {})
            
            spotify = external_meta.get("spotify", {})
            youtube = external_meta.get("youtube", {})
            
            # Extraire les genres
            genres = []
            for genre in music.get("genres", []):
                if isinstance(genre, dict):
                    genres.append(genre.get("name", ""))
                elif isinstance(genre, str):
                    genres.append(genre)
            
            # Calculer la confiance (score sur 100)
            score = music.get("score", 0)
            confidence = min(score / 100, 1.0) if score else 0.5

            result = {
                "title": music.get("title", ""),
                "artist": artist_name,
                "album": album.get("name", ""),
                "release_date": music.get("release_date", ""),
                "duration": music.get("duration_ms", 0) // 1000,
                "genres": genres,
                "isrc": external.get("isrc", ""),
                "spotify_id": spotify.get("track", {}).get("id", ""),
                "youtube_id": youtube.get("vid", ""),
                "score": score,
                "confidence": confidence,
                "label": music.get("label", ""),
                "acrid": music.get("acrid", ""),
            }
            
            logger.debug(f"ACRCloudClient: Résultat parsé: {result.get('title')} - {result.get('artist')} (confiance: {confidence:.2f})")
            return result
            
        except Exception as e:
            logger.error(f"ACRCloudClient: Erreur de parsing: {e}")
            return None

    def _mock_recognize(self, file_path: str) -> Dict[str, Any]:
        """Génère une réponse mock pour le développement."""
        filename = os.path.basename(file_path).lower()
        
        # Personnaliser le mock en fonction du nom du fichier
        if "test" in filename or "sample" in filename:
            return {
                "title": "Test Song",
                "artist": "Test Artist",
                "album": "Test Album",
                "release_date": "2024-01-01",
                "duration": 180,
                "genres": ["Rock", "Alternative"],
                "isrc": "TEST12345678",
                "spotify_id": "test_spotify_id",
                "youtube_id": "test_youtube_id",
                "confidence": 0.85,
                "acrid": "test_acrid_12345",
                "label": "Test Records"
            }
        else:
            return {
                "title": "Unknown Track",
                "artist": "Unknown Artist",
                "album": "Unknown Album",
                "release_date": "",
                "duration": 0,
                "genres": [],
                "isrc": "",
                "spotify_id": "",
                "youtube_id": "",
                "confidence": 0.5,
                "acrid": "",
                "label": ""
            }