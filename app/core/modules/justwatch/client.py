import asyncio
import logging
from typing import Optional, Dict, Any, List
import aiohttp
from app.core.config import settings

logger = logging.getLogger(__name__)

class JustWatchClient:
    BASE_URL = "https://apis.justwatch.com/contentpartner/v3"
    GRAPHQL_URL = "https://apis.justwatch.com/graphql"

    def __init__(self):
        self.enabled = settings.JUSTWATCH_ENABLED
        self.country = settings.JUSTWATCH_COUNTRY

    async def search_movie(self, title: str) -> Optional[Dict[str, Any]]:
        if not self.enabled:
            return self._mock_streaming(title)
        try:
            query = """
            query SearchTitles($searchQuery: String!, $country: Country!, $language: Language!) {
              searchTitles(
                searchQuery: $searchQuery
                country: $country
                language: $language
                first: 1
              ) {
                edges {
                  node {
                    id
                    objectId
                    objectType
                    content {
                      title
                      posterUrl
                    }
                    offers {
                      standardWebURL
                      package { packageId clearName technicalName iconUrl }
                      monetizationType
                    }
                  }
                }
              }
            }
            """
            variables = {
                "searchQuery": title,
                "country": self.country.upper(),
                "language": "fr",
            }
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    self.GRAPHQL_URL,
                    json={"query": query, "variables": variables},
                    headers={"Content-Type": "application/json"},
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        return self._parse_graphql(data)
        except Exception as e:
            logger.error(f"JustWatch error: {e}")
        return self._mock_streaming(title)

    async def search_by_tmdb_id(self, tmdb_id: Optional[int]) -> Optional[Dict[str, Any]]:
        if not self.enabled or not tmdb_id:
            return self._mock_streaming(str(tmdb_id))
        return await self.search_movie(f"tmdb:{tmdb_id}")

    async def _get_movie_details(self, justwatch_id: int) -> Optional[Dict[str, Any]]:
        if not self.enabled:
            return None
        return self._mock_streaming(str(justwatch_id))

    def _parse_graphql(self, data: dict) -> Optional[Dict[str, Any]]:
        try:
            edges = data.get("data", {}).get("searchTitles", {}).get("edges", [])
            if not edges:
                return None
            node = edges[0]["node"]
            offers = node.get("offers", [])

            streaming, rent, buy, free = [], [], [], []
            seen = set()

            for offer in offers:
                pkg = offer.get("package", {})
                name = pkg.get("clearName", "")
                url = offer.get("standardWebURL", "")
                icon = pkg.get("iconUrl", "")
                m_type = offer.get("monetizationType", "")

                if name in seen:
                    continue
                seen.add(name)
                entry = {"provider": name, "url": url, "icon": icon}

                if m_type == "FLATRATE":
                    streaming.append(entry)
                elif m_type == "RENT":
                    rent.append(entry)
                elif m_type == "BUY":
                    buy.append(entry)
                elif m_type == "FREE":
                    free.append(entry)

            return {
                "justwatch_id": node.get("objectId"),
                "streaming": streaming,
                "rent": rent,
                "buy": buy,
                "free": free,
            }
        except Exception as e:
            logger.error(f"JustWatch parse error: {e}")
            return None

    def _mock_streaming(self, title: str) -> Dict[str, Any]:
        return {
            "justwatch_id": 0,
            "streaming": [
                {"provider": "Netflix", "url": "https://netflix.com", "icon": ""},
                {"provider": "Disney+", "url": "https://disneyplus.com", "icon": ""},
            ],
            "rent": [
                {"provider": "Amazon Prime Video", "url": "https://primevideo.com", "icon": ""},
            ],
            "buy": [],
            "free": [],
        }
