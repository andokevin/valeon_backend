# app/api/routers/websocket.py
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends, Query
from typing import Optional
import asyncio
import json
import logging
from jose import JWTError, jwt
from datetime import datetime

from app.core.config import settings
from app.core.websocket import manager  # ✅ IMPORT CORRIGÉ
from app.api.dependencies.auth import get_user_from_token

router = APIRouter(tags=["WebSocket"])
logger = logging.getLogger(__name__)

@router.websocket("/ws/scan")
async def websocket_scan_endpoint(
    websocket: WebSocket,
    token: Optional[str] = Query(None)
):
    """
    WebSocket pour les scans en temps réel
    """
    user_id = None
    
    try:
        # Authentification via token
        if not token:
            # Essayer de recevoir le token dans le premier message
            data = await websocket.receive_json()
            token = data.get("token")
            subscription = data.get("subscription", "Free")
        else:
            subscription = "Free"
            data = await websocket.receive_json()
        
        if not token:
            await websocket.close(code=1008, reason="Token manquant")
            return
        
        # Valider le token
        user_id = await get_user_from_token(token)
        if not user_id:
            await websocket.close(code=1008, reason="Token invalide")
            return
        
        # Accepter la connexion
        await manager.connect(websocket, user_id, subscription)
        
        # Envoyer confirmation
        await websocket.send_json({
            "type": "connection_established",
            "user_id": user_id,
            "subscription": subscription,
            "message": "Connecté au service de scan en temps réel",
            "timestamp": datetime.utcnow().isoformat()
        })
        
        # Gérer les messages
        while True:
            data = await websocket.receive_json()
            message_type = data.get("type")
            
            if message_type == "ping":
                await websocket.send_json({
                    "type": "pong",
                    "timestamp": datetime.utcnow().isoformat()
                })
            
            elif message_type == "subscribe_scan":
                scan_id = data.get("scan_id")
                # S'abonner aux mises à jour d'un scan spécifique
                scan_key = manager.subscribe_to_scan(scan_id, user_id)
                await websocket.send_json({
                    "type": "subscribed",
                    "scan_id": scan_id,
                    "message": f"Abonné au scan {scan_id}"
                })
            
            elif message_type == "unsubscribe_scan":
                scan_id = data.get("scan_id")
                manager.unsubscribe_from_scan(scan_id, user_id)
                await websocket.send_json({
                    "type": "unsubscribed",
                    "scan_id": scan_id
                })
            
            elif message_type == "get_active_scans":
                active_scans = manager.get_user_active_scans(user_id)
                await websocket.send_json({
                    "type": "active_scans",
                    "scans": active_scans
                })
            
            else:
                await websocket.send_json({
                    "type": "error",
                    "message": f"Type de message inconnu: {message_type}"
                })
    
    except WebSocketDisconnect:
        if user_id:
            manager.disconnect(user_id)
            logger.info(f"Utilisateur {user_id} déconnecté du WebSocket scan")
    except Exception as e:
        logger.error(f"Erreur WebSocket scan: {e}")
        try:
            await websocket.close(code=1011, reason="Erreur interne")
        except:
            pass

@router.websocket("/ws/notifications")
async def websocket_notifications_endpoint(
    websocket: WebSocket,
    token: Optional[str] = Query(None)
):
    """
    WebSocket pour les notifications en temps réel
    """
    user_id = None
    
    try:
        # Authentification
        if not token:
            data = await websocket.receive_json()
            token = data.get("token")
        else:
            data = await websocket.receive_json() if token else {}
        
        if not token:
            await websocket.close(code=1008, reason="Token manquant")
            return
        
        user_id = await get_user_from_token(token)
        if not user_id:
            await websocket.close(code=1008, reason="Token invalide")
            return
        
        # Accepter la connexion
        await manager.connect(websocket, user_id, "Free")
        
        await websocket.send_json({
            "type": "notifications_ready",
            "message": "Prêt à recevoir des notifications",
            "timestamp": datetime.utcnow().isoformat()
        })
        
        # Garder la connexion ouverte et envoyer des notifications périodiques
        last_ping = datetime.utcnow()
        
        while True:
            # Recevoir les messages (pour keep-alive)
            try:
                data = await asyncio.wait_for(websocket.receive_json(), timeout=30.0)
                
                if data.get("type") == "ping":
                    await websocket.send_json({
                        "type": "pong",
                        "timestamp": datetime.utcnow().isoformat()
                    })
                    last_ping = datetime.utcnow()
                
            except asyncio.TimeoutError:
                # Envoyer un ping de keep-alive
                if (datetime.utcnow() - last_ping).seconds > 45:
                    await websocket.send_json({
                        "type": "ping",
                        "timestamp": datetime.utcnow().isoformat()
                    })
                continue
            
    except WebSocketDisconnect:
        if user_id:
            manager.disconnect(user_id)
            logger.info(f"Utilisateur {user_id} déconnecté du WebSocket notifications")
    except Exception as e:
        logger.error(f"Erreur WebSocket notifications: {e}")

