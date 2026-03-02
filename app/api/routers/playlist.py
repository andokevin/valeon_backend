# app/api/routers/playlists.py (à créer - extrait de library.py amélioré)
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from sqlalchemy import desc
from typing import List, Optional
from pydantic import BaseModel, Field
from datetime import datetime

from app.core.database import get_db
from app.api.dependencies.auth import get_current_user
from app.models import User, Playlist, Content, playlist_contents

router = APIRouter(prefix="/playlists", tags=["Playlists"])

class PlaylistCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = None
    is_public: bool = False

class PlaylistUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    image: Optional[str] = None
    is_public: Optional[bool] = None

class PlaylistItem(BaseModel):
    playlist_id: int
    name: str
    description: Optional[str]
    image: Optional[str]
    content_count: int
    is_public: bool
    created_at: datetime
    updated_at: datetime

class PlaylistDetail(PlaylistItem):
    contents: List[dict]

class AddContentRequest(BaseModel):
    content_id: int
    position: Optional[int] = None

@router.get("/", response_model=List[PlaylistItem])
async def get_playlists(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Récupère toutes les playlists de l'utilisateur"""
    playlists = db.query(Playlist).filter(
        Playlist.user_id == current_user.user_id
    ).order_by(desc(Playlist.created_at)).all()
    
    return [{
        "playlist_id": p.playlist_id,
        "name": p.playlist_name,
        "description": p.playlist_description,
        "image": p.playlist_image,
        "content_count": len(p.contents),
        "is_public": p.is_public,
        "created_at": p.created_at,
        "updated_at": p.updated_at
    } for p in playlists]

@router.post("/", status_code=201, response_model=PlaylistItem)
async def create_playlist(
    data: PlaylistCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Crée une nouvelle playlist"""
    playlist = Playlist(
        playlist_name=data.name,
        playlist_description=data.description,
        playlist_image=None,
        user_id=current_user.user_id,
        is_public=data.is_public,
        is_collaborative=False,
        content_count=0,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow()
    )
    db.add(playlist)
    db.commit()
    db.refresh(playlist)
    
    return {
        "playlist_id": playlist.playlist_id,
        "name": playlist.playlist_name,
        "description": playlist.playlist_description,
        "image": playlist.playlist_image,
        "content_count": 0,
        "is_public": playlist.is_public,
        "created_at": playlist.created_at,
        "updated_at": playlist.updated_at
    }

@router.get("/{playlist_id}", response_model=PlaylistDetail)
async def get_playlist(
    playlist_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Récupère une playlist avec son contenu"""
    playlist = db.query(Playlist).filter(
        Playlist.playlist_id == playlist_id,
        Playlist.user_id == current_user.user_id
    ).first()
    
    if not playlist:
        raise HTTPException(404, "Playlist non trouvée")
    
    contents = []
    for content in playlist.contents:
        contents.append({
            "content_id": content.content_id,
            "title": content.content_title,
            "type": content.content_type,
            "artist": content.content_artist,
            "image": content.content_image,
            "duration": content.content_duration,
            "year": content.content_release_date[:4] if content.content_release_date else None
        })
    
    return {
        "playlist_id": playlist.playlist_id,
        "name": playlist.playlist_name,
        "description": playlist.playlist_description,
        "image": playlist.playlist_image,
        "content_count": len(contents),
        "is_public": playlist.is_public,
        "created_at": playlist.created_at,
        "updated_at": playlist.updated_at,
        "contents": contents
    }

@router.put("/{playlist_id}", response_model=PlaylistItem)
async def update_playlist(
    playlist_id: int,
    data: PlaylistUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Met à jour une playlist"""
    playlist = db.query(Playlist).filter(
        Playlist.playlist_id == playlist_id,
        Playlist.user_id == current_user.user_id
    ).first()
    
    if not playlist:
        raise HTTPException(404, "Playlist non trouvée")
    
    if data.name is not None:
        playlist.playlist_name = data.name
    if data.description is not None:
        playlist.playlist_description = data.description
    if data.image is not None:
        playlist.playlist_image = data.image
    if data.is_public is not None:
        playlist.is_public = data.is_public
    
    playlist.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(playlist)
    
    return {
        "playlist_id": playlist.playlist_id,
        "name": playlist.playlist_name,
        "description": playlist.playlist_description,
        "image": playlist.playlist_image,
        "content_count": len(playlist.contents),
        "is_public": playlist.is_public,
        "created_at": playlist.created_at,
        "updated_at": playlist.updated_at
    }

@router.delete("/{playlist_id}")
async def delete_playlist(
    playlist_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Supprime une playlist"""
    playlist = db.query(Playlist).filter(
        Playlist.playlist_id == playlist_id,
        Playlist.user_id == current_user.user_id
    ).first()
    
    if not playlist:
        raise HTTPException(404, "Playlist non trouvée")
    
    db.delete(playlist)
    db.commit()
    
    return {"message": "Playlist supprimée"}

@router.post("/{playlist_id}/items")
async def add_to_playlist(
    playlist_id: int,
    data: AddContentRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Ajoute un contenu à la playlist"""
    playlist = db.query(Playlist).filter(
        Playlist.playlist_id == playlist_id,
        Playlist.user_id == current_user.user_id
    ).first()
    
    if not playlist:
        raise HTTPException(404, "Playlist non trouvée")
    
    content = db.query(Content).filter(
        Content.content_id == data.content_id
    ).first()
    
    if not content:
        raise HTTPException(404, "Contenu non trouvé")
    
    # Vérifier si déjà présent
    stmt = playlist_contents.select().where(
        playlist_contents.c.playlist_id == playlist_id,
        playlist_contents.c.content_id == data.content_id
    )
    existing = db.execute(stmt).first()
    
    if existing:
        raise HTTPException(400, "Contenu déjà dans la playlist")
    
    # Ajouter
    ins = playlist_contents.insert().values(
        playlist_id=playlist_id,
        content_id=data.content_id,
        added_at=datetime.utcnow(),
        position=data.position or 0
    )
    db.execute(ins)
    
    # Mettre à jour le compteur
    playlist.content_count = len(playlist.contents) + 1
    playlist.updated_at = datetime.utcnow()
    db.commit()
    
    return {"message": "Contenu ajouté à la playlist"}

@router.delete("/{playlist_id}/items/{content_id}")
async def remove_from_playlist(
    playlist_id: int,
    content_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Retire un contenu de la playlist"""
    playlist = db.query(Playlist).filter(
        Playlist.playlist_id == playlist_id,
        Playlist.user_id == current_user.user_id
    ).first()
    
    if not playlist:
        raise HTTPException(404, "Playlist non trouvée")
    
    # Vérifier si présent
    stmt = playlist_contents.select().where(
        playlist_contents.c.playlist_id == playlist_id,
        playlist_contents.c.content_id == content_id
    )
    existing = db.execute(stmt).first()
    
    if not existing:
        raise HTTPException(404, "Contenu non trouvé dans la playlist")
    
    # Supprimer
    delete_stmt = playlist_contents.delete().where(
        playlist_contents.c.playlist_id == playlist_id,
        playlist_contents.c.content_id == content_id
    )
    db.execute(delete_stmt)
    
    # Mettre à jour le compteur
    playlist.content_count = max(0, len(playlist.contents) - 1)
    playlist.updated_at = datetime.utcnow()
    db.commit()
    
    return {"message": "Contenu retiré de la playlist"}

@router.put("/{playlist_id}/items/reorder")
async def reorder_playlist(
    playlist_id: int,
    content_ids: List[int],
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Réordonne les éléments de la playlist"""
    playlist = db.query(Playlist).filter(
        Playlist.playlist_id == playlist_id,
        Playlist.user_id == current_user.user_id
    ).first()
    
    if not playlist:
        raise HTTPException(404, "Playlist non trouvée")
    
    # Supprimer toutes les associations
    delete_stmt = playlist_contents.delete().where(
        playlist_contents.c.playlist_id == playlist_id
    )
    db.execute(delete_stmt)
    
    # Réinsérer dans le nouvel ordre
    for position, content_id in enumerate(content_ids):
        ins = playlist_contents.insert().values(
            playlist_id=playlist_id,
            content_id=content_id,
            added_at=datetime.utcnow(),
            position=position
        )
        db.execute(ins)
    
    playlist.updated_at = datetime.utcnow()
    db.commit()
    
    return {"message": "Playlist réordonnée"}