# app/core/modules/tmdb/client.py
import httpx
from typing import Optional, Dict, Any, List
import logging
from app.core.config import settings

logger = logging.getLogger(__name__)

class TMDBClient:
    """
    Client pour l'API TMDB (enrichissement films/séries).
    """
    
    def __init__(self):
        self.api_key = settings.TMDB_API_KEY
        self.base_url = "https://api.themoviedb.org/3"
        self.image_base_url = "https://image.tmdb.org/t/p/w500"
    
    async def search_movie(self, query: str, year: Optional[int] = None) -> Optional[Dict]:
        """Recherche un film."""
        params = {
            "api_key": self.api_key,
            "query": query,
            "language": "fr-FR",
            "include_adult": False
        }
        
        if year:
            params["year"] = year
        
        async with httpx.AsyncClient() as client:
            try:
                response = await client.get(
                    f"{self.base_url}/search/movie",
                    params=params
                )
                response.raise_for_status()
                data = response.json()
                
                if data["results"]:
                    movie = data["results"][0]
                    return {
                        "tmdb_id": movie["id"],
                        "title": movie["title"],
                        "original_title": movie["original_title"],
                        "description": movie["overview"],
                        "release_date": movie["release_date"],
                        "poster": f"{self.image_base_url}{movie['poster_path']}" if movie["poster_path"] else None,
                        "backdrop": f"{self.image_base_url}{movie['backdrop_path']}" if movie["backdrop_path"] else None,
                        "rating": movie["vote_average"],
                        "popularity": movie["popularity"]
                    }
            except Exception as e:
                logger.error(f"Erreur TMDB: {e}")
        
        return None