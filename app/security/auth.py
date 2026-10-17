import secrets
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.config import Settings, get_settings

_bearer = HTTPBearer(auto_error=False)


def require_token(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> None:
    if not settings.api_token:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "ICORE_API_TOKEN is not configured.")
    if credentials is None or not secrets.compare_digest(credentials.credentials, settings.api_token):
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "Invalid or missing token.",
            headers={"WWW-Authenticate": "Bearer"},
        )
