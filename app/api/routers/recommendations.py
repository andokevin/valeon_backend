from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func, desc
from typing import Optional, List
from datetime import datetime, timedelta
from pydantic import BaseModel

from app.core.database import get_db
from app.core.cache import cache
from app.models import User, Content, Scan, Favorite
from app.api.dependencies.auth import get_current_user_optional, get_current_user
from app.core.modules.gemini import GeminiClient
from app.core.modules.tmdb import TMDBClient
from app.core.modules.spotify import SpotifyClient

router = APIRouter(prefix="/recommendations", tags=["Recommendations"])
gemini = GeminiClient()
tmdb = TMDBClient()
spotify = SpotifyClient()

# ===== MODÈLES PYDANTIC =====
class ChatRequest(BaseModel):
    query: str
    context: Optional[dict] = None

class ChatResponse(BaseModel):
    response: str
    recommendations: Optional[List[dict]] = None

# ===== RECOMMANDATIONS PERSONNALISÉES =====
@router.get("/personalized")
async def get_personalized_recommendations(
    limit: int = Query(10, ge=1, le=50),   
    content_type: Optional[str] = Query(None, pattern="^(music|movie|tv_show)$"),
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional),
):
    """
    Recommandations personnalisées basées sur l'historique de l'utilisateur.
    """
    cache_key = f"reco:user_{current_user.user_id if current_user else 'anon'}:{content_type}:{limit}"
    cached = cache.get(cache_key)
    if cached:
        return cached

    # Construire l'historique utilisateur
    user_history = []
    
    if current_user:
        # Récupérer les favoris
        favorites = db.query(Favorite).filter(
            Favorite.user_id == current_user.user_id
        ).order_by(desc(Favorite.created_at)).limit(20).all()
        
        for fav in favorites:
            if fav.content:
                user_history.append({
                    "title": fav.content.content_title,
                    "type": fav.content.content_type,
                    "artist": fav.content.content_artist,
                    "source": "favorite",
                    "confidence": 1.0
                })
        
        # Récupérer les scans récents
        recent_scans = db.query(Scan).filter(
            Scan.scan_user == current_user.user_id,
            Scan.status == "completed",
            Scan.result.isnot(None)
        ).order_by(desc(Scan.scan_date)).limit(30).all()
        
        for scan in recent_scans:
            if scan.result:
                result = scan.result
                user_history.append({
                    "title": result.get("title"),
                    "type": result.get("type", scan.scan_type),
                    "artist": result.get("artist"),
                    "source": "scan",
                    "confidence": result.get("confidence", 0.7),
                    "date": scan.scan_date.isoformat()
                })

    # Si pas d'historique, utiliser les tendances
    if not user_history:
        trending = await get_trending_content(db, limit=limit, content_type=content_type)
        cache.set(cache_key, trending, ttl=1800)  # 30 minutes
        return trending

    # Générer des recommandations avec Gemini
    system_prompt = (
        "Tu es un expert en recommandations de musique, films et séries. "
        "Analyse l'historique de l'utilisateur et propose des recommandations pertinentes. "
        "Pour chaque recommandation, explique POURQUOI elle est pertinente (basé sur l'historique)."
    )

    user_prompt = f"""Historique utilisateur (par ordre chronologique):
{user_history[:20]}

Type demandé: {content_type if content_type else 'tous'}

Génère {limit} recommandations pertinentes. Pour chaque recommandation, inclure:
- title: titre du contenu
- type: music/movie/tv_show
- artist: artiste/réalisateur (si applicable)
- reason: explication pourquoi cette recommandation (basée sur l'historique)
- confidence: score 0-1

Réponds en JSON avec une liste 'recommendations'."""

    result = await gemini.generate_text(
        prompt=user_prompt,
        system_prompt=system_prompt,
        max_tokens=1000,
        json_mode=True
    )

    recommendations = result.get("recommendations", [])
    
    # Enrichir avec TMDB/Spotify si possible
    enriched_recommendations = []
    for rec in recommendations[:limit]:
        enriched = rec.copy()
        
        if rec.get("type") == "movie" and tmdb:
            details = await tmdb.search_movie(rec["title"])
            if details:
                enriched["image"] = details.get("image")
                enriched["description"] = details.get("description")
                enriched["year"] = details.get("release_date", "")[:4]
                enriched["tmdb_id"] = details.get("tmdb_id")
        
        elif rec.get("type") == "music" and spotify:
            query = f"{rec.get('artist', '')} {rec['title']}".strip()
            tracks = await spotify.search_track(query, limit=1)
            if tracks and len(tracks) > 0:
                enriched["image"] = tracks[0].get("image")
                enriched["spotify_id"] = tracks[0].get("spotify_id")
                enriched["preview_url"] = tracks[0].get("preview_url")
        
        enriched_recommendations.append(enriched)

    response = {"recommendations": enriched_recommendations}
    cache.set(cache_key, response, ttl=3600)  # 1 heure
    return response

