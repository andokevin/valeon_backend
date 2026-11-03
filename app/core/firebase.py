import firebase_admin
from firebase_admin import credentials, auth
from fastapi import HTTPException
import logging
import os
from app.core.config import settings

logger = logging.getLogger(__name__)

# Variable globale pour l'initialisation
_firebase_app = None

def initialize_firebase():
    """Initialise Firebase Admin SDK"""
    global _firebase_app
    
    # Éviter la double initialisation
    if _firebase_app is not None:
        return _firebase_app
    
    try:
        # Chemin vers le fichier de clé de service
        # À définir dans votre .env ou directement ici
        cred_path = getattr(settings, 'FIREBASE_SERVICE_ACCOUNT_KEY', 'serviceAccountKey.json')
        if not settings.FIREBASE_ENABLED:
            print("⚠️ Firebase désactivé (FIREBASE_ENABLED=false)")
            return None
        # Chemin relatif : chercher aussi depuis la racine du backend et dans app/
        if not os.path.isabs(cred_path) and not os.path.exists(cred_path):
            backend_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            for candidate in (os.path.join(backend_root, cred_path), os.path.join(backend_root, "app", cred_path)):
                if os.path.exists(candidate):
                    cred_path = candidate
                    break

        options = {"projectId": settings.FIREBASE_PROJECT_ID} if settings.FIREBASE_PROJECT_ID else None
        if os.path.exists(cred_path):
            cred = credentials.Certificate(cred_path)
        elif settings.FIREBASE_USE_ADC or os.getenv("K_SERVICE"):
            # Cloud Run (K_SERVICE défini) : identité du service, aucun fichier de clé à déployer
            cred = credentials.ApplicationDefault()
        else:
            print(f"⚠️ Fichier de clé Firebase non trouvé: {cred_path}")
            print("   Le service fonctionnera sans validation Firebase")
            return None

        _firebase_app = firebase_admin.initialize_app(cred, options)
        print(f"✅ Firebase Admin SDK initialisé avec succès")
        return _firebase_app
        
    except Exception as e:
        print(f"❌ Erreur initialisation Firebase: {e}")
        return None

def verify_firebase_token(id_token: str):
    """
    Vérifie un token Firebase ID token
    Retourne le token décodé ou lève une exception
    """
    try:
        # Vérifier que Firebase est initialisé
        if _firebase_app is None:
            initialize_firebase()
            
        if _firebase_app is None:
            # Ne jamais accepter un token non vérifié (sinon usurpation de compte)
            raise HTTPException(status_code=503, detail="Connexion sociale indisponible (Firebase non configuré)")

        # Tolérance d'horloge : sans elle, un serveur en retard d'une seconde sur Google
        # refuse le jeton tout juste émis (« Token used too early »)
        decoded_token = auth.verify_id_token(id_token, clock_skew_seconds=30)
        return decoded_token

    except HTTPException:
        raise
    except auth.ExpiredIdTokenError:
        raise HTTPException(status_code=401, detail="Token Firebase expiré")
    except auth.RevokedIdTokenError:
        raise HTTPException(status_code=401, detail="Token Firebase révoqué")
    except auth.InvalidIdTokenError as e:
        # La raison exacte (projet, audience, horloge…) n'est visible que dans les logs
        logger.warning(f"Token Firebase refusé : {e}")
        raise HTTPException(status_code=401, detail="Token Firebase invalide")
    except Exception as e:
        logger.error(f"Erreur de vérification Firebase : {e}")
        raise HTTPException(status_code=401, detail=f"Erreur de vérification: {str(e)}")