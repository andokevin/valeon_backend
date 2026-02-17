from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import desc, func
from typing import List, Optional
from pydantic import BaseModel, Field
from datetime import datetime

from app.core.database import get_db
from app.models import User, Content, Favorite, Playlist, UserActivity, Scan
from app.models.library import playlist_contents
from app.api.dependencies.auth import get_current_user

router = APIRouter(prefix="/library", tags=["Library"])

# Modèles Pydantic
class FavoriteResponse(BaseModel):
    favorite_id: int
    content_id: int
    content_title: str
    content_type: str
    content_image: Optional[str] = None
    content_artist: Optional[str] = None
    content_release_date: Optional[str] = None
    notes: Optional[str] = None
    created_at: datetime
    
    class Config:
        from_attributes = True

class PlaylistCreate(BaseModel):
    playlist_name: str = Field(..., min_length=1, max_length=100)
    playlist_description: Optional[str] = Field(None, max_length=500)
    is_public: bool = False
    is_collaborative: bool = False

class PlaylistUpdate(BaseModel):
    playlist_name: Optional[str] = Field(None, min_length=1, max_length=100)
    playlist_description: Optional[str] = Field(None, max_length=500)
    playlist_image: Optional[str] = None
    is_public: Optional[bool] = None
    is_collaborative: Optional[bool] = None

class PlaylistResponse(BaseModel):
    playlist_id: int
    playlist_name: str
    playlist_description: Optional[str] = None
    playlist_image: Optional[str] = None
    is_public: bool
    is_collaborative: bool
    content_count: int
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True

class PlaylistDetailResponse(PlaylistResponse):
    contents: List[dict] = []

class AddToPlaylistRequest(BaseModel):
    content_id: int
    order: Optional[int] = None

class UpdatePlaylistOrderRequest(BaseModel):
    content_ids: List[int]

class ActivityResponse(BaseModel):
    activity_id: int
    activity_type: str
    content_id: Optional[int]
    content_title: Optional[str]
    metadata: Optional[dict]
    created_at: datetime

class StatsResponse(BaseModel):
    total_scans: int
    total_favorites: int
    total_playlists: int
    favorite_categories: dict
    recent_activity: List[ActivityResponse]

# Endpoints Favoris
@router.get("/favorites", response_model=List[FavoriteResponse])
async def get_favorites(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    content_type: Optional[str] = Query(None, regex="^(music|movie|tv_show|image)$"),
    sort_by: str = Query("recent", regex="^(recent|title|artist)$")
):
    """
    Récupérer tous les favoris de l'utilisateur
    """
    query = db.query(Favorite)\
        .filter(Favorite.user_id == current_user.user_id)\
        .join(Content)
    
    if content_type:
        query = query.filter(Content.content_type == content_type)
    
    if sort_by == "recent":
        query = query.order_by(desc(Favorite.created_at))
    elif sort_by == "title":
        query = query.order_by(Content.content_title)
    elif sort_by == "artist":
        query = query.order_by(Content.content_artist)
    
    favorites = query.offset(skip).limit(limit).all()
    
    result = []
    for fav in favorites:
        result.append({
            "favorite_id": fav.favorite_id,
            "content_id": fav.content.content_id,
            "content_title": fav.content.content_title,
            "content_type": fav.content.content_type,
            "content_image": fav.content.content_image,
            "content_artist": fav.content.content_artist,
            "content_release_date": fav.content.content_release_date,
            "notes": fav.notes,
            "created_at": fav.created_at
        })
    
    return result

@router.post("/favorites/{content_id}")
async def add_to_favorites(
    content_id: int,
    notes: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Ajouter un contenu aux favoris
    """
    # Vérifier si le contenu existe
    content = db.query(Content).filter(Content.content_id == content_id).first()
    if not content:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Contenu non trouvé"
        )
    
    # Vérifier si déjà en favori
    existing = db.query(Favorite)\
        .filter(
            Favorite.user_id == current_user.user_id,
            Favorite.content_id == content_id
        ).first()
    
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Contenu déjà dans les favoris"
        )
    
    # Ajouter aux favoris
    favorite = Favorite(
        user_id=current_user.user_id,
        content_id=content_id,
        notes=notes
    )
    db.add(favorite)
    
    # Enregistrer l'activité
    activity = UserActivity(
        user_id=current_user.user_id,
        activity_type="favorite",
        content_id=content_id,
        metadata={"action": "add"}
    )
    db.add(activity)
    
    db.commit()
    
    return {"message": "Contenu ajouté aux favoris"}

@router.put("/favorites/{content_id}")
async def update_favorite_notes(
    content_id: int,
    notes: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Mettre à jour les notes d'un favori
    """
    favorite = db.query(Favorite)\
        .filter(
            Favorite.user_id == current_user.user_id,
            Favorite.content_id == content_id
        ).first()
    
    if not favorite:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Favori non trouvé"
        )
    
    favorite.notes = notes
    db.commit()
    
    return {"message": "Notes mises à jour"}

