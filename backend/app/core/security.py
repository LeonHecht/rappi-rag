from __future__ import annotations

from typing import Dict

import jwt
from jwt import PyJWKClient

from .config import settings

# Deprecated token store kept only for older local tests/helpers that still
# import verify_access_token directly.
tokens_db: Dict[str, str] = {}


def get_supabase_jwks_url() -> str | None:
    """Return the configured or conventional Supabase JWKS endpoint."""
    if settings.SUPABASE_JWKS_URL:
        return settings.SUPABASE_JWKS_URL
    if settings.SUPABASE_URL:
        return f"{settings.SUPABASE_URL.rstrip('/')}/auth/v1/.well-known/jwks.json"
    return None


def verify_supabase_token(token: str) -> dict:
    """Verify a Supabase Auth user access token via JWT signing keys.

    Publishable and secret API keys (`sb_publishable_...` / `sb_secret_...`)
    are opaque API keys, not user JWTs. The frontend must send the signed-in
    user's Supabase Auth access token in the Authorization header.
    """
    if token.startswith("sb_publishable_") or token.startswith("sb_secret_"):
        raise ValueError("Supabase API keys are not user access tokens")

    jwks_url = get_supabase_jwks_url()
    if not jwks_url:
        raise ValueError("Unable to verify token: SUPABASE_URL or SUPABASE_JWKS_URL is required")

    try:
        jwk_client = PyJWKClient(jwks_url)
        signing_key = jwk_client.get_signing_key_from_jwt(token)
        return jwt.decode(
            token,
            signing_key.key,
            algorithms=["ES256", "RS256"],
            options={"verify_aud": False},  # Supabase uses aud='authenticated'
        )
    except jwt.ExpiredSignatureError:
        raise ValueError("Token has expired")
    except jwt.InvalidTokenError as e:
        raise ValueError(f"Invalid token: {str(e)}")
    except Exception as e:
        raise ValueError(f"Unable to verify token via Supabase JWKS: {e}")


def verify_access_token(token: str) -> dict:
    """Deprecated compatibility wrapper for older tests/helpers."""
    try:
        return verify_supabase_token(token)
    except ValueError:
        pass

    username = tokens_db.get(token)
    if not username:
        raise ValueError("Invalid token")
    return {"sub": username, "email": username}
