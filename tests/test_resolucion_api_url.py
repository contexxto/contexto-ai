"""
Cómo resuelven la URL de la API las tres herramientas que corren contra producción:
`scripts/generar_qrs.py`, `scripts/hidratar_activos.py` y `evals/run_evals.py`.

POR QUÉ IMPORTA (2026-08-24): los dos scripts tenían la URL de la API clavada en el código,
apuntando a `https://contexto-ai.onrender.com`. Ese host ya no corresponde al servicio
operativo y devuelve 503; el backend vivo responde en `contexto-ai-oregon.onrender.com`.
El defecto podía pasar inadvertido porque un fallo de disponibilidad del catálogo podía
confundirse con una respuesta sin activos en algunos flujos de tooling — interpretación
razonable de por qué sobrevivió, no un hecho demostrado.

Estos tests fijan la REGLA DE RESOLUCIÓN, no la URL concreta:

    flag --api  >  variable de shell  >  .env  >  respaldo del código

Y fijan sobre todo los dos bordes que ya mordieron una vez:

1. La CADENA VACÍA tiene que caer al respaldo, no ganar como valor. `.env.example` llegó a
   declarar `CONTEXTO_API_URL=` vacía; con `.get(k, default)` eso resolvía a "" y las
   peticiones salían a "/api/v1/chat/" sin host. Hoy el ejemplo la trae comentada, pero el
   manejo defensivo se conserva y esto lo vigila.
2. El `.env` se lee ANCLADO A LA RAÍZ del repo, no al cwd. `run_evals.py` lo abría relativo
   y correrlo desde otra carpeta se saltaba el archivo en silencio: sin ANTHROPIC_API_KEY el
   juez LLM se apaga solo y la suite termina en verde con las rúbricas de criterio sin
   evaluar. Un gate que aprueba por no haber mirado es peor que uno que falla.

No abren una sola conexión ni leen el .env real de la máquina.
"""
import importlib
import shutil
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]
RESPALDO = "https://contexto-ai-oregon.onrender.com"
MODULOS = ("generar_qrs", "hidratar_activos", "scores_heuristicos")


# ══ Andamiaje ═════════════════════════════════════════════════════════════════════════
@pytest.fixture
def espejo(tmp_path, monkeypatch):
    """Copia los scripts REALES a un árbol temporal con su propio .env.

    Se copian los archivos de verdad (no una reimplementación) para que el test también
    cubra el anclaje a ROOT: cada script calcula su raíz desde su propio __file__, así que
    en el espejo lee el .env del espejo. Y el .env real de la máquina queda fuera de juego.
    """
    (tmp_path / "scripts").mkdir()
    for nombre in ("generar_qrs.py", "hidratar_activos.py", "scores_heuristicos.py"):
        shutil.copy(RAIZ / "scripts" / nombre, tmp_path / "scripts" / nombre)
    monkeypatch.syspath_prepend(str(tmp_path / "scripts"))
    _purgar()
    yield tmp_path
    _purgar()


def _purgar() -> None:
    """Sin esto, el segundo caso reusaría el módulo ya importado y no probaría nada."""
    for nombre in MODULOS:
        sys.modules.pop(nombre, None)


def _resolver(espejo: Path, modulo: str, env: str | None) -> str:
    """Devuelve el DEFAULT_API con el que arranca `modulo` dado el contenido del .env."""
    destino = espejo / ".env"
    if env is None:
        destino.unlink(missing_ok=True)
    else:
        destino.write_text(env, encoding="utf-8")
    _purgar()
    return importlib.import_module(modulo).DEFAULT_API


AMBOS = pytest.mark.parametrize("modulo", ["generar_qrs", "hidratar_activos"])


# ══ La regla de resolución en los scripts ═════════════════════════════════════════════
@AMBOS
def test_sin_env_ni_shell_cae_al_respaldo(espejo, monkeypatch, modulo):
    monkeypatch.delenv("CONTEXTO_API_URL", raising=False)
    assert _resolver(espejo, modulo, env=None) == RESPALDO


@AMBOS
def test_el_env_manda_sobre_el_respaldo(espejo, monkeypatch, modulo):
    monkeypatch.delenv("CONTEXTO_API_URL", raising=False)
    resuelto = _resolver(espejo, modulo, env="CONTEXTO_API_URL=https://desde-el-env.example\n")
    assert resuelto == "https://desde-el-env.example"


@AMBOS
def test_el_shell_manda_sobre_el_env(espejo, monkeypatch, modulo):
    monkeypatch.setenv("CONTEXTO_API_URL", "https://desde-el-shell.example")
    resuelto = _resolver(espejo, modulo, env="CONTEXTO_API_URL=https://desde-el-env.example\n")
    assert resuelto == "https://desde-el-shell.example"


@AMBOS
def test_se_le_come_el_slash_final(espejo, monkeypatch, modulo):
    """Sin esto las URLs quedan con doble barra: {api}//api/v1/..."""
    monkeypatch.setenv("CONTEXTO_API_URL", "https://con-slash.example/")
    assert _resolver(espejo, modulo, env=None) == "https://con-slash.example"


# ══ El borde que ya mordió: la cadena vacía ═══════════════════════════════════════════
@AMBOS
def test_env_declarado_pero_vacio_cae_al_respaldo(espejo, monkeypatch, modulo):
    """`CONTEXTO_API_URL=` en el .env es 'no configurado', no 'configurado en vacío'."""
    monkeypatch.delenv("CONTEXTO_API_URL", raising=False)
    assert _resolver(espejo, modulo, env="CONTEXTO_API_URL=\n") == RESPALDO