@router.delete("/favorites/{content_id}")
async def remove_from_favorites(
    content_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Retirer un contenu des favoris
    """
    favorite = db.query(Favorite)\
        .filter(
            Favorite.user_id == current_user.user_id,
            Favorite.content_id == content_id
        ).first()
    
    if not favorite:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Contenu non trouvé dans les favoris"
        )
    
    db.delete(favorite)
    
    # Enregistrer l'activité
    activity = UserActivity(
        user_id=current_user.user_id,
        activity_type="favorite",
        content_id=content_id,
        metadata={"action": "remove"}
    )
    db.add(activity)
    
    db.commit()
    
    return {"message": "Contenu retiré des favoris"}

@router.get("/favorites/check/{content_id}")
async def check_favorite(
    content_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Vérifier si un contenu est en favori
    """
    favorite = db.query(Favorite)\
        .filter(
            Favorite.user_id == current_user.user_id,
            Favorite.content_id == content_id
        ).first()
    
    return {"is_favorite": favorite is not None}

# Endpoints Playlists
@router.get("/playlists", response_model=List[PlaylistResponse])
async def get_playlists(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    include_public: bool = True
):
    """
    Récupérer toutes les playlists de l'utilisateur
    """
    query = db.query(Playlist)\
        .filter(Playlist.user_id == current_user.user_id)
    
    if include_public:
        # Inclure aussi les playlists publiques d'autres utilisateurs
        public_playlists = db.query(Playlist)\
            .filter(Playlist.is_public == True)\
            .filter(Playlist.user_id != current_user.user_id)
        query = query.union(public_playlists)
    
    playlists = query.order_by(desc(Playlist.created_at)).all()
    
    result = []
    for playlist in playlists:
        content_count = len(playlist.contents)
        result.append({
            "playlist_id": playlist.playlist_id,
            "playlist_name": playlist.playlist_name,
            "playlist_description": playlist.playlist_description,
            "playlist_image": playlist.playlist_image,
            "is_public": playlist.is_public,
            "is_collaborative": playlist.is_collaborative,
            "content_count": content_count,
            "created_at": playlist.created_at,
            "updated_at": playlist.updated_at
        })
    
    return result

@router.post("/playlists", response_model=PlaylistResponse, status_code=status.HTTP_201_CREATED)
async def create_playlist(
    playlist_data: PlaylistCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Créer une nouvelle playlist
    """
    playlist = Playlist(
        playlist_name=playlist_data.playlist_name,
        playlist_description=playlist_data.playlist_description,
        is_public=playlist_data.is_public,
        is_collaborative=playlist_data.is_collaborative,
        user_id=current_user.user_id
    )
    
    db.add(playlist)
    db.commit()
    db.refresh(playlist)
    
    # Enregistrer l'activité
    activity = UserActivity(
        user_id=current_user.user_id,
        activity_type="playlist_create",
        metadata={"playlist_id": playlist.playlist_id, "name": playlist.playlist_name}
    )
    db.add(activity)
    db.commit()
    
    return {
        "playlist_id": playlist.playlist_id,
        "playlist_name": playlist.playlist_name,
        "playlist_description": playlist.playlist_description,
        "playlist_image": playlist.playlist_image,
        "is_public": playlist.is_public,
        "is_collaborative": playlist.is_collaborative,
        "content_count": 0,
        "created_at": playlist.created_at,
        "updated_at": playlist.updated_at
    }

@router.get("/playlists/{playlist_id}", response_model=PlaylistDetailResponse)
async def get_playlist(
    playlist_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Récupérer les détails d'une playlist avec son contenu
    """
    playlist = db.query(Playlist)\
        .filter(
            (Playlist.playlist_id == playlist_id) &
            ((Playlist.user_id == current_user.user_id) | (Playlist.is_public == True))
        ).first()
    
    if not playlist:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Playlist non trouvée"
        )
    
    contents = []
    for content in playlist.contents:
        contents.append({
            "content_id": content.content_id,
            "title": content.content_title,
            "type": content.content_type,
            "image": content.content_image,
            "artist": content.content_artist,
            "description": content.content_description,
            "release_date": content.content_release_date
        })
    
    return {
        "playlist_id": playlist.playlist_id,
        "playlist_name": playlist.playlist_name,
        "playlist_description": playlist.playlist_description,
        "playlist_image": playlist.playlist_image,
        "is_public": playlist.is_public,
        "is_collaborative": playlist.is_collaborative,
        "content_count": len(contents),
        "created_at": playlist.created_at,
        "updated_at": playlist.updated_at,
        "contents": contents
    }

@router.put("/playlists/{playlist_id}", response_model=PlaylistResponse)
async def update_playlist(
    playlist_id: int,
    playlist_data: PlaylistUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Mettre à jour une playlist
    """
    playlist = db.query(Playlist)\
        .filter(
            Playlist.playlist_id == playlist_id,
            Playlist.user_id == current_user.user_id
        ).first()
    
    if not playlist:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Playlist non trouvée"
        )
    
    if playlist_data.playlist_name is not None:
        playlist.playlist_name = playlist_data.playlist_name
    if playlist_data.playlist_description is not None:
        playlist.playlist_description = playlist_data.playlist_description
    if playlist_data.playlist_image is not None:
        playlist.playlist_image = playlist_data.playlist_image
    if playlist_data.is_public is not None:
        playlist.is_public = playlist_data.is_public
    if playlist_data.is_collaborative is not None:
        playlist.is_collaborative = playlist_data.is_collaborative
    
    db.commit()
    db.refresh(playlist)
    
    return {
        "playlist_id": playlist.playlist_id,
        "playlist_name": playlist.playlist_name,
        "playlist_description": playlist.playlist_description,
        "playlist_image": playlist.playlist_image,
        "is_public": playlist.is_public,
        "is_collaborative": playlist.is_collaborative,
        "content_count": len(playlist.contents),
        "created_at": playlist.created_at,
        "updated_at": playlist.updated_at
    }

@router.post("/playlists/{playlist_id}/add")
async def add_to_playlist(
    playlist_id: int,
    request: AddToPlaylistRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Ajouter un contenu à une playlist
    """
    # Vérifier la playlist
    playlist = db.query(Playlist)\
        .filter(
            Playlist.playlist_id == playlist_id,
            (Playlist.user_id == current_user.user_id) | (Playlist.is_collaborative == True)
        ).first()
    
    if not playlist:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Playlist non trouvée ou vous n'avez pas les droits"
        )
    
    # Vérifier le contenu
    content = db.query(Content).filter(Content.content_id == request.content_id).first()
    if not content:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Contenu non trouvé"
        )
    
    # Vérifier si déjà dans la playlist
    if content in playlist.contents:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Contenu déjà dans la playlist"
        )
    
    # Ajouter à la playlist avec l'ordre spécifié
    if request.order is not None:
        # Mettre à jour l'ordre
        stmt = playlist_contents.insert().values(
            playlist_id=playlist_id,
            content_id=request.content_id,
            order=request.order,
            added_at=datetime.utcnow()
        )
        db.execute(stmt)
    else:
        playlist.contents.append(content)
    
    # Mettre à jour le compteur
    playlist.track_count = len(playlist.contents)
    
    # Enregistrer l'activité
    activity = UserActivity(
        user_id=current_user.user_id,
        activity_type="playlist_add",
        content_id=request.content_id,
        metadata={"playlist_id": playlist_id, "playlist_name": playlist.playlist_name}
    )
    db.add(activity)
    
    db.commit()
    
    return {"message": "Contenu ajouté à la playlist"}

