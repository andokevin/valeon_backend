# app/api/routers/recommendations.py (CORRIGÉ)
from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func, desc
from typing import Optional, List
from datetime import datetime, timedelta
from pydantic import BaseModel

import logging
logger = logging.getLogger(__name__)

from app.core.database import get_db
from app.core.cache import cache
from app.models import User, Content, Scan, Favorite
from app.api.dependencies.auth import get_current_user_optional, get_current_user
from app.core.modules.gemini import GeminiClient
from app.core.modules.tmdb import TMDBClient
from app.core.modules.spotify import SpotifyClient
from app.core.modules.spotify.client import spotify_search_url
from app.core.modules.youtube.client import YouTubeClient

router = APIRouter(prefix="/recommendations", tags=["Recommendations"])
gemini = GeminiClient()
tmdb = TMDBClient()
spotify = SpotifyClient()
youtube = YouTubeClient()

# ===== CONTENUS SIMILAIRES (Gemini en priorité) =====
def _year(value) -> Optional[str]:
    return str(value)[:4] if value else None

def _similar_prompt(src: dict, limit: int) -> str:
    year = _year(src.get("year")) or "Inconnue"
    if src.get("type") == "music":
        return f"""
        Tu es un expert en musique. L'utilisateur a écouté/scané :
        Titre : {src.get('title')}
        Artiste : {src.get('artist') or 'Inconnu'}
        Album : {src.get('album') or 'Inconnu'}
        Année : {year}

        Propose {limit} chansons similaires (d'autres artistes de préférence) qu'il pourrait aimer.
        Réponds UNIQUEMENT en JSON :
        {{"recommendations": [{{"title": "titre", "artist": "artiste", "album": "album ou null",
          "year": "année", "reason": "pourquoi c'est similaire, en français, 1 phrase",
          "type": "music"}}]}}
        """
    return f"""
    Tu es un expert en cinéma et séries. L'utilisateur a regardé/scané :
    Titre : {src.get('title')}
    Réalisateur : {src.get('director') or src.get('artist') or 'Inconnu'}
    Année : {year}

    Propose {limit} films ou séries similaires qu'il pourrait aimer.
    Réponds UNIQUEMENT en JSON :
    {{"recommendations": [{{"title": "titre", "director": "réalisateur", "year": "année",
      "reason": "pourquoi c'est similaire, en français, 1 phrase", "type": "movie"}}]}}
    """

async def _enrich_recommendation(rec: dict) -> dict:
    """Ajoute image, description, liens YouTube et Spotify à une recommandation."""
    rec["description"] = rec.get("description") or rec.get("reason")
    if rec.get("type") == "music":
        if spotify:
            tracks = await spotify.search_track(f"{rec.get('artist', '')} {rec.get('title', '')}".strip(), limit=1)
            if tracks:
                track = tracks[0]
                rec["image"] = track.get("image")
                rec["spotify_id"] = track.get("spotify_id")
                rec["spotify_url"] = track.get("spotify_url")
                rec["preview_url"] = track.get("preview_url")
                rec["album"] = track.get("album") or rec.get("album")
        # Lien Spotify même si l'API Spotify est indisponible (403 sans Premium)
        rec["spotify_url"] = rec.get("spotify_url") or spotify_search_url(rec.get("title"), rec.get("artist"))
        rec["spotify"] = {"spotify_url": rec["spotify_url"], "spotify_id": rec.get("spotify_id")}
        if youtube and rec.get("artist") and rec.get("title"):
            try:
                video = await youtube.search_music_video(rec["title"], rec["artist"])
                if video:
                    rec["youtube"] = video
                    rec["youtube_url"] = video.get("url")
            except Exception as e:
                logger.error(f"Erreur YouTube: {e}")
    else:
        rec["type"] = rec.get("type") or "movie"
        if tmdb:
            movie = await tmdb.search_movie(rec.get("title"), rec.get("year"))
            if movie:
                rec["image"] = movie.get("image")
                rec["description"] = movie.get("description") or rec["description"]
                rec["director"] = movie.get("director") or rec.get("director")
                rec["tmdb_id"] = movie.get("tmdb_id")
        if youtube and rec.get("title"):
            try:
                trailer = await youtube.search_trailer(rec["title"], rec.get("year"))
                if trailer:
                    rec["youtube"] = trailer
                    rec["youtube_url"] = trailer.get("url")
            except Exception as e:
                logger.error(f"Erreur YouTube trailer: {e}")
    return rec

async def _find_similar(db: Session, src: dict, limit: int, exclude_id: Optional[int] = None) -> dict:
    """src : title, artist, director, album, year, type (music/movie…), tmdb_id."""
    similar, method = [], None

    # 1. Gemini propose les contenus similaires
    gemini_result = await gemini.generate_text(prompt=_similar_prompt(src, limit), max_tokens=1200,
                                               json_mode=True, temperature=0.7)
    for rec in (gemini_result.get("recommendations") or [])[:limit]:
        if isinstance(rec, dict) and rec.get("title"):
            rec.setdefault("type", "music" if src.get("type") == "music" else "movie")
            similar.append(await _enrich_recommendation(rec))
    if similar:
        method = "gemini"

    # 2. Gemini indisponible : films similaires via TMDB
    if not similar and src.get("type") != "music" and tmdb and src.get("tmdb_id"):
        try:
            for movie in (await tmdb.get_similar_movies(src["tmdb_id"], limit) or [])[:limit]:
                movie.setdefault("type", "movie")
                movie["reason"] = movie.get("reason") or "Film similaire selon TMDB"
                similar.append(await _enrich_recommendation(movie))
            method = "tmdb" if similar else None
        except Exception as e:
            logger.error(f"Erreur TMDB similar: {e}")

    # 3. Dernier recours : contenus du même type dans la base
    if not similar:
        random_fn = func.rand() if db.bind.dialect.name == "mysql" else func.random()
        q = db.query(Content).filter(Content.content_type == (src.get("type") or "music"))
        if exclude_id:
            q = q.filter(Content.content_id != exclude_id)
        for c in q.order_by(random_fn).limit(limit).all():
            similar.append({
                "content_id": c.content_id, "title": c.content_title, "artist": c.content_artist,
                "director": c.content_director, "type": c.content_type, "image": c.content_image,
                "year": _year(c.content_release_date), "reason": "Contenu populaire dans la base",
                "description": c.content_description, "source": "local",
                "spotify_url": spotify_search_url(c.content_title, c.content_artist) if c.content_type == "music" else None,
            })
        method = "local_fallback"

    return {
        "source_content": {"content_id": exclude_id, "title": src.get("title"),
                           "type": src.get("type"), "artist": src.get("artist")},
        "recommendations": similar[:limit],
        "detection_method": method,
        "ai_unavailable": bool(gemini_result.get("unavailable")),
        "total": len(similar[:limit]),
    }

