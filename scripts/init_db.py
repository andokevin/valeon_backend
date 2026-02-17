#!/usr/bin/env python3
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.database import engine, Base, SessionLocal
from app.models import Subscription, User
from passlib.context import CryptContext
from datetime import datetime, timedelta

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def init_database():
    print("🚀 Initialisation de la base de données Valeon...")
    
    print("📦 Création des tables...")
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    print("✅ Tables créées avec succès!")
    
    db = SessionLocal()
    
    try:
        # Ajouter les abonnements par défaut
        print("📝 Création des abonnements...")
        subscriptions = [
            Subscription(
                subscription_name="Free",
                subscription_price=0.0,
                subscription_duration=36500, 
                                max_scans_per_day=10,
                max_scans_per_month=300,
                has_ads=True,
                offline_mode=False,
                hd_quality=False,
                priority_processing=False
            ),
            Subscription(
                subscription_name="Premium",
                subscription_price=9.99,
                subscription_duration=30,
                max_scans_per_day=1000,
                max_scans_per_month=30000,
                has_ads=False,
                offline_mode=True,
                hd_quality=True,
                priority_processing=True
            ),
            Subscription(
                subscription_name="Pro",
                subscription_price=19.99,
                subscription_duration=30,
                max_scans_per_day=5000,
                max_scans_per_month=150000,
                has_ads=False,
                offline_mode=True,
                hd_quality=True,
                priority_processing=True
            )
        ]
        
        for sub in subscriptions:
            existing = db.query(Subscription).filter_by(subscription_name=sub.subscription_name).first()
            if not existing:
                db.add(sub)
                print(f"  - {sub.subscription_name} créé")
        
        db.commit()
        print("✅ Abonnements créés avec succès!")
        
        # Créer un utilisateur admin par défaut (optionnel)
        print("👤 Création de l'utilisateur admin...")
        from app.models.password import UserPassword
        
        admin_email = "admin@valeon.com"
        existing_admin = db.query(User).filter_by(user_email=admin_email).first()
        
        if not existing_admin:
            free_sub = db.query(Subscription).filter_by(subscription_name="Free").first()
            
            admin_user = User(
                user_full_name="Administrateur",
                user_email=admin_email,
                user_image=None,
                user_subscription_id=free_sub.subscription_id,
                is_active=True,
                preferences={"role": "admin", "notifications": True}
            )
            db.add(admin_user)
            db.flush()
            
            # Ajouter le mot de passe
            hashed_password = pwd_context.hash("Admin123!")
            user_password = UserPassword(
                user_id=admin_user.user_id,
                password_hash=hashed_password
            )
            db.add(user_password)
            
            print(f"  - Admin créé avec email: {admin_email}")
        
        db.commit()
        print("✅ Utilisateur admin créé avec succès!")
        
    except Exception as e:
        print(f"❌ Erreur lors de l'initialisation: {e}")
        db.rollback()
    finally:
        db.close()
    
    print("\n🎉 Initialisation terminée avec succès!")
    print("\n📊 Connexion à la base de données:")
    print(f"  - URL: {os.getenv('DATABASE_URL', 'postgresql://localhost/valeon_db')}")
    print("\n🔑 Identifiants par défaut:")
    print("  - Email: admin@valeon.com")
    print("  - Mot de passe: Admin123!")
    print("\n⚠️  Changez ces identifiants en production!")

if __name__ == "__main__":
    init_database()