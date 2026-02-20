from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import Optional, List
from datetime import datetime, timedelta

from app.core.database import get_db
from app.core.cache import cache
from app.models import User, Content, Scan, Favorite
from app.api.dependencies.auth import get_current_user_optional
from app.core.modules.openai.chat import ChatClient

router = APIRouter(prefix="/recommendations", tags=["Recommendations"])
chat_client = ChatClient()

@router.get("/personalized")
async def personalized(
    limit: int = Query(20, ge=1, le=50),
    content_type: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional),
):
    key = f"reco:{current_user.user_id if current_user else 'anon'}:{content_type}:{limit}"
    cached = cache.get(key)
    if cached:
        return cached

    if current_user:
        favs = db.query(Favorite).filter(Favorite.user_id == current_user.user_id)\
                 .order_by(Favorite.created_at.desc()).limit(20).all()
        history = [{"title": f.content.content_title, "type": f.content.content_type,
                    "artist": f.content.content_artist} for f in favs if f.content]
        result = await chat_client.get_recommendations(
            user_history=history,
            query=f"Recommandations de {content_type or 'contenus'} similaires",
            preferences=current_user.preferences,
        )
    else:
        q = db.query(Content).order_by(Content.content_rating.desc()).limit(limit).all()
        result = {"recommendations": [{"title": c.content_title, "type": c.content_type,
                                        "artist": c.content_artist, "reason": "Populaire"} for c in q]}
    cache.set(key, result, ttl=3600)
    return result

@router.get("/trending")
async def trending(
    content_type: Optional[str] = None,
    time_range: str = Query("week", regex="^(day|week|month)$"),
    limit: int = Query(20, ge=1, le=50),
    db: Session = Depends(get_db),
):
    key = f"trending:{content_type}:{time_range}:{limit}"
    cached = cache.get(key)
    if cached:
        return cached
    deltas = {"day": 1, "week": 7, "month": 30}
    start = datetime.utcnow() - timedelta(days=deltas[time_range])
    q = db.query(Content, func.count(Scan.scan_id).label("cnt"))\
          .join(Scan, Scan.recognized_content_id == Content.content_id)\
          .filter(Scan.scan_date >= start)
    if content_type:
        q = q.filter(Content.content_type == content_type)
    rows = q.group_by(Content.content_id).order_by(func.count(Scan.scan_id).desc()).limit(limit).all()
    max_cnt = rows[0][1] if rows else 1
    result = [{"content_id": c.content_id, "title": c.content_title, "type": c.content_type,
               "image": c.content_image, "scan_count": cnt, "trend_score": cnt / max_cnt}
              for c, cnt in rows]
    cache.set(key, result, ttl=3600)
    return result
