import asyncio
import base64
import hashlib
import hmac
import os
import time
import logging
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

    def _build_signature(self, timestamp: str) -> str:
        string_to_sign = "\n".join(["POST", "/v1/identify", self.access_key, "audio", "1", timestamp])
        return base64.b64encode(
            hmac.new(
                self.secret_key.encode("utf-8"),
                string_to_sign.encode("utf-8"),
                digestmod=hashlib.sha1,
            ).digest()
        ).decode("utf-8")

    async def recognize(self, file_path: str) -> Optional[Dict[str, Any]]:
        if not self.enabled or not self.host or not self.access_key:
            return self._mock_recognize(file_path)
        try:
            timestamp = str(time.time())
            signature = self._build_signature(timestamp)

            with open(file_path, "rb") as f:
                audio_data = f.read()

            form_data = aiohttp.FormData()
            form_data.add_field("sample", audio_data,
                                filename=os.path.basename(file_path),
                                content_type="audio/mpeg")
            form_data.add_field("access_key", self.access_key)
            form_data.add_field("data_type", "audio")
            form_data.add_field("signature_version", "1")
            form_data.add_field("signature", signature)
            form_data.add_field("sample_bytes", str(len(audio_data)))
            form_data.add_field("timestamp", timestamp)

            url = f"https://{self.host}/v1/identify"
            async with aiohttp.ClientSession() as session:
                async with session.post(url, data=form_data, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        return self._parse_response(data)
            return None
        except Exception as e:
            logger.error(f"ACRCloud error: {e}")
            return self._mock_recognize(file_path)

    def _parse_response(self, data: dict) -> Optional[Dict[str, Any]]:
        if data.get("status", {}).get("code") != 0:
            return None
        metadata = data.get("metadata", {})
        music = metadata.get("music", [{}])[0] if metadata.get("music") else {}
        if not music:
            return None

        artists = music.get("artists", [{}])
        artist_name = artists[0].get("name", "") if artists else ""
        album = music.get("album", {})
        external = music.get("external_ids", {})
        external_meta = music.get("external_metadata", {})
        spotify = external_meta.get("spotify", {})
        youtube = external_meta.get("youtube", {})

        return {
            "title": music.get("title", ""),
            "artist": artist_name,
            "album": album.get("name", ""),
            "release_date": music.get("release_date", ""),
            "duration": music.get("duration_ms", 0) // 1000,
            "genres": [g.get("name") for g in music.get("genres", [])],
            "isrc": external.get("isrc", ""),
            "spotify_id": spotify.get("track", {}).get("id", ""),
            "youtube_id": youtube.get("vid", ""),
            "score": data.get("metadata", {}).get("music", [{}])[0].get("score", 0),
            "confidence": min(music.get("score", 0) / 100, 1.0),
        }

    def _mock_recognize(self, file_path: str) -> Dict[str, Any]:
        return {
            "title": "Mock Song Title",
            "artist": "Mock Artist",
            "album": "Mock Album",
            "release_date": "2023-01-01",
            "duration": 210,
            "genres": ["Pop"],
            "isrc": "MOCK0001",
            "spotify_id": "mock_spotify_id",
            "youtube_id": "mock_youtube_id",
            "confidence": 0.75,
        }