@AMBOS
def test_shell_vacio_cae_al_respaldo(espejo, monkeypatch, modulo):
    monkeypatch.setenv("CONTEXTO_API_URL", "")
    assert _resolver(espejo, modulo, env=None) == RESPALDO


@AMBOS
def test_shell_vacio_no_tapa_al_env(espejo, monkeypatch, modulo):
    """Una variable exportada en vacío no debe silenciar un .env que sí está configurado."""
    monkeypatch.setenv("CONTEXTO_API_URL", "")
    resuelto = _resolver(espejo, modulo, env="CONTEXTO_API_URL=https://desde-el-env.example\n")
    assert resuelto == "https://desde-el-env.example"


# ══ El .env no puede filtrar la credencial de escritura ═══════════════════════════════
def test_leer_el_env_no_inyecta_secretos_al_entorno(espejo, monkeypatch):
    """Los scripts leen el .env con dotenv_values (un dict), no con load_dotenv.

    CONTEXTO_API_KEY autoriza el alta de activos en el catastro de producción (--execute) y
    su docstring promete que sale del shell y solo del shell. Un cambio sobre una URL no
    tiene por qué ensanchar de dónde puede salir una credencial de escritura.
    """
    import os

    monkeypatch.delenv("CONTEXTO_API_KEY", raising=False)
    _resolver(
        espejo,
        "hidratar_activos",
        env="CONTEXTO_API_URL=https://x.example\nCONTEXTO_API_KEY=secreto-del-archivo\n",
    )
    assert "CONTEXTO_API_KEY" not in os.environ


# ══ El flag --api gana sobre todo ═════════════════════════════════════════════════════
@AMBOS
def test_el_flag_api_gana_sobre_el_shell(espejo, monkeypatch, modulo):
    import argparse

    monkeypatch.setenv("CONTEXTO_API_URL", "https://desde-el-shell.example")
    default = _resolver(espejo, modulo, env=None)
    ap = argparse.ArgumentParser()
    ap.add_argument("--api", default=default)
    assert ap.parse_args([]).api == "https://desde-el-shell.example"
    assert ap.parse_args(["--api", "https://desde-el-flag.example"]).api == "https://desde-el-flag.example"


# ══ run_evals: misma regla, pero cargando el .env AL ENTORNO ══════════════════════════
def _recargar_run_evals(monkeypatch, env_del_archivo: dict[str, str] | None = None):
    """Reimporta evals.run_evals con un .env simulado, sin tocar el real.

    Se intercepta dotenv.load_dotenv porque run_evals SÍ inyecta en os.environ (a
    diferencia de los scripts): de ahí saca ANTHROPIC_API_KEY, que enciende el juez LLM.
    Devuelve (modulo, rutas_pedidas) para poder afirmar QUÉ ruta de .env pidió.
    """
    import os

    rutas: list[str] = []

    def falso_load_dotenv(ruta=None, *a, **kw):
        rutas.append(str(ruta))
        for k, v in (env_del_archivo or {}).items():
            os.environ.setdefault(k, v)  # setdefault = override=False, como el real
        return True

    monkeypatch.setattr("dotenv.load_dotenv", falso_load_dotenv)
    import evals.run_evals as run_evals

    return importlib.reload(run_evals), rutas


def test_run_evals_sin_nada_cae_al_respaldo(monkeypatch):
    monkeypatch.delenv("CONTEXTO_API_URL", raising=False)
    modulo, _ = _recargar_run_evals(monkeypatch)
    assert modulo.API_URL == RESPALDO


def test_run_evals_shell_vacio_cae_al_respaldo(monkeypatch):
    """El mismo borde que en los scripts: con .get(k, default) esto resolvía a ""."""
    monkeypatch.setenv("CONTEXTO_API_URL", "")
    modulo, _ = _recargar_run_evals(monkeypatch)
    assert modulo.API_URL == RESPALDO
    assert modulo.API_URL, "una base vacía arma peticiones a '/api/v1/chat/' sin host"


def test_run_evals_toma_el_valor_del_env(monkeypatch):
    monkeypatch.delenv("CONTEXTO_API_URL", raising=False)
    modulo, _ = _recargar_run_evals(
        monkeypatch, {"CONTEXTO_API_URL": "https://desde-el-env.example/"}
    )
    assert modulo.API_URL == "https://desde-el-env.example"


def test_run_evals_lee_el_env_anclado_a_la_raiz(monkeypatch):
    """El bug de fondo: abrirlo relativo al cwd lo hacía invisible desde otra carpeta."""
    monkeypatch.delenv("CONTEXTO_API_URL", raising=False)
    _, rutas = _recargar_run_evals(monkeypatch)
    assert rutas, "run_evals dejó de cargar el .env"
    pedida = Path(rutas[0])
    assert pedida.is_absolute(), f"ruta relativa al cwd: {pedida}"
    assert pedida == RAIZ / ".env"


def test_run_evals_si_inyecta_al_entorno(monkeypatch):
    """La asimetría con los scripts es deliberada y aquí queda fijada.

    Si alguien 'unifica' esto a dotenv_values por estética, ANTHROPIC_API_KEY deja de
    llegar, el juez se apaga sin avisar y la suite sigue pasando en verde.
    """
    import os

    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("CONTEXTO_API_URL", raising=False)
    modulo, _ = _recargar_run_evals(monkeypatch, {"ANTHROPIC_API_KEY": "sk-del-archivo"})
    assert os.environ.get("ANTHROPIC_API_KEY") == "sk-del-archivo"
    assert modulo.ANTHROPIC_API_KEY == "sk-del-archivo"
