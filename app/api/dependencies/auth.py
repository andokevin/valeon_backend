import asyncio
from datetime import timedelta
from typing import Optional
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.security import decode_token, verify_password, get_password_hash, create_access_token, create_refresh_token
from app.models import User, UserPassword

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")

async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> User:
    payload = decode_token(token)
    if not payload or payload.get("type") != "access":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token invalide")
    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token invalide")
    user = db.query(User).filter(User.user_id == int(user_id)).first()
    if not user or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Utilisateur introuvable")
    return user

async def get_current_user_optional(
    token: Optional[str] = Depends(OAuth2PasswordBearer(tokenUrl="/api/auth/login", auto_error=False)),
    db: Session = Depends(get_db),
) -> Optional[User]:
    if not token:
        return None
    try:
        return await get_current_user(token, db)
    except Exception:
        return None

async def get_user_from_token(token: str) -> Optional[int]:
    payload = decode_token(token)
    if not payload:
        return None
    sub = payload.get("sub")
    return int(sub) if sub else None

def verify_refresh_token(token: str) -> Optional[dict]:
    payload = decode_token(token)
    if payload and payload.get("type") == "refresh":
        return payload
    return None
