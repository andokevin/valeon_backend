# app/api/routers/recommendations.py
from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks
from sqlalchemy.orm import Session
from typing import List, Optional
from pydantic import BaseModel, Field
from datetime import datetime, timedelta

from app.core.database import get_db
from app.models import User, Content, Scan, Favorite
from app.api.dependencies.auth import get_current_user, get_current_user_optional
from app.core.modules.openai.chat import ChatClient
from app.core.cache import cache

router = APIRouter(prefix="/recommendations", tags=["Recommendations"])
chat_client = ChatClient()

# Modèles Pydantic
class ContentRecommendation(BaseModel):
    content_id: int
    title: str
    type: str
    image: Optional[str] = None
    artist: Optional[str] = None
    description: Optional[str] = None
    release_date: Optional[str] = None
    reason: str
    score: float
    match_reasons: List[str] = []
    
    class Config:
        from_attributes = True

class ChatRequest(BaseModel):
    query: str = Field(..., min_length=3, max_length=500)
    context: Optional[dict] = None

class ChatResponse(BaseModel):
    recommendations: List[dict]
    source: str
    query_analysis: Optional[dict] = None

class TrendingContent(BaseModel):
    content_id: int
    title: str
    type: str
    image: Optional[str] = None
    artist: Optional[str] = None
    scan_count: int
    trend_score: float

@router.get("/personalized")
async def get_personalized_recommendations(
    limit: int = Query(20, ge=1, le=50),
    content_type: Optional[str] = Query(None, regex="^(music|movie|tv_show|image)$"),
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional)
):
    """
    Obtenir des recommandations personnalisées.
    """
    # Vérifier le cache
    cache_key = f"recommendations:{current_user.user_id if current_user else 'anonymous'}:{content_type}:{limit}"
    cached = cache.get(cache_key)
    if cached:
        return cached
    
    if current_user:
        # Récupérer l'historique
        favorites = db.query(Favorite).filter(
            Favorite.user_id == current_user.user_id
        ).order_by(Favorite.created_at.desc()).limit(20).all()
        
        user_history = []
        for fav in favorites:
            if fav.content:
                user_history.append({
                    "title": fav.content.content_title,
                    "type": fav.content.content_type,
                    "artist": fav.content.content_artist
                })
        
        # Obtenir les recommandations de l'IA
        result = await chat_client.get_recommendations(
            user_history=user_history,
            query=f"Recommandations de {content_type if content_type else 'contenus'} similaires",
            preferences=current_user.preferences
        )
    else:
        # Recommandations générales (populaires)
        query = db.query(Content).order_by(Content.content_rating.desc().nullslast()).limit(limit).all()
        
        result = {
            "recommendations": [
                {
                    "title": c.content_title,
                    "type": c.content_type,
                    "artist": c.content_artist,
                    "description": c.content_description,
                    "reason": "Populaire"
                }
                for c in query
            ]
        }
    
    # Mettre en cache (1 heure)
    cache.set(cache_key, result, ttl=3600)
    
    return result

@router.get("/trending", response_model=List[TrendingContent])
async def get_trending_content(
    content_type: Optional[str] = Query(None, regex="^(music|movie|tv_show|image)$"),
    time_range: str = Query("week", regex="^(day|week|month)$"),
    limit: int = Query(20, ge=1, le=50),
    db: Session = Depends(get_db)
):
    """Obtenir les contenus tendance."""
    cache_key = f"trending:{content_type}:{time_range}:{limit}"
    cached = cache.get(cache_key)
    if cached:
        return cached
    
    now = datetime.utcnow()
    if time_range == "day":
        start_date = now - timedelta(days=1)
    elif time_range == "week":
        start_date = now - timedelta(days=7)
    else:
        start_date = now - timedelta(days=30)
    
    query = db.query(
        Content,
        func.count(Scan.scan_id).label('scan_count')
    ).join(Scan, Scan.recognized_content_id == Content.content_id)\
     .filter(Scan.scan_date >= start_date)
    
    if content_type:
        query = query.filter(Content.content_type == content_type)
    
    trending = query.group_by(Content.content_id)\
                   .order_by(func.count(Scan.scan_id).desc())\
                   .limit(limit)\
                   .all()
    
    max_count = trending[0][1] if trending else 1
    
    result = []
    for content, count in trending:
        result.append({
            "content_id": content.content_id,
            "title": content.content_title,
            "type": content.content_type,
            "image": content.content_image,
            "artist": content.content_artist,
            "scan_count": count,
            "trend_score": count / max_count
        })
    
    cache.set(cache_key, result, ttl=3600)  # 1 heure
    return result

@router.post("/chat", response_model=ChatResponse)
async def chat_recommendation(
    request: ChatRequest,
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional)
):
    """Obtenir des recommandations via chat IA."""
    user_history = []
    if current_user:
        favorites = db.query(Favorite).filter(
            Favorite.user_id == current_user.user_id
        ).order_by(Favorite.created_at.desc()).limit(10).all()
        
        for fav in favorites:
            if fav.content:
                user_history.append({
                    "title": fav.content.content_title,
                    "type": fav.content.content_type
                })
    
    result = await chat_client.get_recommendations(
        user_history=user_history,
        query=request.query,
        preferences=current_user.preferences if current_user else None
    )
    
    return {
        "recommendations": result.get("recommendations", []),
        "source": "gpt-4"
    }