from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query
from typing import Optional
from datetime import datetime
import asyncio, logging

from app.core.websocket.manager import manager
from app.api.dependencies.auth import get_user_from_token

router = APIRouter(tags=["WebSocket"])
logger = logging.getLogger(__name__)

@router.websocket("/ws/scan")
async def ws_scan(websocket: WebSocket, token: Optional[str] = Query(None)):
    user_id = None
    try:
        if not token:
            data = await websocket.receive_json()
            token = data.get("token")
        if not token:
            await websocket.close(code=1008, reason="Token manquant"); return
        user_id = await get_user_from_token(token)
        if not user_id:
            await websocket.close(code=1008, reason="Token invalide"); return
        await manager.connect(websocket, user_id, "Free")
        await websocket.send_json({"type": "connection_established", "user_id": user_id})
        while True:
            data = await websocket.receive_json()
            msg_type = data.get("type")
            if msg_type == "ping":
                await websocket.send_json({"type": "pong", "timestamp": datetime.utcnow().isoformat()})
            elif msg_type == "subscribe_scan":
                manager.subscribe_to_scan(data.get("scan_id"), user_id)
                await websocket.send_json({"type": "subscribed", "scan_id": data.get("scan_id")})
    except WebSocketDisconnect:
        if user_id: manager.disconnect(user_id)
    except Exception as e:
        logger.error(f"WS scan error: {e}")
        try: await websocket.close(code=1011)
        except: pass
