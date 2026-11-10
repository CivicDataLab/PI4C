from fastapi import HTTPException, status

from app.config import get_settings


def require_write_access() -> None:
    """Dependency for endpoints that change data. Read endpoints are open to everyone and need nothing.
    WRITE_ACCESS=true lets anyone write; false (the default) blocks writing for everyone."""
    if not get_settings().write_access:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Write access is turned off (WRITE_ACCESS=false)")
