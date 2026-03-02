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
from app.core.modules.youtube.client import YouTubeClient

router = APIRouter(prefix="/recommendations", tags=["Recommendations"])
gemini = GeminiClient()
tmdb = TMDBClient()
spotify = SpotifyClient()
youtube = YouTubeClient()

# ===== MODÈLES PYDANTIC =====
class ChatRequest(BaseModel):
    query: str
    context: Optional[dict] = None

class ChatResponse(BaseModel):
    response: str
    recommendations: Optional[List[dict]] = None

# ===== ENDPOINT POUR RECOMMANDATIONS SIMILAIRES =====
@router.get("/similar/{content_id}")
async def get_similar_content(
    content_id: int,
    limit: int = Query(3, ge=1, le=5),
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional)
):
    """
    Trouve des contenus similaires à un contenu donné.
    Utilise Gemini pour analyser et proposer des recommandations intelligentes.
    """
    # Récupérer le contenu source
    source_content = db.query(Content).filter(Content.content_id == content_id).first()
    if not source_content:
        raise HTTPException(404, "Contenu non trouvé")

    cache_key = f"similar:{content_id}:{limit}:user_{current_user.user_id if current_user else 'anon'}"
    cached = cache.get(cache_key)
    if cached:
        return cached

    similar = []
    detection_method = "local"

    # ===== STRATÉGIE 1: UTILISER LES APIs EXTERNES =====
    if source_content.content_type == "movie" and tmdb and source_content.tmdb_id:
        try:
            similar_data = await tmdb.get_similar_movies(source_content.tmdb_id, limit)
            if similar_data:
                similar = similar_data
                detection_method = "tmdb"
                logger.info(f"✅ {len(similar)} films similaires trouvés via TMDB")
        except Exception as e:
            logger.error(f"Erreur TMDB similar: {e}")

    elif source_content.content_type == "music" and spotify and source_content.spotify_id:
        try:
            similar_data = await spotify.get_recommendations(
                seed_tracks=[source_content.spotify_id],
                limit=limit
            )
            if similar_data:
                similar = similar_data
                detection_method = "spotify"
                logger.info(f"✅ {len(similar)} musiques similaires trouvées via Spotify")
        except Exception as e:
            logger.error(f"Erreur Spotify similar: {e}")

    # ===== STRATÉGIE 2: UTILISER GEMINI POUR ANALYSE INTELLIGENTE =====
    if not similar:
        logger.info(f"🔍 Utilisation de Gemini pour trouver des contenus similaires à '{source_content.content_title}'")
        
        # Récupérer les attributs avec vérification d'existence
        content_album = getattr(source_content, 'content_album', None)
        content_genre = getattr(source_content, 'content_genre', None)
        content_director = getattr(source_content, 'content_director', None)
        content_actors = getattr(source_content, 'content_actors', None)
        
        # Construire le prompt en fonction du type
        if source_content.content_type == "music":
            prompt = f"""
            Tu es un expert en musique. L'utilisateur a écouté/scané:
            
            Titre: {source_content.content_title}
            Artiste: {source_content.content_artist}
            Album: {content_album if content_album else 'Inconnu'}
            Année: {source_content.content_release_date[:4] if source_content.content_release_date else 'Inconnue'}
            Genre: {content_genre if content_genre else 'Inconnu'}
            
            Propose 3 chansons similaires que l'utilisateur pourrait aimer.
            Pour chaque recommandation, inclure:
            - titre de la chanson
            - nom de l'artiste
            - album (si connu)
            - année approximative
            - raison courte de pourquoi cette chanson est similaire
            
            Réponds UNIQUEMENT en JSON avec cette structure:
            {{
                "recommendations": [
                    {{
                        "title": "titre de la chanson",
                        "artist": "nom de l'artiste",
                        "album": "nom de l'album (optionnel)",
                        "year": "année (optionnel)",
                        "reason": "explication en français",
                        "type": "music"
                    }}
                ]
            }}
            """
        else:  # movie
            prompt = f"""
            Tu es un expert en cinéma. L'utilisateur a regardé/scané:
            
            Titre: {source_content.content_title}
            Réalisateur: {content_director if content_director else 'Inconnu'}
            Acteurs: {content_actors if content_actors else 'Inconnus'}
            Année: {source_content.content_release_date[:4] if source_content.content_release_date else 'Inconnue'}
            Genre: {content_genre if content_genre else 'Inconnu'}
            
            Propose 3 films similaires que l'utilisateur pourrait aimer.
            Pour chaque recommandation, inclure:
            - titre du film
            - réalisateur
            - année
            - raison courte de pourquoi ce film est similaire
            
            Réponds UNIQUEMENT en JSON avec cette structure:
            {{
                "recommendations": [
                    {{
                        "title": "titre du film",
                        "director": "nom du réalisateur",
                        "year": "année",
                        "reason": "explication en français",
                        "type": "movie"
                    }}
                ]
            }}
            """

        try:
            gemini_result = await gemini.generate_text(
                prompt=prompt,
                max_tokens=800,
                json_mode=True,
                temperature=0.7
            )
            
            recommendations = gemini_result.get("recommendations", [])
            
            # Enrichir chaque recommandation avec les APIs
            for rec in recommendations:
                if rec.get("type") == "music":
                    # Chercher sur Spotify
                    if spotify:
                        query = f"{rec.get('artist', '')} {rec.get('title', '')}".strip()
                        tracks = await spotify.search_track(query, limit=1)
                        if tracks and len(tracks) > 0:
                            track = tracks[0]
                            rec["image"] = track.get("image")
                            rec["spotify_id"] = track.get("spotify_id")
                            rec["preview_url"] = track.get("preview_url")
                            rec["album"] = track.get("album") or rec.get("album")
                    
                    # Chercher sur YouTube
                    if youtube and rec.get("artist") and rec.get("title"):
                        try:
                            video = await youtube.search_music_video(
                                rec.get("title", ""),
                                rec.get("artist", "")
                            )
                            if video:
                                rec["youtube"] = video
                                rec["youtube_url"] = video.get("url")
                        except Exception as e:
                            logger.error(f"Erreur YouTube: {e}")
                
                elif rec.get("type") == "movie":
                    # Chercher sur TMDB
                    if tmdb:
                        movie = await tmdb.search_movie(rec.get("title"), rec.get("year"))
                        if movie:
                            rec["image"] = movie.get("image")
                            rec["description"] = movie.get("description")
                            rec["director"] = movie.get("director") or rec.get("director")
                            rec["tmdb_id"] = movie.get("tmdb_id")
                            
                            # Trailer YouTube
                            if youtube:
                                try:
                                    trailer = await youtube.search_trailer(
                                        movie.get("title", ""),
                                        rec.get("year")
                                    )
                                    if trailer:
                                        rec["youtube"] = trailer
                                        rec["youtube_url"] = trailer.get("url")
                                except Exception as e:
                                    logger.error(f"Erreur YouTube trailer: {e}")
                
                similar.append(rec)
            
            if similar:
                detection_method = "gemini"
                logger.info(f"✅ {len(similar)} recommandations générées par Gemini")
                
        except Exception as e:
            logger.error(f"Erreur Gemini: {e}")

    # ===== STRATÉGIE 3: FALLBACK SUR LA BASE LOCALE =====
    if not similar:
        logger.info("Fallback sur la base locale pour les contenus similaires")
        local_similar = db.query(Content).filter(
            Content.content_type == source_content.content_type,
            Content.content_id != source_content.content_id
        ).order_by(func.random()).limit(limit).all()

        for c in local_similar:
            similar.append({
                "content_id": c.content_id,
                "title": c.content_title,
                "artist": c.content_artist,
                "director": c.content_director,
                "type": c.content_type,
                "image": c.content_image,
                "year": c.content_release_date[:4] if c.content_release_date else None,
                "reason": "Contenu populaire dans la base",
                "source": "local"
            })
        
        detection_method = "local_fallback"

    # Préparer la réponse finale
    response = {
        "source_content": {
            "content_id": source_content.content_id,
            "title": source_content.content_title,
            "type": source_content.content_type,
            "artist": source_content.content_artist
        },
        "recommendations": similar[:limit],
        "detection_method": detection_method,
        "total": len(similar[:limit])
    }

    cache.set(cache_key, response, ttl=7200)  # 2 heures
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
    
    # Enrichir avec TMDB/Spotify/YouTube si possible
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

# ===== CHAT ASSISTANT =====
@router.post("/chat", response_model=ChatResponse)
async def chat_with_assistant(
    request: ChatRequest,
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional)
):
    """
    Chat interactif avec l'assistant Valeon.
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
        if "recommand" in response_text.lower():
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
