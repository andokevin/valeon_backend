import asyncio
import logging
from typing import Optional, Dict, Any, List
import aiohttp
from app.core.config import settings

logger = logging.getLogger(__name__)

class YouTubeClient:
    BASE_URL = "https://www.googleapis.com/youtube/v3"

    def __init__(self):
        self.api_key = settings.YOUTUBE_API_KEY
        self.enabled = settings.YOUTUBE_ENABLED

    async def _get(self, endpoint: str, params: dict) -> Optional[dict]:
        if not self.api_key:
            return None
        try:
            params["key"] = self.api_key
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.BASE_URL}/{endpoint}",
                    params=params,
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as resp:
                    if resp.status == 200:
                        return await resp.json()
        except Exception as e:
            logger.error(f"YouTube API error: {e}")
        return None

    async def search_video(
        self, query: str, max_results: int = 5
    ) -> List[Dict[str, Any]]:
        if not self.enabled:
            return self._mock_search(query)
        data = await self._get("search", {
            "part": "snippet",
            "q": query,
            "maxResults": max_results,
            "type": "video",
            "order": "relevance",
        })
        if not data:
            return self._mock_search(query)
        return [
            {
                "video_id": item["id"]["videoId"],
                "title": item["snippet"]["title"],
                "channel": item["snippet"]["channelTitle"],
                "thumbnail": item["snippet"]["thumbnails"]["high"]["url"],
                "published_at": item["snippet"]["publishedAt"],
                "url": f"https://www.youtube.com/watch?v={item['id']['videoId']}",
                "embed_url": f"https://www.youtube.com/embed/{item['id']['videoId']}",
            }
            for item in data.get("items", [])
            if item.get("id", {}).get("videoId")
        ]

    async def get_video_details(self, video_id: str) -> Optional[Dict[str, Any]]:
        if not self.enabled or not video_id:
            return None
        data = await self._get("videos", {
            "part": "snippet,contentDetails,statistics",
            "id": video_id,
        })
        if not data:
            return None
        items = data.get("items", [])
        if not items:
            return None
        v = items[0]
        snippet = v.get("snippet", {})
        stats = v.get("statistics", {})
        content_details = v.get("contentDetails", {})
        return {
            "video_id": video_id,
            "title": snippet.get("title"),
            "description": snippet.get("description"),
            "channel": snippet.get("channelTitle"),
            "thumbnail": snippet.get("thumbnails", {}).get("high", {}).get("url"),
            "published_at": snippet.get("publishedAt"),
            "duration": content_details.get("duration"),
            "view_count": stats.get("viewCount"),
            "like_count": stats.get("likeCount"),
            "url": f"https://www.youtube.com/watch?v={video_id}",
            "embed_url": f"https://www.youtube.com/embed/{video_id}",
        }

    async def search_music_video(
        self, title: str, artist: str
    ) -> Optional[Dict[str, Any]]:
        if not self.enabled:
            return self._mock_music_video(title, artist)
        query = f"{artist} - {title} official video"
        results = await self.search_video(query, max_results=1)
        return results[0] if results else None

    async def search_trailer(
        self, title: str, year: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        if not self.enabled:
            return self._mock_trailer(title)
        query = f"{title} {year or ''} official trailer".strip()
        results = await self.search_video(query, max_results=1)
        return results[0] if results else None

    async def get_video_by_id(self, youtube_id: str) -> Optional[Dict[str, Any]]:
        if not youtube_id:
            return None
        return await self.get_video_details(youtube_id)

    def _mock_search(self, query: str) -> List[Dict[str, Any]]:
        return [
            {
                "video_id": "mock_video_id",
                "title": f"{query} - Résultat mock",
                "channel": "Mock Channel",
                "thumbnail": None,
                "published_at": "2023-01-01T00:00:00Z",
                "url": "https://www.youtube.com/watch?v=mock_video_id",
                "embed_url": "https://www.youtube.com/embed/mock_video_id",
            }
        ]

    def _mock_music_video(self, title: str, artist: str) -> Dict[str, Any]:
        return {
            "video_id": "mock_mv_id",
            "title": f"{artist} - {title} (Official Video)",
            "channel": artist,
            "thumbnail": None,
            "url": "https://www.youtube.com/watch?v=mock_mv_id",
            "embed_url": "https://www.youtube.com/embed/mock_mv_id",
        }

    def _mock_trailer(self, title: str) -> Dict[str, Any]:
        return {
            "video_id": "mock_trailer_id",
            "title": f"{title} - Official Trailer",
            "channel": "Official Channel",
            "thumbnail": None,
            "url": "https://www.youtube.com/watch?v=mock_trailer_id",
            "embed_url": "https://www.youtube.com/embed/mock_trailer_id",
        }
