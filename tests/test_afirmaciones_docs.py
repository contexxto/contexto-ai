"""Afirmaciones de estado ejecutables — la cura de raíz para los encabezados rancios.

EL PROBLEMA. La prosa no puede fallar. El código equivocado lanza una excepción, un test
equivocado se pone rojo; una frase equivocada se queda sentada siendo leída, y gana
autoridad con cada mes que pasa. Tres veces ya un encabezado rancio desvió una decisión:

  1. NORTHSTAR: "Fase 1 casi listo" con la Fase 1 shippeada.
  2. PLAN_Migracion §2.3: "`pois_propios` está vacía" — tenía 4.898 filas. El error se
     copió a dos planes y sobrevivió 19 días, porque cada copia parecía confirmación.
  3. SPEC_Mapa_Vivo: "spec — no implementado" con 2A y 2B construidos.

LA REGLA. Si un documento afirma estado, la afirmación viene en forma comprobable. No se
policían todos los docs: se policía el constructo que ya falló. Un doc que no dice nada
sobre estado no tiene nada que verificar.

FORMATO (comentario HTML, no se renderiza):

    <!-- estado-verificable
    codigo:
      existe: frontend/src/MapSeed.jsx
      existe: app/routers/chat.py::_map_seed_from_cards
      no-existe: app/legacy/mapa_viejo.py
    datos:
      2026-08-04: pois_propios tiene 8.499 filas operativas en quito
    -->

`no-existe:` es la que más importa: "no implementado" ES una afirmación de inexistencia,
y es exactamente la que falló dos de las tres veces.

DUREZA (decisión explícita, 2026-08-04):
  · Una afirmación `codigo:` FALSA pone rojo el build. Es el punto entero.
  · Una afirmación `datos:` sin re-verificar en 90 días pone rojo, con instrucción de
    cómo arreglarla. Caduca porque un dato de la DB no se puede comprobar en cada
    corrida y "verificado alguna vez" es indistinguible de "nunca".
  · Que un doc TENGA bloque es blando (se reporta, no falla): retrofitear 40 docs de
    golpe no es realista, y un build rojo que nadie puede arreglar se desactiva.
"""
import datetime as dt
import re
from pathlib import Path

import pytest

_RAIZ = Path(__file__).resolve().parents[1]
_DOCS = _RAIZ / "docs"

_BLOQUE = re.compile(r"<!--\s*estado-verificable\s*(.*?)-->", re.S)
_CLAIM_CODIGO = re.compile(r"^\s*(existe|no-existe):\s*(\S+)\s*$", re.M)
_CLAIM_DATOS = re.compile(r"^\s*(\d{4}-\d{2}-\d{2}):\s*(.+?)\s*$", re.M)

# Frases con las que un doc afirma su propio estado. Son las que exigen bloque.
_AFIRMA_ESTADO = re.compile(
    r"^\s*[>*\s]*\*{0,2}Estado:?\*{0,2}\s*[:—-]", re.M | re.I)

CADUCIDAD_DIAS = 90


def _docs_con_bloque() -> list[tuple[Path, str]]:
    return [(p, m.group(1))
            for p in sorted(_DOCS.rglob("*.md"))
            for m in _BLOQUE.finditer(p.read_text(encoding="utf-8"))]


def _existe(ref: str) -> bool:
    """`ruta` o `ruta::simbolo`. El símbolo debe estar DEFINIDO, no solo mencionado."""
    ruta, _, simbolo = ref.partition("::")
    f = _RAIZ / ruta
    if not f.exists():
        return False
    if not simbolo:
        return True
    txt = f.read_text(encoding="utf-8", errors="replace")
    # def/class (py) · const/let/var/function/export default function (js/jsx)
    patron = (rf"(?:^|\s)(?:async\s+)?(?:def|class|const|let|var|function)\s+{re.escape(simbolo)}\b"
              rf"|^{re.escape(simbolo)}\s*[:=]")
    return re.search(patron, txt, re.M) is not None


