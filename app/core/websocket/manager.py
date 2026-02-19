# app/core/websocket/manager.py
from fastapi import WebSocket
from typing import Dict, Set, Any, Optional, List
import asyncio
import json
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)

class ConnectionManager:
    def __init__(self):
        # Stocker les connexions actives: user_id -> {websocket, subscription, connected_at}
        self.active_connections: Dict[int, Dict[str, Any]] = {}
        
        # Stocker les scans en cours
        self.active_scans: Dict[str, Dict[str, Any]] = {}
        
        # Stocker les abonnements aux scans: scan_id -> set of user_ids
        self.scan_subscriptions: Dict[int, Set[int]] = {}
        
        # Stocker les files d'attente de messages pour chaque utilisateur
        self.message_queues: Dict[int, asyncio.Queue] = {}
    
    async def connect(self, websocket: WebSocket, user_id: int, subscription: str):
        """Établit une connexion WebSocket"""
        await websocket.accept()
        
        # Créer une file d'attente pour cet utilisateur
        if user_id not in self.message_queues:
            self.message_queues[user_id] = asyncio.Queue()
        
        self.active_connections[user_id] = {
            "websocket": websocket,
            "subscription": subscription,
            "connected_at": datetime.now(),
            "last_activity": datetime.now()
        }
        
        logger.info(f"Utilisateur {user_id} connecté via WebSocket ({subscription})")
    
    def disconnect(self, user_id: int):
        """Ferme une connexion WebSocket"""
        if user_id in self.active_connections:
            del self.active_connections[user_id]
            
            # Nettoyer les abonnements
            for scan_id in list(self.scan_subscriptions.keys()):
                if user_id in self.scan_subscriptions[scan_id]:
                    self.scan_subscriptions[scan_id].remove(user_id)
            
            logger.info(f"Utilisateur {user_id} déconnecté")
    
    async def send_personal_message(self, message: dict, user_id: int):
        """Envoie un message à un utilisateur spécifique"""
        if user_id in self.active_connections:
            websocket = self.active_connections[user_id]["websocket"]
            try:
                await websocket.send_json(message)
                self.active_connections[user_id]["last_activity"] = datetime.now()
                return True
            except Exception as e:
                logger.error(f"Erreur envoi message à {user_id}: {e}")
                self.disconnect(user_id)
                return False
        return False
    
    async def broadcast(self, message: dict, exclude_user: Optional[int] = None):
        """Diffuse un message à tous les utilisateurs connectés"""
        sent_count = 0
        for user_id, connection in list(self.active_connections.items()):
            if exclude_user and user_id == exclude_user:
                continue
            
            try:
                await connection["websocket"].send_json(message)
                sent_count += 1
            except Exception as e:
                logger.error(f"Erreur broadcast à {user_id}: {e}")
                self.disconnect(user_id)
        
        return sent_count
    
    async def broadcast_to_subscribers(self, scan_id: int, message: dict):
        """Diffuse un message à tous les abonnés d'un scan"""
        if scan_id in self.scan_subscriptions:
            for user_id in self.scan_subscriptions[scan_id]:
                await self.send_personal_message(message, user_id)
    
    def subscribe_to_scan(self, scan_id: int, user_id: int) -> str:
        """Abonne un utilisateur aux mises à jour d'un scan"""
        if scan_id not in self.scan_subscriptions:
            self.scan_subscriptions[scan_id] = set()
        
        self.scan_subscriptions[scan_id].add(user_id)
        
        # Créer une clé de scan pour le suivi
        scan_key = f"{user_id}:{scan_id}"
        
        return scan_key
    
    def unsubscribe_from_scan(self, scan_id: int, user_id: int):
        """Désabonne un utilisateur d'un scan"""
        if scan_id in self.scan_subscriptions and user_id in self.scan_subscriptions[scan_id]:
            self.scan_subscriptions[scan_id].remove(user_id)
            
            if not self.scan_subscriptions[scan_id]:
                del self.scan_subscriptions[scan_id]
    
    def start_scan(self, scan_id: int, user_id: int, metadata: Optional[dict] = None):
        """Démarre le suivi d'un scan"""
        scan_key = f"{user_id}:{scan_id}"
        
        self.active_scans[scan_key] = {
            "scan_id": scan_id,
            "user_id": user_id,
            "status": "processing",
            "progress": 0,
            "message": "Démarrage du scan...",
            "started_at": datetime.now(),
            "metadata": metadata or {}
        }
        
        # Abonnement automatique
        self.subscribe_to_scan(scan_id, user_id)
        
        return scan_key
    
    def update_scan_progress(self, scan_key: str, progress: int, message: str = None):
        """Met à jour la progression d'un scan"""
        if scan_key in self.active_scans:
            self.active_scans[scan_key]["progress"] = progress
            if message:
                self.active_scans[scan_key]["message"] = message
    
    def complete_scan(self, scan_key: str, result: dict):
        """Marque un scan comme terminé"""
        if scan_key in self.active_scans:
            self.active_scans[scan_key]["status"] = "completed"
            self.active_scans[scan_key]["result"] = result
            self.active_scans[scan_key]["completed_at"] = datetime.now()
    
    def fail_scan(self, scan_key: str, error: str):
        """Marque un scan comme échoué"""
        if scan_key in self.active_scans:
            self.active_scans[scan_key]["status"] = "failed"
            self.active_scans[scan_key]["error"] = error
            self.active_scans[scan_key]["failed_at"] = datetime.now()
    
    def get_scan_status(self, scan_key: str) -> Optional[Dict]:
        """Récupère le statut d'un scan"""
        return self.active_scans.get(scan_key)
    
    def get_user_active_scans(self, user_id: int) -> List[Dict]:
        """Récupère tous les scans actifs d'un utilisateur"""
        scans = []
        for scan_key, scan_data in self.active_scans.items():
            if scan_data["user_id"] == user_id:
                scan_data["key"] = scan_key
                scans.append(scan_data.copy())
        return scans
    
    def cleanup_old_scans(self, max_age_hours: int = 24):
        """Nettoie les scans plus vieux que max_age_hours"""
        now = datetime.now()
        cutoff = now - timedelta(hours=max_age_hours)
        
        to_delete = []
        for scan_key, scan_data in self.active_scans.items():
            started_at = scan_data["started_at"]
            if started_at < cutoff:
                to_delete.append(scan_key)
        
        for scan_key in to_delete:
            del self.active_scans[scan_key]
    
    def is_connected(self, user_id: int) -> bool:
        """Vérifie si un utilisateur est connecté"""
        return user_id in self.active_connections
    
    def get_connected_users(self) -> List[int]:
        """Retourne la liste des utilisateurs connectés"""
        return list(self.active_connections.keys())
    
    def get_connection_count(self) -> int:
        """Retourne le nombre de connexions actives"""
        return len(self.active_connections)
    
    def get_scan_count(self) -> int:
        """Retourne le nombre de scans actifs"""
        return len(self.active_scans)

# Instance globale du gestionnaire
manager = ConnectionManager()