@router.websocket("/ws/chat")
async def websocket_chat_endpoint(
    websocket: WebSocket,
    token: Optional[str] = Query(None)
):
    """
    WebSocket pour le chat en temps réel avec l'IA
    """
    user_id = None
    
    try:
        # Authentification
        if not token:
            data = await websocket.receive_json()
            token = data.get("token")
        else:
            data = await websocket.receive_json() if token else {}
        
        if not token:
            await websocket.close(code=1008, reason="Token manquant")
            return
        
        user_id = await get_user_from_token(token)
        if not user_id:
            await websocket.close(code=1008, reason="Token invalide")
            return
        
        # Accepter la connexion
        await manager.connect(websocket, user_id, "Free")
        
        await websocket.send_json({
            "type": "chat_ready",
            "message": "Assistant IA prêt à vous répondre",
            "timestamp": datetime.utcnow().isoformat()
        })
        
        # Gérer les messages de chat
        while True:
            data = await websocket.receive_json()
            message_type = data.get("type")
            
            if message_type == "message":
                query = data.get("query", "")
                
                if not query:
                    await websocket.send_json({
                        "type": "error",
                        "message": "Requête vide"
                    })
                    continue
                
                # Simuler une réponse de l'IA (à remplacer par votre logique réelle)
                await websocket.send_json({
                    "type": "typing",
                    "status": "En train d'écrire..."
                })
                
                await asyncio.sleep(1)  # Simulation de traitement
                
                await websocket.send_json({
                    "type": "response",
                    "query": query,
                    "response": f"Je comprends que vous cherchez: {query}. Voici quelques recommandations...",
                    "timestamp": datetime.utcnow().isoformat()
                })
            
            elif message_type == "stop":
                await websocket.send_json({
                    "type": "stopped",
                    "message": "Génération arrêtée"
                })
            
            elif message_type == "ping":
                await websocket.send_json({
                    "type": "pong",
                    "timestamp": datetime.utcnow().isoformat()
                })
    
    except WebSocketDisconnect:
        if user_id:
            manager.disconnect(user_id)
            logger.info(f"Utilisateur {user_id} déconnecté du WebSocket chat")
    except Exception as e:
        logger.error(f"Erreur WebSocket chat: {e}")

@router.websocket("/ws/admin")
async def websocket_admin_endpoint(
    websocket: WebSocket,
    token: str = Query(...)
):
    """
    WebSocket pour les administrateurs (statistiques en temps réel)
    """
    try:
        user_id = await get_user_from_token(token)
        if not user_id:
            await websocket.close(code=1008, reason="Token invalide")
            return
        
        # Vérifier si l'utilisateur est admin
        # Cette vérification dépend de votre logique d'administration
        # if not is_admin(user_id):
        #     await websocket.close(code=1008, reason="Non autorisé")
        #     return
        
        await manager.connect(websocket, user_id, "admin")
        
        await websocket.send_json({
            "type": "admin_connected",
            "message": "Connexion admin établie",
            "timestamp": datetime.utcnow().isoformat()
        })
        
        # Envoyer des statistiques périodiques
        while True:
            # Compter les connexions actives
            active_users = len(manager.active_connections)
            active_scans = len(manager.active_scans)
            
            await websocket.send_json({
                "type": "stats",
                "active_users": active_users,
                "active_scans": active_scans,
                "timestamp": datetime.utcnow().isoformat()
            })
            
            await asyncio.sleep(5)  # Mise à jour toutes les 5 secondes
    
    except WebSocketDisconnect:
        if user_id:
            manager.disconnect(user_id)
    except Exception as e:
        logger.error(f"Erreur WebSocket admin: {e}")