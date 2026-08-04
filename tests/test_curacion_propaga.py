"""
El invariante que protege el foso: la verificación del corredor sobrevive al refresco
semanal y se propaga a todo el barrio (migración 023).

POR QUÉ ESTOS TESTS SON ESTÁTICOS. El fallo que hay que atrapar aquí no lanza una
excepción ni rompe un request: una query contra `pois_propios` en vez de `pois_vivos`
devuelve filas perfectamente válidas — solo que ignora al corredor que caminó hasta el
local y lo marcó cerrado. Todo "funciona"; el foso se apaga en silencio. Es exactamente
el género de fallo que documenta docs/AUDITORIA_Fallos_Silenciosos_2026-07-31.md, y no
hay DB de pruebas en este repo, así que el guard es sobre el texto del SQL.

Los dos frentes:
  1. LECTURA  — ningún camino de entorno puede leer la tabla cruda (se saltaría el overlay).
  2. ESCRITURA — el upsert del refresco no puede tocar nada que produzca el humano
                 (si lo tocara, el cron del lunes borraría la verificación).
"""
import logging
import re
from pathlib import Path

from app.entorno_curacion import aplicar_curacion, info_verificacion
from app.rutas import _avisar_capa_caida

_APP = Path(__file__).resolve().parents[1] / "app"
_SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"

# `FROM pois_propios` / `JOIN pois_propios` en el SQL embebido de un módulo.
_LEE_TABLA_CRUDA = re.compile(r"\b(?:FROM|JOIN)\s+pois_propios\b", re.I)


# ══ Frente 1 — las lecturas de entorno van contra la vista ═══════════════════════════
def test_rutas_no_lee_la_tabla_cruda_de_pois():
    """rutas.py sirve el entorno al comprador: TODAS sus lecturas pasan por el overlay.

    Si este test falla, alguien devolvió una query a `pois_propios` y con eso los POIs
    que un corredor cerró en terreno volvieron a mostrarse. No hay error visible: solo
    vuelve la farmacia fantasma.
    """
    sql = (_APP / "rutas.py").read_text(encoding="utf-8")
    assert not _LEE_TABLA_CRUDA.search(sql), (
        "app/rutas.py lee `pois_propios` directo. Las lecturas de entorno deben usar la "
        "vista `pois_vivos` (migración 023) o se saltan la curación del corredor."
    )


def test_rutas_usa_la_vista():
    """Contrapeso del test anterior: que no lea la tabla no basta si tampoco lee la vista
    (un refactor que borre las queries pasaría el test de arriba sin hacer nada)."""
    sql = (_APP / "rutas.py").read_text(encoding="utf-8")
    assert sql.count("FROM pois_vivos") >= 4, (
        "Se esperaban al menos 4 lecturas contra `pois_vivos` (entorno, transporte, "
        "nearest, dentro-de-isócrona)."
    )


def test_la_vista_no_filtra_operativo_por_su_cuenta():
    """`WHERE operativo` en el llamador anularía la resurrección por 'confirmado'.

    La vista ya resolvió quién vive. Si además el llamador exige `operativo`, un POI que
    el origen dio de baja pero un corredor confirmó en terreno queda fuera — y el humano
    que estuvo ahí ayer pierde contra un dataset del mes pasado.
    """
    sql = (_APP / "rutas.py").read_text(encoding="utf-8")
    for bloque in re.findall(r"FROM pois_vivos(.*?)\"\"\"", sql, re.S):
        assert not re.search(r"\bWHERE\s+operativo\b", bloque, re.I), (
            "Una query sobre `pois_vivos` vuelve a filtrar por `operativo`: rompe el "
            "caso 'el origen lo cerró pero el corredor lo confirmó'."
        )


# ══ Frente 2 — el refresco semanal no pisa el trabajo humano ═════════════════════════
def test_el_upsert_del_refresco_no_toca_columnas_de_verificacion():
    """El cron de los lunes hace ON CONFLICT DO UPDATE sobre pois_propios.

    Mientras la verificación viva en `entorno_curacion` (y no en columnas de
    `pois_propios`), el refresco es inofensivo por construcción. Este test falla el día
    que alguien intente "simplificar" moviendo la verificación a la tabla del origen:
    ahí el upsert del lunes empezaría a borrarla cada semana, en silencio.
    """
    src = (_SCRIPTS / "foso_pois_spike.py").read_text(encoding="utf-8")
    set_clause = re.search(r"_SET\s*=\s*\"\"\"(.*?)\"\"\"", src, re.S)
    assert set_clause, "No se encontró la cláusula _SET del upsert en foso_pois_spike.py"
    prohibidas = ("verificado", "curacion", "curación", "corredor", "poi_id")
    for col in prohibidas:
        assert col not in set_clause.group(1).lower(), (
            f"El upsert del refresco escribe '{col}'. La verificación humana NO puede "
            f"vivir en columnas que el origen sobrescribe cada lunes (migración 023)."
        )


