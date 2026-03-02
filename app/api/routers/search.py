# app/api/routers/search.py
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import or_, func, desc
from typing import List, Optional, Dict, Any
from pydantic import BaseModel

from app.core.database import get_db
from app.api.dependencies.auth import get_current_user_optional
from app.models import Content, User, Scan

router = APIRouter(prefix="/search", tags=["Search"])

class SearchResult(BaseModel):
    content_id: Optional[int]
    title: str
    type: str  # "music", "movie", "tv_show", "artist", "album"
    artist: Optional[str] = None
    year: Optional[str] = None
    image: Optional[str] = None
    description: Optional[str] = None
    source: str  # "local", "tmdb", "spotify"
    external_id: Optional[str] = None

class SearchResponse(BaseModel):
    query: str
    results: List[SearchResult]
    total: int

@router.get("/", response_model=SearchResponse)
async def search(
    q: str = Query(..., min_length=1, max_length=100),
    type: Optional[str] = Query(None, pattern="^(music|movie|tv_show|all)$"),
    limit: int = Query(20, ge=1, le=50),
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional)
):
    """
    Recherche multi-sources (base locale uniquement pour l'instant)
    """
    results = []
    query = q.strip()

    # 1. Recherche dans la base locale
    local_query = db.query(Content)
    
    # CORRECTION: Filtrer par type correctement
    if type and type != "all":
        local_query = local_query.filter(Content.content_type == type)
    elif not type or type == "all":
        # Si "all" ou pas de type, ne pas filtrer par type
        pass
    
    # Recherche par titre, artiste, réalisateur
    search_filter = or_(
        Content.content_title.ilike(f"%{query}%"),
        Content.content_artist.ilike(f"%{query}%"),
        Content.content_director.ilike(f"%{query}%")
    )
    
    local_query = local_query.filter(search_filter).limit(limit).all()

    for content in local_query:
        results.append(SearchResult(
            content_id=content.content_id,
            title=content.content_title,
            type=content.content_type,
            artist=content.content_artist,
            year=content.content_release_date[:4] if content.content_release_date else None,
            image=content.content_image,
            description=content.content_description,
            source="local",
            external_id=content.spotify_id or str(content.tmdb_id) if content.tmdb_id else None
        ))

    return SearchResponse(
        query=query,
        results=results,
        total=len(results)
    )

@router.get("/suggestions")
async def get_search_suggestions(
    q: str = Query(..., min_length=2),
    limit: int = Query(5, ge=1, le=10),
    db: Session = Depends(get_db)
):
    """
    Suggestions de recherche en temps réel
    """
    suggestions = db.query(Content.content_title).filter(
        Content.content_title.ilike(f"{q}%")
    ).distinct().limit(limit).all()

    return {
        "query": q,
        "suggestions": [s[0] for s in suggestions if s[0]]
    }

@router.get("/trending")
async def get_trending_searches(
    limit: int = Query(10, ge=1, le=20),
    db: Session = Depends(get_db)
):
    """
    Récupère les recherches tendances (basées sur les scans récents)
    """
    # Version simplifiée avec des résultats mock
    mock_trending = [
        {"title": "Blinding Lights", "count": 156},
        {"title": "Inception", "count": 98},
        {"title": "Heat Waves", "count": 87},
        {"title": "Interstellar", "count": 76},
        {"title": "The Weeknd", "count": 65},
        {"title": "Christopher Nolan", "count": 54},
        {"title": "Glass Animals", "count": 43},
        {"title": "Daft Punk", "count": 38},
        {"title": "Stranger Things", "count": 32},
        {"title": "Oppenheimer", "count": 29},
    ]
    
    return {
        "trending": mock_trending[:limit]
    }