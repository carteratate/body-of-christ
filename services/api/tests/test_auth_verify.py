"""verify_supabase_jwt: issuer handling across the project URL and a custom auth domain."""

import json
import time

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import HTTPException

from app.auth import verify
from app.config import settings

PROJECT_URL = "https://abcdefghijklmnopqrst.supabase.co"
CUSTOM_URL = "https://auth.example.com"

_private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
_jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(_private_key.public_key()))
_jwk["kid"] = "test-kid"


def _token(iss: str) -> str:
    claims = {"sub": "user-1", "aud": "authenticated", "iss": iss, "exp": int(time.time()) + 300}
    return jwt.encode(claims, _private_key, algorithm="RS256", headers={"kid": "test-kid"})


@pytest.fixture(autouse=True)
def _settings(monkeypatch):
    async def fake_get_jwks(force_refresh: bool = False):
        return {"keys": [_jwk]}

    monkeypatch.setattr(verify, "get_jwks", fake_get_jwks)
    monkeypatch.setattr(settings, "supabase_project_url", PROJECT_URL)
    monkeypatch.setattr(settings, "supabase_jwt_audience", "authenticated")
    monkeypatch.setattr(settings, "supabase_custom_domain_url", "")


async def test_accepts_project_issuer():
    user = await verify.verify_supabase_jwt(_token(f"{PROJECT_URL}/auth/v1"))
    assert user.user_id == "user-1"


async def test_rejects_custom_domain_issuer_when_not_configured():
    with pytest.raises(HTTPException) as exc:
        await verify.verify_supabase_jwt(_token(f"{CUSTOM_URL}/auth/v1"))
    assert exc.value.detail == "Invalid issuer"


async def test_accepts_both_issuers_once_custom_domain_is_configured(monkeypatch):
    monkeypatch.setattr(settings, "supabase_custom_domain_url", CUSTOM_URL)

    assert (await verify.verify_supabase_jwt(_token(f"{CUSTOM_URL}/auth/v1"))).user_id == "user-1"
    assert (await verify.verify_supabase_jwt(_token(f"{PROJECT_URL}/auth/v1"))).user_id == "user-1"


async def test_rejects_unrelated_issuer_even_with_custom_domain(monkeypatch):
    monkeypatch.setattr(settings, "supabase_custom_domain_url", CUSTOM_URL)
    with pytest.raises(HTTPException) as exc:
        await verify.verify_supabase_jwt(_token("https://evil.example.com/auth/v1"))
    assert exc.value.detail == "Invalid issuer"


async def test_rejects_token_without_issuer():
    claims = {"sub": "user-1", "aud": "authenticated", "exp": int(time.time()) + 300}
    token = jwt.encode(claims, _private_key, algorithm="RS256", headers={"kid": "test-kid"})
    with pytest.raises(HTTPException) as exc:
        await verify.verify_supabase_jwt(token)
    assert exc.value.detail == "Invalid issuer"
