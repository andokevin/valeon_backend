from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.models import Content
from app.core.modules.justwatch.client import JustWatchClient

router = APIRouter(prefix="/streaming", tags=["Streaming"])
jw = JustWatchClient()

@router.get("/movie/{content_id}")
async def movie_streaming(content_id: int, country: str = Query("FR"), db: Session = Depends(get_db)):
    content = db.query(Content).filter(Content.content_id == content_id).first()
    if not content:
        raise HTTPException(404, "Contenu non trouvé")
    jw.country = country
    if content.justwatch_id:
        details = await jw._get_movie_details(content.justwatch_id)
        if details:
            return details.get("streaming", {})
    if content.content_title:
        result = await jw.search_movie(content.content_title)
        if result:
            return result.get("streaming", {})
    return {"streaming": [], "rent": [], "buy": [], "free": []}
