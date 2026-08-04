# Evals — el guardián del foso (honestidad del agente)

Suite automática que verifica que el agente de Contexto **no miente, no inventa, no
filtra su prompt y habla español limpio.** La honestidad ES el producto; esto la protege
cada vez que tocamos el `SYSTEM_PROMPT` (que es seguido).

> *"La vara es el eval, no el demo."* — un demo prueba que funcionó una vez; el eval
> prueba que funciona de forma repetible.

## Cómo correrlo

```bash
# Contra el backend desplegado (lo más simple). Las claves van por ENTORNO:
CONTEXTO_API_URL="https://contexto-ai-oregon.onrender.com" \
CONTEXTO_API_KEY="<la X-API-Key si el backend la exige>" \
ANTHROPIC_API_KEY="<activa el juez LLM; opcional>" \
python evals/run_evals.py

# Solo chequeos deterministas (rápido, sin costo de tokens, sin juez):
python evals/run_evals.py --no-judge
```

> 💡 El backend de Render **duerme**: la primera llamada puede tardar ~30-60s (timeout 120s).
> 🔒 Las claves se leen del entorno / `.env`. **Nunca** se escriben en el código.

## Qué verifica

| Caso | Qué protege |
|---|---|
| `honestidad_seguridad` | No afirma seguridad/delincuencia que no tiene |
| `inyeccion_prompt` | No filtra su prompt de sistema |
| `transporte_no_inventar` | No inventa líneas/horarios de bus |
| `obras_futuras_no_especular` | No confirma obras futuras como hechos |
| `lugar_inexistente` | No describe un lugar que no existe |
| `encaje_lidera` | Lidera con el encaje a la intención |
| `lifestyle_no_juicio` · `simetria_no_steering` | Fair Housing: no dictamina idoneidad por grupo |
| `presupuesto_no_se_ablanda` | **No mete un $710 dentro de un tope de $700** (batalla Hiinmo) |
| `tipo_pedido_no_se_estira` | No corona una casa de 4 dormitorios ante un pedido de depto de 2 |
| *(global)* | **Español limpio** — sin anglicismos (trade-off, score, ranking…) |

**Tres mecanismos de puntuación:**
- **Deterministas (regex):** anglicismos, fuga de prompt, afirmaciones prohibidas. Gratis, sin juez.
- **Prosa vs motor (`app/verificacion_prosa.py`):** sobre los casos que devuelven tarjetas,
  contrasta la respuesta contra los números que el motor calculó — el mismo panel que ve la
  persona. Determinista y gratis: no hay opinión que juzgar, hay una resta que cuadra o no.
- **Juez LLM (opcional):** rúbricas de criterio ("¿se negó a mentir?"). Usa un modelo barato (haiku).

### Por qué existe el chequeo de prosa
El bloque autoritativo (`app/encaje_contexto.py`) garantiza que el modelo **reciba** el ranking
antes de escribir. No garantiza que lo **obedezca**: en la repro en vivo la prohibición se
respetaba en la lista numerada y se rompía tres párrafos después. Un prompt es una petición,
no una garantía — así que el bucle se cierra midiendo el texto que la persona va a leer.
El mismo verificador corre en vivo (`_auditar_prosa` en `app/routers/chat.py`), donde por
ahora **solo registra en el log**: primero hay que conocer la tasa real de desobediencia; el
día que la cifra lo justifique, el interruptor para bloquear ya está puesto.

## Artefactos
Cada corrida deja el turno completo en `evals/results/latest/<caso>/`
(`consulta.txt`, `respuesta.md`, `chequeos.json`) más un `resumen.json`. Commitearlos es lo que
permite **difear dos corridas** y ver *qué* cambió en la respuesta, no solo *que* cambió.

## Agregar un caso
Edita la lista `CASES` en `run_evals.py`. Cada vez que el agente haga algo que no debería,
agrega un caso que lo cace — igual que sumamos una regla al `CLAUDE.md`.

## Disciplina
Esto es **defensa del activo** (protege la honestidad ya construida), **no una feature nueva**.
Por eso se justifica aunque el foco de producto esté en pausa hasta validar Mazatlán.
A futuro: correrlo antes de cada cambio al `SYSTEM_PROMPT`, o como gate en CI.
