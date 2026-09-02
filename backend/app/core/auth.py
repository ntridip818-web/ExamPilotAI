import json
import os
import secrets
from functools import lru_cache
from typing import Any, Dict

import firebase_admin
from firebase_admin import auth, credentials
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.database import get_db
from app.models.models import User
from sqlalchemy.orm import Session


bearer_scheme = HTTPBearer(auto_error=False)


@lru_cache(maxsize=1)
def _firebase_app():
    if firebase_admin._apps:
        return firebase_admin.get_app()

    raw = os.getenv("FIREBASE_SERVICE_ACCOUNT_JSON")
    if not raw:
        raise RuntimeError("FIREBASE_SERVICE_ACCOUNT_JSON is not configured")

    try:
        service_account = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError("FIREBASE_SERVICE_ACCOUNT_JSON is invalid JSON") from exc

    return firebase_admin.initialize_app(credentials.Certificate(service_account))


def verify_bearer_token(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> Dict[str, Any]:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        return auth.verify_id_token(credentials.credentials, app=_firebase_app())
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired authentication token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc


def get_current_user(
    token: Dict[str, Any] = Depends(verify_bearer_token),
    db: Session = Depends(get_db),
) -> User:
    uid = token.get("uid")
    if not uid:
        raise HTTPException(status_code=401, detail="Invalid authentication token")

    user = db.query(User).filter(User.firebase_uid == uid).first()
    if not user:
        raise HTTPException(status_code=403, detail="User profile not found")

    return user


def require_admin(
    token: Dict[str, Any] = Depends(verify_bearer_token),
) -> Dict[str, Any]:
    uid = token.get("uid")
    admins = {
        value.strip()
        for value in os.getenv("ADMIN_FIREBASE_UIDS", "").split(",")
        if value.strip()
    }
    if not uid or uid not in admins:
        raise HTTPException(status_code=403, detail="Admin access required")
    return token


def require_cleanup_token(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> None:
    """Protect maintenance endpoints with the dedicated CLEANUP_TOKEN secret.

    This is intentionally separate from Firebase authentication: the cleanup
    token is a server-side maintenance secret, not a Firebase ID token.
    """
    expected = os.getenv("CLEANUP_TOKEN", "").strip()

    if not expected:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Cleanup authentication is not configured",
        )

    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not secrets.compare_digest(credentials.credentials, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid cleanup authentication token",
            headers={"WWW-Authenticate": "Bearer"},
        )
