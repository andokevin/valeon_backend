# app/core/modules/spotify/client.py
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials
from typing import Optional, Dict, Any, List
import logging
from app.core.config import settings

logger = logging.getLogger(__name__)

class SpotifyClient:
    """
    Client pour l'API Spotify (enrichissement uniquement).
    """
    
    def __init__(self):
        self.client_id = settings.SPOTIFY_CLIENT_ID
        self.client_secret = settings.SPOTIFY_CLIENT_SECRET
        self.client = None
        self._initialize_client()
    
    def _initialize_client(self):
        """Initialise le client Spotify."""
        if self.client_id and self.client_secret:
            auth_manager = SpotifyClientCredentials(
                client_id=self.client_id,
                client_secret=self.client_secret
            )
            self.client = spotipy.Spotify(
                auth_manager=auth_manager,
                requests_timeout=10
            )
            logger.info("Client Spotify initialisé")
    
    async def get_track(self, spotify_id: str) -> Optional[Dict]:
        """
        Récupère les détails d'un titre.
        """
        if not self.client:
            return None
        
        try:
            track = self.client.track(spotify_id)
            return {
                'spotify_id': track['id'],
                'title': track['name'],
                'artist': track['artists'][0]['name'],
                'artists': [a['name'] for a in track['artists']],
                'album': track['album']['name'],
                'release_date': track['album']['release_date'],
                'image': track['album']['images'][0]['url'] if track['album']['images'] else None,
                'duration_ms': track['duration_ms'],
                'popularity': track['popularity'],
                'preview_url': track['preview_url'],
                'external_url': track['external_urls']['spotify'],
                'genres': []  # Les genres sont sur l'artiste, pas le track
            }
        except Exception as e:
            logger.error(f"Erreur Spotify: {e}")
            return None
    
    async def search_album(self, query: str) -> Optional[Dict]:
        """
        Recherche un album.
        """
        if not self.client:
            return None
        
        try:
            results = self.client.search(q=query, type='album', limit=1)
            
            if results['albums']['items']:
                album = results['albums']['items'][0]
                return {
                    'spotify_id': album['id'],
                    'title': album['name'],
                    'artist': album['artists'][0]['name'],
                    'release_date': album['release_date'],
                    'image': album['images'][0]['url'] if album['images'] else None,
                    'total_tracks': album['total_tracks'],
                    'external_url': album['external_urls']['spotify']
                }
        except Exception as e:
            logger.error(f"Erreur recherche album: {e}")
        
        return None