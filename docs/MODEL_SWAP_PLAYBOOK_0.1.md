# MODEL SWAP PLAYBOOK 0.1

Procedimiento reutilizable para cambiar el modelo del producto. Existe porque el retiro de Sonnet 4.5 (2026-11-24) demostró que cambiar sólo `LLM_MODEL` tumbaba el chat (400 por `temperature`), y que las peculiaridades de cada modelo estaban repartidas por siete call sites.

Desde MODEL RUNTIME BOUNDARY 0.1, **cambiar de modelo es calificar un perfil, no refactorizar el producto**:

```
DISCOVER → PROFILE → PREFLIGHT → CONTRACT PROBES → PARITY HARNESS → QUALIFY → RELEASE → ROLLBACK
```

## Piezas

| pieza | dónde | qué hace |
|---|---|---|
| Frontera de runtime | `app/llm_runtime.py` | `ModelProfile` (capacidades + configuración calificada por propósito), `CallPurpose`, `ModelRuntime`. Único lugar que sabe qué admite cada modelo. |
| Registro | `REGISTRO` en ese módulo | Perfiles de producto: `claude-sonnet-4-5`, `claude-sonnet-5`. Evaluador: `claude-haiku-4-5`, sólo para el juez de evals. Se valida al importar. |
| Guarda e inventario | `tests/test_llm_runtime.py` | Inventario exacto de call sites y guarda AST: nadie fija `model`, `thinking`, `temperature`, `effort` ni `tool_choice` fuera de la frontera. |
| Golden del cable | `tests/fixtures/llm_wire_calificado.json` | Lo que debe llegar al proveedor en los 8 call sites, por modelo. Sale de la configuración **calificada**, nunca del código candidato. |
| Arnés de paridad | `Whaber-Claude Code/arneses/paridad_chat_sonnet5/` (fuera del repo) | El endpoint real del chat por ASGI, fixtures sin base, tripwire de red, dos capas RAW/SYSTEM, captura del cable (`cuerpos_http.py`). |

**Propósitos** (`CallPurpose`): `CHAT`, `CRM`, `PREFERENCIAS`, `INTERPRETE`, `MATCH`, `VISION`, `JUEZ`.

**Falla cerrado.** Un modelo sin perfil, un propósito sin configuración o una capacidad no admitida lanzan `ModelConfigError`:
- el chat y el CRM, al arrancar la app;
- las micro-llamadas y el juez, antes de su `try`, así que no se degradan en silencio.

## 1 · DISCOVER

Qué cambia en el modelo nuevo respecto al activo. Fuentes: la página del modelo y la guía de migración del proveedor, las notas del SDK instalado (hoy `anthropic==0.55.0`, `langchain-anthropic==0.3.15`) y la memoria del proyecto.

**Salida:** una tabla de diferencias con fuente. No se decide nada todavía.

Qué mirar siempre:
- sampling params (`temperature`, `top_p`) admitidos;
- `thinking`: modos admitidos, qué pasa si se omite, si cuenta contra `max_tokens`;
- `effort` / `output_config`, y si el SDK instalado los tipa o hay que ir por `extra_body`;
- `tool_choice` forzado (`{"type": "tool"}`) y su compatibilidad con thinking;
- `strict` en tools;
- reglas sobre bloques de thinking en el historial;
- precio y ventana de contexto.

## 2 · PROFILE · registrar el modelo

1. Añadir un `ModelProfile` en `app/llm_runtime.py`:
   - `model_id` exacto, tal cual irá en `LLM_MODEL` (**no se aceptan alias**);
   - `rol="producto"`;
   - capacidades declaradas **sólo como verificadas**;
   - `propositos` con una `PurposeConfig` para cada propósito de producto.
2. Punto de partida conservador para `propositos`: la configuración del modelo activo que el nuevo admita. Si algo no se admite, **no se omite**: se elige una alternativa explícita y se marca como pendiente de calificar.
3. Añadirlo a `REGISTRO` (`_registro(...)`).
4. Correr `tests/test_llm_runtime.py`. `validar_perfil` rechaza al importar cualquier combinación incoherente:
   - un thinking no admitido;
   - `effort` sin transporte o sin adaptive;
   - `temperature` en un modelo que no la admite;
   - omitir `thinking` cuando el default del modelo es razonar;
   - propósitos que faltan o sobran.

Registrar un perfil **no** lo activa. Ningún call site cambia.

## 3 · PREFLIGHT · sin modelo real

- **Cable** (`cuerpos_http.py <worktree> <model_id>`): captura con `httpx.MockTransport` el cuerpo HTTP exacto de los 8 call sites. Se revisa a mano: `thinking`, `effort`, `temperature`, `tool_choice` y `max_tokens` son los esperados.
- **Serialización.** Si un parámetro va por `extra_body`, confirmar que el SDK instalado lo fusiona en el cuerpo. **Sin actualizar dependencias dentro de esta fase.**
- **Si el perfil exige algo que el cable no puede expresar:** STOP.

## 4 · CONTRACT PROBES · modelo real, pocas llamadas

Una llamada mínima por capacidad declarada, para confirmar que el proveedor acepta lo que el perfil dice:
- forced `tool_choice` con thinking apagado (y que el tool call llega entero y valida su esquema);
- thinking en cada modo declarado;
- `effort` en cada valor declarado;
- que `temperature` se rechaza, si el perfil dice que no la admite;
- truncamiento con el `max_tokens` real de cada propósito.

