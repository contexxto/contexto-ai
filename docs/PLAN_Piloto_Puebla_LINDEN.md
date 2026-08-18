# Plan — Piloto Puebla con LINDEN Inmobiliaria

### Documento ancla · se itera EN ESTE MISMO doc con cada aprendizaje del piloto

**Creado:** 2026-08-17 · **Estado:** propuesta · nada construido para Puebla · **Dueño:** Carlos + Contexto

<!-- estado-verificable
codigo:
  existe: app/llegada.py::clasificar_canal
  existe: app/puerta.py::evaluar_puerta
  existe: app/embudo.py::componer_reparto
  existe: app/pendiente.py::componer_pendiente
  existe: app/scores_heuristicos.py
  existe: scripts/foso_pois_spike.py
  no-existe: app/agenda.py
  no-existe: app/expediente.py
  no-existe: app/tokko.py
datos:
  2026-08-17: scripts/foso_pois_spike.py tiene UNA sola ciudad con bbox medido (quito); puebla está comentada como "pendiente de medir"
  2026-08-17: app/scores_heuristicos.py resuelve ruido/walk/vegetación con 7 sectores de Quito escritos a mano; fuera de esa lista devuelve el default MEDIO
  2026-08-17: docker-compose.valhalla.yml carga tiles de ecuador-latest.osm.pbf — no cubre México
  2026-08-17: la API de Tokko es pública (developers.tokkobroker.com), acepta escribir contactos con properties[] y tags[], y su doc dice que TODO contacto entra etiquetado como "WEB" sin distinguir el canal de origen
-->

> **Idea en una línea.** Contexto sostiene **el ciclo completo del comprador** —de la llegada
> al handoff, al seguimiento, a la visita agendada— sobre 10-20 unidades en Puebla. Tokko
> conserva la operación (portales, expediente, comisiones) y recibe el lead ya perfilado por
> API. Lo que se prueba no es una funcionalidad: es que **un lead que llega explicado vale
> más que uno de ruleta**.

---

## 0. Nota de honestidad — léelo primero

**Para Puebla no hay nada construido.** El dato de entorno de Contexto es de Quito, y tres
piezas concretas lo bloquean (§3). Antes de prometerle algo a LINDEN, esas tres tienen que
tener respuesta — porque **son la propuesta de valor entera**, no preparación.

El motivo es incómodo y conviene tenerlo escrito: la categoría de *"IA que atiende WhatsApp
y califica leads"* está **commoditizada**. Waichatt (USD 180/mes, usuarios ilimitados,
importa propiedades de Tokko), Cliengo "Ignacio", Bot School, Waibot, Wakai y MyWChannel
hacen todos lo mismo, y su panel de calificación entrega los mismos campos que el handoff
destilado de Contexto. **Ninguno dice una palabra del lugar.** Si Contexto llega a Puebla
sin dato de entorno, llega siendo un competidor peor de algo que ya existe seis veces.

---

## 1. Qué es LINDEN (de sus propios documentos)

Inmobiliaria mexicana, 15 asesores más coordinaciones. CRM **Tokko Broker**. Alianza de
crédito con **Solidez Hipotecaria**. Su proceso comercial son 4 bloques —captación,
alta/comercialización, formalización, operación— y su generación de leads viene de Meta Ads,
Google Ads, portales, redes, lonas y referidos, con asignación por *"guardia / ruleta
comercial"*.

**Su dolor declarado, textual:** *"el cliente está viendo propiedades con otros 3-7 asesores"*.
Quien llega sabiendo, llega primero.

**Y una carencia que documenta el propio Tokko:** *"todos los contactos ingresados vienen
como WEB sea cual sea su origen"*. Listan seis fuentes de leads y el CRM las colapsa en una:
hoy LINDEN **no puede saber qué canal le funciona**.

---

## 2. Alcance — el ciclo del comprador, completo

**DENTRO (Contexto lo sostiene entero):**

