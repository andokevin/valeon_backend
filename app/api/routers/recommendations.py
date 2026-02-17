from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks
from sqlalchemy.orm import Session
from typing import List, Optional
from pydantic import BaseModel, Field
from datetime import datetime, timedelta

from app.core.database import get_db
from app.models import User, Content, Scan, Favorite
from app.api.dependencies.auth import get_current_user, get_current_user_optional
from app.services.recommendation.engine import RecommendationEngine

router = APIRouter(prefix="/recommendations", tags=["Recommendations"])

# Initialiser le moteur de recommandation
recommendation_engine = RecommendationEngine()

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

@router.get("/personalized", response_model=List[ContentRecommendation])
async def get_personalized_recommendations(
    background_tasks: BackgroundTasks,
    limit: int = Query(20, ge=1, le=50),
    content_type: Optional[str] = Query(None, regex="^(music|movie|tv_show|image)$"),
    diversity: float = Query(0.3, ge=0, le=1, description="Facteur de diversité (0 = plus similaire, 1 = plus diversifié)"),
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional)
):
    """
    Obtenir des recommandations personnalisées
    """
    if current_user:
        # Recommandations personnalisées pour l'utilisateur connecté
        recommendations = await recommendation_engine.get_personalized_recommendations(
            user=current_user,
            db=db,
            limit=limit,
            content_type=content_type,
            diversity=diversity
        )
        
        # Enregistrer l'activité en arrière-plan
        background_tasks.add_task(
            log_recommendation_activity,
            current_user.user_id,
            recommendations,
            db
        )
    else:
        # Recommandations générales pour les utilisateurs non connectés
        recommendations = await recommendation_engine.get_trending_recommendations(
            db=db,
            limit=limit,
            content_type=content_type
        )
    
    result = []
    for rec in recommendations:
        content = rec["content"]
        result.append({
            "content_id": content.content_id,
            "title": content.content_title,
            "type": content.content_type,
            "image": content.content_image,
            "artist": content.content_artist,
            "description": content.content_description,
            "release_date": content.content_release_date,
            "reason": rec["reason"],
            "score": rec["score"],
            "match_reasons": rec.get("match_reasons", [])
        })
    
    return result

@router.get("/trending", response_model=List[TrendingContent])
async def get_trending_content(
    content_type: Optional[str] = Query(None, regex="^(music|movie|tv_show|image)$"),
    time_range: str = Query("week", regex="^(day|week|month)$"),
    limit: int = Query(20, ge=1, le=50),
    db: Session = Depends(get_db)
):
    """
    Obtenir les contenus tendance
    """
    # Définir la période
    now = datetime.utcnow()
    if time_range == "day":
        start_date = now - timedelta(days=1)
    elif time_range == "week":
        start_date = now - timedelta(days=7)
    else:  # month
        start_date = now - timedelta(days=30)
    
    # Requête pour les contenus les plus scannés
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
    
    # Calculer le score de tendance
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
    
    return result

@router.get("/similar/{content_id}", response_model=List[ContentRecommendation])
async def get_similar_content(
    content_id: int,
    limit: int = Query(10, ge=1, le=30),
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional)
):
    """
    Obtenir des contenus similaires à un contenu donné
    """
    content = db.query(Content).filter(Content.content_id == content_id).first()
    if not content:
        raise HTTPException(status_code=404, detail="Contenu non trouvé")
    
    # Chercher des contenus similaires
    similar = await recommendation_engine.get_similar_content(
        content=content,
        db=db,
        limit=limit,
        exclude_user_id=current_user.user_id if current_user else None
    )
    
    result = []
    for item in similar:
        sim_content = item["content"]
        result.append({
            "content_id": sim_content.content_id,
            "title": sim_content.content_title,
            "type": sim_content.content_type,
            "image": sim_content.content_image,
            "artist": sim_content.content_artist,
            "description": sim_content.content_description,
            "release_date": sim_content.content_release_date,
            "reason": item["reason"],
            "score": item["score"],
            "match_reasons": item.get("match_reasons", [])
        })
    
    return result

