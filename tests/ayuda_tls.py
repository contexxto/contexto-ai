"""Ancla de confianza para las pruebas que usan una URL REMOTA.

Desde R2C1 la política del núcleo exige `verify-full` contra un bundle para cualquier host
que no sea loopback, y falla cerrado si el bundle no está. La ruta de producción
(`/app/certs/supabase-ca-bundle.pem`) sólo existe dentro de la imagen, así que en un
checkout las pruebas que hablan de `aws-1-…pooler.supabase.com` toparían con esa guarda
antes de llegar a lo que quieren probar.

Se apunta al bundle VERSIONADO DEL REPO, que viaja en todo checkout y es exactamente el
mismo certificado que el Dockerfile copia a la ruta de producción. No es un certificado de
mentira: es el ancla real.

Deliberadamente NO es un fixture autouse global. Un módulo que necesita el ancla lo dice.
Si fuese automático para toda la suite, una prueba nueva podría depender del ancla sin
saberlo y el fallo-cerrado dejaría de verse donde tiene que verse.
"""
from pathlib import Path

import pytest

BUNDLE_DEL_REPO = Path(__file__).resolve().parents[1] / "certs" / "supabase" / "bundle-v1.pem"


@pytest.fixture(autouse=True)
def ancla_de_confianza(monkeypatch):
    assert BUNDLE_DEL_REPO.is_file(), f"falta el bundle versionado: {BUNDLE_DEL_REPO}"
    monkeypatch.setattr("app.db_tls.RUTA_BUNDLE", str(BUNDLE_DEL_REPO))