# ===== CONTENU TENDANCE =====
@router.get("/trending")
async def get_trending_content(
    db: Session = Depends(get_db),
    content_type: Optional[str] = Query(None, pattern="^(music|movie|tv_show)$"),
    time_range: str = Query("week", pattern="^(day|week|month)$"),
    limit: int = Query(20, ge=1, le=50)
):
    """
    Contenu tendance basé sur les scans récents.
    """
    cache_key = f"trending:{content_type}:{time_range}:{limit}"
    cached = cache.get(cache_key)
    if cached:
        return cached

    # Calculer la période
    delta_map = {"day": 1, "week": 7, "month": 30}
    start_date = datetime.utcnow() - timedelta(days=delta_map[time_range])

    # Requête de base
    query = db.query(
        Content,
        func.count(Scan.scan_id).label("scan_count"),
        func.max(Scan.scan_date).label("last_scan")
    ).join(
        Scan, Scan.recognized_content_id == Content.content_id
    ).filter(
        Scan.scan_date >= start_date,
        Scan.status == "completed"
    )

    if content_type:
        query = query.filter(Content.content_type == content_type)

    # Grouper et ordonner
    results = query.group_by(Content.content_id)\
                   .order_by(desc("scan_count"))\
                   .limit(limit).all()

    # Formater les résultats
    trending = []
    for content, scan_count, last_scan in results:
        trending.append({
            "content_id": content.content_id,
            "title": content.content_title,
            "type": content.content_type,
            "artist": content.content_artist,
            "image": content.content_image,
            "scan_count": scan_count,
            "last_scan": last_scan.isoformat() if last_scan else None,
            "trend_score": min(scan_count / 10, 1.0)  # Score normalisé
        })

    cache.set(cache_key, trending, ttl=3600)
    return trending

# ===== CONTENU SIMILAIRE =====
@router.get("/similar/{content_id}")
async def get_similar_content(
    content_id: int,
    limit: int = Query(10, ge=1, le=20),
    db: Session = Depends(get_db)
):
    """
    Trouve des contenus similaires à un contenu donné.
    """
    # Récupérer le contenu source
    source_content = db.query(Content).filter(Content.content_id == content_id).first()
    if not source_content:
        raise HTTPException(404, "Contenu non trouvé")

    cache_key = f"similar:{content_id}:{limit}"
    cached = cache.get(cache_key)
    if cached:
        return cached

    similar = []

    # Utiliser les APIs externes selon le type
    if source_content.content_type == "movie" and tmdb and source_content.tmdb_id:
        # Récupérer films similaires via TMDB
        similar_data = await tmdb.get_similar_movies(source_content.tmdb_id, limit)
        if similar_data:
            similar = similar_data

    elif source_content.content_type == "music" and spotify and source_content.spotify_id:
        # Récupérer recommandations Spotify
        similar_data = await spotify.get_recommendations(
            seed_tracks=[source_content.spotify_id],
            limit=limit
        )
        if similar_data:
            similar = similar_data

    # Si pas de résultats des APIs, chercher dans la base locale
    if not similar:
        similar = db.query(Content).filter(
            Content.content_type == source_content.content_type,
            Content.content_id != source_content.content_id
        ).order_by(func.random()).limit(limit).all()

        similar = [{
            "content_id": c.content_id,
            "title": c.content_title,
            "type": c.content_type,
            "artist": c.content_artist,
            "image": c.content_image,
            "reason": "Contenu populaire"
        } for c in similar]

    cache.set(cache_key, similar, ttl=7200)  # 2 heures
    return similar