_CON_BLOQUE = _docs_con_bloque()


@pytest.mark.skipif(not _CON_BLOQUE, reason="ningún doc declara afirmaciones todavía")
@pytest.mark.parametrize("doc,cuerpo", _CON_BLOQUE, ids=lambda v: v.name if isinstance(v, Path) else "")
def test_afirmaciones_de_codigo_siguen_siendo_ciertas(doc, cuerpo):
    """Cada `existe:`/`no-existe:` se comprueba contra el árbol real."""
    fallos = []
    for tipo, ref in _CLAIM_CODIGO.findall(cuerpo):
        hay = _existe(ref)
        if tipo == "existe" and not hay:
            fallos.append(f"afirma `existe: {ref}` pero NO está en el árbol")
        if tipo == "no-existe" and hay:
            fallos.append(
                f"afirma `no-existe: {ref}` pero SÍ existe — el doc quedó rancio, que es "
                f"justo el fallo que esta regla persigue")
    assert not fallos, (
        f"\n{doc.relative_to(_RAIZ)} tiene afirmaciones falsas:\n  - "
        + "\n  - ".join(fallos)
        + "\n\nActualiza el doc (y su bloque estado-verificable) contra el código real.")


@pytest.mark.skipif(not _CON_BLOQUE, reason="ningún doc declara afirmaciones todavía")
@pytest.mark.parametrize("doc,cuerpo", _CON_BLOQUE, ids=lambda v: v.name if isinstance(v, Path) else "")
def test_afirmaciones_de_datos_no_estan_caducadas(doc, cuerpo):
    """Una afirmación sobre la DB no se puede comprobar en cada corrida: caduca.

    Sin caducidad, "verificado alguna vez" es indistinguible de "nunca" — que es
    exactamente cómo el "pois_propios está vacía" sobrevivió 19 días.
    """
    hoy = dt.date.today()
    viejas = []
    for fecha_txt, afirmacion in _CLAIM_DATOS.findall(cuerpo):
        try:
            fecha = dt.date.fromisoformat(fecha_txt)
        except ValueError:
            viejas.append(f"fecha ilegible: {fecha_txt}")
            continue
        dias = (hoy - fecha).days
        if dias > CADUCIDAD_DIAS:
            viejas.append(f'"{afirmacion}" verificada hace {dias} días ({fecha_txt})')
    assert not viejas, (
        f"\n{doc.relative_to(_RAIZ)} tiene afirmaciones de datos caducadas "
        f"(>{CADUCIDAD_DIAS} días):\n  - " + "\n  - ".join(viejas)
        + "\n\nArréglalo así: vuelve a correr la consulta, y (a) actualiza el dato y la "
          "fecha, o (b) borra la afirmación si ya no sostiene nada del doc.")


def test_reporte_de_docs_que_afirman_estado_sin_bloque(capsys):
    """BLANDO a propósito: informa, no falla.

    Exigirle bloque a los ~40 docs de golpe pondría el build rojo sin que nadie pueda
    arreglarlo hoy, y un build rojo inarreglable se desactiva — perdiendo también la
    parte dura, que sí funciona. Este reporte es la lista de adopción pendiente.
    """
    con_bloque = {p for p, _ in _CON_BLOQUE}
    pendientes = [p.relative_to(_RAIZ) for p in sorted(_DOCS.rglob("*.md"))
                  if p not in con_bloque and _AFIRMA_ESTADO.search(p.read_text(encoding="utf-8"))]
    if pendientes:
        with capsys.disabled():
            print(f"\n  [afirmaciones] {len(pendientes)} doc(s) afirman estado sin bloque "
                  f"verificable:")
            for p in pendientes[:12]:
                print(f"    · {p}")
            if len(pendientes) > 12:
                print(f"    … y {len(pendientes) - 12} más")
    assert True  # nunca falla; ver docstring
