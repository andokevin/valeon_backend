from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from datetime import timedelta, datetime
from pydantic import BaseModel, EmailStr, Field
from typing import Optional
import secrets, string

from app.core.database import get_db
from app.core.config import settings
from app.core.security import verify_password, get_password_hash, create_access_token, create_refresh_token
from app.api.dependencies.auth import get_current_user, verify_refresh_token
from app.models import User, Subscription, UserPassword

router = APIRouter(prefix="/auth", tags=["Authentication"])

class UserCreate(BaseModel):
    user_full_name: str = Field(..., min_length=2, max_length=100)
    user_email: EmailStr
    password: str = Field(..., min_length=8)
    accept_terms: bool

class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int
    user_id: int
    user_email: str
    user_full_name: str
    subscription: str
    is_premium: bool

class UserResponse(BaseModel):
    user_id: int
    user_full_name: str
    user_email: str
    user_image: Optional[str]
    subscription: str
    is_premium: bool
    is_active: bool
    preferences: Optional[dict]
    created_at: datetime

class PasswordChange(BaseModel):
    current_password: str
    new_password: str = Field(..., min_length=8)
    confirm_password: str

class RefreshTokenRequest(BaseModel):
    refresh_token: str

class UpdateProfileRequest(BaseModel):
    user_full_name: Optional[str] = Field(None, min_length=2, max_length=100)
    preferences: Optional[dict] = None

def _token_response(user: User, db: Session, refresh_token: Optional[str] = None) -> dict:
    sub = db.query(Subscription).filter(Subscription.subscription_id == user.user_subscription_id).first()
    sub_name = sub.subscription_name if sub else "Free"
    is_premium = sub.is_premium if sub else False
    access = create_access_token(data={"sub": str(user.user_id)})
    rt = refresh_token or create_refresh_token(data={"sub": str(user.user_id)})
    return {
        "access_token": access, "refresh_token": rt,
        "token_type": "bearer",
        "expires_in": settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        "user_id": user.user_id, "user_email": user.user_email,
        "user_full_name": user.user_full_name,
        "subscription": sub_name, "is_premium": is_premium,
    }

@router.post("/register", response_model=TokenResponse, status_code=201)
async def register(data: UserCreate, db: Session = Depends(get_db)):
    if not data.accept_terms:
        raise HTTPException(400, "Vous devez accepter les conditions")
    
    if db.query(User).filter(User.user_email == data.user_email).first():
        raise HTTPException(400, "Email déjà utilisé")
    
    if not any(c.isupper() for c in data.password) or not any(c.isdigit() for c in data.password):
        raise HTTPException(400, "Mot de passe trop faible (majuscule + chiffre requis)")
    
    # RECHERCHER L'ABONNEMENT FREE
    free_sub = db.query(Subscription).filter(Subscription.subscription_name == "Free").first()
    
    # SI L'ABONNEMENT FREE N'EXISTE PAS, LE CRÉER AUTOMATIQUEMENT
    if not free_sub:
        print("⚠️  Abonnement 'Free' non trouvé - Création automatique...")
        free_sub = Subscription(
            subscription_name="Free",
            subscription_price=0.0,
            subscription_duration=None,  # Illimité
            max_scans_per_day=5,
            max_scans_per_month=50,
            is_premium=False,
            created_at=datetime.utcnow()
        )
        db.add(free_sub)
        db.flush()  # Pour obtenir l'ID sans commit final
        print(f"✅ Abonnement 'Free' créé avec l'ID: {free_sub.subscription_id}")
    
    # CRÉATION DE L'UTILISATEUR
    user = User(
        user_full_name=data.user_full_name, 
        user_email=data.user_email,
        user_subscription_id=free_sub.subscription_id,  # Maintenant sûr
        is_active=True,
        preferences={"language": "fr", "notifications": True},
    )
    
    db.add(user)
    db.flush()
    
    # AJOUT DU MOT DE PASSE
    db.add(UserPassword(
        user_id=user.user_id, 
        password_hash=get_password_hash(data.password)
    ))
    
    db.commit()
    db.refresh(user)
    
    return _token_response(user, db)

