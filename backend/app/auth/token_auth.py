import hmac
import logging
from datetime import datetime, timezone
import asyncio
from fastapi import HTTPException, Security, WebSocket, Header, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from backend.app.config import settings
from backend.app.db.database import db_manager

logger = logging.getLogger("TokenAuth")

security = HTTPBearer()

def get_token():
    token = settings.ASTA_API_BEARER_TOKEN.strip()
    if not token:
        logger.error("[Auth] ASTA_API_BEARER_TOKEN is not configured on the backend server")
        raise HTTPException(status_code=500, detail="ASTA_API_BEARER_TOKEN not configured")
    return token

def verify_bearer(credentials: HTTPAuthorizationCredentials = Security(security)) -> str:
    """Validate static bearer token for HTTP requests (without device check, used for device registration)."""
    token = get_token()
    if not hmac.compare_digest(credentials.credentials, token):
        raise HTTPException(status_code=401, detail="Invalid token")
    return credentials.credentials

async def verify_bearer_and_device(
    request: Request,
    authorization: HTTPAuthorizationCredentials = Security(security),
    x_device_id: str = Header(None)
) -> str:
    """Validate static bearer token and verify the device ID matches the registered device."""
    # 1. Verify bearer
    token = get_token()
    if not hmac.compare_digest(authorization.credentials, token):
        raise HTTPException(status_code=401, detail="Invalid token")
        
    # 2. Verify device binding
    if not x_device_id:
        raise HTTPException(status_code=403, detail="Missing X-Device-Id header")
        
    collection = db_manager.get_collection("registered_devices")
    registered = await collection.find_one({})
    if not registered:
        raise HTTPException(status_code=403, detail="No device registered yet. Please register your device first.")
        
    if registered["device_id"] != x_device_id:
        logger.warning(f"[Auth] Device authorization failed. Header device_id: {x_device_id}, registered: {registered['device_id']}")
        raise HTTPException(status_code=403, detail="Unauthorized device ID")
        
    async def _update_last_seen():
        await collection.update_one(
            {"_id": registered["_id"]},
            {"$set": {"last_seen": datetime.now(timezone.utc)}}
        )
    asyncio.create_task(_update_last_seen())
    
    return authorization.credentials

async def verify_ws_token_and_device(websocket: WebSocket) -> bool:
    """Validate bearer token and device ID during websocket handshake."""
    token_val = get_token()
    token = websocket.query_params.get("token")
    device_id = websocket.query_params.get("device_id")
    
    if not token:
        auth_header = websocket.headers.get("authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header.split("Bearer ", 1)[1].strip()
            
    if not device_id:
        device_id = websocket.headers.get("x-device-id", "")
        
    if not token or not hmac.compare_digest(token, token_val):
        logger.warning("[Auth] WS unauthorized connection attempt: invalid or missing token")
        return False
        
    if not device_id:
        logger.warning("[Auth] WS unauthorized connection attempt: missing device ID")
        return False
        
    collection = db_manager.get_collection("registered_devices")
    registered = await collection.find_one({})
    if not registered or registered["device_id"] != device_id:
        logger.warning(f"[Auth] WS unauthorized connection attempt: device ID {device_id} not registered")
        return False
        
    async def _update_last_seen():
        await collection.update_one(
            {"_id": registered["_id"]},
            {"$set": {"last_seen": datetime.now(timezone.utc)}}
        )
    asyncio.create_task(_update_last_seen())
    
    return True
