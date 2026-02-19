from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from datetime import timedelta, datetime
from pydantic import BaseModel, EmailStr, Field
from typing import Optional, List
import secrets
import string

from app.core.database import get_db
from app.core.config import settings
from app.models import User, Subscription
from app.models.user import UserPassword
from app.api.dependencies.auth import (
    create_access_token, 
    create_refresh_token,
    get_current_user,
    verify_password,
    get_password_hash,
    verify_refresh_token
)

router = APIRouter(prefix="/auth", tags=["Authentication"])

# Modèles Pydantic
class UserCreate(BaseModel):
    user_full_name: str = Field(..., min_length=2, max_length=100)
    user_email: EmailStr
    password: str = Field(..., min_length=8, max_length=100)
    accept_terms: bool = Field(..., description="Acceptation des conditions d'utilisation")

class UserLogin(BaseModel):
    user_email: EmailStr
    password: str
    remember_me: bool = False

class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int
    user_id: int
    user_email: str
    user_full_name: str
    subscription: str

class UserResponse(BaseModel):
    user_id: int
    user_full_name: str
    user_email: str
    user_image: Optional[str] = None
    subscription: str
    is_active: bool
    preferences: Optional[dict] = None
    created_at: datetime
    
    class Config:
        from_attributes = True

class PasswordChange(BaseModel):
    current_password: str
    new_password: str = Field(..., min_length=8, max_length=100)
    confirm_password: str

class PasswordResetRequest(BaseModel):
    user_email: EmailStr

class PasswordResetConfirm(BaseModel):
    token: str
    new_password: str = Field(..., min_length=8, max_length=100)
    confirm_password: str

class RefreshTokenRequest(BaseModel):
    refresh_token: str

class UpdateProfileRequest(BaseModel):
    user_full_name: Optional[str] = Field(None, min_length=2, max_length=100)
    preferences: Optional[dict] = None

# Endpoints
@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def register(user_data: UserCreate, db: Session = Depends(get_db)):
    """
    Inscription d'un nouvel utilisateur
    """
    # Vérifier les conditions d'utilisation
    if not user_data.accept_terms:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Vous devez accepter les conditions d'utilisation"
        )
    
    # Vérifier si l'email existe déjà
    existing_user = db.query(User).filter(User.user_email == user_data.user_email).first()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Un compte avec cet email existe déjà"
        )
    
    # Vérifier la complexité du mot de passe
    if not any(c.isupper() for c in user_data.password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Le mot de passe doit contenir au moins une majuscule"
        )
    if not any(c.isdigit() for c in user_data.password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Le mot de passe doit contenir au moins un chiffre"
        )
    
    # Récupérer l'abonnement gratuit par défaut
    free_subscription = db.query(Subscription).filter(
        Subscription.subscription_name == "Free"
    ).first()
    
    if not free_subscription:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Configuration d'abonnement par défaut manquante"
        )
    
    # Créer l'utilisateur
    db_user = User(
        user_full_name=user_data.user_full_name,
        user_email=user_data.user_email,
        user_subscription_id=free_subscription.subscription_id,
        is_active=True,
        preferences={"language": "fr", "notifications": True}
    )
    
    db.add(db_user)
    db.flush()  # Pour obtenir l'ID
    
    # Créer l'entrée de mot de passe
    hashed_password = get_password_hash(user_data.password)
    user_password = UserPassword(
        user_id=db_user.user_id,
        password_hash=hashed_password
    )
    db.add(user_password)
    
    db.commit()
    db.refresh(db_user)
    
    # Créer les tokens
    access_token = create_access_token(
        data={"sub": str(db_user.user_id)},
        expires_delta=timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    
    refresh_token = create_refresh_token(
        data={"sub": str(db_user.user_id)}
    )
    
    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "expires_in": settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        "user_id": db_user.user_id,
        "user_email": db_user.user_email,
        "user_full_name": db_user.user_full_name,
        "subscription": "Free"
    }

