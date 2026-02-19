#!/usr/bin/env python3
"""
Script de synchronisation des tables
"""
import sys
import os
import enum

current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)
sys.path.insert(0, project_root)

print(f"📂 Dossier racine: {project_root}")

from app.core.database import engine
from app.models import Base  # ← Maintenant Base vient des modèles !
from sqlalchemy import inspect

def sync_database():
    print("📦 Création des tables...")
    
    tables_in_metadata = list(Base.metadata.tables.keys())
    print(f"📊 Modèles trouvés: {tables_in_metadata}")
    
    Base.metadata.create_all(bind=engine)
    print("✅ Tables créées!")
    
    inspector = inspect(engine)
    tables_in_db = inspector.get_table_names()
    print(f"📊 Tables dans la DB: {tables_in_db}")

if __name__ == "__main__":
    sync_database()