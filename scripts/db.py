#!/usr/bin/env python3
# scripts/migrate_passwords.py
"""
Script de migration des mots de passe vers le nouveau format (SHA-256 + bcrypt).
À exécuter depuis le répertoire racine du projet.
"""

import os
import sys
from pathlib import Path

# Ajouter le répertoire racine du projet au PYTHONPATH
# Ceci permet d'importer les modules de l'application
current_file = Path(__file__).resolve()  # scripts/migrate_passwords.py
project_root = current_file.parent.parent  # remonte de 2 niveaux : scripts/ -> valeon_back/ -> racine ?

# Si vous êtes dans valeon_back, le chemin est correct
sys.path.insert(0, str(project_root))

try:
    from app.core.database import SessionLocal
    from app.models import UserPassword
    from app.core.security import get_password_hash
except ImportError as e:
    print(f"❌ Erreur d'import: {e}")
    print(f"📁 Chemin actuel: {project_root}")
    print("👉 Assurez-vous d'exécuter ce script depuis le bon répertoire")
    sys.exit(1)

import hashlib
import logging

# Configuration du logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def migrate_passwords():
    """
    Migre tous les mots de passe vers le nouveau format (SHA-256 + bcrypt).
    """
    logger.info("🚀 Début de la migration des mots de passe...")
    
    db = SessionLocal()
    try:
        # Récupérer tous les mots de passe
        passwords = db.query(UserPassword).all()
        logger.info(f"📊 {len(passwords)} mots de passe trouvés")
        
        migrated_count = 0
        unchanged_count = 0
        unknown_count = 0
        
        for pwd in passwords:
            old_hash = pwd.password_hash
            user_id = pwd.user_id
            
            # Vérifier si c'est un hash SHA-256 pur (64 caractères hex)
            if len(old_hash) == 64 and all(c in '0123456789abcdef' for c in old_hash.lower()):
                # C'est un ancien hash SHA-256, le remplacer par SHA-256 + bcrypt
                logger.info(f"🔄 Migration user_id={user_id} (SHA-256 pur -> SHA-256+bcrypt)")
                
                # On ne peut pas récupérer le mot de passe original
                # On met un placeholder pour forcer l'utilisateur à changer son mot de passe
                # OU on utilise le hash SHA-256 comme mot de passe (pas idéal)
                # Option recommandée : forcer le changement
                new_hash = "MIGRATION_REQUIRED_" + old_hash
                pwd.password_hash = new_hash
                migrated_count += 1
            
            # Vérifier si c'est un hash bcrypt (commence par $2b$)
            elif old_hash.startswith('$2b$'):
                # C'est déjà un hash bcrypt, mais on vérifie s'il correspond à notre nouveau format
                logger.info(f"✓ Hash bcrypt existant pour user_id={user_id} - inchangé")
                unchanged_count += 1
            
            # Vérifier si c'est déjà au nouveau format (SHA-256+bcrypt)
            elif len(old_hash) > 64 and old_hash.startswith('$2b$'):
                # C'est déjà au bon format
                logger.info(f"✓ Hash déjà au nouveau format pour user_id={user_id}")
                unchanged_count += 1
            
            else:
                logger.warning(f"⚠️ Format inconnu pour user_id={user_id}: {old_hash[:30]}...")
                unknown_count += 1
        
        db.commit()
        
        # Résumé
        logger.info("=" * 50)
        logger.info("📊 RÉSUMÉ DE LA MIGRATION")
        logger.info(f"✅ Migrés (SHA-256 pur): {migrated_count}")
        logger.info(f"✓ Inchangés: {unchanged_count}")
        logger.info(f"⚠️ Inconnus: {unknown_count}")
        logger.info("=" * 50)
        
        if migrated_count > 0:
            logger.warning("⚠️  Des mots de passe ont été migrés. Les utilisateurs concernés devront changer leur mot de passe!")
        
    except Exception as e:
        logger.error(f"❌ Erreur: {e}")
        db.rollback()
    finally:
        db.close()

def reset_password_for_user(user_id: int, new_password: str):
    """
    Réinitialise le mot de passe d'un utilisateur spécifique.
    Utile pour les tests.
    """
    db = SessionLocal()
    try:
        from app.models import User
        user = db.query(User).filter(User.user_id == user_id).first()
        if not user:
            logger.error(f"Utilisateur {user_id} non trouvé")
            return
        
        user_pwd = db.query(UserPassword).filter(UserPassword.user_id == user_id).first()
        if not user_pwd:
            logger.error(f"Mot de passe pour user_id={user_id} non trouvé")
            return
        
        # Nouveau hash avec SHA-256 + bcrypt
        new_hash = get_password_hash(new_password)
        user_pwd.password_hash = new_hash
        db.commit()
        
        logger.info(f"✅ Mot de passe réinitialisé pour {user.user_email}")
        
        # Vérification
        from app.core.security import verify_password
        if verify_password(new_password, new_hash):
            logger.info("✅ Vérification réussie")
        else:
            logger.error("❌ Échec de la vérification")
            
    except Exception as e:
        logger.error(f"❌ Erreur: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Migration des mots de passe")
    parser.add_argument("--reset", nargs=2, metavar=("USER_ID", "PASSWORD"),
                       help="Réinitialiser le mot de passe d'un utilisateur")
    parser.add_argument("--migrate", action="store_true",
                       help="Lancer la migration")
    
    args = parser.parse_args()
    
    if args.reset:
        user_id, password = args.reset
        reset_password_for_user(int(user_id), password)
    elif args.migrate:
        migrate_passwords()
    else:
        # Par défaut, lancer la migration
        migrate_passwords()