@router.post("/login", response_model=TokenResponse)
async def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db)
):
    """
    Connexion utilisateur (compatible OAuth2)
    """
    # Chercher l'utilisateur par email
    user = db.query(User).filter(User.user_email == form_data.username).first()
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Email ou mot de passe incorrect",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Ce compte a été désactivé"
        )
    
    # Vérifier le mot de passe
    user_password = db.query(UserPassword).filter(
        UserPassword.user_id == user.user_id
    ).first()
    
    if not user_password or not verify_password(form_data.password, user_password.password_hash):
        # Incrémenter les tentatives
        if user_password:
            user_password.login_attempts += 1
            
            # Verrouiller après 5 tentatives
            if user_password.login_attempts >= 5:
                user_password.locked_until = datetime.utcnow() + timedelta(minutes=30)
            
            db.commit()
        
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Email ou mot de passe incorrect",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Vérifier si le compte est verrouillé
    if user_password.locked_until and user_password.locked_until > datetime.utcnow():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Compte verrouillé jusqu'à {user_password.locked_until}"
        )
    
    # Réinitialiser les tentatives
    user_password.login_attempts = 0
    user_password.locked_until = None
    user_password.last_login = datetime.utcnow()
    
    # Récupérer le nom de l'abonnement
    subscription = db.query(Subscription).filter(
        Subscription.subscription_id == user.user_subscription_id
    ).first()
    subscription_name = subscription.subscription_name if subscription else "Free"
    
    # Créer les tokens
    access_token = create_access_token(
        data={"sub": str(user.user_id)},
        expires_delta=timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    
    refresh_token = create_refresh_token(
        data={"sub": str(user.user_id)}
    )
    
    db.commit()
    
    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "expires_in": settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        "user_id": user.user_id,
        "user_email": user.user_email,
        "user_full_name": user.user_full_name,
        "subscription": subscription_name
    }

@router.post("/login/json", response_model=TokenResponse)
async def login_json(user_login: UserLogin, db: Session = Depends(get_db)):
    """
    Connexion utilisateur (format JSON)
    """
    user = db.query(User).filter(User.user_email == user_login.user_email).first()
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Email ou mot de passe incorrect"
        )
    
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Ce compte a été désactivé"
        )
    
    user_password = db.query(UserPassword).filter(
        UserPassword.user_id == user.user_id
    ).first()
    
    if not user_password or not verify_password(user_login.password, user_password.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Email ou mot de passe incorrect"
        )
    
    subscription = db.query(Subscription).filter(
        Subscription.subscription_id == user.user_subscription_id
    ).first()
    
    access_token = create_access_token(
        data={"sub": str(user.user_id)},
        expires_delta=timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES) if not user_login.remember_me else timedelta(days=7)
    )
    
    refresh_token = create_refresh_token(
        data={"sub": str(user.user_id)}
    )
    
    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "expires_in": settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        "user_id": user.user_id,
        "user_email": user.user_email,
        "user_full_name": user.user_full_name,
        "subscription": subscription.subscription_name if subscription else "Free"
    }

