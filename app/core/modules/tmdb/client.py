# app/core/modules/tmdb/client.py
import asyncio
import logging
from typing import Optional, Dict, Any, List
import aiohttp
from app.core.config import settings

logger = logging.getLogger(__name__)

class TMDBClient:
    BASE_URL = "https://api.themoviedb.org/3"
    IMAGE_BASE = "https://image.tmdb.org/t/p/w500"

    def __init__(self):
        self.api_key = settings.TMDB_API_KEY
        self.enabled = settings.TMDB_ENABLED
        self.language = settings.TMDB_LANGUAGE

    async def _get(self, endpoint: str, params: dict = None) -> Optional[dict]:
        if not self.api_key:
            return None
        try:
            p = {"api_key": self.api_key, "language": self.language}
            p.update(params or {})
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.BASE_URL}/{endpoint}",
                    params=p,
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as resp:
                    if resp.status == 200:
                        return await resp.json()
        except Exception as e:
            logger.error(f"TMDB API error: {e}")
        return None

    async def search_movie(self, query: str, year: Optional[str] = None) -> Optional[Dict[str, Any]]:
        if not self.enabled:
            return self._mock_movie(query)
        params = {"query": query}
        if year:
            params["year"] = year
        data = await self._get("search/movie", params)
        if not data:
            return self._mock_movie(query)
        results = data.get("results", [])
        if not results:
            return None
        m = results[0]
        # Récupérer les détails complets
        details = await self.get_movie(m.get("id"))
        return details or self._format_movie(m)

    async def get_movie(self, tmdb_id: int) -> Optional[Dict[str, Any]]:
        if not self.enabled or not tmdb_id:
            return None
        data = await self._get(f"movie/{tmdb_id}", {"append_to_response": "credits,videos,release_dates"})
        if not data:
            return None
        return self._format_movie(data, detailed=True)

    async def search_tv(self, query: str) -> Optional[Dict[str, Any]]:
        if not self.enabled:
            return self._mock_tv(query)
        data = await self._get("search/tv", {"query": query})
        if not data:
            return self._mock_tv(query)
        results = data.get("results", [])
        if not results:
            return None
        tv = results[0]
        # Récupérer les détails complets
        details = await self.get_tv(tv.get("id"))
        return details or self._format_tv(tv)

    async def get_tv(self, tv_id: int) -> Optional[Dict[str, Any]]:
        if not self.enabled or not tv_id:
            return None
        data = await self._get(f"tv/{tv_id}", {"append_to_response": "credits,videos"})
        if not data:
            return None
        return self._format_tv(data, detailed=True)

    def _format_movie(self, m: dict, detailed: bool = False) -> Dict[str, Any]:
        result = {
            "tmdb_id": m.get("id"),
            "title": m.get("title"),
            "original_title": m.get("original_title"),
            "description": m.get("overview"),
            "image": f"{self.IMAGE_BASE}{m['poster_path']}" if m.get("poster_path") else None,
            "backdrop": f"https://image.tmdb.org/t/p/w1280{m['backdrop_path']}" if m.get("backdrop_path") else None,
            "release_date": m.get("release_date"),
            "rating": m.get("vote_average"),
            "vote_count": m.get("vote_count"),
            "content_type": "movie",
            "imdb_id": m.get("imdb_id"),
        }
        
        if detailed:
            credits = m.get("credits", {})
            crew = credits.get("crew", [])
            cast = credits.get("cast", [])
            
            # Réalisateurs
            directors = [p["name"] for p in crew if p.get("job") == "Director"]
            result["director"] = directors[0] if directors else None
            
            # Scénaristes
            writers = [p["name"] for p in crew if p.get("job") in ["Writer", "Screenplay", "Story"]]
            result["writers"] = writers
            
            # Acteurs principaux
            result["cast"] = [p["name"] for p in cast[:10]]
            result["cast_details"] = [{"name": p["name"], "character": p["character"]} for p in cast[:10]]
            
            # Durée
            result["runtime"] = m.get("runtime")
            
            # Genres
            result["genres"] = [g["name"] for g in m.get("genres", [])]
            
            # Production
            result["production_companies"] = [c["name"] for c in m.get("production_companies", [])]
            result["production_countries"] = [c["name"] for c in m.get("production_countries", [])]
            
            # Budget / Revenus
            result["budget"] = m.get("budget")
            result["revenue"] = m.get("revenue")
            
            # Bandes-annonces
            videos = m.get("videos", {}).get("results", [])
            trailers = [v for v in videos if v.get("type") == "Trailer"]
            result["trailer_key"] = trailers[0]["key"] if trailers else None
            
            # Certification
            releases = m.get("release_dates", {}).get("results", [])
            for r in releases:
                if r.get("iso_3166_1") == "FR":
                    for rel in r.get("release_dates", []):
                        if rel.get("certification"):
                            result["certification"] = rel.get("certification")
                            break
        
        return result

    def _format_tv(self, tv: dict, detailed: bool = False) -> Dict[str, Any]:
        result = {
            "tmdb_id": tv.get("id"),
            "title": tv.get("name"),
            "original_title": tv.get("original_name"),
            "description": tv.get("overview"),
            "image": f"{self.IMAGE_BASE}{tv['poster_path']}" if tv.get("poster_path") else None,
            "backdrop": f"https://image.tmdb.org/t/p/w1280{tv['backdrop_path']}" if tv.get("backdrop_path") else None,
            "first_air_date": tv.get("first_air_date"),
            "last_air_date": tv.get("last_air_date"),
            "rating": tv.get("vote_average"),
            "vote_count": tv.get("vote_count"),
            "content_type": "tv_show",
        }
        
        if detailed:
            credits = tv.get("credits", {})
            crew = credits.get("crew", [])
            cast = credits.get("cast", [])
            
            # Créateurs
            created_by = [c["name"] for c in tv.get("created_by", [])]
            result["created_by"] = created_by
            
            # Acteurs principaux
            result["cast"] = [p["name"] for p in cast[:10]]
            
            # Genres
            result["genres"] = [g["name"] for g in tv.get("genres", [])]
            
            # Production
            result["production_companies"] = [c["name"] for c in tv.get("production_companies", [])]
            
            # Nombre de saisons/épisodes
            result["number_of_seasons"] = tv.get("number_of_seasons")
            result["number_of_episodes"] = tv.get("number_of_episodes")
            
            # Statut
            result["status"] = tv.get("status")
            
            # Dernière saison
            last_season = tv.get("last_air_date")
            if last_season:
                result["last_season"] = last_season
        
        return result

    def _mock_movie(self, query: str) -> Dict[str, Any]:
        return {
            "tmdb_id": 0,
            "title": query,
            "original_title": query,
            "description": "Description du film non disponible.",
            "image": None,
            "backdrop": None,
            "release_date": "2023",
            "rating": 7.0,
            "content_type": "movie",
        }

    def _mock_tv(self, query: str) -> Dict[str, Any]:
        return {
            "tmdb_id": 0,
            "title": query,
            "description": "Description de la série non disponible.",
            "image": None,
            "first_air_date": "2023",
            "rating": 7.5,
            "content_type": "tv_show",
        }