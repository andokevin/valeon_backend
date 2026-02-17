# api/routers/streaming.py (NOUVEAU FICHIER)

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import Optional, List
from app.core.database import get_db
from app.models import Content, ExternalLink
from app.api.dependencies.auth import get_current_user_optional
from app.services.vision.justwatch_client import JustWatchClient

router = APIRouter(prefix="/streaming", tags=["Streaming"])
justwatch_client = JustWatchClient()

@router.get("/movie/{content_id}")
async def get_movie_streaming(
    content_id: int,
    country: str = Query("FR", regex="^(FR|US|GB|DE|ES|IT)$"),
    db: Session = Depends(get_db)
):
    """
    Récupère les informations de streaming pour un film
    """
    content = db.query(Content).filter(Content.content_id == content_id).first()
    
    if not content:
        raise HTTPException(status_code=404, detail="Contenu non trouvé")
    
    # Si on a déjà les infos en cache dans metadata
    if content.metadata and content.metadata.get('streaming'):
        return content.metadata['streaming']
    
    # Sinon, chercher sur JustWatch
    if content.justwatch_id:
        # Utiliser l'ID JustWatch si disponible
        justwatch_client.country = country
        details = await justwatch_client._get_movie_details(content.justwatch_id)
        if details:
            return details.get('streaming')
    
    # Chercher par titre
    if content.content_title:
        justwatch_client.country = country
        result = await justwatch_client.search_movie(
            content.content_title,
            int(content.content_release_date[:4]) if content.content_release_date else None
        )
        if result:
            return result.get('streaming')
    
    return {"streaming": [], "rent": [], "buy": []}

@router.get("/search")
async def search_streaming_availability(
    query: str,
    content_type: str = Query("movie", regex="^(movie|show)$"),
    country: str = Query("FR", regex="^(FR|US|GB|DE|ES|IT)$"),
    limit: int = Query(10, ge=1, le=50)
):
    """
    Recherche des films et leur disponibilité streaming
    """
    justwatch_client.country = country
    
    search_payload = {
        "query": query,
        "content_types": [content_type],
        "page_size": limit,
        "page": 1
    }
    
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{justwatch_client.base_url}/content/titles/{country}/popular",
            json=search_payload,
            headers={
                "User-Agent": justwatch_client.user_agent,
                "Content-Type": "application/json"
            }
        )
        
        if response.status_code == 200:
            data = response.json()
            results = []
            
            for item in data.get("items", []):
                streaming_offers = justwatch_client._parse_offers(item.get("offers", []))
                results.append({
                    "justwatch_id": item["id"],
                    "title": item.get("title"),
                    "poster": f"https://images.justwatch.com{item['poster']}" if item.get("poster") else None,
                    "release_year": item.get("original_release_year"),
                    "streaming": streaming_offers
                })
            
            return results
    
    return []