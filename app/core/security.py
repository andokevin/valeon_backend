from datetime import datetime, timedelta, timezone
from typing import Optional
from jose import JWTError, jwt
from passlib.context import CryptContext
from app.core.config import settings
import hashlib
import logging

# Configuration du logging
logger = logging.getLogger(__name__)

# Configuration de passlib avec bcrypt
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def get_password_hash(password: str) -> str:
    """
    Hache un mot de passe en gérant la limite de 72 bytes de bcrypt.
    """
    try:
        # Essayer avec bcrypt (pour les mots de passe courts)
        return pwd_context.hash(password)
    except ValueError as e:
        if "password cannot be longer than 72 bytes" in str(e):
            # Si le mot de passe est trop long, utiliser SHA-256
            logger.info(f"Mot de passe trop long, utilisation de SHA-256")
            # SHA-256 produit 64 caractères hex (32 bytes) - toujours ≤ 72 bytes
            password_hash = hashlib.sha256(password.encode('utf-8')).hexdigest()
            # Retourner DIRECTEMENT le SHA-256 (PAS de re-hachage bcrypt!)
            return password_hash
        else:
            # Autre erreur
            logger.error(f"Erreur de hachage: {e}")
            raise

def verify_password(plain: str, hashed: str) -> bool:
    """
    Vérifie un mot de passe en gérant les deux formats possibles.
    """
    # Vérifier d'abord si c'est un hash SHA-256 (64 caractères hex)
    if len(hashed) == 64 and all(c in '0123456789abcdef' for c in hashed.lower()):
        logger.info("Hash SHA-256 détecté, vérification directe")
        plain_hash = hashlib.sha256(plain.encode('utf-8')).hexdigest()
        return plain_hash == hashed
    
    # Sinon, essayer avec bcrypt
    try:
        logger.info("Tentative de vérification bcrypt")
        return pwd_context.verify(plain, hashed)
    except Exception as e:
        logger.error(f"Erreur de vérification bcrypt: {e}")
        
        # Dernier recours : essayer SHA-256 au cas où le format serait différent
        try:
            logger.info("Tentative de vérification SHA-256")
            plain_hash = hashlib.sha256(plain.encode('utf-8')).hexdigest()
            return plain_hash == hashed
        except:
            return False

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