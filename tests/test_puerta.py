"""
Tests del control de CONTACTO EN PROSA (B2) — lo que queda de `app/puerta.py`.

EXPECTED UPDATE · SURFACE RETIRED BY OFD-02 (Plan 1.1 · TR-1). Este fichero probaba la PUERTA
SUAVE: cuándo se ofrecía avisar por correo y cuándo no. La puerta se retiró porque prometía un
aviso que ningún código envía, y con ella salieron de aquí 15 funciones de test (30 casos) que
ejercían `evaluar_puerta`, `pidio_aviso`, `criterio_whitelist`, `ENCAJE_SUFICIENTE` y la promesa
fija — código que ya no existe. No se borraron por fallar: se retiraron con la superficie. Su
versión íntegra vive en `8d8dd683:tests/test_puerta.py`, y **tiene que volver** con la puerta si
algún día existe el consumidor (sobre todo las dos LÍNEAS ROJAS y la whitelist de `demanda`).

Lo que se conserva, sin tocar una línea, es el control hermano: el modelo no puede pedir el
contacto en prosa por su cuenta. La retirada de la puerta se prueba en
`tests/test_tr1_retiro_alerta.py`.
"""
import pytest

from app.puerta import detectar_solicitud_contacto


# ── El control hermano ──────────────────────────────────────────────────────────────

@pytest.mark.parametrize("texto", [
    "Déjame tu correo y te aviso",
    "¿Cuál es tu email?",
    "Necesito tu teléfono para continuar",
    "Escribe tu correo aquí abajo",
    "Dame tu whatsapp",
])
def test_caza_al_modelo_pidiendo_contacto_por_su_cuenta(texto):
    assert detectar_solicitud_contacto(texto), f"debió cazar: {texto}"


@pytest.mark.parametrize("texto", [
    # Mención legítima DESPUÉS de un handoff: el corredor ya tiene el canal.
    "El corredor te escribirá a tu correo en las próximas horas.",
    "Tu solicitud quedó registrada; te contactan por este chat.",
    # Hablar del inmueble, no de la persona.
    "El departamento tiene 2 dormitorios y está dentro de tu presupuesto.",
    "No tengo ese dato.",
    "",
])
def test_alta_precision_no_marca_la_mencion_legitima(texto):
    assert detectar_solicitud_contacto(texto) == [], f"falso positivo en: {texto}"
