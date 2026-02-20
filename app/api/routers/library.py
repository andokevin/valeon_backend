from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from sqlalchemy import desc, func
from typing import List, Optional
from pydantic import BaseModel, Field
from datetime import datetime

from app.core.database import get_db
from app.models import User, Content, Favorite, Playlist, UserActivity, Scan
from app.models.playlist import playlist_contents
from app.api.dependencies.auth import get_current_user

router = APIRouter(prefix="/library", tags=["Library"])

class PlaylistCreate(BaseModel):
    playlist_name: str = Field(..., min_length=1, max_length=100)
    playlist_description: Optional[str] = None

class PlaylistUpdate(BaseModel):
    playlist_name: Optional[str] = None
    playlist_description: Optional[str] = None
    playlist_image: Optional[str] = None

class AddToPlaylistRequest(BaseModel):
    content_id: int
    position: Optional[int] = None

@router.get("/favorites")
async def get_favorites(
    db: Session = Depends(get_db), current_user: User = Depends(get_current_user),
    skip: int = 0, limit: int = Query(50, le=100),
    content_type: Optional[str] = None, sort_by: str = "recent",
):
    q = db.query(Favorite).filter(Favorite.user_id == current_user.user_id).join(Content)
    if content_type:
        q = q.filter(Content.content_type == content_type)
    if sort_by == "title":
        q = q.order_by(Content.content_title)
    else:
        q = q.order_by(desc(Favorite.created_at))
    return [{"favorite_id": f.favorite_id, "content_id": f.content.content_id,
             "content_title": f.content.content_title, "content_type": f.content.content_type,
             "content_image": f.content.content_image, "content_artist": f.content.content_artist,
             "notes": f.notes, "created_at": f.created_at} for f in q.offset(skip).limit(limit).all()]

@router.post("/favorites/{content_id}")
async def add_favorite(content_id: int, notes: Optional[str] = None,
                       db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    if not db.query(Content).filter(Content.content_id == content_id).first():
        raise HTTPException(404, "Contenu non trouvé")
    if db.query(Favorite).filter(Favorite.user_id == current_user.user_id, Favorite.content_id == content_id).first():
        raise HTTPException(400, "Déjà en favori")
    db.add(Favorite(user_id=current_user.user_id, content_id=content_id, notes=notes))
    db.add(UserActivity(user_id=current_user.user_id, activity_type="favorite", content_id=content_id, metadata={"action": "add"}))
    db.commit()
    return {"message": "Ajouté aux favoris"}

@router.delete("/favorites/{content_id}")
async def remove_favorite(content_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    fav = db.query(Favorite).filter(Favorite.user_id == current_user.user_id, Favorite.content_id == content_id).first()
    if not fav:
        raise HTTPException(404, "Favori non trouvé")
    db.delete(fav)
    db.add(UserActivity(user_id=current_user.user_id, activity_type="favorite", content_id=content_id, metadata={"action": "remove"}))
    db.commit()
    return {"message": "Retiré des favoris"}

@router.get("/favorites/check/{content_id}")
async def check_favorite(content_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    exists = db.query(Favorite).filter(Favorite.user_id == current_user.user_id, Favorite.content_id == content_id).first()
    return {"is_favorite": exists is not None}

@router.get("/playlists")
async def get_playlists(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    playlists = db.query(Playlist).filter(Playlist.user_id == current_user.user_id).order_by(desc(Playlist.created_at)).all()
    return [{"playlist_id": p.playlist_id, "playlist_name": p.playlist_name,
             "playlist_description": p.playlist_description, "playlist_image": p.playlist_image,
             "content_count": len(p.contents), "created_at": p.created_at, "updated_at": p.updated_at} for p in playlists]

@router.post("/playlists", status_code=201)
async def create_playlist(data: PlaylistCreate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    p = Playlist(playlist_name=data.playlist_name, playlist_description=data.playlist_description,
                 user_id=current_user.user_id, content_count=0)
    db.add(p); db.commit(); db.refresh(p)
    return {"playlist_id": p.playlist_id, "playlist_name": p.playlist_name,
            "content_count": 0, "created_at": p.created_at, "updated_at": p.updated_at}

@router.get("/playlists/{playlist_id}")
async def get_playlist(playlist_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    p = db.query(Playlist).filter(Playlist.playlist_id == playlist_id, Playlist.user_id == current_user.user_id).first()
    if not p:
        raise HTTPException(404, "Playlist non trouvée")
    return {"playlist_id": p.playlist_id, "playlist_name": p.playlist_name,
            "playlist_description": p.playlist_description, "content_count": len(p.contents),
            "contents": [{"content_id": c.content_id, "title": c.content_title,
                          "type": c.content_type, "image": c.content_image} for c in p.contents]}

@router.delete("/playlists/{playlist_id}")
async def delete_playlist(playlist_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    p = db.query(Playlist).filter(Playlist.playlist_id == playlist_id, Playlist.user_id == current_user.user_id).first()
    if not p:
        raise HTTPException(404, "Playlist non trouvée")
    db.delete(p); db.commit()
    return {"message": "Playlist supprimée"}

@router.post("/playlists/{playlist_id}/add")
async def add_to_playlist(playlist_id: int, req: AddToPlaylistRequest,
                          db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    p = db.query(Playlist).filter(Playlist.playlist_id == playlist_id, Playlist.user_id == current_user.user_id).first()
    if not p:
        raise HTTPException(404, "Playlist non trouvée")
    c = db.query(Content).filter(Content.content_id == req.content_id).first()
    if not c:
        raise HTTPException(404, "Contenu non trouvé")
    if c in p.contents:
        raise HTTPException(400, "Déjà dans la playlist")
    p.contents.append(c); p.content_count = len(p.contents); db.commit()
    return {"message": "Ajouté à la playlist"}

@router.delete("/playlists/{playlist_id}/remove/{content_id}")
async def remove_from_playlist(playlist_id: int, content_id: int,
                               db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    p = db.query(Playlist).filter(Playlist.playlist_id == playlist_id, Playlist.user_id == current_user.user_id).first()
    if not p:
        raise HTTPException(404, "Playlist non trouvée")
    c = db.query(Content).filter(Content.content_id == content_id).first()
    if not c or c not in p.contents:
        raise HTTPException(404, "Contenu non dans la playlist")
    p.contents.remove(c); p.content_count = len(p.contents); db.commit()
    return {"message": "Retiré de la playlist"}

@router.get("/history")
async def get_history(skip: int = 0, limit: int = Query(50, le=100),
                      db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    scans = db.query(Scan).filter(Scan.scan_user == current_user.user_id)\
              .order_by(desc(Scan.scan_date)).offset(skip).limit(limit).all()
    return [{"scan_id": s.scan_id, "scan_type": s.scan_type, "status": s.status,
             "scan_date": s.scan_date, "processing_time": s.processing_time,
             "content": {"title": s.content.content_title, "type": s.content.content_type,
                         "image": s.content.content_image} if s.content else None} for s in scans]

@router.get("/stats")
async def get_stats(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    return {
        "total_scans": db.query(Scan).filter(Scan.scan_user == current_user.user_id).count(),
        "total_favorites": db.query(Favorite).filter(Favorite.user_id == current_user.user_id).count(),
        "total_playlists": db.query(Playlist).filter(Playlist.user_id == current_user.user_id).count(),
    }
