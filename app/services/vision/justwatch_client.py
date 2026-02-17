# services/vision/justwatch_client.py
import httpx
from typing import Optional, Dict, Any, List
from app.core.config import settings
import hashlib
import json

class JustWatchClient:
    def __init__(self):
        self.base_url = "https://apis.justwatch.com"
        self.user_agent = "Valeon/1.0.0"
        self.country = "FR"  # Par défaut France, peut être modifié
        
    async def search_movie(self, query: str, year: Optional[int] = None) -> Optional[Dict]:
        """
        Recherche un film sur JustWatch pour voir sa disponibilité
        """
        try:
            # Construire la requête
            search_payload = {
                "query": query,
                "content_types": ["movie"],
                "page_size": 5,
                "page": 1
            }
            
            if year:
                search_payload["release_year_from"] = year
                search_payload["release_year_to"] = year
            
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.base_url}/content/titles/{self.country}/popular",
                    json=search_payload,
                    headers={
                        "User-Agent": self.user_agent,
                        "Content-Type": "application/json"
                    }
                )
                
                if response.status_code == 200:
                    data = response.json()
                    if data.get("items"):
                        # Prendre le premier résultat
                        movie = data["items"][0]
                        
                        # Récupérer les détails complets
                        return await self._get_movie_details(movie["id"])
                        
        except Exception as e:
            print(f"Erreur recherche JustWatch: {e}")
        return None
    
    async def search_tv_show(self, query: str) -> Optional[Dict]:
        """
        Recherche une série TV sur JustWatch
        """
        try:
            search_payload = {
                "query": query,
                "content_types": ["show"],
                "page_size": 5,
                "page": 1
            }
            
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.base_url}/content/titles/{self.country}/popular",
                    json=search_payload,
                    headers={
                        "User-Agent": self.user_agent,
                        "Content-Type": "application/json"
                    }
                )
                
                if response.status_code == 200:
                    data = response.json()
                    if data.get("items"):
                        show = data["items"][0]
                        return await self._get_movie_details(show["id"])
                        
        except Exception as e:
            print(f"Erreur recherche série JustWatch: {e}")
        return None
    
    async def _get_movie_details(self, content_id: int) -> Optional[Dict]:
        """
        Récupère les détails complets d'un contenu (offres de streaming)
        """
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.base_url}/content/titles/{self.country}/title/{content_id}",
                    headers={"User-Agent": self.user_agent}
                )
                
                if response.status_code == 200:
                    data = response.json()
                    
                    # Analyser les offres de streaming
                    streaming_offers = self._parse_offers(data.get("offers", []))
                    
                    return {
                        "justwatch_id": content_id,
                        "title": data.get("title"),
                        "original_title": data.get("original_release_year"),
                        "release_year": data.get("original_release_year"),
                        "age_rating": data.get("age_rating"),
                        "runtime": data.get("runtime"),
                        "genres": [g["name"] for g in data.get("genres", [])],
                        "streaming": streaming_offers,
                        "poster": f"https://images.justwatch.com{data['poster']}" if data.get("poster") else None,
                        "backdrop": f"https://images.justwatch.com{data['backdrop']}" if data.get("backdrop") else None,
                        "short_description": data.get("short_description"),
                        "tmdb_id": data.get("tmdb_popularity", {}).get("id")
                    }
        except Exception as e:
            print(f"Erreur détails JustWatch: {e}")
        return None
    
    def _parse_offers(self, offers: List[Dict]) -> Dict[str, List[Dict]]:
        """
        Parse les offres de streaming par type (streaming, rent, buy)
        """
        result = {
            "streaming": [],  # Abonnement (Netflix, Prime, etc.)
            "rent": [],       # Location
            "buy": [],        # Achat
            "free": []        # Gratuit avec pubs
        }
        
        for offer in offers:
            # Déterminer le type d'offre
            monetization_type = offer.get("monetization_type", "unknown")
            package = offer.get("package", {})
            package_name = package.get("name")
            package_icon = package.get("icon")
            
            offer_data = {
                "provider": package_name,
                "provider_id": package.get("id"),
                "icon": f"https://images.justwatch.com{package_icon}" if package_icon else None,
                "url": offer.get("urls", {}).get("standard_web"),
                "price": offer.get("retail_price"),
                "currency": offer.get("currency"),
                "presentation_type": offer.get("presentation_type"),  # hd, sd, 4k
                "country": offer.get("country"),
                "audio": offer.get("audio", []),
                "subtitles": offer.get("subtitles", [])
            }
            
            # Classer par type
            if monetization_type == "flatrate":
                result["streaming"].append(offer_data)
            elif monetization_type == "rent":
                result["rent"].append(offer_data)
            elif monetization_type == "buy":
                result["buy"].append(offer_data)
            elif monetization_type == "ads":
                result["free"].append(offer_data)
        
        return result
    
    async def search_by_tmdb_id(self, tmdb_id: int) -> Optional[Dict]:
        """
        Recherche un film par son ID TMDB
        """
        try:
            # D'abord chercher le film
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.base_url}/content/titles/{self.country}/tmdb/{tmdb_id}",
                    headers={"User-Agent": self.user_agent}
                )
                
                if response.status_code == 200:
                    data = response.json()
                    if data:
                        return await self._get_movie_details(data["id"])
        except Exception as e:
            print(f"Erreur recherche par TMDB ID: {e}")
        return None
    
    async def get_popular_streaming(self, content_type: str = "movie", limit: int = 10) -> List[Dict]:
        """
        Récupère les contenus populaires actuellement en streaming
        """
        try:
            search_payload = {
                "content_types": [content_type],
                "page_size": limit,
                "page": 1
            }
            
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.base_url}/content/titles/{self.country}/popular",
                    json=search_payload,
                    headers={
                        "User-Agent": self.user_agent,
                        "Content-Type": "application/json"
                    }
                )
                
                if response.status_code == 200:
                    data = response.json()
                    results = []
                    
                    for item in data.get("items", []):
                        streaming_offers = self._parse_offers(item.get("offers", []))
                        results.append({
                            "justwatch_id": item["id"],
                            "title": item.get("title"),
                            "poster": f"https://images.justwatch.com{item['poster']}" if item.get("poster") else None,
                            "release_year": item.get("original_release_year"),
                            "streaming": streaming_offers
                        })
                    
                    return results
        except Exception as e:
            print(f"Erreur popular streaming: {e}")
        return []