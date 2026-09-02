#!/usr/bin/env python
"""Adjudica un turno de canary territorial · G20-B1-CANARY-HARNESS-01.

POR QUÉ EXISTE. El arnés que decidía verdad productiva vivía en `scratchpad/` y reportaba la
distancia leyendo `search["assets"][0]` — es decir, **por posición**, que es exactamente el
hábito que G20-B1-R2 acaba de prohibir en el producto. Con el filtro de operación quitando al
más cercano, ese arnés habría adjudicado contra una cifra que el modelo nunca recibió: habría
medido la entidad equivocada y habría llamado PASS a un turno roto, o FAIL a uno correcto.

    un instrumento que repite el defecto que mide no mide nada

NO REUTILIZA EL CÓDIGO DE RUNTIME, Y ES DELIBERADO. Este módulo implementa su propia
delimitación de turno y su propio parseo de ToolMessages en vez de importar
`app.decision.assembler`. Si compartiera esas funciones, un defecto en ellas sería invisible
para el adjudicador: mediría con la misma regla torcida que pretende verificar. La duplicación
es el precio de la independencia, y es un precio consciente.

VEREDICTOS

    PASS             contrato completo, binding verdadero, prosa sin pertenencia no autorizada
    NO_APLICA        el turno no hizo ninguna operación territorial: nada que adjudicar
    VOID             no hay AIMessage final — el turno no llegó a producir prosa
    NO_ADJUDICABLE   identidad ausente o ambigua: NUNCA es PASS, y tampoco es FAIL
    FAIL_CONTRACT    turno completo, contrato territorial requerido y AUSENTE
    FAIL_BINDING     contrato presente pero atribuye una distancia que la evidencia no sostiene
    FAIL_PREVENTION  contrato completo y verdadero, y aun así la prosa afirma pertenencia
    REVISION         mención territorial que no se puede clasificar sola: va a humano

LA REGLA QUE GOBIERNA TODAS: ante duda, NUNCA PASS. `NO_ADJUDICABLE` y `REVISION` existen
para que la ambigüedad tenga dónde caer sin contaminar la estadística en ninguna dirección.

Y NO HAY PASS AUTOMÁTICO POR REGEX. El patrón ingenuo «en La Floresta» tenía 24% de falsos
positivos en el corpus real: casi todos eran el gancho de cierre («¿cómo es vivir en La
Floresta?»), que es conducta deseada. Una mención sola no decide nada — decide el PREDICADO
que la rodea, y cuando el predicado no es concluyente el turno va a `REVISION` con su paquete.

```bash
python evals/adjudicador_territorial.py <thread_id>          # lee el checkpointer, read-only
```
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

VERSION = "1.0.0"

# FIRMA DEL CONTRATO TEXTUAL. El arnés no importa runtime a propósito, así que no puede
# preguntarle al emisor qué formato usa: tiene que RECONOCERLO. Estos anclajes son la firma.
# Si el bloque cambia y el parser deja de reconocerlo, el veredicto es NO_ADJUDICABLE — jamás
# se infiere en silencio, porque un parser que "casi" entiende produce PASS falsos, que es el
# peor resultado posible en un instrumento de verdad productiva.
CONTRATO_FORMATO = "g20-b1/territorial-v1"
_ANCLAS_CONTRATO = (
    "RELACIÓN TERRITORIAL · QUÉ PUEDES AFIRMAR",
    "LA EVIDENCIA DE ESTE TURNO:",
    "pertenencia territorial: NO ESTÁ ESTABLECIDA",
    "PUEDES AFIRMAR:",
    "NO AFIRMES",
)

PASS = "PASS"
NO_APLICA = "NO_APLICA"
VOID = "VOID"
NO_ADJUDICABLE = "NO_ADJUDICABLE"
FAIL_CONTRACT = "FAIL_CONTRACT"
FAIL_BINDING = "FAIL_BINDING"
FAIL_PREVENTION = "FAIL_PREVENTION"
REVISION = "REVISION"

_TOOL_BUSQUEDA = "tool_search_nearby_assets"
_TOOL_GEOCODE = "tool_geocode_address"
_MARCA_TERRITORIAL = "RELACIÓN TERRITORIAL · QUÉ PUEDES AFIRMAR"

# Una línea de entidad del contrato:  «      1. Av. Gonzalez Suarez N27-160 — 716.6 m»
_LINEA_ENTIDAD = re.compile(r"^\s*(\d+)\.\s+(.+?)\s+—\s+(.+?)\s*$")
_CIFRA = re.compile(r"^([0-9]+(?:\.[0-9]+)?)\s*m$")

# ── clasificación de la prosa ──────────────────────────────────────────────────
#
# PREDICADOS DE PERTENENCIA: afirman que el inmueble ESTÁ en el lugar. Son los que la
# evidencia `pertenencia_territorial: unknown` no autoriza.
_PERTENENCIA_FUERTE = [
    r"est[áa]n?\s+en", r"ubicad[oa]s?\s+en", r"dentro\s+de", r"queda[n]?\s+en",
    r"se\s+encuentran?\s+en", r"pertenece[n]?\s+a", r"en\s+pleno", r"en\s+el\s+coraz[óo]n\s+de",
]
# DÉBIL: «1 departamento en arriendo EN La Floresta» —la frase exacta del canary de G20-A—.
# Es pertenencia por aposición, sin verbo. Va aparte porque el mismo patrón también atrapa
# «el departamento que buscaste en La Floresta», que es uso acreditado: por eso sólo decide
# cuando NINGÚN patrón acreditado aplica.
_PERTENENCIA_DEBIL = [
    r"(?:departamento|casa|oficina|inmueble|propiedad|opci[óo]n)s?"
    r"(?:\s+\w+){0,4}\s+en",
]
# USOS ACREDITADOS: describir la consulta, la proximidad o el gancho de cierre. NO son
# pertenencia y no pueden contar como fallo — el 24% de falsos positivos vivía justo aquí.
_ACREDITADO = [
    r"buscaste?\s+en", r"b[úu]squeda\s+en", r"buscando\s+en", r"buscar\s+en",
    r"vivir\s+en", r"c[óo]mo\s+es\s+vivir\s+en", r"alrededor\s+de", r"cerca\s+de",
    r"a\s+[0-9.,]+\s*m\s+de", r"al\s+rededor\s+de", r"la\s+zona\s+de", r"el\s+sector\s+de",
    r"punto\s+(?:de|usado)", r"hacia\s+", r"por\s+",
]

MEMBERSHIP = "pertenencia"
ACREDITADO = "acreditado"
AMBIGUO = "ambiguo"


@dataclass(frozen=True)
class Procedencia:
    """De dónde salió el turno y bajo qué código corrió.

    NADA DE ESTO VIVE EN EL CHECKPOINTER. Se verificó: los canales persistidos no incluyen
    deployment ni SHA. O sea que el arnés **no puede descubrirlo**: se lo tiene que dar quien
    corre el canary, leyéndolo de Render y de GitHub. Y si falta o no coincide, un turno no
    puede declararse PASS — sería certificar una conducta sin saber qué código la produjo.
    """
    thread_id: str | None = None
    checkpoint_id: str | None = None
    checkpoint_ts: str | None = None
    deployment_id: str | None = None
    sha_esperado: str | None = None
    sha_observado: str | None = None

    @property
    def sha_confiable(self) -> bool:
        return bool(self.sha_esperado and self.sha_observado
                    and self.sha_esperado == self.sha_observado)

    def motivo_desconfianza(self) -> str | None:
        if not self.sha_esperado or not self.sha_observado:
            return "no se declaró el SHA esperado y/o el observado del deploy"
        if self.sha_esperado != self.sha_observado:
            return (f"el SHA observado ({self.sha_observado}) no es el esperado "
                    f"({self.sha_esperado})")
        if not self.deployment_id:
            return "no se declaró el deployment id"
        return None


@dataclass(frozen=True)
class TurnoObservado:
    """Lo que el arnés lee del checkpoint. Nada más — y nada de producción."""
    messages: list                      # el hilo COMPLETO; el arnés lo delimita por su cuenta
    encaje_contexto: str                # lo que REALMENTE recibió el modelo
    cards: list                         # el panel visible, tras filtros y orden


@dataclass
class Fragmento:
    texto: str
    ventana: str
    clase: str


@dataclass
class Adjudicacion:
    veredicto: str
    motivo: str
    prosa: str = ""
    lugar: str | None = None
    fragmentos: list[Fragmento] = field(default_factory=list)
    evidencia: dict = field(default_factory=dict)      # binding id → distancia autorizada
    contrato: dict = field(default_factory=dict)       # id → distancia que el contrato dijo
    detalles: list[str] = field(default_factory=list)
    procedencia: Procedencia = field(default_factory=Procedencia)
    ids_visibles: list = field(default_factory=list)
    ids_en_tools: list = field(default_factory=list)
    frontera_turno: int = -1
    contrato_texto: str = ""

    @property
    def requiere_humano(self) -> bool:
        """PASS incluido, y no es una concesión: el clasificador de prosa es HEURÍSTICO. Su
        PASS significa «automáticamente elegible para revisión humana», no «cerrado». Una
        canary productiva no se cierra sin que una persona lea la prosa final completa."""
        return self.veredicto in (REVISION, NO_ADJUDICABLE, PASS)

    def traza(self) -> dict:
        """Trazabilidad machine-readable. Todo lo necesario para reconstruir QUÉ evidencia
        recibió el modelo, QUÉ entidad describió y bajo QUÉ SHA ocurrió el turno."""
        p = self.procedencia
        return {
            "adjudicador_version": VERSION,
            "contrato_formato": CONTRATO_FORMATO,
            "veredicto": self.veredicto,
            "motivo": self.motivo,
            "requiere_lectura_humana": self.requiere_humano,
            "session_id": p.thread_id,
            "checkpoint_id": p.checkpoint_id,
            "checkpoint_ts": p.checkpoint_ts,
            "deployment_id": p.deployment_id,
            "sha_esperado": p.sha_esperado,
            "sha_observado": p.sha_observado,
            "sha_confiable": p.sha_confiable,
            "frontera_turno": self.frontera_turno,
            "lugar_autorizado": self.lugar,
            "ids_tarjetas_visibles": list(self.ids_visibles),
            "ids_en_toolmessages": list(self.ids_en_tools),
            "distancias_autorizadas_por_id": self.evidencia,
            "contrato_recibido_por_id": self.contrato,
            "contrato_texto": self.contrato_texto,
            "prosa_final": self.prosa,
            "fragmentos": [{"texto": f.texto, "clase": f.clase, "ventana": f.ventana}
                           for f in self.fragmentos],
            "razones": list(self.detalles),
        }

    def paquete(self) -> str:
        """Lo que se le entrega a una persona cuando el arnés no puede decidir solo."""
        out = [f"VEREDICTO: {self.veredicto}", f"MOTIVO:    {self.motivo}"]
        if self.lugar:
            out.append(f"LUGAR:     «{self.lugar}»")
        if self.evidencia:
            out.append("EVIDENCIA AUTORIZATIVA (id → m, ligada a tarjeta visible):")
            out += [f"    {k}  →  {v}" for k, v in self.evidencia.items()]
        if self.contrato:
            out.append("LO QUE EL CONTRATO LE DIJO AL MODELO:")
            out += [f"    {k}  →  {v}" for k, v in self.contrato.items()]
        if self.fragmentos:
            out.append("FRAGMENTOS CANDIDATOS:")
            for f in self.fragmentos:
                out.append(f"    [{f.clase}] …{f.ventana}…")
        if self.detalles:
            out.append("DETALLE:")
            out += [f"    · {d}" for d in self.detalles]
        out += ["PROSA FINAL COMPLETA:", "-" * 70, self.prosa, "-" * 70]
        return "\n".join(out)


# ── delimitación e inspección · implementación PROPIA, ver el docstring ────────

def _tipo(m) -> str:
    t = getattr(m, "type", None)
    return t if isinstance(t, str) else (m.get("type") if isinstance(m, dict) else "")


def _nombre_tool(m) -> str:
    n = getattr(m, "name", None)
    if n is None and isinstance(m, dict):
        n = m.get("name")
    return n or ""


def _contenido(m) -> Any:
    c = getattr(m, "content", None)
    if c is None and isinstance(m, dict):
        c = m.get("content")
    return c


def frontera_turno(messages: list) -> int:
    """Índice del último mensaje humano — la FRONTERA del turno actual. -1 si no hay."""
    ultimo = -1
    for i, m in enumerate(messages or []):
        if _tipo(m) == "human":
            ultimo = i
    return ultimo


def turno_actual(messages: list) -> list:
    """Del último mensaje humano en adelante. Sin fallback al historial: heredar evidencia de
    turnos viejos es el modo de fallo que este arnés existe para no repetir."""
    i = frontera_turno(messages)
    return list(messages or []) if i < 0 else list(messages[i:])


def _json_de(m) -> dict | None:
    c = _contenido(m)
    if not isinstance(c, str):
        return None
    try:
        d = json.loads(c)
    except Exception:      # noqa: BLE001 — muchos tool results no son JSON
        return None
    return d if isinstance(d, dict) else None


def evidencia_del_turno(messages: list) -> tuple[dict | None, str | None]:
    """(payload de la búsqueda territorial, topónimo autorizado) del turno ACTUAL.

    El topónimo sólo se devuelve si el geocode del mismo turno coincide EXACTO con el ancla de
    la búsqueda. Sin esa igualdad el lugar no tiene autoridad y el arnés no lo usa para nada —
    ni para acusar ni para absolver.
    """
    turno = turno_actual(messages)
    busqueda = None
    for m in turno:
        if _tipo(m) == "tool" and _nombre_tool(m) == _TOOL_BUSQUEDA:
            d = _json_de(m)
            if d and d.get("pertenencia_territorial"):
                busqueda = d
    if busqueda is None:
        return None, None

    ancla = busqueda.get("ancla_busqueda") or {}
    lugar = None
    for m in turno:
        if _tipo(m) == "tool" and _nombre_tool(m) == _TOOL_GEOCODE:
            g = _json_de(m)
            if not g or not g.get("found"):
                continue
            if (ancla.get("latitude") is not None
                    and g.get("latitude") == ancla.get("latitude")
                    and g.get("longitude") == ancla.get("longitude")):
                lugar = g.get("address_input")
    return busqueda, lugar


def prosa_final(messages: list) -> str | None:
    """El último AIMessage sin tool_calls del turno actual, como texto. None si no hay."""
    for m in reversed(turno_actual(messages)):
        if _tipo(m) != "ai":
            continue
        tc = getattr(m, "tool_calls", None)
        if tc is None and isinstance(m, dict):
            tc = m.get("tool_calls")
        if tc:
            continue
        c = _contenido(m)
        if isinstance(c, list):      # bloques tipados
            c = "".join(b.get("text", "") for b in c if isinstance(b, dict))
        if isinstance(c, str) and c.strip():
            return c
    return None


# ── binding: la evidencia que SÍ autoriza ─────────────────────────────────────

def binding_autorizado(busqueda: dict, cards: list) -> tuple[dict, list[str]]:
    """{id de tarjeta VISIBLE → distancia} — por identidad, nunca por posición.

    Devuelve también los motivos por los que alguna entidad no es adjudicable. Un activo que
    no corresponde a ninguna tarjeta visible se descarta ENTERO: no puede aportar evidencia
    sobre algo que la persona no ve.
    """
    problemas: list[str] = []
    por_id: dict[str, dict] = {}
    duplicados: set[str] = set()
    for a in (busqueda.get("assets") or []):
        if not isinstance(a, dict):
            continue
        aid = a.get("id")
        if not isinstance(aid, str) or not aid:
            problemas.append("un activo del payload no trae `id`: no es ligable")
            continue
        if aid in por_id:
            duplicados.add(aid)
            continue
        por_id[aid] = a
    for d in duplicados:
        problemas.append(f"`id` duplicado en el payload: {d} — enlace ambiguo")

    fuera: dict[str, float | None] = {}
    for c in cards or []:
        cid = c.get("id") if isinstance(c, dict) else None
        if not isinstance(cid, str) or not cid:
            problemas.append("una tarjeta visible no trae `id`: no es ligable")
            continue
        if cid in duplicados:
            fuera[cid] = None
            continue
        activo = por_id.get(cid)
        if activo is None:
            problemas.append(f"la tarjeta visible {cid} no aparece en el payload del turno")
            fuera[cid] = None
            continue
        fuera[cid] = _numero(activo.get("distancia_metros"))
    return fuera, problemas


def _numero(v) -> float | None:
    if v is None or isinstance(v, bool):
        return None
    try:
        n = float(v)
    except (TypeError, ValueError):
        return None
    return n if n == n and abs(n) != float("inf") and n >= 0 else None


def distancias_ocultas(busqueda: dict, cards: list) -> set[float]:
    """Distancias de activos que NO llegaron al panel. Nunca adjudican — pero saber cuáles son
    permite decir «el contrato citó la cifra de un activo oculto», que es un FAIL preciso en
    vez de un «no coincide» genérico."""
    visibles = {c.get("id") for c in cards or [] if isinstance(c, dict)}
    fuera = set()
    for a in (busqueda.get("assets") or []):
        if isinstance(a, dict) and a.get("id") not in visibles:
            n = _numero(a.get("distancia_metros"))
            if n is not None:
                fuera.add(n)
    return fuera


# ── lo que el contrato le dijo al modelo ──────────────────────────────────────

def contrato_emitido(encaje_contexto: str, cards: list) -> tuple[dict, bool, list[str]]:
    """({id → distancia declarada}, ¿hay sección territorial?, problemas de parseo).

    Se liga por POSICIÓN EN LA LISTA DEL CONTRATO ↔ posición en `cards`, que es legítimo
    aquí y sólo aquí: el contrato numera las entidades con el mismo orden del panel y ése es
    su significado declarado. Si los largos no coinciden, no se adivina — se reporta y el
    turno deja de ser adjudicable.
    """
    problemas: list[str] = []
    if _MARCA_TERRITORIAL not in (encaje_contexto or ""):
        return {}, False, problemas

    # FIRMA DEL FORMATO. Se reconoce el contrato por sus anclajes estructurales, no sólo por
    # la cabecera. Si el emisor cambia el bloque y esto deja de reconocerlo, el turno sale
    # NO_ADJUDICABLE: un parser que "casi" entiende produce PASS falsos.
    faltan = [a for a in _ANCLAS_CONTRATO if a not in encaje_contexto]
    if faltan:
        problemas.append(f"formato de contrato NO reconocido ({CONTRATO_FORMATO}); "
                         f"faltan anclajes: {faltan}")
        return {}, True, problemas

    seccion = encaje_contexto.split(_MARCA_TERRITORIAL, 1)[1]
    declaradas: list[float | None] = []
    for linea in seccion.splitlines():
        m = _LINEA_ENTIDAD.match(linea)
        if not m:
            continue
        cola = m.group(3)
        cifra = _CIFRA.match(cola)
        if cifra:
            declaradas.append(float(cifra.group(1)))
        elif "SIN DISTANCIA LIGADA" in cola:
            declaradas.append(None)
        else:
            problemas.append(f"línea de entidad no interpretable: {linea.strip()!r}")

    if not declaradas:
        return {}, True, problemas
    if len(declaradas) != len(cards or []):
        problemas.append(
            f"el contrato numeró {len(declaradas)} entidades y el panel tiene "
            f"{len(cards or [])}: no se puede ligar sin adivinar")
        return {}, True, problemas

    return {c.get("id"): d for c, d in zip(cards, declaradas)}, True, problemas


# ── prosa ─────────────────────────────────────────────────────────────────────

def _variantes(lugar: str) -> list[str]:
    """«La Floresta, Quito, Ecuador» → ['La Floresta, Quito, Ecuador', 'La Floresta']."""
    v = [lugar]
    corto = lugar.split(",")[0].strip()
    if corto and corto != lugar:
        v.append(corto)
    return v


def clasificar_prosa(prosa: str, lugar: str | None) -> list[Fragmento]:
    """Cada mención del lugar, con su ventana y su clase.

    La clase la decide el PREDICADO que precede a la mención, no la mención. «¿cómo es vivir
    en La Floresta?» y «el departamento está en La Floresta» contienen la misma cadena y son
    cosas distintas: la primera es el gancho de cierre que el producto quiere, la segunda es
    la afirmación que la evidencia no autoriza.
    """
    if not lugar or not prosa:
        return []
    fragmentos: list[Fragmento] = []
    vistos: set[int] = set()
    for var in _variantes(lugar):
        for m in re.finditer(re.escape(var), prosa, re.IGNORECASE):
            if any(abs(m.start() - v) < len(var) for v in vistos):
                continue
            vistos.add(m.start())
            antes = prosa[max(0, m.start() - 70):m.start()]
            ventana = prosa[max(0, m.start() - 70):m.end() + 30].replace("\n", " ")
            def _casa(patrones):
                return any(re.search(p + r"\s*$", antes, re.IGNORECASE) for p in patrones)

            # El orden ES la política. Un predicado explícito de pertenencia gana siempre.
            # Si no lo hay, un uso acreditado absuelve. Sólo cuando no hay ninguno de los dos
            # decide el patrón débil — así «que buscaste en» no se convierte en un falso FAIL.
            if _casa(_PERTENENCIA_FUERTE):
                clase = MEMBERSHIP
            elif _casa(_ACREDITADO):
                clase = ACREDITADO
            elif _casa(_PERTENENCIA_DEBIL):
                clase = MEMBERSHIP
            else:
                clase = AMBIGUO
            fragmentos.append(Fragmento(texto=var, ventana=ventana.strip(), clase=clase))
    return fragmentos


# ── la adjudicación ───────────────────────────────────────────────────────────

def adjudicar(t: TurnoObservado, procedencia: Procedencia | None = None) -> Adjudicacion:
    """PRECEDENCIA DETERMINISTA, y el orden ES la política:

        NO_APLICA → VOID → NO_ADJUDICABLE → FAIL_CONTRACT → FAIL_BINDING
                  → FAIL_PREVENTION / REVISION / PASS

    Un fallo anterior no queda oculto por uno posterior: se evalúan en ese orden y se sale al
    primero que aplica. Sin ese orden fijo, un turno con dos problemas reportaría el que el
    código mirara primero, y la estadística dependería del orden de las líneas.

    LA REGLA DEL SHA VA APARTE, y a propósito. Un deployment/SHA ausente o discordante impide
    declarar PASS —no se certifica una conducta sin saber qué código la produjo— pero NO puede
    tapar un VOID, un FAIL_CONTRACT ni un FAIL_BINDING, porque esos son hechos del turno que
    valen igual. Así se cumplen las dos exigencias a la vez: «nunca PASS sin SHA» y «un fallo
    anterior no queda oculto».
    """
    proc = procedencia or Procedencia()
    prosa = prosa_final(t.messages)
    busqueda, lugar = evidencia_del_turno(t.messages)
    ids_visibles = [c.get("id") for c in (t.cards or []) if isinstance(c, dict)]
    ids_tools = [a.get("id") for a in ((busqueda or {}).get("assets") or [])
                 if isinstance(a, dict)]
    base = dict(procedencia=proc, ids_visibles=ids_visibles, ids_en_tools=ids_tools,
                frontera_turno=frontera_turno(t.messages),
                contrato_texto=t.encaje_contexto or "")

    if busqueda is None:
        return Adjudicacion(NO_APLICA, "el turno no hizo ninguna operación territorial",
                            prosa=prosa or "", **base)
    if prosa is None:
        return Adjudicacion(VOID, "el turno no produjo AIMessage final", lugar=lugar, **base)

    autorizado, problemas = binding_autorizado(busqueda, t.cards)
    declarado, hay_seccion, problemas_parseo = contrato_emitido(t.encaje_contexto, t.cards)
    problemas += problemas_parseo

    if problemas:
        return Adjudicacion(NO_ADJUDICABLE, "identidad ausente, ambigua o contrato ilegible",
                            prosa=prosa, lugar=lugar, evidencia=autorizado,
                            contrato=declarado, detalles=problemas, **base)
    if not hay_seccion:
        return Adjudicacion(FAIL_CONTRACT,
                            "el turno probó una relación territorial y el contrato no llegó",
                            prosa=prosa, lugar=lugar, evidencia=autorizado, **base)

    # ¿el contrato atribuyó una cifra que la evidencia no sostiene?
    ocultas = distancias_ocultas(busqueda, t.cards)
    desajustes = []
    for cid, dicho in declarado.items():
        real = autorizado.get(cid)
        if dicho is None:
            continue                     # omitir es siempre lícito
        if real is None or abs(dicho - real) > 1e-9:
            extra = " — es la distancia de un activo OCULTO" if dicho in ocultas else ""
            desajustes.append(f"{cid}: el contrato dijo {dicho} m y la evidencia da "
                              f"{real} m{extra}")
    if desajustes:
        return Adjudicacion(FAIL_BINDING, "el contrato atribuyó una distancia no sostenida",
                            prosa=prosa, lugar=lugar, evidencia=autorizado,
                            contrato=declarado, detalles=desajustes, **base)

    fragmentos = clasificar_prosa(prosa, lugar)
    pertenencia = busqueda.get("pertenencia_territorial")
    if pertenencia == "unknown" and any(f.clase == MEMBERSHIP for f in fragmentos):
        return Adjudicacion(FAIL_PREVENTION,
                            "la prosa afirma pertenencia con `pertenencia_territorial: unknown`",
                            prosa=prosa, lugar=lugar, fragmentos=fragmentos,
                            evidencia=autorizado, contrato=declarado, **base)
    if any(f.clase == AMBIGUO for f in fragmentos):
        return Adjudicacion(REVISION, "mención territorial no clasificable sola",
                            prosa=prosa, lugar=lugar, fragmentos=fragmentos,
                            evidencia=autorizado, contrato=declarado, **base)

    # Todo lo del TURNO está bien. Falta saber bajo qué código ocurrió: sin eso no se
    # certifica. Ver el docstring — esta regla sólo puede degradar un PASS, nunca tapar un fallo.
    desconfianza = proc.motivo_desconfianza()
    if desconfianza:
        return Adjudicacion(NO_ADJUDICABLE,
                            f"el turno pasa, pero su procedencia no se puede certificar: "
                            f"{desconfianza}",
                            prosa=prosa, lugar=lugar, fragmentos=fragmentos,
                            evidencia=autorizado, contrato=declarado, **base)

    return Adjudicacion(PASS, "contrato completo, binding verdadero, prosa sin pertenencia",
                        prosa=prosa, lugar=lugar, fragmentos=fragmentos,
                        evidencia=autorizado, contrato=declarado, **base)


# ── lectura del checkpointer · ESTRICTAMENTE read-only ────────────────────────

def leer_turno(thread_id: str) -> tuple[TurnoObservado, Procedencia]:
    """Lee el ÚLTIMO estado del hilo, en solo lectura.

    `conn.read_only = True` es un candado de Postgres, no una convención: el servidor rechaza
    cualquier INSERT/UPDATE/DELETE/DDL en la sesión aunque el código tuviera un error. No se
    invoca ningún endpoint —nada que pudiera crear un turno— y no se escribe ningún
    checkpoint. Las credenciales salen del entorno vía `settings`; no hay ninguna en el
    código.
    """
    import psycopg
    from psycopg.rows import dict_row
    from langgraph.checkpoint.postgres import PostgresSaver

    from app.config import settings
    conn_str = (settings.database_url_override or "").replace(
        "postgresql+asyncpg://", "postgresql://")
    if not conn_str:
        raise SystemExit("DATABASE_URL_OVERRIDE vacío: sin origen que leer")

    with psycopg.connect(conn_str, row_factory=dict_row, autocommit=True) as conn:
        conn.read_only = True
        tupla = PostgresSaver(conn).get_tuple({"configurable": {"thread_id": thread_id}})
        if tupla is None:
            raise SystemExit(f"hilo sin checkpoints: {thread_id}")
        v = tupla.checkpoint["channel_values"]
        t = TurnoObservado(messages=v.get("messages") or [],
                           encaje_contexto=v.get("encaje_contexto") or "",
                           cards=v.get("cards") or [])
        p = Procedencia(thread_id=thread_id,
                        checkpoint_id=tupla.config["configurable"].get("checkpoint_id"),
                        checkpoint_ts=tupla.checkpoint.get("ts"))
        return t, p


RESULTADOS = "evals/resultados"


def guardar(a: Adjudicacion, destino: str = RESULTADOS) -> str:
    """Escribe la traza machine-readable. SÓLO local, dentro de `evals/resultados/`."""
    import os
    from datetime import datetime, timezone
    os.makedirs(destino, exist_ok=True)
    sello = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%z")
    hilo = (a.procedencia.thread_id or "sin-hilo").replace("/", "_")
    ruta = os.path.join(destino, f"canary_territorial_{hilo}_{sello}.json")
    with open(ruta, "w", encoding="utf-8") as f:
        json.dump(a.traza(), f, ensure_ascii=False, indent=2, default=str)
        f.write("\n")
    return ruta


def main(argv: list[str]) -> int:
    import argparse
    ap = argparse.ArgumentParser(description="Adjudica un turno de canary territorial.")
    ap.add_argument("thread_id")
    ap.add_argument("--sha-esperado", default=None, help="el SHA que se desplegó a propósito")
    ap.add_argument("--sha-observado", default=None, help="el SHA que Render reporta LIVE")
    ap.add_argument("--deployment", default=None, help="deployment id de Render")
    ap.add_argument("--sin-guardar", action="store_true")
    args = ap.parse_args(argv[1:])

    t, p = leer_turno(args.thread_id)
    p = Procedencia(thread_id=p.thread_id, checkpoint_id=p.checkpoint_id,
                    checkpoint_ts=p.checkpoint_ts, deployment_id=args.deployment,
                    sha_esperado=args.sha_esperado, sha_observado=args.sha_observado)
    a = adjudicar(t, p)
    print(a.paquete())
    if not args.sin_guardar:
        print(f"\ntraza: {guardar(a)}")
    return 0 if a.veredicto == PASS else 1


if __name__ == "__main__":   # pragma: no cover
    import sys
    raise SystemExit(main(sys.argv))
