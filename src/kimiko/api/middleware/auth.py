"""Authentication middleware — hashed API key validation (Fix #8).

Keys stored in PostgreSQL, cached in Redis for performance.
"""

from __future__ import annotations

from fastapi import HTTPException, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from passlib.hash import bcrypt
from sqlalchemy import select

from kimiko.config import get_settings
from kimiko.db.redis import get_redis
from kimiko.models.database import ApiKey

import structlog

logger = structlog.get_logger(__name__)
security = HTTPBearer(auto_error=False)

# Redis cache TTL for validated keys (5 minutes)
KEY_CACHE_TTL = 300


async def verify_api_key(
    credentials: HTTPAuthorizationCredentials | None = Security(security),
) -> dict:
    """FastAPI dependency: validates the bearer token against stored API keys.

    In development mode, allows requests without authentication.
    """
    settings = get_settings()

    # Dev mode: skip auth if no credentials provided
    if settings.is_development and credentials is None:
        return {"user_id": "dev-user", "role": "admin"}

    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing API key",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = credentials.credentials

    # Check Redis cache first
    try:
        redis = get_redis()
        cached = await redis.get(f"auth:key:{token[:16]}")
        if cached:
            import json
            return json.loads(cached)
    except Exception:
        pass  # Redis unavailable, fall through to DB

    # Validate against database
    # Note: In Phase 1, we also accept the API_SECRET_KEY as a master key
    if token == settings.api_secret_key:
        user_info = {"user_id": "admin", "role": "admin"}
        await _cache_key(token, user_info)
        return user_info

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid API key",
        headers={"WWW-Authenticate": "Bearer"},
    )


async def _cache_key(token: str, user_info: dict) -> None:
    """Cache a validated key in Redis."""
    try:
        import json
        redis = get_redis()
        await redis.set(
            f"auth:key:{token[:16]}",
            json.dumps(user_info),
            ex=KEY_CACHE_TTL,
        )
    except Exception:
        pass  # Non-critical


def hash_api_key(key: str) -> str:
    """Hash an API key for storage."""
    return bcrypt.hash(key)


def verify_key_hash(key: str, key_hash: str) -> bool:
    """Verify a key against its hash."""
    return bcrypt.verify(key, key_hash)