@router.get("/me", response_model=UserResponse)
async def get_current_user_info(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Récupérer les informations de l'utilisateur connecté
    """
    subscription = db.query(Subscription).filter(
        Subscription.subscription_id == current_user.user_subscription_id
    ).first()
    
    return {
        "user_id": current_user.user_id,
        "user_full_name": current_user.user_full_name,
        "user_email": current_user.user_email,
        "user_image": current_user.user_image,
        "subscription": subscription.subscription_name if subscription else "Free",
        "is_active": current_user.is_active,
        "preferences": current_user.preferences,
        "created_at": current_user.created_at
    }

@router.put("/me", response_model=UserResponse)
async def update_profile(
    profile_data: UpdateProfileRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Mettre à jour le profil utilisateur
    """
    if profile_data.user_full_name:
        current_user.user_full_name = profile_data.user_full_name
    
    if profile_data.preferences:
        current_user.preferences = profile_data.preferences
    
    db.commit()
    db.refresh(current_user)
    
    subscription = db.query(Subscription).filter(
        Subscription.subscription_id == current_user.user_subscription_id
    ).first()
    
    return {
        "user_id": current_user.user_id,
        "user_full_name": current_user.user_full_name,
        "user_email": current_user.user_email,
        "user_image": current_user.user_image,
        "subscription": subscription.subscription_name if subscription else "Free",
        "is_active": current_user.is_active,
        "preferences": current_user.preferences,
        "created_at": current_user.created_at
    }

@router.post("/change-password")
async def change_password(
    password_change: PasswordChange,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Changer le mot de passe
    """
    if password_change.new_password != password_change.confirm_password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Les mots de passe ne correspondent pas"
        )
    
    user_password = db.query(UserPassword).filter(
        UserPassword.user_id == current_user.user_id
    ).first()
    
    if not user_password or not verify_password(password_change.current_password, user_password.password_hash):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Mot de passe actuel incorrect"
        )
    
    # Vérifier que le nouveau mot de passe est différent
    if verify_password(password_change.new_password, user_password.password_hash):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Le nouveau mot de passe doit être différent de l'ancien"
        )
    
    # Mettre à jour le mot de passe
    user_password.password_hash = get_password_hash(password_change.new_password)
    db.commit()
    
    return {"message": "Mot de passe changé avec succès"}

@router.post("/refresh-token", response_model=TokenResponse)
async def refresh_token(
    request: RefreshTokenRequest,
    db: Session = Depends(get_db)
):
    """
    Rafraîchir le token d'accès
    """
    payload = verify_refresh_token(request.refresh_token)
    
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token de rafraîchissement invalide"
        )
    
    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token invalide"
        )
    
    user = db.query(User).filter(User.user_id == int(user_id)).first()
    
    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Utilisateur non trouvé ou inactif"
        )
    
    # Créer un nouveau token d'accès
    new_access_token = create_access_token(
        data={"sub": str(user.user_id)}
    )
    
    subscription = db.query(Subscription).filter(
        Subscription.subscription_id == user.user_subscription_id
    ).first()
    
    return {
        "access_token": new_access_token,
        "refresh_token": request.refresh_token,
        "token_type": "bearer",
        "expires_in": settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        "user_id": user.user_id,
        "user_email": user.user_email,
        "user_full_name": user.user_full_name,
        "subscription": subscription.subscription_name if subscription else "Free"
    }

@router.post("/logout")
async def logout(current_user: User = Depends(get_current_user)):
    """
    Déconnexion (côté client doit supprimer les tokens)
    """
    return {"message": "Déconnexion réussie"}

@router.post("/reset-password/request")
async def reset_password_request(
    request: PasswordResetRequest,
    db: Session = Depends(get_db)
):
    """
    Demander une réinitialisation de mot de passe
    """
    user = db.query(User).filter(User.user_email == request.user_email).first()
    
    if user:
        # Générer un token de réinitialisation
        reset_token = ''.join(secrets.choice(string.ascii_letters + string.digits) for _ in range(32))
        
        user_password = db.query(UserPassword).filter(
            UserPassword.user_id == user.user_id
        ).first()
        
        if user_password:
            user_password.password_reset_token = reset_token
            user_password.password_reset_expires = datetime.utcnow() + timedelta(hours=24)
            db.commit()
            
            # Ici, envoyer un email avec le token
            # send_reset_email(user.user_email, reset_token)
    
    # Toujours retourner le même message pour ne pas divulguer l'existence de l'email
    return {
        "message": "Si un compte existe avec cet email, vous recevrez un lien de réinitialisation"
    }

@router.post("/reset-password/confirm")
async def reset_password_confirm(
    request: PasswordResetConfirm,
    db: Session = Depends(get_db)
):
    """
    Confirmer la réinitialisation du mot de passe
    """
    if request.new_password != request.confirm_password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Les mots de passe ne correspondent pas"
        )
    
    # Chercher l'utilisateur avec ce token
    user_password = db.query(UserPassword).filter(
        UserPassword.password_reset_token == request.token,
        UserPassword.password_reset_expires > datetime.utcnow()
    ).first()
    
    if not user_password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Token invalide ou expiré"
        )
    
    # Mettre à jour le mot de passe
    user_password.password_hash = get_password_hash(request.new_password)
    user_password.password_reset_token = None
    user_password.password_reset_expires = None
    user_password.login_attempts = 0
    
    db.commit()
    
    return {"message": "Mot de passe réinitialisé avec succès"}