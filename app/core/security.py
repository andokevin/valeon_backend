from datetime import datetime, timedelta, timezone
from typing import Optional
from jose import JWTError, jwt
from app.core.config import settings
import base64
import bcrypt
import hashlib
import hmac
import logging

# Configuration du logging
logger = logging.getLogger(__name__)

def _bcrypt_input(password: str) -> bytes:
    """
    bcrypt ne prend en compte que 72 bytes : on pré-hache en SHA-256 (base64)
    pour que les mots de passe longs restent entièrement significatifs.
    """
    digest = hashlib.sha256(password.encode("utf-8")).digest()
    return base64.b64encode(digest)

def _is_legacy_sha256(hashed: str) -> bool:
    return len(hashed) == 64 and all(c in "0123456789abcdef" for c in hashed.lower())

def get_password_hash(password: str) -> str:
    """Hache un mot de passe avec bcrypt (salé)."""
    return bcrypt.hashpw(_bcrypt_input(password), bcrypt.gensalt()).decode("utf-8")

def verify_password(plain: str, hashed: str) -> bool:
    """
    Vérifie un mot de passe. Accepte aussi les anciens hash SHA-256 non salés
    (créés quand passlib échouait avec bcrypt >= 4.1) : voir needs_rehash().
    """
    if not hashed:
        return False
    if _is_legacy_sha256(hashed):
        plain_hash = hashlib.sha256(plain.encode("utf-8")).hexdigest()
        return hmac.compare_digest(plain_hash, hashed.lower())
    try:
        return bcrypt.checkpw(_bcrypt_input(plain), hashed.encode("utf-8"))
    except ValueError as e:
        logger.error(f"Hash de mot de passe invalide: {e}")
        return False

def needs_rehash(hashed: str) -> bool:
    """True si le hash stocké est un ancien format à migrer vers bcrypt."""
    return _is_legacy_sha256(hashed)

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """
    Crée un token JWT d'accès.
    """
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    to_encode.update({"exp": expire, "type": "access"})
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)

def create_refresh_token(data: dict) -> str:
    """
    Crée un token JWT de rafraîchissement.
    """
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    to_encode.update({"exp": expire, "type": "refresh"})
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)

def decode_token(token: str) -> Optional[dict]:
    """
    Décode et valide un token JWT.
    """
    try:
        return jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
    except JWTError:
        return None

# Clés de préférences que l'utilisateur ne doit jamais pouvoir modifier lui-même
PROTECTED_PREFERENCE_KEYS = {"role", "auth_provider", "firebase_uid"}

def merge_user_preferences(current: Optional[dict], incoming: Optional[dict], replace: bool = False) -> dict:
    """
    Fusionne (ou remplace) les préférences envoyées par le client en conservant
    les clés protégées (rôle admin, provider...) telles qu'elles sont en base.
    """
    current = dict(current or {})
    incoming = {k: v for k, v in (incoming or {}).items() if k not in PROTECTED_PREFERENCE_KEYS}
    merged = incoming if replace else {**current, **incoming}
    for key in PROTECTED_PREFERENCE_KEYS:
        if key in current:
            merged[key] = current[key]
        else:
            merged.pop(key, None)
    return merged
