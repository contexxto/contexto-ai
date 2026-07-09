# FASE 1 — Piloto manual AuraReal 🚦 LUZ VERDE (2026-07-09)

> **Decisiones del fundador que activan esta fase:** nombre = **AuraReal** (pendiente SENADI) · monetización = **el 360 ES el producto** (SaaS mensual, leads incluidos con cupo) · luz verde = **2026-07-09**.
> **Gate de fase (MODELO §7):** NO se construye el generador self-serve hasta que este piloto valide la pregunta de abajo.

---

## 1. La pregunta que valida TODO

> **¿La inmobiliaria PYME paga y RENUEVA aurareal 360 por la tecnología de abajo — no por la web?**

Si la respuesta es sí en 1-3 inmobiliarias reales → Fase 3 (productizar self-serve). Si es no → el aprendizaje nos dice qué capa no vale lo que creemos, ANTES de construir la máquina.

## 2. Selección de las 1-3 inmobiliarias (criterios)

- **PYME de Quito** con inventario activo (≥5-10 publicaciones vivas) — suficiente para que la tienda no se vea vacía.
- **Relación de confianza con Carlos** (feedback franco > cortesía).
- Que hoy **pague o dependa de portales** (siente el dolor que AuraReal ataca).
- Al menos una con **letreros físicos en calle** (para el flujo QR completo).
- Deseable: una escéptica y una entusiasta (evita validar solo con conversos).
- **NO mezclar** con los carriles México (Linden/Puebla, Ricardo/Mazatlán) — esos son otros pilotos con otra tesis.

**⬜ PENDIENTE DE CARLOS: nombres de las 1-3 candidatas + contacto + fecha tentativa de kickoff.**

## 3. Checklist de montaje manual (por inmobiliaria, ~1 semana)

**Día 0 — Kickoff (30 min, el guion ya existe: `guion-demo.md`)**
- [ ] Demo con `storefront-demo.html` + pitch (`pitch-onepager.md`).
- [ ] Firmar el acuerdo simple del piloto: escalón 0 = $0, definición de **lead calificado** por escrito (§2 de `pricing-detalle.md`: pasó por el agente + declaró qué busca + pidió avanzar; tope mensual elegido por la inmobiliaria).
- [ ] Recoger: logo, colores (si tiene), lista de publicaciones, datos de contacto.

**Días 1-3 — Carga y verificación**
- [ ] Crear cuenta de corredor en Contexto para la inmobiliaria (rol corredor existente).
- [ ] Cargar publicaciones vía "Mis publicaciones" (flujo ya en producción).
- [ ] **Verificación de entorno en terreno** por el corredor (Catastro Vivo — el sello es el producto).
- [ ] Generar QR por inmueble (flujo existente) + página `/a/{id}` por inmueble.

**Días 4-5 — La tienda**
- [ ] Montar el storefront A MANO: página índice con la marca de la inmobiliaria sobre el esqueleto (línea CRED parametrizada) listando sus fichas verificadas + el agente embebido. *(Trabajo técnico mío — ver §5.)*
- [ ] Dominio/subdominio de la tienda (decisión por inmobiliaria: su dominio o subdominio de aurareal).
- [ ] QA de claims (reglas duras del paquete) antes de que lo vea su cliente final.

**Día 6-7 — En la calle**
- [ ] Instalar QR nuevos en letreros (mínimo 2-3 inmuebles).
- [ ] Walkthrough con la inmobiliaria: dónde ven sus leads (CRM), qué hace el agente.
- [ ] Acordar el ritmo de seguimiento (check semanal de 15 min).

## 4. Métricas del piloto (medir desde el día 1)

| Métrica | Fuente | Valida |
|---|---|---|
| Leads capturados en canal propio (QR + tienda) | CRM | La tesis del canal propio |
| % de leads que cumplen la definición de "calificado" | CRM + definición firmada | El cupo/excedente del 360 |
| Lift vs su baseline (leads/calificación antes del piloto) | Declarado al kickoff + medición | **El "3x" propio** (tarea #12) |
| Disposición a pagar el 360 (pregunta directa al día 30) | Conversación estructurada | **LA pregunta de la fase** |
| Renovación mes 2-3 | Hechos, no palabras | El foso |
| Costo de servir por tienda (horas + infra) | Registro nuestro | Sostenibilidad del escalón 0 |
| Razón declarada de valor ("¿por qué pagarías?") | Entrevista | ¿Tech o web? — el reframe |

## 5. Mi backlog técnico de Fase 1 (en orden)

1. **Plantilla de storefront manual** — página índice por inmobiliaria (marca parametrizada + fichas `/a/{id}` + agente). Reusa lo que existe; NO es el generador self-serve.
2. **Vista "mis leads del piloto"** — ya existe el CRM Vivo (tarea #33, en progreso); asegurar que el corredor del piloto vea sus leads del QR/tienda etiquetados por fuente.
3. **Medición del lift** — instrumentación ya lista (tarea #12); conectarla al reporte semanal del piloto.
4. QA de claims sobre lo que Lovable produzca (cuando Carlos traiga el diseño).

## 6. Acciones de Carlos (fuera de mi alcance)

- [ ] **Nombres de las 1-3 inmobiliarias** + fecha de kickoff ← **lo único que bloquea el arranque**
- [ ] Comprar `aurareal.ec` (NIC.ec) — centavos, candado temprano.
- [ ] Búsqueda SENADI (clases 35/36/42) — gate antes de que el nombre toque público.
- [ ] Diseño en Lovable (`PROMPT_LOVABLE.md` + capturas) — en paralelo, no bloquea el piloto.

## 7. Qué NO hacemos en Fase 1 (disciplina)

- ❌ Generador self-serve / "tienda en clicks" (Fase 3, post-validación).
- ❌ Encaje financiero construido (spec listo, hoja de ruta del 360).
- ❌ Cobrar el 360 desde el día 1 (el piloto valida disposición; el acuerdo es $0 con fecha de conversación de precio al día 30).
- ❌ Más de 3 inmobiliarias (profundidad > volumen; P5).
- ❌ Publicar el nombre/landing antes del SENADI.
