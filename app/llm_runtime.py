"""FRONTERA DE RUNTIME DE MODELOS (MODEL RUNTIME BOUNDARY 0.1).

El ÚNICO lugar del repo que sabe qué admite cada modelo y cómo se le habla. Antes esto estaba
repartido por los call sites (`THINKING_APAGADO`, `temperatura_llm()` y un `startswith` sobre el
nombre del modelo en `config.py`), y cambiar de modelo obligaba a refactorizar el producto.

    ModelProfile   lo que un modelo ADMITE (thinking, effort, temperatura, tool forzada) y la
                   configuración de request que tiene CALIFICADA para cada propósito.
    CallPurpose    PARA QUÉ se llama al modelo. Cada call site declara el suyo y nada más.
    ModelRuntime   compone la request de un propósito con el perfil activo, y la valida.

Un call site nunca decide `model`, `thinking`, `temperature`, `effort` ni `tool_choice`: los pide
aquí por propósito (`runtime().sdk_kwargs(CallPurpose.X)`), y la guarda AST de
`tests/test_llm_runtime.py` impide que vuelvan a aparecer fuera de este módulo.

FALLA CERRADO. Un `model_id` sin perfil, un propósito sin configuración calificada o una
combinación que el perfil no admite lanzan `ModelConfigError`. Nunca se omite un parámetro para
«dejar el default del proveedor»: en Sonnet 5 omitir `thinking` ENCIENDE el razonamiento, y así
fue como el cambio «obvio» de `LLM_MODEL` iba a tumbar el chat.

Cambiar de modelo es un proceso de calificación, no de código: ver
`docs/MODEL_SWAP_PLAYBOOK_0.1.md`.
"""
from __future__ import annotations

import enum
from dataclasses import dataclass
from types import MappingProxyType
from typing import Mapping


class ModelConfigError(RuntimeError):
    """Configuración de modelo no registrada o no admitida. No se degrada: se detiene."""


class CallPurpose(str, enum.Enum):
    """Para qué se llama al modelo. El inventario exacto de call sites vive en el test."""

    CHAT = "chat"                  # app/agent/graph.py · el agente del comprador
    CRM = "crm"                    # app/agent/crm_graph.py · Copiloto / Estratega
    PREFERENCIAS = "preferencias"  # app/preferencias.py · extracción con tool forzada
    INTERPRETE = "interprete"      # app/buyer/interprete.py · propuestas con tool forzada
    MATCH = "match"                # app/routers/match.py · refinado (texto) y justificación (tool)
    VISION = "vision"              # app/vision.py · ficha visual con tool forzada
    JUEZ = "juez"                  # evals/run_evals.py · EVAL/JUDGE, fuera del producto


class Thinking(str, enum.Enum):
    DISABLED = "disabled"
    ADAPTIVE = "adaptive"
    # No se envía `thinking`. SÓLO es válido si el perfil declara que, sin él, el modelo no
    # razona (`thinking_por_defecto=DISABLED`). Para Sonnet 5 el registro lo rechaza.
    OMITIDO = "omitido"


@dataclass(frozen=True)
class PurposeConfig:
    """La configuración de request CALIFICADA para un propósito en un modelo."""

    thinking: Thinking
    effort: str | None = None
    temperature: float | None = None


@dataclass(frozen=True)
class ModelProfile:
    clave: str
    provider: str
    model_id: str
    # "producto": seleccionable con LLM_MODEL. "evaluador": sólo sirve al propósito JUEZ.
    rol: str
    # Lo que el proveedor hace si NO se envía `thinking`.
    thinking_por_defecto: Thinking
    thinking_admitido: frozenset[Thinking]
    effort_admitido: frozenset[str]
    # Cómo llega `effort` al proveedor. anthropic 0.55 no tipa `output_config`: va por
    # `extra_body`, que el SDK fusiona en el cuerpo JSON.
    effort_via: str | None
    # False = el proveedor rechaza cualquier `temperature` distinta del default → no se envía.
    temperatura_admitida: bool
    tool_forzada: bool
    # Una tool forzada (`tool_choice` tipo "tool") exige el razonamiento apagado.
    tool_forzada_requiere_thinking_apagado: bool
    strict_tools: bool
    propositos: Mapping[CallPurpose, PurposeConfig]


_PRODUCTO = frozenset(p for p in CallPurpose if p is not CallPurpose.JUEZ)

# ── Perfiles ────────────────────────────────────────────────────────────────────────────
# Cada valor de `propositos` es la configuración que YA se demostró en producción o en un
# arnés con modelo real; la procedencia va al lado.

