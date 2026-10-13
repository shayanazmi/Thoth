try:
    import jwt
except ImportError:
    jwt = None

from typing import Optional, Dict, Any
from fastapi import Depends, HTTPException, Security, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from backend.core.config import get_settings
from backend.core.logging import get_logger
from backend.core.errors import AuthenticationError

logger = get_logger("ThothAuth")
security = HTTPBearer(auto_error=False)

GUEST_USER: Dict[str, Any] = {
    "sub": "guest-researcher-001",
    "email": "guest@thoth.studio",
    "role": "authenticated",
    "is_guest": True
}

async def get_optional_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Security(security)
) -> Dict[str, Any]:
    """
    Validates Supabase JWT if present. If absent, falls back to GUEST_USER
    so local development and public research studio testing remain functional.
    """
    if not credentials:
        return GUEST_USER

    token = credentials.credentials
    settings = get_settings()

    if not settings.SUPABASE_JWT_SECRET or jwt is None:
        # If secret not set or PyJWT not installed, operate in safe guest mode
        return GUEST_USER

    try:
        payload = jwt.decode(
            token,
            settings.SUPABASE_JWT_SECRET,
            algorithms=["HS256"],
            audience="authenticated"
        )
        payload["is_guest"] = False
        return payload
    except jwt.ExpiredSignatureError:
        logger.warning("Supabase Bearer token has expired.")
        raise AuthenticationError("Authorization token has expired.")
    except jwt.InvalidTokenError as e:
        logger.warning(f"Invalid Supabase Bearer token: {str(e)}")
        raise AuthenticationError(f"Invalid authorization credentials: {str(e)}")

async def get_current_user(
    user: Dict[str, Any] = Depends(get_optional_user)
) -> Dict[str, Any]:
    """
    Strict authentication dependency. Rejects unauthenticated guest access.
    """
    if user.get("is_guest"):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authenticated session required. Please sign in via Supabase."
        )
    return user
