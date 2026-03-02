# app/core/modules/__init__.py
from .gemini import GeminiClient
from .whisper_client import WhisperClient  # ← Remplacer whisper_cpp par whisper_client
from .acrcloud import ACRCloudClient
from .spotify import SpotifyClient
from .tmdb import TMDBClient
from .justwatch import JustWatchClient
from .youtube import client as YouTubeClient
from .vision.client import CloudVisionClient 

__all__ = [
    "GeminiClient", 
    "WhisperClient",  
    "ACRCloudClient", 
    "SpotifyClient", 
    "TMDBClient",
    "JustWatchClient", 
    "YouTubeClient",
    "CloudVisionClient",  
]