SONNET_45 = ModelProfile(
    clave="claude-sonnet-4-5",
    provider="anthropic",
    model_id="claude-sonnet-4-5-20250929",
    rol="producto",
    thinking_por_defecto=Thinking.DISABLED,
    thinking_admitido=frozenset({Thinking.DISABLED}),
    effort_admitido=frozenset(),
    effort_via=None,
    temperatura_admitida=True,
    tool_forzada=True,
    tool_forzada_requiere_thinking_apagado=True,
    strict_tools=False,
    # Lo de producción hasta hoy (bc2a6e3): chat y CRM a 0.2, todo sin razonamiento. El
    # `thinking` explícito no cambia nada en 4.5 (su default es no razonar) y deja la request
    # idéntica a la calificada.
    propositos=MappingProxyType({
        CallPurpose.CHAT: PurposeConfig(Thinking.DISABLED, temperature=0.2),
        CallPurpose.CRM: PurposeConfig(Thinking.DISABLED, temperature=0.2),
        CallPurpose.PREFERENCIAS: PurposeConfig(Thinking.DISABLED),
        CallPurpose.INTERPRETE: PurposeConfig(Thinking.DISABLED),
        CallPurpose.MATCH: PurposeConfig(Thinking.DISABLED),
        CallPurpose.VISION: PurposeConfig(Thinking.DISABLED),
    }),
)

SONNET_5 = ModelProfile(
    clave="claude-sonnet-5",
    provider="anthropic",
    model_id="claude-sonnet-5",
    rol="producto",
    # Sin `thinking`, Sonnet 5 RAZONA, y eso cuenta contra `max_tokens` (preferencias tiene 400).
    thinking_por_defecto=Thinking.ADAPTIVE,
    thinking_admitido=frozenset({Thinking.DISABLED, Thinking.ADAPTIVE}),
    effort_admitido=frozenset({"low", "medium", "high"}),
    effort_via="extra_body.output_config",
    # Responde 400 a un `temperature` distinto del default.
    temperatura_admitida=False,
    tool_forzada=True,
    tool_forzada_requiere_thinking_apagado=True,
    strict_tools=False,
    propositos=MappingProxyType({
        # SCREEN ADAPTIVE 0.1 · Fase B: `adaptive` + `effort: low` en el chat, PASS con 31
        # turnos-caso (RESULTADO_2026-09-30_SONNET5-ADAPTIVE-LOW-PHASE-B).
        CallPurpose.CHAT: PurposeConfig(Thinking.ADAPTIVE, effort="low"),
        # Lo probado en #180: sin razonamiento. No se extiende `adaptive` sin evidencia; las
        # micro-llamadas con tool forzada tampoco podrían (ver `tool_forzada_requiere_…`).
        CallPurpose.CRM: PurposeConfig(Thinking.DISABLED),
        CallPurpose.PREFERENCIAS: PurposeConfig(Thinking.DISABLED),
        CallPurpose.INTERPRETE: PurposeConfig(Thinking.DISABLED),
        CallPurpose.MATCH: PurposeConfig(Thinking.DISABLED),
        CallPurpose.VISION: PurposeConfig(Thinking.DISABLED),
    }),
)

# El juez de evals no usa `LLM_MODEL`: es un evaluador fijo (`CONTEXTO_JUDGE_MODEL`). Se registra
# con rol "evaluador" para que también falle cerrado, y sólo admite el propósito JUEZ: no se puede
# elegir como modelo del producto. Su request es la de siempre: sin `thinking` (Haiku 4.5 no
# razona si no se le pide) y sin `temperature`.
HAIKU_45_JUEZ = ModelProfile(
    clave="claude-haiku-4-5",
    provider="anthropic",
    model_id="claude-haiku-4-5",
    rol="evaluador",
    thinking_por_defecto=Thinking.DISABLED,
    thinking_admitido=frozenset(),
    effort_admitido=frozenset(),
    effort_via=None,
    temperatura_admitida=True,
    tool_forzada=False,
    tool_forzada_requiere_thinking_apagado=True,
    strict_tools=False,
    propositos=MappingProxyType({CallPurpose.JUEZ: PurposeConfig(Thinking.OMITIDO)}),
)

JUEZ_MODELO_POR_DEFECTO = HAIKU_45_JUEZ.model_id


def validar_perfil(p: ModelProfile) -> None:
    """Rechaza un perfil cuya configuración calificada pida algo que el propio perfil no admite."""
    if p.provider != "anthropic":
        raise ModelConfigError(f"{p.clave}: proveedor {p.provider!r} sin transporte en este runtime")
    if p.rol not in ("producto", "evaluador"):
        raise ModelConfigError(f"{p.clave}: rol {p.rol!r} desconocido")
    esperados = _PRODUCTO if p.rol == "producto" else frozenset({CallPurpose.JUEZ})
    if set(p.propositos) != esperados:
        faltan = sorted(x.value for x in esperados - set(p.propositos))
        sobran = sorted(x.value for x in set(p.propositos) - esperados)
        raise ModelConfigError(f"{p.clave} ({p.rol}): propósitos que faltan {faltan}, que sobran {sobran}")
    for proposito, c in p.propositos.items():
        donde = f"{p.clave} · {proposito.value}"
        if c.thinking is Thinking.OMITIDO:
            if p.thinking_por_defecto is not Thinking.DISABLED:
                raise ModelConfigError(f"{donde}: omitir `thinking` encendería "
                                       f"{p.thinking_por_defecto.value!r} por defecto")
        elif c.thinking not in p.thinking_admitido:
            raise ModelConfigError(f"{donde}: thinking {c.thinking.value!r} no admitido")
        if c.effort is not None:
            if p.effort_via is None or c.effort not in p.effort_admitido:
                raise ModelConfigError(f"{donde}: effort {c.effort!r} no admitido")
            if c.thinking is not Thinking.ADAPTIVE:
                raise ModelConfigError(f"{donde}: effort sin thinking adaptive no está calificado")
        if c.temperature is not None and not p.temperatura_admitida:
            raise ModelConfigError(f"{donde}: el modelo no admite `temperature`")