**Cómo se detectan capacidades incompatibles:**
- **Un 400** = la capacidad no existe. El perfil se corrige; nunca se envuelve en un `try`.
- **Un éxito silencioso con otro comportamiento** (p. ej. razona aunque se pidió apagado) = incompatible también.
- Antecedentes: Sonnet 5 responde 400 a `temperature`; Sonnet 5.5 responde 400 a `thinking: disabled` y a `tool_choice` forzado. Por eso 5.5 **no tiene perfil**.

## 5 · PARITY HARNESS · comparar contra el modelo activo

- **Mismas condiciones.** El arnés corre el grafo y el endpoint reales con el perfil candidato, **y con el activo**, sobre el mismo corpus y las mismas fixtures.
- **Prerregistro.** Casos, N, reglas INVALID / FAIL y criterios PASS / HOLD / FAIL **antes** de correr, con las huellas del arnés. Un adendo sólo para ambigüedades, fechado y antes de leer las corridas que afecta.
- **INVALID ≠ FAIL.** Una falla de infraestructura (red, tripwire, 5xx) nunca se adjudica al modelo.
- **Dos capas:**
  - RAW MODEL: lo que hizo el modelo;
  - SYSTEM: lo que el producto detectó en el camino vivo.
  - Taxonomía: `UNDETECTED / USER-VISIBLE`, `DETECTED / USER-VISIBLE` y `BLOCKED` (sólo si de verdad no llega a la persona). **Detectado no es bloqueado.**
- **Tasas por configuración:**
  - defectos crudos;
  - defectos materiales user-visible, y cuántos no detectados;
  - pérdida de restricciones duras;
  - evidencia espacial y afirmaciones espaciales respaldadas;
  - coste y latencia.
- **El juez LLM es evidencia secundaria.** Si contradice la evidencia, se registra `JUDGE ERROR`.
- **Si una configuración del perfil falla**, se prueba otra configuración (screen) antes de descartar el modelo. Cada screen, con su propio prerregistro.

## 6 · QUALIFY · cuándo un modelo es `QUALIFIED`

Un perfil pasa a **`QUALIFIED`** cuando se cumplen las siete condiciones:
1. Perfil registrado y `validar_perfil` en verde.
2. Contract probes sin 400 en ninguna capacidad declarada.
3. Paridad PASS según su prerregistro:
   - sin pérdida sistemática de restricciones duras;
   - sin clases nuevas de defecto material user-visible;
   - sin regresión por caso frente al modelo activo;
   - cero 400 y cero truncamientos atribuibles.
4. **Golden actualizado** desde la configuración que calificó. Se captura con el arnés; nunca se escribe a mano desde el código candidato.
5. **Equivalencia de cable.** El código candidato envía, byte a byte, lo que calificó (`equivalencia_runtime.py`). Si el código cambia después de calificar:
   - se repite la equivalencia;
   - si es idéntica, basta un smoke de los casos de mayor riesgo (**herencia de calificación**);
   - si no lo es, se recalifica.
6. Suite completa verde, con la guarda AST y los controles de mutación (`mutar_runtime.py`: cambiar thinking, effort o temperatura pone la suite en rojo).
7. Commit local con SHA exacto.

**Qué no es `QUALIFIED`:** ni un deploy ni un merge. Es: «este SHA, con `LLM_MODEL=<model_id>`, se comporta como lo calificado».

## 7 · RELEASE · `QUALIFIED` ≠ `AUTHORIZED FOR PRODUCTION`

`AUTHORIZED FOR PRODUCTION` exige, **además** de `QUALIFIED`, una autorización explícita de Carlos para ese SHA y ese modelo. Nada en este playbook la concede.

Pasos de la liberación:
1. PR → CI (`pytest`) verde → merge a mano (lo hace Carlos).
2. Deploy **por SHA exacto** con `LLM_MODEL` **todavía en el modelo activo**. El código nuevo no cambia nada por sí solo: la equivalencia de cable del modelo activo lo garantiza.
3. Carlos cambia `LLM_MODEL` en Render y hace un **DEPLOY del mismo SHA**. Un Restart **no** aplica variables de entorno.
4. Canary en producción con los casos de mayor riesgo, y observación de los registros de guardrails y de las auditorías del camino vivo.

## 8 · ROLLBACK · sin tocar código

Los perfiles calificados **conviven en el registro**. Revertir es:
1. `LLM_MODEL` = el `model_id` anterior en Render;
2. **DEPLOY** del mismo SHA.

Ni código, ni PR, ni CI.

- **El perfil anterior se conserva** mientras el proveedor sirva ese modelo. Se retira sólo en un PR aparte, **después** de su fecha de retiro. Sonnet 4.5 se retira el 2026-11-24; desde el 2026-10-30 puede fallar intermitentemente, así que a partir de entonces el rollback a 4.5 deja de ser una red de seguridad fiable.
- **Si el modelo anterior ya no existe**, el rollback es a otro perfil `QUALIFIED`. Si no hay ninguno, el cambio de modelo no debía haberse liberado.
- **El juez de evals** (`CONTEXTO_JUDGE_MODEL`) se revierte igual, por entorno. Su perfil evaluador sólo admite el propósito `JUEZ`.

## Lo que este playbook NO hace

- No hay routing automático entre modelos, ni failover entre proveedores, ni selección por precio: un proceso corre con **un** modelo de producto, el de `LLM_MODEL`.
- No hay adaptadores para otros proveedores. `validar_perfil` rechaza cualquier `provider` distinto de `anthropic` hasta que exista su transporte, calificado con este mismo procedimiento.
- No se extiende thinking a las micro-llamadas con tool forzada sin evidencia. Además, la frontera lo impide: tool forzada exige el razonamiento apagado.
