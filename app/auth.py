import secrets

from fastapi import Depends, HTTPException, status
from fastapi.security import APIKeyHeader

from app.config import get_settings

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def _parse_keys(raw: str) -> list[tuple[str, str, str]]:
    """'name:scope:key,...' → [(name, scope, key)]"""
    keys = []
    for item in filter(None, (part.strip() for part in raw.split(","))):
        name, scope, key = item.split(":", 2)
        keys.append((name, scope, key))
    return keys


def require_scope(scope: str):
    """Dependency returning the client name. Read endpoints are public (prototype, testing only):
    a request without a key is client "public". Write endpoints need a 'write' key."""

    def dependency(api_key: str | None = Depends(api_key_header)) -> str:
        if scope == "read" and not api_key:
            return "public"
        keys = _parse_keys(get_settings().api_keys)
        if not keys:
            raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "API keys not configured")
        if not api_key:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing X-API-Key")
        for name, key_scope, key in keys:
            if secrets.compare_digest(api_key, key):
                if scope == "read" or key_scope == "write":
                    return name
                raise HTTPException(status.HTTP_403_FORBIDDEN, f"Key lacks '{scope}' scope")
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid API key")

    return dependency