@router.get("/for-you", response_model=List[ContentRecommendation])
async def get_for_you_recommendations(
    background_tasks: BackgroundTasks,
    limit: int = Query(20, ge=1, le=50),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Page d'accueil "Pour vous" avec différents types de recommandations
    """
    # Récupérer différents types de recommandations
    recommendations = []
    
    # 1. Reprendre où vous vous êtes arrêté (scans récents)
    recent_scans = db.query(Scan)\
        .filter(Scan.scan_user == current_user.user_id)\
        .filter(Scan.recognized_content_id.isnot(None))\
        .order_by(Scan.scan_date.desc())\
        .limit(5)\
        .all()
    
    for scan in recent_scans[:3]:
        if scan.content:
            recommendations.append({
                "content": scan.content,
                "reason": "Reprendre où vous vous êtes arrêté",
                "score": 0.9,
                "match_reasons": ["Vous avez scanné récemment"]
            })
    
    # 2. Basé sur vos favoris
    favorites = db.query(Favorite)\
        .filter(Favorite.user_id == current_user.user_id)\
        .order_by(Favorite.created_at.desc())\
        .limit(5)\
        .all()
    
    fav_contents = [f.content for f in favorites if f.content]
    
    # 3. Recommandations personnalisées
    personalized = await recommendation_engine.get_personalized_recommendations(
        user=current_user,
        db=db,
        limit=limit - len(recommendations),
        diversity=0.4
    )
    
    recommendations.extend(personalized)
    
    # 4. Nouveautés
    week_ago = datetime.utcnow() - timedelta(days=7)
    new_contents = db.query(Content)\
        .filter(Content.content_date >= week_ago)\
        .order_by(Content.content_date.desc())\
        .limit(5)\
        .all()
    
    for content in new_contents:
        recommendations.append({
            "content": content,
            "reason": "Nouveauté",
            "score": 0.7,
            "match_reasons": ["Nouveau contenu ajouté"]
        })
    
    # Fusionner et dédupliquer
    seen_ids = set()
    unique_recs = []
    
    for rec in recommendations:
        content_id = rec["content"].content_id
        if content_id not in seen_ids:
            seen_ids.add(content_id)
            unique_recs.append(rec)
    
    # Limiter et formater
    result = []
    for rec in unique_recs[:limit]:
        content = rec["content"]
        result.append({
            "content_id": content.content_id,
            "title": content.content_title,
            "type": content.content_type,
            "image": content.content_image,
            "artist": content.content_artist,
            "description": content.content_description,
            "release_date": content.content_release_date,
            "reason": rec["reason"],
            "score": rec["score"],
            "match_reasons": rec.get("match_reasons", [])
        })
    
    return result

@router.post("/chat", response_model=ChatResponse)
async def chat_recommendation(
    request: ChatRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional)
):
    """
    Obtenir des recommandations via chat IA
    """
    result = await recommendation_engine.get_ai_chat_recommendation(
        user_query=request.query,
        user=current_user,
        db=db,
        context=request.context
    )
    
    # Enregistrer la requête pour améliorer le système
    if current_user:
        background_tasks.add_task(
            log_chat_query,
            current_user.user_id,
            request.query,
            result,
            db
        )
    
    return result

@router.get("/discover")
async def discover_content(
    genres: Optional[List[str]] = Query(None),
    years: Optional[str] = Query(None, regex="^\d{4}-\d{4}$"),
    rating_min: float = Query(0, ge=0, le=10),
    content_type: Optional[str] = Query(None, regex="^(music|movie|tv_show|image)$"),
    limit: int = Query(30, ge=1, le=100),
    db: Session = Depends(get_db)
):
    """
    Découvrir du contenu avec filtres
    """
    query = db.query(Content)
    
    if content_type:
        query = query.filter(Content.content_type == content_type)
    
    if rating_min > 0:
        query = query.filter(Content.content_rating >= rating_min)
    
    if years:
        start_year, end_year = years.split('-')
        query = query.filter(
            Content.content_release_date.between(f"{start_year}-01-01", f"{end_year}-12-31")
        )
    
    # Filtrer par genres si supporté
    if genres:
        # Note: Cette partie dépend de comment vous stockez les genres
        pass
    
    # Trier par popularité
    contents = query.order_by(Content.content_rating.desc().nullslast())\
                    .limit(limit)\
                    .all()
    
    return {
        "total": len(contents),
        "contents": [
            {
                "content_id": c.content_id,
                "title": c.content_title,
                "type": c.content_type,
                "image": c.content_image,
                "artist": c.content_artist,
                "rating": c.content_rating,
                "release_date": c.content_release_date
            }
            for c in contents
        ]
    }

@router.get("/daily-mix")
async def get_daily_mix(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Obtenir un mix quotidien personnalisé
    """
    # Générer un mix basé sur l'historique
    mix = await recommendation_engine.generate_daily_mix(
        user=current_user,
        db=db
    )
    
    return mix

async def log_recommendation_activity(user_id: int, recommendations: List[dict], db: Session):
    """
    Logger les recommandations pour améliorer le système
    """
    from app.models import UserActivity
    
    activity = UserActivity(
        user_id=user_id,
        activity_type="recommendation_view",
        metadata={
            "count": len(recommendations),
            "content_ids": [r["content"].content_id for r in recommendations[:10]]
        }
    )
    db.add(activity)
    db.commit()

async def log_chat_query(user_id: int, query: str, result: dict, db: Session):
    """
    Logger les requêtes chat pour améliorer le système
    """
    from app.models import UserActivity
    
    activity = UserActivity(
        user_id=user_id,
        activity_type="chat_query",
        metadata={
            "query": query,
            "recommendations_count": len(result.get("recommendations", []))
        }
    )
    db.add(activity)
    db.commit()