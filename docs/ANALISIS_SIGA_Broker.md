# Análisis Competitivo — SIGA Broker

**Fecha:** 2026-06-15
**Autor:** Contexto AI (estrategia)
**Categoría del análisis:** CRM / gestión de operaciones para corredores

---

## TL;DR (lo esencial en 4 líneas)
- **SIGA Broker NO es competidor de Contexto.** Es otra **capa del stack**: gestiona el *proceso de venta del corredor* (leads, embudos, citas), no la *verdad del inmueble ni de la zona*.
- El único solape es su **"agente conversacional"**, que casi con certeza es un chatbot de CRM (califica leads), no un agente que razona sobre catastro + rentabilidad.
- La jugada correcta NO es competir en features de CRM, sino posicionar a SIGA (y a cualquier CRM inmobiliario) como **canal/partner** que enchufa la **API de inteligencia de Contexto**.
- **Acción:** agendar su demo como **reconocimiento barato**; medir el solape real y si tienen API/integraciones.

> *Nota de honestidad: este análisis razona desde el mensaje comercial recibido. Los puntos marcados como "verificar" no están confirmados con el producto por dentro.*

---

## 1. Qué es SIGA Broker
Por sus funciones declaradas:

| Función declarada | Qué resuelve | Capa |
|---|---|---|
| Gestión de prospectos/clientes | Base de datos de contactos | CRM |
| Embudos con vinculación a WhatsApp | Pipeline de ventas + canal | CRM / mensajería |
| Organización de citas | Agenda comercial | Productividad |
| Reportes | Métricas del corredor | BI ligero |
| Agente conversacional | Atención/calificación automática | Chatbot |
| Capacitación y asistencia | Onboarding / soporte | Servicio |

**Conclusión de categoría:** SIGA es un **CRM vertical para corredores**, centrado en el *proceso humano de venta*. Su unidad de valor es el **lead/cliente**, no el **activo inmobiliario**.

---

## 2. El veredicto: capas distintas, no rivales

```
┌──────────────────────────────────────────────┐
│  SIGA Broker → CRM / pipeline / WhatsApp        │  ← gestiona al CORREDOR
├──────────────────────────────────────────────┤
│  Contexto AI → inteligencia del ACTIVO + ZONA   │  ← ficha verificada, caminabilidad,
│                 + capa de inversión (yield)      │     ruido, transporte, "vivir aquí"
└──────────────────────────────────────────────┘
```

Un corredor con SIGA gestiona impecablemente sus leads… y sigue teniendo **cero datos verificables** del inmueble y del entorno que vende. Ese vacío es exactamente el territorio de Contexto.

**Son complementarios.** SIGA mueve al lead por el embudo; Contexto le da al lead **la verdad del inmueble** (estado técnico, habitabilidad, rentabilidad) que cierra la venta con confianza.

---

## 3. El único solape: "Agente conversacional"
Es la línea a vigilar, pero hay que distinguir dos cosas que el mercado confunde:

| | Chatbot de CRM (probable SIGA) | Agente de Contexto |
|---|---|---|
| Propósito | Calificar/atender leads | Analizar inmueble + zona + inversión |
| Fuente | Reglas / FAQ / guion | Catastro geoespacial + ficha **verificada en terreno** |
| Salida | "Déjame tus datos y te contactan" | "Caminabilidad 78, ruido medio, yield bruto 6.3% estimado" |
| Foso | Bajo (commodity) | Alto (datos verificables, lento de copiar) |

El agente de Contexto se apoya en el **foso de datos** (ficha técnica + catastro acumulado). Eso es caro y lento de construir → un CRM racional preferirá **integrarlo, no construirlo**.

---

## 4. La oportunidad real (encaja con la estrategia API-first / Apaleo)
- Contexto **no quiere ser el CRM del broker**: es commodity y guerra de features sin foso.
- Todo CRM inmobiliario necesita **enriquecer la ficha del lead** con inteligencia real del inmueble.
- La **API de Contexto** (`/investment`, habitabilidad, ficha técnica, scores) se enchufa **dentro del flujo de SIGA**.

**Pitch de integración:** *"SIGA gestiona el lead; Contexto le da al lead la verdad del inmueble y su rentabilidad — verificada, no scrapeada."*

Es el mismo encuadre que para Ricardo/InmobIA y Bolívar: **"integra mi motor", no "compra mi app."**

---

## 5. Qué aprender de su Go-To-Market
- **WhatsApp-native + demo-led + "el tiempo es clave":** valida que el corredor LATAM vive en WhatsApp y compra rápido si le reduces fricción. → Reforzar el ángulo WhatsApp en el piloto.
- **"Capacitación y asistencia":** el onboarding con la mano puesta es decisivo en este mercado. → Aplicar al piloto del corredor (no soltar la herramienta sola).
- **Mensaje corto y de beneficios:** buen recordatorio de tono comercial (concreto, sin hype).

---

## 6. Escenario de amenaza (y por qué es bajo)
| Escenario | Probabilidad | Defensa de Contexto |
|---|---|---|
| SIGA añade datos reales del inmueble/zona | Media-baja | Requiere el foso (ficha en terreno + catastro) — lento y caro |
| Su chatbot evoluciona a "asesor de inversión" | Baja | Sin datos verificables, sería hype no defendible |
| Un portal grande copia ambos | Existente siempre | El foso es el dato verificado, no el software |

La defensa no es el software (copiable); es el **dato verificado en terreno** + la **bitácora de mantenimiento** que retiene al propietario.

---

## 7. Recomendación: agendar la demo (reconocimiento de bajo costo)
Vale más como inteligencia que como compra. Objetivo: medir el solape real y detectar la costura de integración.

### Guion de 6 preguntas para la demo
1. **"Su agente conversacional, ¿entiende algo del inmueble y la zona, o se enfoca en calificar al lead?"** → mide el solape real.
2. **"¿Tienen API o integraciones con otras herramientas?"** → confirma si pueden ser canal de la API de Contexto.
3. **"¿De dónde sacan los datos de las propiedades, si los manejan?"** → revela si hay (o no) capa de datos del activo.
4. **"¿A quién venden: corredor independiente, agencia o portal? ¿Cuál es el precio?"** → segmento y poder de compra.
5. **"¿Cómo manejan la ficha del inmueble — fotos, estado, precio? ¿Verifican algo?"** → ver si tocan nuestro territorio.
6. **"¿Tienen pensado integrar inteligencia de mercado o de inversión?"** → detecta intención de moverse hacia nuestra capa.

### Qué verificar por fuera (antes o después de la demo)
- Sitio web / quién está detrás / país de origen.
- Si publican docs de API o marketplace de integraciones.
- Reseñas de corredores (qué aman y qué les falta) → posibles ganchos para Contexto.

---

## 8. Posición de una línea (para tener lista si surge)
> *"SIGA organiza tu trabajo como corredor. Contexto le pone cerebro a cada inmueble que vendes. No competimos — encajamos: tu CRM con nuestra inteligencia de activo y de inversión."*
