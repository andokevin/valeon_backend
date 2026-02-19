# app/core/modules/youtube/client.py
from typing import Optional, Dict, Any, List
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from app.core.config import settings
import isodate
import re
import logging

logger = logging.getLogger(__name__)

class YouTubeClient:
    """
    Client pour l'API YouTube (enrichissement vidéo).
    """
    
    def __init__(self):
        self.api_key = settings.YOUTUBE_API_KEY
        self.youtube = None
        self._initialize_client()
    
    def _initialize_client(self):
        """Initialise le client YouTube."""
        if self.api_key:
            try:
                self.youtube = build('youtube', 'v3', developerKey=self.api_key)
                logger.info("Client YouTube initialisé")
            except Exception as e:
                logger.error(f"Erreur initialisation YouTube: {e}")
    
    async def search_video(
        self,
        query: str,
        max_results: int = 5
    ) -> List[Dict[str, Any]]:
        """
        Recherche des vidéos YouTube.
        """
        if not self.youtube:
            return []
        
        try:
            request = self.youtube.search().list(
                q=query,
                part='snippet',
                maxResults=max_results,
                type='video'
            )
            response = request.execute()
            
            videos = []
            for item in response.get('items', []):
                video_id = item['id']['videoId']
                snippet = item['snippet']
                
                videos.append({
                    'youtube_id': video_id,
                    'title': snippet['title'],
                    'channel': snippet['channelTitle'],
                    'thumbnail': snippet['thumbnails']['high']['url'],
                    'url': f"https://youtube.com/watch?v={video_id}",
                    'embed_url': f"https://youtube.com/embed/{video_id}"
                })
            
            return videos
            
        except HttpError as e:
            logger.error(f"Erreur YouTube: {e}")
            return []
    
    async def search_music_video(
        self,
        title: str,
        artist: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Recherche un clip musical.
        """
        query = f"{title} {artist} official music video" if artist else f"{title} music"
        return await self.search_video(query, max_results=3)