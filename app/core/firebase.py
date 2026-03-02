import firebase_admin
from firebase_admin import credentials, auth
from fastapi import HTTPException
import os
from app.core.config import settings

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
        
        # Vérifier si le fichier existe
        if not os.path.exists(cred_path):
            print(f"⚠️ Fichier de clé Firebase non trouvé: {cred_path}")
            print("   Le service fonctionnera sans validation Firebase")
            return None
        
        # Initialiser avec le fichier de clé
        cred = credentials.Certificate(cred_path)
        _firebase_app = firebase_admin.initialize_app(cred)
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
            # Mode développement sans Firebase
            print("⚠️ Firebase non initialisé - Token non vérifié")
            return {"uid": "dev_user", "email": "dev@example.com"}
        
        # Vérifier le token
        decoded_token = auth.verify_id_token(id_token)
        return decoded_token
        
    except auth.ExpiredIdTokenError:
        raise HTTPException(status_code=401, detail="Token Firebase expiré")
    except auth.InvalidIdTokenError:
        raise HTTPException(status_code=401, detail="Token Firebase invalide")
    except auth.RevokedIdTokenError:
        raise HTTPException(status_code=401, detail="Token Firebase révoqué")
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Erreur de vérification: {str(e)}")