@router.put("/playlists/{playlist_id}/order")
async def update_playlist_order(
    playlist_id: int,
    request: UpdatePlaylistOrderRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Mettre à jour l'ordre des contenus dans une playlist
    """
    playlist = db.query(Playlist)\
        .filter(
            Playlist.playlist_id == playlist_id,
            Playlist.user_id == current_user.user_id
        ).first()
    
    if not playlist:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Playlist non trouvée"
        )
    
    # Mettre à jour l'ordre pour chaque contenu
    for index, content_id in enumerate(request.content_ids):
        stmt = playlist_contents.update().\
            where(
                playlist_contents.c.playlist_id == playlist_id,
                playlist_contents.c.content_id == content_id
            ).\
            values(order=index)
        db.execute(stmt)
    
    db.commit()
    
    return {"message": "Ordre mis à jour"}

@router.delete("/playlists/{playlist_id}/remove/{content_id}")
async def remove_from_playlist(
    playlist_id: int,
    content_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Retirer un contenu d'une playlist
    """
    playlist = db.query(Playlist)\
        .filter(
            Playlist.playlist_id == playlist_id,
            (Playlist.user_id == current_user.user_id) | (Playlist.is_collaborative == True)
        ).first()
    
    if not playlist:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Playlist non trouvée"
        )
    
    content = db.query(Content).filter(Content.content_id == content_id).first()
    if not content:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Contenu non trouvé"
        )
    
    if content not in playlist.contents:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Contenu non trouvé dans la playlist"
        )
    
    playlist.contents.remove(content)
    playlist.track_count = len(playlist.contents)
    
    db.commit()
    
    return {"message": "Contenu retiré de la playlist"}