@router.post("/login", response_model=TokenResponse)
async def login(form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.user_email == form.username).first()
    if not user:
        raise HTTPException(401, "Email ou mot de passe incorrect", headers={"WWW-Authenticate": "Bearer"})
    if not user.is_active:
        raise HTTPException(403, "Compte désactivé")
    up = db.query(UserPassword).filter(UserPassword.user_id == user.user_id).first()
    if not up or not verify_password(form.password, up.password_hash):
        if up:
            up.login_attempts += 1
            if up.login_attempts >= 5:
                up.locked_until = datetime.utcnow() + timedelta(minutes=30)
            db.commit()
        raise HTTPException(401, "Email ou mot de passe incorrect", headers={"WWW-Authenticate": "Bearer"})
    if up.locked_until and up.locked_until > datetime.utcnow():
        raise HTTPException(403, f"Compte verrouillé jusqu'à {up.locked_until}")
    up.login_attempts = 0; up.locked_until = None; up.last_login = datetime.utcnow()
    db.commit()
    return _token_response(user, db)

@router.get("/me", response_model=UserResponse)
async def me(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    sub = db.query(Subscription).filter(Subscription.subscription_id == current_user.user_subscription_id).first()
    return {**current_user.__dict__, "subscription": sub.subscription_name if sub else "Free", "is_premium": sub.is_premium if sub else False}

@router.put("/me", response_model=UserResponse)
async def update_me(data: UpdateProfileRequest, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if data.user_full_name:
        current_user.user_full_name = data.user_full_name
    if data.preferences:
        current_user.preferences = {**(current_user.preferences or {}), **data.preferences}
    db.commit(); db.refresh(current_user)
    sub = db.query(Subscription).filter(Subscription.subscription_id == current_user.user_subscription_id).first()
    return {**current_user.__dict__, "subscription": sub.subscription_name if sub else "Free", "is_premium": sub.is_premium if sub else False}

@router.post("/refresh-token", response_model=TokenResponse)
async def refresh(req: RefreshTokenRequest, db: Session = Depends(get_db)):
    payload = verify_refresh_token(req.refresh_token)
    if not payload:
        raise HTTPException(401, "Token de rafraîchissement invalide")
    user = db.query(User).filter(User.user_id == int(payload["sub"])).first()
    if not user or not user.is_active:
        raise HTTPException(401, "Utilisateur inactif")
    return _token_response(user, db, refresh_token=req.refresh_token)

@router.post("/logout")
async def logout(current_user: User = Depends(get_current_user)):
    return {"message": "Déconnexion réussie"}

@router.post("/change-password")
async def change_password(data: PasswordChange, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if data.new_password != data.confirm_password:
        raise HTTPException(400, "Les mots de passe ne correspondent pas")
    up = db.query(UserPassword).filter(UserPassword.user_id == current_user.user_id).first()
    if not up or not verify_password(data.current_password, up.password_hash):
        raise HTTPException(400, "Mot de passe actuel incorrect")
    up.password_hash = get_password_hash(data.new_password)
    db.commit()
    return {"message": "Mot de passe changé"}


# ===== ENDPOINTS POUR LA SYNCHRONISATION =====

@router.post("/users/sync")
async def sync_user(
    data: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Synchronise les données utilisateur depuis l'application mobile.
    Utile pour le mode hors ligne et la synchronisation des préférences.
    """
    try:
        # Mettre à jour le nom si fourni
        if "user_full_name" in data and data["user_full_name"]:
            current_user.user_full_name = data["user_full_name"]
        
        # Mettre à jour l'image si fournie
        if "user_image" in data and data["user_image"]:
            current_user.user_image = data["user_image"]
        
        # Mettre à jour les préférences si fournies
        if "preferences" in data and data["preferences"]:
            # Fusionner avec les préférences existantes
            current_user.preferences = {
                **(current_user.preferences or {}),
                **data["preferences"]
            }
        
        # Mettre à jour la date de modification
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


@router.post("/sync")
async def sync_user_alias(
    data: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Alias pour /users/sync - Endpoint simplifié pour la compatibilité.
    """
    return await sync_user(data, db, current_user)


@router.post("/users/sync-all")
async def sync_all_user_data(
    data: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Synchronise toutes les données utilisateur (préférences, paramètres, etc.)
    Version plus complète pour la synchronisation initiale.
    """
    try:
        update_fields = {}
        
        # Champs autorisés à la mise à jour
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