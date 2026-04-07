import logging
from fastapi import HTTPException, Request, WebSocket

from backend.app.config import config

logger = logging.getLogger(__name__)


def verify_api_key(request: Request):
    """Validate x-api-key for HTTP requests when API_KEY is configured."""
    if not config.API_KEY:
        return

    key = request.headers.get("x-api-key")
    if key != config.API_KEY:
        raise HTTPException(status_code=401, detail="Unauthorized")


def verify_websocket_api_key(websocket: WebSocket) -> bool:
    """Validate API key during websocket handshake.

    Supports header and query param fallback for browser clients.
    """
    if not config.API_KEY:
        return True

    key = websocket.headers.get("x-api-key") or websocket.query_params.get("api_key")
    if key != config.API_KEY:
        logger.warning("WS unauthorized request rejected")
        return False

    return True