@router.delete("/playlists/{playlist_id}")
async def delete_playlist(
    playlist_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Supprimer une playlist
    """
    playlist = db.query(Playlist)\
        .filter(
            Playlist.playlist_id == playlist_id,
            Playlist.user_id == current_user.user_id
        ).first()
    
    if not playlist:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Playlist non trouvée"
        )
    
    db.delete(playlist)
    db.commit()
    
    return {"message": "Playlist supprimée"}

# Endpoints Activité et Statistiques
@router.get("/activity", response_model=List[ActivityResponse])
async def get_user_activity(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    activity_type: Optional[str] = Query(None, regex="^(scan|favorite|share|playlist_add|playlist_create)$")
):
    """
    Récupérer l'activité récente de l'utilisateur
    """
    query = db.query(UserActivity)\
        .filter(UserActivity.user_id == current_user.user_id)\
        .order_by(desc(UserActivity.created_at))
    
    if activity_type:
        query = query.filter(UserActivity.activity_type == activity_type)
    
    activities = query.offset(skip).limit(limit).all()
    
    result = []
    for activity in activities:
        content_title = None
        if activity.content:
            content_title = activity.content.content_title
        
        result.append({
            "activity_id": activity.activity_id,
            "activity_type": activity.activity_type,
            "content_id": activity.content_id,
            "content_title": content_title,
            "metadata": activity.metadata,
            "created_at": activity.created_at
        })
    
    return result

@router.get("/stats", response_model=StatsResponse)
async def get_user_stats(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Récupérer les statistiques de l'utilisateur
    """
    # Total des scans
    total_scans = db.query(Scan)\
        .filter(Scan.scan_user == current_user.user_id)\
        .count()
    
    # Total des favoris
    total_favorites = db.query(Favorite)\
        .filter(Favorite.user_id == current_user.user_id)\
        .count()
    
    # Total des playlists
    total_playlists = db.query(Playlist)\
        .filter(Playlist.user_id == current_user.user_id)\
        .count()
    
    # Favoris par catégorie
    favorite_categories = db.query(
        Content.content_type,
        func.count(Favorite.favorite_id).label('count')
    ).join(Favorite)\
     .filter(Favorite.user_id == current_user.user_id)\
     .group_by(Content.content_type)\
     .all()
    
    favorites_by_type = {cat: count for cat, count in favorite_categories}
    
    # Activité récente
    recent_activities = db.query(UserActivity)\
        .filter(UserActivity.user_id == current_user.user_id)\
        .order_by(desc(UserActivity.created_at))\
        .limit(10)\
        .all()
    
    activities = []
    for activity in recent_activities:
        content_title = None
        if activity.content:
            content_title = activity.content.content_title
        
        activities.append({
            "activity_id": activity.activity_id,
            "activity_type": activity.activity_type,
            "content_id": activity.content_id,
            "content_title": content_title,
            "metadata": activity.metadata,
            "created_at": activity.created_at
        })
    
    return {
        "total_scans": total_scans,
        "total_favorites": total_favorites,
        "total_playlists": total_playlists,
        "favorite_categories": favorites_by_type,
        "recent_activity": activities
    }

@router.get("/history", response_model=List[dict])
async def get_scan_history(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100)
):
    """
    Récupérer l'historique des scans
    """
    scans = db.query(Scan)\
        .filter(Scan.scan_user == current_user.user_id)\
        .order_by(desc(Scan.scan_date))\
        .offset(skip)\
        .limit(limit)\
        .all()
    
    result = []
    for scan in scans:
        scan_data = {
            "scan_id": scan.scan_id,
            "scan_type": scan.scan_type,
            "input_source": scan.input_source,
            "status": scan.status,
            "scan_date": scan.scan_date,
            "processing_time": scan.processing_time
        }
        
        if scan.content:
            scan_data["content"] = {
                "content_id": scan.content.content_id,
                "title": scan.content.content_title,
                "type": scan.content.content_type,
                "artist": scan.content.content_artist,
                "image": scan.content.content_image
            }
        
        result.append(scan_data)
    
    return result