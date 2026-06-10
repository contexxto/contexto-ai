"""
Tests del asignador heurístico de scores por sector (scripts/scores_heuristicos.py).
Offline y determinístico.
"""
import importlib.util
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent.parent
_SPEC = importlib.util.spec_from_file_location(
    "scores_heuristicos", _ROOT / "scripts" / "scores_heuristicos.py"
)
sh = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(sh)  # type: ignore[union-attr]


@pytest.mark.parametrize(
    "direccion,esperado",
    [
        ("Av. República del Salvador, La Carolina, Quito", "La Carolina"),
        ("Calle Los Shyris N35-61", "La Carolina"),
        ("Av. Pampite, Cumbayá", "Cumbayá"),
        ("Av. Colón y 12 de Octubre, La Mariscal", "La Mariscal"),
        ("Av. González Suárez N27-160", "González Suárez"),
        ("El Condado Shopping", "El Condado"),
        ("Av. La Prensa, Cotocollao", "Cotocollao"),
    ],
)
def test_detecta_sector(direccion, esperado):
    assert sh.detectar_sector(direccion) == esperado


def test_sector_desconocido_es_none():
    assert sh.detectar_sector("Calle inventada 123, Marte") is None


def test_scores_determinista():
    a = sh.scores_para("Av. Pampite y Chimborazo, Cumbayá")
    b = sh.scores_para("Av. Pampite y Chimborazo, Cumbayá")
    assert a == b  # mismo input → mismo output (reproducible)


def test_scores_en_rangos_validos():
    sc = sh.scores_para("Av. República del Salvador, La Carolina")
    assert 0 <= sc["walk_score"] <= 100
    assert 0.0 <= sc["porcentaje_cobertura_vegetal"] <= 100.0
    assert sc["score_ruido_predictivo"] in ("BAJO", "MEDIO", "ALTO")
    assert sc["volumen_trafico_historico"] >= 0


def test_default_para_sector_desconocido():
    sc = sh.scores_para("Lugar sin sector reconocible")
    assert "default" in sc["sector_detectado"]


def test_local_comercial_sube_ruido():
    # Cumbayá base = BAJO; un local comercial allí debería subir a MEDIO.
    base = sh.scores_para("Av. Pampite, Cumbayá", tipo_activo="Departamento")
    local = sh.scores_para("Av. Pampite, Cumbayá", tipo_activo="Local Comercial")
    orden = {"BAJO": 0, "MEDIO": 1, "ALTO": 2}
    assert orden[local["score_ruido_predictivo"]] >= orden[base["score_ruido_predictivo"]]
    assert orden[local["score_ruido_predictivo"]] > orden["BAJO"] - 1