# ===== CHAT ASSISTANT =====
@router.post("/chat", response_model=ChatResponse)
async def chat_with_assistant(
    request: ChatRequest,
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional)
):
    """
    Chat interactif avec l'assistant Valeon.
    L'assistant peut recommander des contenus, répondre aux questions, etc.
    """
    # Construire le contexte
    context_messages = []
    
    # Message système
    system_prompt = (
        "Tu es Valeon Assistant, expert en musique, films et séries. "
        "Tu connais les tendances, les artistes, les réalisateurs, et tu aides "
        "les utilisateurs à découvrir de nouveaux contenus. "
        "Tu es amical, concis et toujours utile. "
        "Si l'utilisateur demande des recommandations, base-toi sur son historique si disponible."
    )
    context_messages.append({"role": "system", "content": system_prompt})

    # Ajouter l'historique utilisateur si disponible
    if current_user and request.context and request.context.get("use_history", True):
        recent = db.query(Scan).filter(
            Scan.scan_user == current_user.user_id,
            Scan.status == "completed"
        ).order_by(desc(Scan.scan_date)).limit(10).all()
        
        if recent:
            history_text = "Scans récents de l'utilisateur:\n"
            for scan in recent:
                if scan.result:
                    title = scan.result.get("title", "inconnu")
                    type_ = scan.result.get("type", scan.scan_type)
                    history_text += f"- {title} ({type_})\n"
            context_messages.append({"role": "system", "content": history_text})

    # Ajouter la question
    context_messages.append({"role": "user", "content": request.query})

    # Obtenir la réponse de Gemini
    response = await gemini.chat(messages=context_messages, max_tokens=500)
    response_text = response.get("text", "Désolé, je n'ai pas pu traiter votre demande.")

    # Essayer d'extraire des recommandations de la réponse
    recommendations = None
    try:
        if "recommendation" in response_text.lower():
            # Prompt pour structurer les recommandations
            extract_prompt = f"""
            Extrait les recommandations de cette réponse et formate-les en JSON.
            Réponse: "{response_text}"
            
            Format JSON attendu:
            {{
                "recommendations": [
                    {{"title": "...", "type": "music/movie/tv_show", "artist": "..."}}
                ]
            }}
            """
            extract_result = await gemini.generate_text(extract_prompt, json_mode=True)
            recommendations = extract_result.get("recommendations")
    except:
        pass

    return ChatResponse(
        response=response_text,
        recommendations=recommendations
    )

# ===== ANALYSE DE TEXTE POUR RECHERCHE =====
@router.post("/analyze-search")
async def analyze_search_query(
    query: str,
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional)
):
    """
    Analyse une requête de recherche pour comprendre l'intention.
    """
    prompt = f"""Analyse cette requête de recherche: "{query}"

Détermine:
1. Le type de contenu recherché (music/movie/tv_show/artist/other)
2. Les mots-clés principaux
3. L'intention (recherche exacte, recommandation, question)
4. Si c'est une demande de recommandation

Réponds en JSON avec:
{{
    "content_type": "...",
    "keywords": ["..."],
    "intent": "search/recommendation/question",
    "is_recommendation_request": true/false,
    "artists": ["..."],
    "titles": ["..."]
}}"""

    result = await gemini.generate_text(prompt, json_mode=True)
    return result