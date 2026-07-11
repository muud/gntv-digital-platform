"""Health check endpoints for the backend API.
Provides a simple /health route that verifies database and Redis connectivity.
"""

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import text
from sqlalchemy.exc import OperationalError
from app.core.database import engine
from app.core.redis import get_redis, redis_manager

router = APIRouter()

@router.get("/health", summary="Health check", tags=["Health"])
async def health_check() -> dict[str, str]:
    # Check DB connection
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except OperationalError:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Database unavailable")
    # Check Redis connection
    if redis_manager.client is None:
        await redis_manager.connect()
    redis = await get_redis()
    try:
        pong = redis.ping()
        if hasattr(pong, "__await__"):
            pong = await pong
        if pong != b"PONG":
            raise Exception("Invalid ping response")
    except Exception:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Redis unavailable")
    return {"status": "ok", "database": "connected", "redis": "connected"}
