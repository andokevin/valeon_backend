# app/api/routers/users.py
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from datetime import datetime
from typing import Optional, Dict, Any

from app.core.database import get_db
from app.api.dependencies.auth import get_current_user
from app.models import User

router = APIRouter(prefix="/users", tags=["Users"])

@router.post("/sync")
async def sync_user(
    data: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Synchronise les données utilisateur depuis l'application mobile.
    """
    try:
        if "user_full_name" in data and data["user_full_name"]:
            current_user.user_full_name = data["user_full_name"]
        
        if "user_image" in data and data["user_image"]:
            current_user.user_image = data["user_image"]
        
        if "preferences" in data and data["preferences"]:
            current_user.preferences = {
                **(current_user.preferences or {}),
                **data["preferences"]
            }
        
        current_user.updated_at = datetime.utcnow()
        db.commit()
        
        return {
            "message": "Utilisateur synchronisé avec succès",
            "status": "success",
            "user_id": current_user.user_id,
            "updated_at": current_user.updated_at.isoformat()
        }
        
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=400,
            detail=f"Erreur lors de la synchronisation: {str(e)}"
        )

@router.post("/sync-all")
async def sync_all_user_data(
    data: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Synchronise toutes les données utilisateur.
    """
    try:
        update_fields = {}
        allowed_fields = ["user_full_name", "user_image", "preferences"]
        
        for field in allowed_fields:
            if field in data:
                setattr(current_user, field, data[field])
                update_fields[field] = data[field]
        
        current_user.updated_at = datetime.utcnow()
        db.commit()
        
        return {
            "message": "Données synchronisées",
            "updated_fields": update_fields,
            "timestamp": current_user.updated_at.isoformat()
        }
        
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e))