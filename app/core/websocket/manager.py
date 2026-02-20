import asyncio, logging
from typing import Dict, Set, Any, Optional, List
from fastapi import WebSocket
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[int, Dict[str, Any]] = {}
        self.scan_subscriptions: Dict[int, Set[int]] = {}
        self.active_scans: Dict[str, Dict[str, Any]] = {}
        self._lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket, user_id: int, subscription: str):
        await websocket.accept()
        async with self._lock:
            self.active_connections[user_id] = {
                "websocket": websocket, "subscription": subscription,
                "connected_at": datetime.now(), "last_activity": datetime.now(),
            }
        logger.info(f"User {user_id} connected via WS")

    def disconnect(self, user_id: int):
        self.active_connections.pop(user_id, None)
        for scan_id in list(self.scan_subscriptions.keys()):
            self.scan_subscriptions[scan_id].discard(user_id)
            if not self.scan_subscriptions[scan_id]:
                del self.scan_subscriptions[scan_id]

    async def send_personal_message(self, message: dict, user_id: int) -> bool:
        conn = self.active_connections.get(user_id)
        if not conn:
            return False
        try:
            await conn["websocket"].send_json(message)
            conn["last_activity"] = datetime.now()
            return True
        except Exception as e:
            logger.error(f"WS send error to {user_id}: {e}")
            self.disconnect(user_id)
            return False

    async def broadcast(self, message: dict, exclude: Optional[int] = None):
        for uid, conn in list(self.active_connections.items()):
            if uid == exclude:
                continue
            try:
                await conn["websocket"].send_json(message)
            except Exception:
                self.disconnect(uid)

    def subscribe_to_scan(self, scan_id: int, user_id: int):
        self.scan_subscriptions.setdefault(scan_id, set()).add(user_id)

    def unsubscribe_from_scan(self, scan_id: int, user_id: int):
        if scan_id in self.scan_subscriptions:
            self.scan_subscriptions[scan_id].discard(user_id)

    def is_connected(self, user_id: int) -> bool:
        return user_id in self.active_connections

    def get_connection_count(self) -> int:
        return len(self.active_connections)

    def cleanup_old_scans(self, max_age_hours: int = 24):
        cutoff = datetime.now() - timedelta(hours=max_age_hours)
        to_del = [k for k, v in self.active_scans.items() if v.get("started_at", datetime.now()) < cutoff]
        for k in to_del:
            del self.active_scans[k]

manager = ConnectionManager()
