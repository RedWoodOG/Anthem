"""
Anthem API Key Authentication.
Real key validation with hashed storage. No decorative flags.
"""

import hashlib
import logging
import secrets
from datetime import datetime, timezone
from typing import Dict, Optional

from fastapi import HTTPException, Request, status

logger = logging.getLogger(__name__)


class APIKeyManager:
    """
    Manages API key creation, validation, and revocation.

    In production, keys are stored in Postgres. For local dev,
    an in-memory store is used with a bootstrapped admin key.
    """

    def __init__(self, require_keys: bool = True) -> None:
        self.require_keys = require_keys
        # In-memory store for local dev: {key_hash: metadata}
        self._keys: Dict[str, Dict] = {}
        self._admin_key: Optional[str] = None

        if not require_keys:
            logger.warning("API key validation DISABLED — dev mode only")

    def bootstrap_admin_key(self) -> str:
        """Generate and store an admin key. Returns the raw key (only shown once)."""
        raw_key = f"anthem_{secrets.token_urlsafe(32)}"
        key_hash = self._hash_key(raw_key)
        self._keys[key_hash] = {
            "tenant_id": "admin",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "expires_at": None,
            "revoked": False,
            "scopes": ["admin", "read", "write"],
        }
        self._admin_key = raw_key
        logger.info("Admin API key bootstrapped")
        return raw_key

    def create_key(self, tenant_id: str, scopes: Optional[list] = None) -> str:
        """Create a new API key for a tenant. Returns the raw key (only shown once)."""
        raw_key = f"anthem_{secrets.token_urlsafe(32)}"
        key_hash = self._hash_key(raw_key)
        self._keys[key_hash] = {
            "tenant_id": tenant_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "expires_at": None,
            "revoked": False,
            "scopes": scopes or ["read", "write"],
        }
        logger.info("API key created for tenant: %s", tenant_id)
        return raw_key

    def validate_key(self, raw_key: str) -> Dict:
        """
        Validate an API key. Returns key metadata if valid.
        Raises HTTPException if invalid.
        """
        key_hash = self._hash_key(raw_key)
        meta = self._keys.get(key_hash)

        if not meta:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={"code": "INVALID_API_KEY", "message": "Invalid API key"},
            )

        if meta.get("revoked"):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={"code": "REVOKED_API_KEY", "message": "API key has been revoked"},
            )

        expires = meta.get("expires_at")
        if expires and datetime.fromisoformat(expires) < datetime.now(timezone.utc):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={"code": "EXPIRED_API_KEY", "message": "API key has expired"},
            )

        return meta

    def revoke_key(self, raw_key: str) -> bool:
        """Revoke an API key."""
        key_hash = self._hash_key(raw_key)
        if key_hash in self._keys:
            self._keys[key_hash]["revoked"] = True
            return True
        return False

    @staticmethod
    def _hash_key(raw_key: str) -> str:
        return hashlib.sha256(raw_key.encode()).hexdigest()


def require_api_key(api_key_manager: APIKeyManager):
    """
    FastAPI dependency that validates the X-API-Key header.
    """

    async def _validate(request: Request) -> Dict:
        if not api_key_manager.require_keys:
            return {"tenant_id": "dev", "scopes": ["admin", "read", "write"]}

        key = request.headers.get("X-API-Key")
        if not key:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={"code": "MISSING_API_KEY", "message": "X-API-Key header required"},
            )

        return api_key_manager.validate_key(key)

    return _validate
