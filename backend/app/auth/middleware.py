from fastapi import Header, HTTPException, Depends
from backend.app.config import config


async def verify_token(authorization: str = Header(default=None)) -> str:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing Authorization header")
    token = authorization.split("Bearer ")[1].strip()
    if token != config.ASTA_JWT_TOKEN:
        raise HTTPException(status_code=401, detail="Unauthorized")
    return "karthik"


async def get_current_user(user: str = Depends(verify_token)) -> dict:
    return {"user": user}
