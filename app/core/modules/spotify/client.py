# app/core/modules/spotify/client.py (CORRIGÉ - avec get_recommendations)
import asyncio
import logging
import time
from typing import Optional, Dict, Any, List
import aiohttp
from app.core.config import settings

logger = logging.getLogger(__name__)

class SpotifyClient:
    BASE_URL = "https://api.spotify.com/v1"
    AUTH_URL = "https://accounts.spotify.com/api/token"

    def __init__(self):
        self.client_id = settings.SPOTIFY_CLIENT_ID
        self.client_secret = settings.SPOTIFY_CLIENT_SECRET
        self.enabled = settings.SPOTIFY_ENABLED
        self._access_token: Optional[str] = None
        self._token_expires: float = 0

    async def _get_token(self) -> Optional[str]:
        if not self.client_id or not self.client_secret:
            return None
        if self._access_token and time.time() < self._token_expires - 60:
            return self._access_token
        try:
            import base64
            credentials = base64.b64encode(
                f"{self.client_id}:{self.client_secret}".encode()
            ).decode()
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    self.AUTH_URL,
                    data={"grant_type": "client_credentials"},
                    headers={"Authorization": f"Basic {credentials}"},
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        self._access_token = data["access_token"]
                        self._token_expires = time.time() + data["expires_in"]
                        return self._access_token
        except Exception as e:
            logger.error(f"Spotify auth error: {e}")
        return None

    async def _get(self, endpoint: str, params: dict = None) -> Optional[dict]:
        token = await self._get_token()
        if not token:
            return None
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.BASE_URL}/{endpoint}",
                    headers={"Authorization": f"Bearer {token}"},
                    params=params or {},
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as resp:
                    if resp.status == 200:
                        return await resp.json()
        except Exception as e:
            logger.error(f"Spotify API error: {e}")
        return None

    async def get_track(self, track_id: str) -> Optional[Dict[str, Any]]:
        if not self.enabled or not track_id:
            return self._mock_track(track_id)
        
        logger.info(f"SpotifyClient: Récupération du track {track_id}")
        data = await self._get(f"tracks/{track_id}")
        
        if not data:
            return self._mock_track(track_id)
        
        artists = [a["name"] for a in data.get("artists", [])]
        
        # Récupérer les informations de l'album pour le label
        album_data = None
        if data.get('album', {}).get('id'):
            album_data = await self._get(f"albums/{data['album']['id']}")
        
        result = {
            "spotify_id": data.get("id"),
            "title": data.get("name"),
            "artist": ", ".join(artists),
            "artists": artists,
            "album": data.get("album", {}).get("name"),
            "album_id": data.get("album", {}).get("id"),
            "duration": data.get("duration_ms", 0) // 1000,
            "preview_url": data.get("preview_url"),
            "spotify_url": data.get("external_urls", {}).get("spotify"),
            "image": (data.get("album", {}).get("images") or [{}])[0].get("url"),
            "popularity": data.get("popularity", 0),
            "release_date": data.get("album", {}).get("release_date"),
            "track_number": data.get("track_number"),
            "disc_number": data.get("disc_number"),
            "explicit": data.get("explicit", False),
            "label": album_data.get("label") if album_data else None,
            "total_tracks": album_data.get("total_tracks") if album_data else None,
            "copyrights": album_data.get("copyrights") if album_data else None,
        }
        
        logger.info(f"✅ Spotify track: {result['title']} - {result['artist']}")
        return result

    # ===== NOUVELLE MÉTHODE: get_recommendations =====
    async def get_recommendations(self, seed_tracks: List[str], limit: int = 5) -> List[Dict[str, Any]]:
        """
        Obtient des recommandations basées sur des pistes.
        """
        if not self.enabled:
            return self._mock_recommendations(seed_tracks, limit)
        
        try:
            params = {
                'limit': limit,
                'seed_tracks': ','.join(seed_tracks)
            }
            
            result = await self._get('recommendations', params)
            if not result or 'tracks' not in result:
                return []
            
            recommendations = []
            for track in result['tracks'][:limit]:
                recommendations.append({
                    'title': track.get('name'),
                    'artist': track['artists'][0]['name'] if track.get('artists') else None,
                    'album': track['album'].get('name') if track.get('album') else None,
                    'image': track['album']['images'][0]['url'] if track.get('album') and track['album'].get('images') else None,
                    'spotify_id': track.get('id'),
                    'preview_url': track.get('preview_url'),
                    'popularity': track.get('popularity'),
                    'type': 'music',
                    'reason': 'Recommandé par Spotify'
                })
            
            logger.info(f"✅ {len(recommendations)} recommandations Spotify trouvées")
            return recommendations
            
        except Exception as e:
            logger.error(f"Erreur get_recommendations: {e}")
            return self._mock_recommendations(seed_tracks, limit)

    def _mock_recommendations(self, seed_tracks: List[str], limit: int) -> List[Dict[str, Any]]:
        """Génère des recommandations mock pour le développement"""
        mock_recommendations = [
            {
                'title': 'Shape of You',
                'artist': 'Ed Sheeran',
                'album': '÷ (Deluxe)',
                'image': None,
                'spotify_id': 'mock_spotify_1',
                'preview_url': None,
                'popularity': 95,
                'type': 'music',
                'reason': 'Chanson pop populaire'
            },
            {
                'title': 'Blinding Lights',
                'artist': 'The Weeknd',
                'album': 'After Hours',
                'image': None,
                'spotify_id': 'mock_spotify_2',
                'preview_url': None,
                'popularity': 98,
                'type': 'music',
                'reason': 'Hit mondial'
            },
            {
                'title': 'Dance Monkey',
                'artist': 'Tones and I',
                'album': 'The Kids Are Coming',
                'image': None,
                'spotify_id': 'mock_spotify_3',
                'preview_url': None,
                'popularity': 92,
                'type': 'music',
                'reason': 'Chanson virale'
            }
        ]
        return mock_recommendations[:limit]

    async def search_track(self, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        if not self.enabled:
            return []
        logger.info(f"SpotifyClient: Recherche de track '{query}'")
        data = await self._get("search", {"q": query, "type": "track", "limit": limit})
        if not data:
            return []
        tracks = data.get("tracks", {}).get("items", [])
        return [
            {
                "spotify_id": t.get("id"),
                "title": t.get("name"),
                "artist": ", ".join(a["name"] for a in t.get("artists", [])),
                "artists": [a["name"] for a in t.get("artists", [])],
                "album": t.get("album", {}).get("name"),
                "image": (t.get("album", {}).get("images") or [{}])[0].get("url"),
                "spotify_url": t.get("external_urls", {}).get("spotify"),
                "preview_url": t.get("preview_url"),
                "duration": t.get("duration_ms", 0) // 1000,
                "popularity": t.get("popularity", 0),
            }
            for t in tracks
        ]

    async def search_album(self, query: str) -> Optional[Dict[str, Any]]:
        if not self.enabled:
            return self._mock_album(query)
        logger.info(f"SpotifyClient: Recherche d'album '{query}'")
        data = await self._get("search", {"q": query, "type": "album", "limit": 1})
        if not data:
            return self._mock_album(query)
        items = data.get("albums", {}).get("items", [])
        if not items:
            return None
        album = items[0]
        
        # Récupérer les détails complets de l'album
        album_details = await self._get(f"albums/{album['id']}")
        
        result = {
            "spotify_id": album.get("id"),
            "title": album.get("name"),
            "artist": ", ".join(a["name"] for a in album.get("artists", [])),
            "artists": [a["name"] for a in album.get("artists", [])],
            "image": (album.get("images") or [{}])[0].get("url"),
            "release_date": album.get("release_date"),
            "total_tracks": album.get("total_tracks"),
            "spotify_url": album.get("external_urls", {}).get("spotify"),
            "label": album_details.get("label") if album_details else None,
            "copyrights": album_details.get("copyrights") if album_details else None,
            "genres": album_details.get("genres", []) if album_details else [],
            "popularity": album_details.get("popularity") if album_details else None,
        }
        
        logger.info(f"✅ Spotify album: {result['title']} - {result['artist']}")
        return result

    def _mock_track(self, track_id: str) -> Dict[str, Any]:
        return {
            "spotify_id": track_id,
            "title": "Mock Track",
            "artist": "Mock Artist",
            "artists": ["Mock Artist"],
            "album": "Mock Album",
            "duration": 200,
            "preview_url": None,
            "spotify_url": f"https://open.spotify.com/track/{track_id}",
            "image": None,
            "popularity": 70,
            "release_date": "2023-01-01",
        }

    def _mock_album(self, query: str) -> Dict[str, Any]:
        return {
            "spotify_id": "mock_album_id",
            "title": query,
            "artist": "Mock Artist",
            "artists": ["Mock Artist"],
            "image": None,
            "release_date": "2023",
            "total_tracks": 12,
            "spotify_url": None,
        }
