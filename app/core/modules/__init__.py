# app/core/modules/__init__.py
"""
Modules spécialisés isolés.
"""
from .acrcloud.client import ACRCloudClient
from .openai.whisper import WhisperClient
from .openai.vision import VisionClient
from .openai.chat import ChatClient
from .spotify.client import SpotifyClient
from .tmdb.client import TMDBClient
from .youtube.client import YouTubeClient
from .justwatch.client import JustWatchClient

__all__ = [
    'ACRCloudClient',
    'WhisperClient',
    'VisionClient',
    'ChatClient',
    'SpotifyClient',
    'TMDBClient',
    'YouTubeClient',
    'JustWatchClient'
]