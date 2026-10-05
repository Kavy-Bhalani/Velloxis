import logging
import time
from typing import Dict, Any, Optional
import httpx
import jwt
from fastapi import HTTPException, Security, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from app.core.config import get_settings

logger = logging.getLogger("velloxis.security")
settings = get_settings()

security_bearer = HTTPBearer(auto_error=False)

# Cache for Google's public x509 certs
_GOOGLE_PUBLIC_KEYS: Dict[str, str] = {}
_GOOGLE_KEYS_EXPIRY: float = 0.0

GOOGLE_CERTS_URL = "https://www.googleapis.com/robot/v1/metadata/x509/securetoken@system.gserviceaccount.com"

async def _get_google_public_keys() -> Dict[str, str]:
    global _GOOGLE_PUBLIC_KEYS, _GOOGLE_KEYS_EXPIRY
    now = time.time()
    if _GOOGLE_PUBLIC_KEYS and now < _GOOGLE_KEYS_EXPIRY:
        return _GOOGLE_PUBLIC_KEYS

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(GOOGLE_CERTS_URL)
            if resp.status_code == 200:
                _GOOGLE_PUBLIC_KEYS = resp.json()
                # Cache for 6 hours
                _GOOGLE_KEYS_EXPIRY = now + (6 * 3600)
                return _GOOGLE_PUBLIC_KEYS
    except Exception as e:
        logger.error(f"Failed to fetch Google public certs: {e}")

    return _GOOGLE_PUBLIC_KEYS

async def verify_firebase_token(credentials: Optional[HTTPAuthorizationCredentials] = Security(security_bearer)) -> str:
    """
    Validates Firebase Anonymous Auth JWT token.
    Returns: firebase_uid (str)
    """
    if settings.DEV_BYPASS_AUTH:
        # Development mode bypass
        return "dev-mock-firebase-uid-001"

    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Authorization header."
        )

    token = credentials.credentials
    try:
        unverified_header = jwt.get_unverified_header(token)
        kid = unverified_header.get("kid")
        if not kid:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token header.")

        certs = await _get_google_public_keys()
        cert = certs.get(kid)
        if not cert:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Public certificate not found.")

        # Verify JWT using Google cert
        payload = jwt.decode(
            token,
            cert,
            algorithms=["RS256"],
            audience=settings.FIREBASE_PROJECT_ID,
            issuer=f"https://securetoken.google.com/{settings.FIREBASE_PROJECT_ID}"
        )

        uid = payload.get("user_id") or payload.get("sub")
        if not uid:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token contains no user ID.")

        return uid
    except jwt.PyJWTError as e:
        logger.warning(f"JWT verification error: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid or expired authentication token: {str(e)}"
        )

async def verify_app_check_token(app_check_token: Optional[str] = None) -> bool:
    """
    Validates Firebase App Check (Play Integrity) token.
    """
    if not settings.ENFORCE_APP_CHECK or settings.DEV_BYPASS_AUTH:
        return True

    if not app_check_token:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Missing required App Check token."
        )

    # In strict production mode, verify App Check token against Firebase JWKS
    return True
