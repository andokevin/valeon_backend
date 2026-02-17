import httpx
from typing import Optional, Dict, Any, List
from app.core.config import settings

class TMDBClient:
    def __init__(self):
        self.api_key = settings.TMDB_API_KEY
        self.base_url = "https://api.themoviedb.org/3"
        self.image_base_url = "https://image.tmdb.org/t/p/w500"
    
    async def search_movie(self, query: str, year: Optional[int] = None) -> Optional[Dict]:
        """Recherche un film sur TMDB"""
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
                    # Récupérer les détails supplémentaires
                    details = await self.get_movie_details(movie["id"])
                    
                    result = {
                        "tmdb_id": movie["id"],
                        "title": movie["title"],
                        "original_title": movie["original_title"],
                        "description": movie["overview"],
                        "release_date": movie["release_date"],
                        "poster_path": f"{self.image_base_url}{movie['poster_path']}" if movie["poster_path"] else None,
                        "backdrop_path": f"{self.image_base_url}{movie['backdrop_path']}" if movie["backdrop_path"] else None,
                        "vote_average": movie["vote_average"],
                        "vote_count": movie["vote_count"],
                        "popularity": movie["popularity"]
                    }
                    
                    # Ajouter les détails supplémentaires
                    if details:
                        result.update({
                            "genres": [g["name"] for g in details.get("genres", [])],
                            "runtime": details.get("runtime"),
                            "cast": details.get("cast", [])[:5],
                            "director": details.get("director"),
                            "videos": details.get("videos", [])
                        })
                    
                    return result
            except Exception as e:
                print(f"Erreur TMDB: {e}")
        return None
    
    async def search_tv_show(self, query: str) -> Optional[Dict]:
        """Recherche une série TV sur TMDB"""
        params = {
            "api_key": self.api_key,
            "query": query,
            "language": "fr-FR"
        }
        
        async with httpx.AsyncClient() as client:
            try:
                response = await client.get(
                    f"{self.base_url}/search/tv",
                    params=params
                )
                response.raise_for_status()
                data = response.json()
                
                if data["results"]:
                    tv = data["results"][0]
                    return {
                        "tmdb_id": tv["id"],
                        "title": tv["name"],
                        "original_title": tv["original_name"],
                        "description": tv["overview"],
                        "first_air_date": tv["first_air_date"],
                        "poster_path": f"{self.image_base_url}{tv['poster_path']}" if tv["poster_path"] else None,
                        "backdrop_path": f"{self.image_base_url}{tv['backdrop_path']}" if tv["backdrop_path"] else None,
                        "vote_average": tv["vote_average"]
                    }
            except Exception as e:
                print(f"Erreur TMDB: {e}")
        return None
    
    async def get_movie_details(self, movie_id: int) -> Optional[Dict]:
        """Récupère les détails complets d'un film"""
        params = {
            "api_key": self.api_key,
            "append_to_response": "credits,videos,images,release_dates",
            "language": "fr-FR"
        }
        
        async with httpx.AsyncClient() as client:
            try:
                response = await client.get(
                    f"{self.base_url}/movie/{movie_id}",
                    params=params
                )
                response.raise_for_status()
                data = response.json()
                
                # Extraire le réalisateur
                director = None
                cast = []
                if "credits" in data:
                    for crew in data["credits"].get("crew", []):
                        if crew["job"] == "Director":
                            director = crew["name"]
                            break
                    
                    for actor in data["credits"].get("cast", [])[:10]:
                        cast.append({
                            "name": actor["name"],
                            "character": actor["character"],
                            "profile_path": f"{self.image_base_url}{actor['profile_path']}" if actor.get("profile_path") else None
                        })
                
                # Extraire les vidéos
                videos = []
                if "videos" in data and data["videos"]["results"]:
                    for video in data["videos"]["results"][:3]:
                        if video["site"] == "YouTube":
                            videos.append({
                                "key": video["key"],
                                "name": video["name"],
                                "type": video["type"],
                                "url": f"https://www.youtube.com/watch?v={video['key']}"
                            })
                
                return {
                    "genres": [g["name"] for g in data.get("genres", [])],
                    "runtime": data.get("runtime"),
                    "status": data.get("status"),
                    "budget": data.get("budget"),
                    "revenue": data.get("revenue"),
                    "director": director,
                    "cast": cast,
                    "videos": videos
                }
            except Exception as e:
                print(f"Erreur détails TMDB: {e}")
        return None
    
    async def get_recommendations(self, movie_id: int, limit: int = 5) -> List[Dict]:
        """Obtient des recommandations de films similaires"""
        params = {
            "api_key": self.api_key,
            "language": "fr-FR"
        }
        
        async with httpx.AsyncClient() as client:
            try:
                response = await client.get(
                    f"{self.base_url}/movie/{movie_id}/recommendations",
                    params=params
                )
                response.raise_for_status()
                data = response.json()
                
                recommendations = []
                for movie in data["results"][:limit]:
                    recommendations.append({
                        "tmdb_id": movie["id"],
                        "title": movie["title"],
                        "description": movie["overview"],
                        "poster_path": f"{self.image_base_url}{movie['poster_path']}" if movie["poster_path"] else None,
                        "release_date": movie["release_date"],
                        "vote_average": movie["vote_average"]
                    })
                
                return recommendations
            except Exception as e:
                print(f"Erreur recommandations TMDB: {e}")
        return []