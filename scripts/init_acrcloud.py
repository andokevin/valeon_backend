#!/usr/bin/env python3
"""
Script de test pour ACRCloud.
"""
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import asyncio
from app.core.modules.acrcloud.client import ACRCloudClient
from app.core.config import settings

async def test_acrcloud():
    """Teste la connexion à ACRCloud."""
    print("🔍 Test de connexion ACRCloud...")
    
    if not settings.ACRCLOUD_ENABLED:
        print("❌ ACRCloud n'est pas activé dans la configuration")
        return
    
    if not all([settings.ACRCLOUD_HOST, settings.ACRCLOUD_ACCESS_KEY, settings.ACRCLOUD_SECRET_KEY]):
        print("❌ Configuration ACRCloud incomplète")
        print(f"  Host: {'✅' if settings.ACRCLOUD_HOST else '❌'}")
        print(f"  Access Key: {'✅' if settings.ACRCLOUD_ACCESS_KEY else '❌'}")
        print(f"  Secret Key: {'✅' if settings.ACRCLOUD_SECRET_KEY else '❌'}")
        return
    
    client = ACRCloudClient()
    
    # Tester avec un fichier audio de test
    test_file = sys.argv[1] if len(sys.argv) > 1 else None
    
    if not test_file:
        print("❌ Veuillez fournir un fichier audio de test")
        print(f"Usage: {sys.argv[0]} <fichier_audio>")
        return
    
    print(f"🎵 Test avec fichier: {test_file}")
    result = await client.recognize(test_file)
    
    if result:
        print("✅ Reconnaissance réussie !")
        print(f"  Titre: {result.get('title')}")
        print(f"  Artiste: {result.get('artist')}")
        print(f"  Album: {result.get('album')}")
        print(f"  Spotify ID: {result.get('spotify_id')}")
    else:
        print("❌ Échec de la reconnaissance")

if __name__ == "__main__":
    asyncio.run(test_acrcloud())