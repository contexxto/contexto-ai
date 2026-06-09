"""
Tests offline de app/embeddings.py — no tocan red ni DB real.

Cubren:
  - roundtrip to_pgvector_literal <-> _parse_pgvector (incluye casos borde)
  - _content_key (estable, hex de 64, sensible a input_type)
  - embed_text rechaza texto vacío
  - embed_text_cached: HIT devuelve cacheado sin llamar a Voyage;
                       MISS llama a Voyage y persiste; tabla ausente degrada bien
"""
import types

import pytest

from app import embeddings
from app.embeddings import (
    EmbeddingError,
    _content_key,
    _parse_pgvector,
    embed_text,
    embed_text_cached,
    to_pgvector_literal,
)


# ───────────────────────── helpers de prueba ─────────────────────────
class _Nested:
    """Stub de db.begin_nested() como context manager async."""

    def __init__(self, raise_on_enter: bool = False):
        self._raise = raise_on_enter

    async def __aenter__(self):
        if self._raise:
            raise RuntimeError("relation \"embedding_cache\" does not exist")
        return self

    async def __aexit__(self, *exc):
        return False


class _Result:
    def __init__(self, row):
        self._row = row

    def first(self):
        return self._row


class _FakeSession:
    """
    Sesión async falsa para probar embed_text_cached sin DB.

    - select_row: lo que devuelve .first() en el SELECT (None = miss).
    - nested_raises: si True, begin_nested() falla (simula migración ausente).
    """

    def __init__(self, select_row=None, nested_raises: bool = False):
        self._select_row = select_row
        self._nested_raises = nested_raises
        self.executed = []  # lista de SQL ejecutado (para asserts)

    def begin_nested(self):
        return _Nested(raise_on_enter=self._nested_raises)

    async def execute(self, sql, params=None):
        text = str(sql)
        self.executed.append(text)
        if text.strip().upper().startswith("SELECT"):
            return _Result(self._select_row)
        return _Result(None)


# ───────────────────────── pgvector roundtrip ─────────────────────────
@pytest.mark.parametrize("vec", [[0.1, -0.2, 3.0, 0.0], [1.5], [0.0, 0.0]])
def test_pgvector_roundtrip(vec):
    assert _parse_pgvector(to_pgvector_literal(vec)) == vec


def test_parse_pgvector_empty():
    assert _parse_pgvector("[]") == []


def test_parse_pgvector_invalid_raises():
    with pytest.raises(EmbeddingError):
        _parse_pgvector("0.1,0.2")  # sin corchetes


# ───────────────────────── content key ─────────────────────────
def test_content_key_is_stable_hex64():
    k1 = _content_key("hola mundo", "query")
    k2 = _content_key("hola mundo", "query")
    assert k1 == k2
    assert len(k1) == 64
    int(k1, 16)  # es hex válido


def test_content_key_sensitive_to_input_type():
    assert _content_key("x", "query") != _content_key("x", "document")


# ───────────────────────── embed_text vacío ─────────────────────────
async def test_embed_text_empty_raises():
    with pytest.raises(EmbeddingError):
        await embed_text("   ")


# ───────────────────────── embed_text_cached ─────────────────────────
async def test_cache_hit_no_llama_voyage(monkeypatch):
    """Si la caché tiene el vector, NO se llama a Voyage."""
    cached = [0.5, 0.25, -1.0]
    row = types.SimpleNamespace(e=to_pgvector_literal(cached))
    db = _FakeSession(select_row=row)

    async def _boom(*a, **k):  # embed_text NO debe ejecutarse
        raise AssertionError("embed_text no debería llamarse en un HIT de caché")

    monkeypatch.setattr(embeddings, "embed_text", _boom)

    out = await embed_text_cached(db, "consulta repetida", input_type="query")
    assert out == cached
    assert any("SELECT" in s.upper() for s in db.executed)


async def test_cache_miss_llama_voyage_y_persiste(monkeypatch):
    """En MISS: llama a Voyage una vez y escribe en la caché (INSERT)."""
    generated = [0.1, 0.2, 0.3]
    calls = {"n": 0}

    async def _fake_embed(text, input_type="document"):
        calls["n"] += 1
        return generated

    monkeypatch.setattr(embeddings, "embed_text", _fake_embed)

    db = _FakeSession(select_row=None)  # miss
    out = await embed_text_cached(db, "consulta nueva", input_type="query")

    assert out == generated
    assert calls["n"] == 1
    assert any("INSERT" in s.upper() for s in db.executed)


async def test_cache_tabla_ausente_degrada(monkeypatch):
    """Si begin_nested falla (migración 007 no aplicada), igual devuelve el vector."""
    generated = [9.0, 8.0]

    async def _fake_embed(text, input_type="document"):
        return generated

    monkeypatch.setattr(embeddings, "embed_text", _fake_embed)

    db = _FakeSession(nested_raises=True)
    out = await embed_text_cached(db, "algo", input_type="query")
    assert out == generated  # no explota pese a la caché rota
