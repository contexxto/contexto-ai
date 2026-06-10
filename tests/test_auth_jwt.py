"""
Tests offline del módulo app/auth.py (validación de JWT Supabase).
No tocan red: cubren los helpers puros.
"""
import pytest

from app import auth, config


def test_extract_token_bearer():
    assert auth._extract_token("Bearer abc.def.ghi") == "abc.def.ghi"
    assert auth._extract_token("bearer  xyz ") == "xyz"


@pytest.mark.parametrize("h", [None, "", "Token abc", "Bearer", "Bearer    "])
def test_extract_token_invalido(h):
    assert auth._extract_token(h) is None


def test_jwks_url_se_deriva_de_supabase_url(monkeypatch):
    monkeypatch.setattr(config.settings, "supabase_url", "https://demo.supabase.co/")
    assert auth._jwks_url() == "https://demo.supabase.co/auth/v1/.well-known/jwks.json"


def test_key_for_sin_coincidencia_devuelve_none():
    # token con header kid=abc; keys vacías → None (no crashea)
    import base64
    import json

    header = base64.urlsafe_b64encode(json.dumps({"alg": "ES256", "kid": "abc"}).encode()).rstrip(b"=")
    fake = header.decode() + ".e30.sig"
    assert auth._key_for(fake, []) is None


async def test_get_current_user_sin_token_lanza_401():
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc:
        await auth.get_current_user(authorization=None, db=None)
    assert exc.value.status_code == 401
