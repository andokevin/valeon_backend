import spotipy
from spotipy.oauth2 import SpotifyClientCredentials
from typing import Optional, Dict, Any, List
import httpx
from app.core.config import settings

class SpotifyClient:
    def __init__(self):
        self.client_id = settings.SPOTIFY_CLIENT_ID
        self.client_secret = settings.SPOTIFY_CLIENT_SECRET
        self.client = None
        self._initialize_client()
    
    def _initialize_client(self):
        """Initialise le client Spotify"""
        if self.client_id and self.client_secret:
            auth_manager = SpotifyClientCredentials(
                client_id=self.client_id,
                client_secret=self.client_secret
            )
            self.client = spotipy.Spotify(auth_manager=auth_manager)
    
    async def search_track(self, query: str, artist: Optional[str] = None) -> Optional[Dict]:
        """Recherche un titre sur Spotify"""
        if not self.client:
            return None
        
        try:
            # Construire la requête
            search_query = query
            if artist:
                search_query = f"track:{query} artist:{artist}"
            
            results = self.client.search(q=search_query, type='track', limit=5)
            
            if results['tracks']['items']:
                track = results['tracks']['items'][0]
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
                    'uri': track['uri']
                }
        except Exception as e:
            print(f"Erreur recherche Spotify: {e}")
        return None
    
    async def get_track_details(self, spotify_id: str) -> Optional[Dict]:
        """Récupère les détails d'un titre Spotify"""
        if not self.client:
            return None
        
        try:
            track = self.client.track(spotify_id)
            if track:
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
                    'external_url': track['external_urls']['spotify']
                }
        except Exception as e:
            print(f"Erreur détails Spotify: {e}")
        return None
    
    async def get_recommendations(self, seed_tracks: List[str], limit: int = 10) -> List[Dict]:
        """Obtient des recommandations basées sur des titres"""
        if not self.client:
            return []
        
        try:
            recommendations = self.client.recommendations(
                seed_tracks=seed_tracks[:5],
                limit=limit
            )
            
            result = []
            for track in recommendations['tracks']:
                result.append({
                    'spotify_id': track['id'],
                    'title': track['name'],
                    'artist': track['artists'][0]['name'],
                    'album': track['album']['name'],
                    'image': track['album']['images'][0]['url'] if track['album']['images'] else None,
                    'preview_url': track['preview_url']
                })
            return result
        except Exception as e:
            print(f"Erreur recommandations Spotify: {e}")
        return []