def test_el_script_de_refresco_no_escribe_en_entorno_curacion():
    """La otra dirección: la ingesta nunca toca la tabla de observaciones humanas."""
    src = (_SCRIPTS / "foso_pois_spike.py").read_text(encoding="utf-8").lower()
    assert "entorno_curacion" not in src, (
        "El script de ingesta toca `entorno_curacion`. Esa tabla es de captura humana; "
        "el pipeline del origen no debe escribirla."
    )


# ══ La acción 'confirmado' no ensucia el texto ═══════════════════════════════════════
def test_confirmado_no_altera_el_texto_de_servicios():
    """'confirmado' es una acción de alcance CIUDAD (sobre el POI), no de texto.

    El lugar ya está listado en `servicios_cercanos`; confirmarlo no debe duplicarlo ni
    re-escribirlo. Solo sostiene vivo el POI en la vista.
    """
    texto = "🏥 Hospital Metropolitano a ~300 m · 💊 Fybeca a ~120 m"
    curaciones = [{"accion": "confirmado", "nombre": "Fybeca", "poi_id": 42,
                   "creado_en": "2026-08-04T10:00:00+00:00"}]
    assert aplicar_curacion(texto, curaciones) == texto


def test_confirmado_si_cuenta_como_verificacion_para_la_insignia():
    """Aunque no cambie el texto, el corredor SÍ estuvo ahí: la ficha queda verificada."""
    curaciones = [{"accion": "confirmado", "nombre": "Fybeca", "poi_id": 42,
                   "creado_en": "2026-08-04T10:00:00+00:00"}]
    info = info_verificacion(curaciones)
    assert info["verificado"] is True
    assert info["fecha"] == "2026-08-04"


# ══ La degradación se conserva; el silencio no ══════════════════════════════════════
def test_vista_ausente_se_reporta_como_error_con_la_migracion_a_aplicar(caplog):
    """Si falta `pois_vivos`, el producto sigue respondiendo — pero sin curación.

    Ese es el peor caso posible: todo "funciona", el comprador ve el entorno de Google
    y el trabajo de terreno del corredor no se aplica en ningún lado. Tiene que salir
    como ERROR y decir QUÉ correr, no como una advertencia genérica más.
    """
    with caplog.at_level(logging.WARNING, logger="foso"):
        _avisar_capa_caida("_servicios_propios",
                           Exception('relation "pois_vivos" does not exist'))
    reg = caplog.records[-1]
    assert reg.levelno == logging.ERROR
    assert "023" in reg.getMessage(), "el aviso debe nombrar la migración a aplicar"


def test_fallo_transitorio_no_se_reporta_como_error(caplog):
    """Contrapeso: un timeout no es un despliegue roto.

    Si ambos salieran como ERROR, el que sí exige acción quedaría enterrado entre
    ruido y el aviso dejaría de leerse — que es como se pierde un canal de alerta.
    """
    with caplog.at_level(logging.WARNING, logger="foso"):
        _avisar_capa_caida("_nearest_propio", TimeoutError("connection timed out"))
    reg = caplog.records[-1]
    assert reg.levelno == logging.WARNING
    assert "023" not in reg.getMessage()


def test_cerrado_sigue_quitando_del_texto_con_poi_id():
    """El enganche al POI no rompe el camino de texto: una curación con poi_id también
    limpia el texto de ESTA ficha, además de propagarse por la vista."""
    texto = "🏥 Hospital Metropolitano a ~300 m · 💊 Fybeca a ~120 m"
    curaciones = [{"accion": "cerrado", "nombre": "Fybeca", "poi_id": 42,
                   "creado_en": "2026-08-04T10:00:00+00:00"}]
    resultado = aplicar_curacion(texto, curaciones)
    assert "Fybeca" not in resultado
    assert "Hospital Metropolitano" in resultado
