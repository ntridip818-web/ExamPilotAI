import os
import secrets
from functools import lru_cache
from typing import Any, Dict

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import APIKeyHeader, HTTPAuthorizationCredentials, HTTPBearer
from jwt import PyJWKClient
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.models import User


# Supabase Auth access tokens use the standard Bearer authorization scheme.
# The scheme name is exposed in Swagger/OpenAPI so the Authorize dialog
# clearly asks for a Supabase JWT rather than a Firebase token.
bearer_scheme = HTTPBearer(
    auto_error=False,
    scheme_name="SupabaseBearer",
    description="Supabase Auth access token (JWT).",
)

# Maintenance endpoints use a separate header so Swagger can authorize it
# independently from Supabase authentication.
cleanup_token_scheme = APIKeyHeader(
    name="X-Cleanup-Token",
    auto_error=False,
    scheme_name="CleanupToken",
    description="Server-side maintenance token for admin cleanup operations.",
)


@lru_cache(maxsize=1)
def _supabase_jwks_client() -> PyJWKClient:
    url = os.getenv("SUPABASE_URL", "").strip().rstrip("/")
    if not url:
        raise RuntimeError("SUPABASE_URL is not configured")
    return PyJWKClient(f"{url}/auth/v1/.well-known/jwks.json")


def _verify_supabase_jwt(token: str) -> Dict[str, Any]:
    """Verify a Supabase Auth access token.

    Newer Supabase projects use asymmetric signing keys exposed through the
    project's JWKS endpoint. Older projects using an HS256 JWT secret are
    supported through SUPABASE_JWT_SECRET when configured.
    """
    try:
        header = jwt.get_unverified_header(token)
        algorithm = header.get("alg")
        supabase_url = os.getenv("SUPABASE_URL", "").strip().rstrip("/")
        if not supabase_url:
            raise RuntimeError("SUPABASE_URL is not configured")

        issuer = f"{supabase_url}/auth/v1"

        if algorithm in {"HS256", "HS384", "HS512"}:
            secret = os.getenv("SUPABASE_JWT_SECRET", "").strip()
            if not secret:
                raise RuntimeError(
                    "SUPABASE_JWT_SECRET is required for HS256 Supabase tokens"
                )
            return jwt.decode(
                token,
                secret,
                algorithms=[algorithm],
                audience="authenticated",
                issuer=issuer,
            )

        signing_key = _supabase_jwks_client().get_signing_key_from_jwt(token)
        return jwt.decode(
            token,
            signing_key.key,
            algorithms=[algorithm] if algorithm else ["ES256", "RS256"],
            audience="authenticated",
            issuer=issuer,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired Supabase authentication token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc


def verify_bearer_token(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> Dict[str, Any]:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return _verify_supabase_jwt(credentials.credentials)


def get_current_user(
    token: Dict[str, Any] = Depends(verify_bearer_token),
    db: Session = Depends(get_db),
) -> User:
    # Supabase Auth uses `sub` as the authenticated user's UUID. The existing
    # database column remains named firebase_uid for backwards compatibility;
    # it now stores the Supabase user UUID instead.
    uid = token.get("sub")
    if not uid:
        raise HTTPException(status_code=401, detail="Invalid authentication token")

    user = db.query(User).filter(User.firebase_uid == uid).first()
    if not user:
        raise HTTPException(status_code=403, detail="User profile not found")

    return user


def require_admin(
    token: Dict[str, Any] = Depends(verify_bearer_token),
) -> Dict[str, Any]:
    uid = token.get("sub")
    admins = {
        value.strip()
        for value in os.getenv("ADMIN_SUPABASE_UIDS", "").split(",")
        if value.strip()
    }
    if not uid or uid not in admins:
        raise HTTPException(status_code=403, detail="Admin access required")
    return token


def require_cleanup_token(
    token: str | None = Depends(cleanup_token_scheme),
) -> None:
    """Protect maintenance endpoints with the dedicated CLEANUP_TOKEN secret."""
    expected = os.getenv("CLEANUP_TOKEN", "").strip()

    if not expected:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Cleanup authentication is not configured",
        )

    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Cleanup authentication required",
            headers={"WWW-Authenticate": "ApiKey"},
        )

    if not secrets.compare_digest(token, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid cleanup authentication token",
            headers={"WWW-Authenticate": "ApiKey"},
        )