| Etapa | Estado |
|---|---|
| Llegada y canal | ✅ F0 — incluido el escaneo de QR que no escribe |
| Conversación y encaje | ✅ Motor de intención + encaje con evidencia |
| Puerta suave (alerta) | ✅ F1 — captura sin transferir a nadie |
| Handoff al asesor | ✅ Con la conversación destilada y el porqué |
| Seguimiento / reenganche | ✅ Con holdout y medición de lift |
| Qué espera hoy | ✅ El CRM abre con el pendiente |
| **Visita agendada** | ❌ **Falta** (§4) |

**FUERA por diseño (se queda en Tokko):** multipublicación en portales, expediente
documental y escrituración, comisiones y facturación, y el crédito —que es de Solidez, y
donde las barandas de Contexto prohíben opinar.

**El criterio de admisión, y es el candado contra la deriva:** una pieza entra si puede
trazar su línea hasta el handoff que cierra **y** hasta el dato del lugar. Un calendario la
traza (visita agendada = handoff que avanzó). Un módulo de facturación no.

---

## 3. Los tres bloqueos de Puebla — resolver ANTES de prometer

| # | Bloqueo | Qué se hace | Esfuerzo |
|---|---|---|---|
| 1 | **POIs del entorno** | Medir el bbox de Puebla en un visor real y correr `foso_pois_spike.py puebla`. El código ya está listo y multi-ciudad desde la migración 019 | Una tarde |
| 2 | **Ruido / "tranquilidad"** | Hoy son **7 sectores de Quito escritos a mano**; en Puebla devolvería `MEDIO` para las 20 unidades. **Decisión: o se mide, o se saca de la whitelist para ese mercado** | Decisión + 1-2 días |
| 3 | **Isócronas** | Valhalla carga `ecuador-latest.osm.pbf`. México pesa 3-4× — es RAM, disco y build | Días + costo de infra |

**Sobre el #2, que es el importante.** `tranquilidad` es una de las 8 dimensiones del
encaje. Un `MEDIO` universal no rompe nada —el sistema ya reporta su cobertura y las
tarjetas dirían *"calculado sobre 5 de las 6 cosas que pediste"*— pero **empata a las 20
unidades en esa dimensión y no impresiona a nadie**. Sacarla del mercado Puebla es más
honesto que fingirla.

---

## 4. Las tres piezas de producto que faltan

Las tres son **de la relación**, no de la contabilidad — por eso entran.

1. **Agendamiento de visita.** Es el paso siguiente del handoff y el bloque "Citas y
   Recorridos" del proceso de LINDEN. Sin esto el ciclo se corta justo donde el lead vale más.
2. **Checklist documental.** Lo que ellos llaman *"integración de expediente"*. Es una lista
   de estados, no un motor: qué falta y de quién depende.
3. **Alta de inmueble por el corredor**, capaz de sostener 20 fichas bien hidratadas.
   Existe `PublishAsset`; falta confirmar que aguanta.

---

## 5. La integración con Tokko

