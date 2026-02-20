#!/usr/bin/env python3
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.database import engine, Base
from app.models import *
from app.models import Subscription
from sqlalchemy.orm import Session

def init():
    print("📦 Création des tables...")
    Base.metadata.create_all(bind=engine)
    print(f"✅ Tables créées: {list(Base.metadata.tables.keys())}")

    with Session(engine) as db:
        if db.query(Subscription).count() == 0:
            db.add_all([
                Subscription(subscription_name="Free",    subscription_price=0,     subscription_duration=0,  max_scans_per_day=5,   max_scans_per_month=50,   is_premium=False),
                Subscription(subscription_name="Basic",   subscription_price=4.99,  subscription_duration=30, max_scans_per_day=20,  max_scans_per_month=200,  is_premium=False),
                Subscription(subscription_name="Premium", subscription_price=9.99,  subscription_duration=30, max_scans_per_day=999, max_scans_per_month=9999, is_premium=True),
            ])
            db.commit()
            print("✅ Abonnements par défaut créés (Free / Basic / Premium)")

if __name__ == "__main__":
    init()