def _registro(*perfiles: ModelProfile) -> Mapping[str, ModelProfile]:
    ids = [p.model_id for p in perfiles]
    if len(ids) != len(set(ids)):
        raise ModelConfigError(f"model_id duplicado en el registro: {ids}")
    for p in perfiles:
        validar_perfil(p)
    return MappingProxyType({p.model_id: p for p in perfiles})


# Se valida al importar: un perfil incoherente no llega a atender una sola llamada.
REGISTRO: Mapping[str, ModelProfile] = _registro(SONNET_45, SONNET_5, HAIKU_45_JUEZ)


def perfil(model_id: str, *, rol: str = "producto") -> ModelProfile:
    """El perfil registrado de `model_id` con ese rol. Sin perfil → ModelConfigError."""
    p = REGISTRO.get(model_id)
    if p is None:
        raise ModelConfigError(
            f"modelo {model_id!r} sin perfil registrado (registrados: {sorted(REGISTRO)}). "
            "Registrarlo es un proceso de calificación: docs/MODEL_SWAP_PLAYBOOK_0.1.md")
    if p.rol != rol:
        raise ModelConfigError(f"modelo {model_id!r} tiene rol {p.rol!r}, no {rol!r}")
    return p


@dataclass(frozen=True)
class ModelRuntime:
    """La configuración de request de un perfil, propósito por propósito."""

    perfil: ModelProfile

    def _config(self, proposito: CallPurpose) -> PurposeConfig:
        c = self.perfil.propositos.get(proposito)
        if c is None:
            raise ModelConfigError(f"{self.perfil.clave}: sin configuración calificada para "
                                   f"{proposito.value!r}")
        return c

    def sdk_kwargs(self, proposito: CallPurpose, *, tool_forzada: str | None = None) -> dict:
        """Argumentos para `client.messages.create(**…)` del SDK de Anthropic."""
        c = self._config(proposito)
        kw: dict = {"model": self.perfil.model_id}
        if c.thinking is not Thinking.OMITIDO:
            kw["thinking"] = {"type": c.thinking.value}
        if c.temperature is not None:
            kw["temperature"] = c.temperature
        if c.effort is not None:
            kw["extra_body"] = {"output_config": {"effort": c.effort}}
        if tool_forzada is not None:
            if not self.perfil.tool_forzada:
                raise ModelConfigError(f"{self.perfil.clave}: no admite tool forzada "
                                       f"({proposito.value}: {tool_forzada})")
            apagado = c.thinking is Thinking.DISABLED or (
                c.thinking is Thinking.OMITIDO and self.perfil.thinking_por_defecto is Thinking.DISABLED)
            if self.perfil.tool_forzada_requiere_thinking_apagado and not apagado:
                raise ModelConfigError(f"{self.perfil.clave} · {proposito.value}: tool forzada "
                                       f"con thinking {c.thinking.value!r}")
            kw["tool_choice"] = {"type": "tool", "name": tool_forzada}
        return kw

    def langchain_kwargs(self, proposito: CallPurpose) -> dict:
        """Argumentos para `ChatAnthropic(**…)`: `extra_body` viaja por `model_kwargs`."""
        kw = self.sdk_kwargs(proposito)
        extra = kw.pop("extra_body", None)
        if extra:
            kw["model_kwargs"] = {"extra_body": extra}
        return kw

    def http_json(self, proposito: CallPurpose, *, tool_forzada: str | None = None) -> dict:
        """Campos de modelo para un cuerpo JSON crudo (sin SDK): `extra_body` ya fusionado."""
        kw = self.sdk_kwargs(proposito, tool_forzada=tool_forzada)
        return {**{k: v for k, v in kw.items() if k != "extra_body"}, **kw.get("extra_body", {})}


def runtime() -> ModelRuntime:
    """El runtime del modelo de producto configurado (`LLM_MODEL`)."""
    from app.config import settings  # perezoso: los evals importan este módulo sin base

    return ModelRuntime(perfil(settings.llm_model))


def runtime_evaluador(model_id: str) -> ModelRuntime:
    """El runtime de un modelo evaluador (el juez de evals)."""
    return ModelRuntime(perfil(model_id, rol="evaluador"))