@router.get("/similar/{content_id}")
async def get_similar_content(
    content_id: int,
    limit: int = Query(3, ge=1, le=5),
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional)
):
    """Contenus similaires à un contenu enregistré (Gemini, puis TMDB, puis base locale)."""
    c = db.query(Content).filter(Content.content_id == content_id).first()
    if not c:
        raise HTTPException(404, "Contenu non trouvé")
    cache_key = f"similar:{content_id}:{limit}"
    cached = cache.get(cache_key)
    if cached:
        return cached
    src = {"title": c.content_title, "artist": c.content_artist, "director": c.content_director,
           "year": c.content_release_date, "type": c.content_type, "tmdb_id": c.tmdb_id}
    response = await _find_similar(db, src, limit, exclude_id=c.content_id)
    if not response["ai_unavailable"]:
        cache.set(cache_key, response, ttl=7200)
    return response

@router.get("/similar-to")
async def get_similar_to(
    title: str = Query(..., min_length=1, max_length=200),
    artist: Optional[str] = Query(None, max_length=200),
    type: str = Query("music", max_length=30),
    year: Optional[str] = Query(None, max_length=10),
    limit: int = Query(3, ge=1, le=5),
    db: Session = Depends(get_db),
):
    """
    Contenus similaires à partir du titre/artiste, pour un contenu absent de la base
    (ex. une recommandation proposée par Gemini).
    """
    ctype = "music" if type in ("music", "album_cover", "music_video", "concert_photo") else "movie"
    cache_key = f"similar_to:{ctype}:{title.lower()}:{(artist or '').lower()}:{limit}"
    cached = cache.get(cache_key)
    if cached:
        return cached
    src = {"title": title, "artist": artist, "director": artist, "year": year, "type": ctype}
    response = await _find_similar(db, src, limit)
    if not response["ai_unavailable"]:
        cache.set(cache_key, response, ttl=7200)
    return response

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

    # Si pas d'historique, utiliser les tendances (même format de réponse)
    if not user_history:
        # Appel direct : il faut passer time_range, sinon c'est l'objet Query() par défaut
        trending = await get_trending_content(db, content_type=content_type, time_range="week", limit=limit)
        response = {"recommendations": trending, "source": "trending"}
        cache.set(cache_key, response, ttl=1800)  # 30 minutes
        return response

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
    
    # Enrichir avec TMDB/Spotify/YouTube si possible
    enriched_recommendations = []
    for rec in recommendations[:limit]:
        enriched = rec.copy()
        
        if rec.get("type") == "movie" and tmdb:
            details = await tmdb.search_movie(rec["title"])
            if details:
                enriched["image"] = details.get("image")
                enriched["description"] = details.get("description")
                enriched["year"] = (details.get("release_date") or "")[:4]
                enriched["tmdb_id"] = details.get("tmdb_id")
                
                # Trailer YouTube
                if youtube:
                    try:
                        trailer = await youtube.search_trailer(
                            details.get("title", ""),
                            enriched["year"]
                        )
                        if trailer:
                            enriched["youtube"] = trailer
                            enriched["youtube_url"] = trailer.get("url")
                    except Exception as e:
                        logger.error(f"Erreur YouTube trailer: {e}")
        
        elif rec.get("type") == "music" and spotify:
            enriched["spotify_url"] = spotify_search_url(rec.get("title"), rec.get("artist"))
            query = f"{rec.get('artist', '')} {rec['title']}".strip()
            tracks = await spotify.search_track(query, limit=1)
            if tracks and len(tracks) > 0:
                track = tracks[0]
                enriched["image"] = track.get("image")
                enriched["spotify_id"] = track.get("spotify_id")
                enriched["preview_url"] = track.get("preview_url")
                
                # Vidéo YouTube
                if youtube and rec.get("artist"):
                    try:
                        video = await youtube.search_music_video(
                            rec.get("title", ""),
                            rec.get("artist", "")
                        )
                        if video:
                            enriched["youtube"] = video
                            enriched["youtube_url"] = video.get("url")
                    except Exception as e:
                        logger.error(f"Erreur YouTube video: {e}")
        
        enriched_recommendations.append(enriched)

    # Gemini indisponible (surcharge, quota) : tendances réelles de la base plutôt que rien
    if not enriched_recommendations:
        trending = await get_trending_content(db, content_type=content_type, time_range="month", limit=limit)
        response = {"recommendations": trending, "source": "trending", "ai_unavailable": True}
        cache.set(cache_key, response, ttl=300)  # court : on réessaiera Gemini bientôt
        return response

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
