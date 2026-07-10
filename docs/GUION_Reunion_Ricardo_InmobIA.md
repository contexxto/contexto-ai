# Guion — Reunión con Ricardo Suárez (InmobIA, Mazatlán)

> ⚠️ **SUPERSEDED (2026-07-09):** este guion es de la etapa "integración por API" (15-jun) y
> contradice la estrategia v2 (propone revenue-share con números, fee mensual y piloto de 90 días —
> prohibido por "cero números primero"). **Usar [`PREP_Mesa_Ricardo_SieteHuesos.md`](PREP_Mesa_Ricardo_SieteHuesos.md) +
> [`ENCAJE_Mazatlan_Ricardo_1pager.md`](ENCAJE_Mazatlan_Ricardo_1pager.md).** Se conserva solo como historial.

**Objetivo:** descubrir su interés real, posicionar Contexto como **el motor que integra (no construye)**, y aterrizar un **piloto acotado**. NO vender una app; ofrecer infraestructura.
**Duración sugerida:** 30 min. **Regla de oro:** escucha 80%, habla 20%.

---

## 0) Antes de la llamada (checklist)
- [ ] **NDA mutuo** listo para enviar (no enseñar arquitectura a fondo sin firmar).
- [ ] **Demo preparada y probada:**
  - Mapa conversacional **sobre Mazatlán** (funciona global): tener una pregunta lista, p. ej. *"qué hay cerca de Marina Mazatlán"*.
  - **API de inversión** sobre un inmueble real: el de Jorge Salvador Lara (Quito) con **renta realista ($350 → bruta 8,4%)** para que el número luzca. *(Nota interna: aún no hay activos en Mazatlán; la demo de inversión es sobre un activo de Quito para mostrar la capacidad.)*
- [ ] One-pager `.docx` a la mano por si lo pide.

---

## 1) Apertura — escuchar primero (5 min)
No abras con tu pitch. Abre con **su mundo**:
> *"Ricardo, antes de contarte lo mío — cuéntame: ¿en qué punto exacto de tu funnel sientes que el comprador se enfría o que el lead llega 'flojo' para el desarrollador?"*

Deja que **él nombre el hueco** (la zona, la calidad del lead). Toma nota. Ese hueco es lo que tú llenas.

---

## 2) El encuadre (2 min)
> *"Yo no compito con tu funnel — soy la **capa de inteligencia** que lo hace más inteligente. Tú cierras la cita; yo hago que el comprador llegue sabiendo, y que el lead llegue con tesis. No construyes nada: lo integras vía API, como integrarías un proveedor de pagos."*

---

## 3) La demo en vivo (10 min) — *muestra, no cuentes*
1. **Mapa conversacional sobre Mazatlán:** *"párate en cualquier punto y pregúntale al mapa"* → ilumina servicios/rutas reales. Mensaje: *"esto responde con datos verificables de cualquier zona, hoy."*
2. **API de inversión (el momento fuerte):** muestra `GET /assets/{id}/investment` devolviendo el dashboard de un inmueble real — yields + veredicto + **alertas honestas** + **confianza por dato**. Mensaje:
   > *"Tu desarrollador no recibe 'alguien preguntó'. Recibe 'comprador interesado en un activo que rinde 8,4%, con la renta marcada como estimación y el estado por verificar'. Eso es un lead premium — y honesto. Por eso paga más."*

---

## 4) El modelo (3 min)
- **Revenue-share por cita calificada**, no tarifa plana. *"Mi contexto sube el valor de tu cita; tomo una tajada del delta. Si ganas más, gano más."*
- Arranque simple: fee mensual bajo + share por cita en el piloto.
- **Menú de integración A–E** (zona, mapa embebido, powered-by, captura de intención, **API de inversión**). Empezar por una.

---

## 5) Manejo de objeciones (prepáralas)
- **"¿Eres solo tú?"** → *"Opero AI-nativo: yo + un motor de estrategia + ejecución técnica con IA. Por eso envío como un equipo grande con costos de uno. Para ti eso es velocidad y un proveedor enfocado — y empezamos con un piloto acotado, no un matrimonio."* (No te disculpes; reencuádralo como virtud.)
- **"¿Funciona con datos de México?"** → *"El motor es global (validado en Quito y Bogotá); zona y servicios salen de Google/OpenStreetMap, que cubren Mazatlán hoy. La ficha verificada se construye con tus aliados en el piloto — y ese dato propio es el foso."*
- **"¿Por qué no lo construyo yo?"** → *"Podrías, en meses y con equipo. O lo integras esta semana y te concentras en lo tuyo: leads y desarrolladores. Apaleo le ganó al mercado hotelero siendo el motor que se integra, no el que cada hotel reconstruye."*
- **"¿Y si quiero exclusividad/los datos?"** → *"Tú eres dueño de tus análisis y datos; sin lock-in. Hablemos de exclusividad por mercado en el piloto."*

---

## 6) El cierre (3 min)
> *"Propongo: NDA mutuo esta semana, y un **piloto de 90 días** en Mazatlán — yo pongo la capa de inteligencia sobre tu inventario inicial, y medimos el *lift* en calidad de cita (las métricas de tu propio deck). Si las citas 'con contexto' valen y cierran más, escalamos. ¿Te late arrancar así?"*

Cierra con un siguiente paso CONCRETO y una fecha.

---

## Lo que NO hacer
- ❌ No revelar la arquitectura técnica a fondo sin NDA.
- ❌ No rogar ni sobrevender la "empresa" — vende el **motor** y el **piloto**.
- ❌ No perder de vista que **Grupo Bolívar es el pez 100x**: Ricardo es piloto + prueba internacional, no la prioridad. Que no te consuma foco.

## La frase ancla
> *"No vendo una app inmobiliaria. Vendo el motor de inteligencia que tu InmobIA integra — y que hace que cada lead llegue con tesis y verdad verificada."*
