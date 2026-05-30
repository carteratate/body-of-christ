import base64
import json
from typing import Any

import jwt
from cryptography import x509
from fastapi import HTTPException

from app.auth.jwks import get_jwks
from app.config import settings
from app.models.auth import AuthUser


_ALLOWED_ALGORITHMS = ["RS256", "ES256"]


def _issuer() -> str:
    return f"{settings.supabase_project_url}/auth/v1"


def _find_jwk(jwks: dict[str, Any], kid: str) -> dict[str, Any] | None:
    for key in jwks.get("keys", []):
        if key.get("kid") == kid:
            return key
    return None


def _public_key_from_jwk(jwk: dict[str, Any]) -> Any:
    kty = jwk.get("kty")
    jwk_json = json.dumps(jwk)

    if kty == "RSA":
        return jwt.algorithms.RSAAlgorithm.from_jwk(jwk_json)

    if kty == "EC":
        if "x" in jwk and "y" in jwk:
            return jwt.algorithms.ECAlgorithm.from_jwk(jwk_json)
        if "x5c" in jwk:
            der = base64.b64decode(jwk["x5c"][0])
            cert = x509.load_der_x509_certificate(der)
            return cert.public_key()
        raise HTTPException(status_code=401, detail="EC key missing coordinates and x5c")

    raise HTTPException(status_code=401, detail="Unsupported signing key type")


async def verify_supabase_jwt(token: str) -> AuthUser:
    try:
        header = jwt.get_unverified_header(token)
    except jwt.exceptions.DecodeError:
        raise HTTPException(status_code=401, detail="Invalid token format")

    kid: str | None = header.get("kid")
    alg: str = header.get("alg", "")

    if alg not in _ALLOWED_ALGORITHMS:
        raise HTTPException(status_code=401, detail="Unsupported token algorithm")

    if not kid:
        raise HTTPException(status_code=401, detail="Token missing kid")

    # Try cached JWKS first; refresh once if kid is absent
    jwks = await get_jwks()
    jwk = _find_jwk(jwks, kid)
    if jwk is None:
        jwks = await get_jwks(force_refresh=True)
        jwk = _find_jwk(jwks, kid)
    if jwk is None:
        raise HTTPException(status_code=401, detail="Unknown signing key")

    try:
        public_key = _public_key_from_jwk(jwk)
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid signing key")

    try:
        payload: dict[str, Any] = jwt.decode(
            token,
            public_key,  # type: ignore[arg-type]
            algorithms=_ALLOWED_ALGORITHMS,
            audience=settings.supabase_jwt_audience,
            issuer=_issuer(),
        )
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidAudienceError:
        raise HTTPException(status_code=401, detail="Invalid audience")
    except jwt.InvalidIssuerError:
        raise HTTPException(status_code=401, detail="Invalid issuer")
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Token verification failed")

    user_id: str | None = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="Token missing sub")

    return AuthUser(
        user_id=user_id,
        email=payload.get("email"),
        role=payload.get("role"),
    )