Verificada el 2026-08-17 en [developers.tokkobroker.com](https://developers.tokkobroker.com/):
pública, con playground, **una API key por inmobiliaria** — o sea que **LINDEN autoriza sin
pedirle permiso a Tokko**.

- **Leer:** `/api/v1/property`, `/property/search`, `/development` (1000 por request + offset).
- **Escribir el lead:** `TokkoWebContact` con `name`, `email`, `phone`, `text` **libre**,
  `tags[]` y `properties[]` para vincularlo al inmueble.

**El `text` libre y los `tags` son la jugada:** ahí caben el perfil destilado, las razones
del score y —lo que su CRM no puede— **el canal real de F0**. El asesor abre la consulta de
siempre y encuentra el perfil ya escrito.

**Cautela:** la documentación muestra la URL base en `http://`. Antes de mandar datos de un
comprador hay que confirmar TLS; PII en claro no es una opción. Y la doc dice "actualizado
hace un año": confirmar vigencia con soporte antes de construir.

---

## 6. Qué se mide, y qué NO se puede medir con 20 unidades

**La trampa a evitar:** prometer "más cierres". Con 20 unidades y 8-12 semanas habrá quizá
1-3 escrituraciones. **Con ese N no se prueba nada**, y afirmarlo sería exactamente la cifra
sobre universo insuficiente que este proyecto persigue.

**Métricas primarias (sí alcanzan N):**

| Qué | Por qué se puede |
|---|---|
| **Llegadas → conversaron → handoff**, por canal | F0 y el reparto lo dan desde el día uno. Y es lo que Tokko no puede |
| **Handoffs por cada 100 llegadas** | El escalón real, con suficiente volumen |
| **¿El asesor llegó con datos?** | Cuántos de los 16 puntos venían resueltos antes de la llamada |
| **Demanda no cubierta** | `hubo_match = false`: qué pide Puebla que LINDEN no tiene |

**Secundaria:** lift del reenganche (tocado vs. holdout) — ya instrumentado, reportará
"acumulando" hasta tener N.

**Cualitativa, y decisiva:** ¿los 15 asesores lo abren sin que nadie se los recuerde?

---

## 7. Criterio de parada

Se declara ahora, no cuando duela:

- **A las 4 semanas, si los asesores no lo abren solos**, el piloto no está midiendo el
  producto: está midiendo la adopción, y hay que arreglar eso antes de seguir.
- **Si el dato de entorno de Puebla no se puede cargar con calidad**, Contexto no tiene
  diferenciador ahí y el piloto se detiene o se muda a un mercado con dato.
- **Si el volumen de llegadas es tan bajo que el reparto no distingue canales**, el problema
  es de tráfico (de LINDEN) y no de producto; se dice y no se disfraza.

---

## 8. Riesgos

**1. Fair Housing / datos personales — y hay que ponerlo sobre la mesa al inicio.** El
checklist de perfilamiento de LINDEN pide *"número de personas que vivirán"*, *"quién firma"*,
*"¿su familia está creciendo?"*, *"¿compra individual o en pareja?"*. Recolectar composición
familiar para dimensionar el espacio es legítimo; **guardarla como atributo del cliente y
usarla para decidir a quién se atiende, no lo es** — y su sistema no distingue las dos cosas.

Contexto puede darles el mismo valor comercial sin la exposición: *"necesita 3 dormitorios y
acepta mascotas"* en vez de *"familia de 5"*. `DIMENSIONES` es una whitelist cerrada: el
motor **no puede** puntuar por quién eres. **Esa frontera se fija en el piloto de 20
unidades, no cuando ya son 15 asesores con el hábito hecho.** (No es asesoría legal: es una
exposición que alguien que sí lo sea debe validar.)

**2. La deriva a portal.** Si el CRM crece, el corredor pide funcionalidades a diario y el
comprador —el core declarado— pasa a ser insumo. El candado es el criterio de admisión del §2.

**3. Prospección en frío.** El checklist premium de LINDEN busca *"qué tendría que pasar para
que el cliente QUIERA comprar"* sobre precalificados que no están buscando. Es legal y es su
negocio, pero es el opuesto de la puerta que abre el motor solo en el callejón honesto.
**Contexto sirve el perfilamiento inbound; no automatiza esa prospección.** Y esa frontera es
vendible, no una limitación.

---

## 9. Lo que NO se promete

- No reemplaza Tokko en el piloto. Portales, expediente y comisiones se quedan ahí.
- No opina de crédito. Eso es de Solidez, y las barandas lo prohíben.
- No promete más cierres en 12 semanas: promete **ver el embudo entero por primera vez**.
- No garantiza el diferenciador del lugar hasta que el §3 esté resuelto.

---

## Changelog (iterar aquí)

- **2026-08-17 — v0.1** — Doc creado tras leer los cuatro documentos de LINDEN (proceso
  comercial, flujo general, organigrama, proceso de créditos), el requerimiento de
  perfilamiento (16 puntos + checklist premium), y el scraping de Tokko Broker y su
  competencia (Waichatt, Cliengo, Bot School). Los tres bloqueos de Puebla y la API de Tokko
  se verificaron contra el código y contra la documentación pública el mismo día. Nada
  construido.
