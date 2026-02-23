#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Fichier d'initialisation et de synchronisation de la base de données.
Ce script crée les tables si elles n'existent pas et met à jour leur structure.
"""

import os
import sys
from pathlib import Path

# Ajouter le répertoire parent au path pour pouvoir importer les modules de l'app
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.core.database import engine, Base
from app.models import (
    Subscription, User, UserPassword,
    Content, ExternalLink, Playlist, playlist_contents,
    Scan, RecognitionResult, Favorite, UserActivity
)
from sqlalchemy import inspect, text
from sqlalchemy.exc import SQLAlchemyError
import logging

# Configuration du logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def table_exists(table_name):
    """Vérifie si une table existe dans la base de données."""
    inspector = inspect(engine)
    return table_name in inspector.get_table_names()

def get_existing_columns(table_name):
    """Récupère la liste des colonnes existantes pour une table."""
    inspector = inspect(engine)
    return {col['name']: col for col in inspector.get_columns(table_name)}

def add_missing_columns(table_name, model_class):
    """
    Ajoute les colonnes manquantes à une table existante.
    """
    existing_columns = get_existing_columns(table_name)
    model_columns = {col.name: col for col in model_class.__table__.columns}
    
    columns_added = []
    
    for col_name, column in model_columns.items():
        if col_name not in existing_columns:
            try:
                # Construire la commande ALTER TABLE
                col_type = column.type.compile(engine.dialect)
                nullable = "NULL" if column.nullable else "NOT NULL"
                default = f"DEFAULT {column.default.arg}" if column.default else ""
                
                alter_sql = f"ALTER TABLE {table_name} ADD COLUMN {col_name} {col_type} {nullable} {default}"
                
                with engine.connect() as conn:
                    conn.execute(text(alter_sql))
                    conn.commit()
                
                logger.info(f"✅ Colonne '{col_name}' ajoutée à la table '{table_name}'")
                columns_added.append(col_name)
                
            except Exception as e:
                logger.error(f"❌ Erreur lors de l'ajout de la colonne '{col_name}' à '{table_name}': {e}")
    
    return columns_added

def create_tables():
    """Crée toutes les tables définies dans les modèles."""
    try:
        Base.metadata.create_all(bind=engine)
        logger.info("✅ Tables créées avec succès")
    except SQLAlchemyError as e:
        logger.error(f"❌ Erreur lors de la création des tables: {e}")
        raise

def update_tables():
    """
    Met à jour la structure des tables existantes sans perdre les données.
    """
    # Liste de tous les modèles avec leurs noms de table
    models = [
        (Subscription, 'subscriptions'),
        (User, 'users'),
        (UserPassword, 'user_passwords'),
        (Content, 'contents'),
        (ExternalLink, 'external_links'),
        (Playlist, 'playlists'),
        (Scan, 'scans'),
        (RecognitionResult, 'recognition_results'),
        (Favorite, 'favorites'),
        (UserActivity, 'user_activities')
    ]
    
    for model_class, table_name in models:
        try:
            if table_exists(table_name):
                logger.info(f"🔄 Mise à jour de la table '{table_name}'...")
                
                # Ajouter les colonnes manquantes
                added = add_missing_columns(table_name, model_class)
                
                if added:
                    logger.info(f"   Colonnes ajoutées à '{table_name}': {', '.join(added)}")
                else:
                    logger.info(f"   ✓ Table '{table_name}' est à jour")
            else:
                logger.info(f"📝 La table '{table_name}' n'existe pas encore, elle sera créée")
                
        except Exception as e:
            logger.error(f"❌ Erreur lors de la mise à jour de '{table_name}': {e}")

def verify_tables():
    """Vérifie que toutes les tables nécessaires existent."""
    required_tables = [
        'subscriptions', 'users', 'user_passwords',
        'contents', 'external_links', 'playlists',
        'playlist_contents', 'scans', 'recognition_results',
        'favorites', 'user_activities'
    ]
    
    existing_tables = inspect(engine).get_table_names()
    missing_tables = [table for table in required_tables if table not in existing_tables]
    
    if missing_tables:
        logger.warning(f"⚠️ Tables manquantes: {', '.join(missing_tables)}")
        return False
    
    logger.info("✅ Toutes les tables nécessaires sont présentes")
    return True

def init_database(force_drop=False):
    """
    Initialise la base de données.
    
    Args:
        force_drop (bool): Si True, supprime toutes les tables avant de les recréer
    """
    try:
        logger.info("🚀 Début de l'initialisation de la base de données...")
        
        if force_drop:
            # Supprimer toutes les tables (attention: perte de données!)
            response = input("⚠️  Êtes-vous sûr de vouloir supprimer toutes les tables? (oui/non): ")
            if response.lower() == 'oui':
                Base.metadata.drop_all(bind=engine)
                logger.info("🗑️  Toutes les tables ont été supprimées")
                create_tables()
            else:
                logger.info("Opération annulée")
                return
        else:
            # Mise à jour des tables existantes
            update_tables()
            
            # Créer les tables qui n'existent pas
            create_tables()
            
            # Vérification finale
            verify_tables()
        
        logger.info("✅ Initialisation de la base de données terminée avec succès!")
        
    except SQLAlchemyError as e:
        logger.error(f"❌ Erreur SQLAlchemy: {e}")
        raise
    except Exception as e:
        logger.error(f"❌ Erreur inattendue: {e}")
        raise

def seed_initial_data():
    """Ajoute des données initiales si nécessaire."""
    from sqlalchemy.orm import sessionmaker
    from app.core.database import SessionLocal
    
    db = SessionLocal()
    try:
        # Vérifier s'il y a déjà des abonnements
        from app.models import Subscription
        
        if db.query(Subscription).count() == 0:
            logger.info("🌱 Ajout des abonnements par défaut...")
            
            # Créer l'abonnement Free par défaut
            free_sub = Subscription(
                subscription_name="Free",
                subscription_price=0.0,
                subscription_duration=None,  # Illimité
                max_scans_per_day=5,
                max_scans_per_month=50,
                is_premium=False
            )
            
            # Créer l'abonnement Premium
            premium_sub = Subscription(
                subscription_name="Premium",
                subscription_price=9.99,
                subscription_duration=30,  # 30 jours
                max_scans_per_day=100,
                max_scans_per_month=3000,
                is_premium=True
            )
            
            db.add(free_sub)
            db.add(premium_sub)
            db.commit()
            
            logger.info("✅ Abonnements par défaut créés")
        
    except Exception as e:
        logger.error(f"❌ Erreur lors de l'ajout des données initiales: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Initialisation de la base de données")
    parser.add_argument('--force-drop', action='store_true', 
                       help="Supprime toutes les tables avant de les recréer")
    parser.add_argument('--seed', action='store_true',
                       help="Ajoute des données initiales après la création")
    
    args = parser.parse_args()
    
    # Exécuter l'initialisation
    init_database(force_drop=args.force_drop)
    
    # Ajouter les données initiales si demandé
    if args.seed:
        seed_initial_data()