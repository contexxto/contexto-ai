# Estudio de Habitabilidad Medida — Quito

### Equipamiento urbano a distancia caminable, medido en 18 sectores · Edición 1

**Fecha:** 2026-08-04 · **Autor:** Contexto AI · **Fuente:** capa propia (`pois_propios`, 8.499 puntos en Quito)
**Motor reproducible:** [`scripts/estudio_habitabilidad_quito.py`](../scripts/estudio_habitabilidad_quito.py) · **Datos crudos:** [`datos_estudio_habitabilidad_quito.json`](datos_estudio_habitabilidad_quito.json)

> ⚠️ **Este estudio cuenta equipamiento medido. NO ordena sectores por deseabilidad ni recomienda dónde vivir.** Más servicios no significa "mejor zona": significa más servicios. Quien pondera es cada persona, según su vida — no valora igual quien trabaja desde casa que quien lleva hijos al colegio. La tabla está ordenada **geográficamente**, nunca por cantidad.

---

## 0. Por qué existe este estudio (y en qué se diferencia)

En Lima, **CODIP + IPSOS** publican desde hace 7 ediciones el *Estudio del Perfil del Comprador* (n=739, IC ±4%, panel del portal Nexo Inmobiliario). Es un buen estudio y responde una pregunta legítima: **qué dice la gente que quiere.** Entre sus preguntas está *"¿qué atributos te hacen elegir un distrito?"*.

Este documento responde una pregunta distinta, y complementaria:

> **¿Qué hay realmente en cada sector, a distancia caminable?**

La diferencia no es de presupuesto, es de método. Un estudio de perfil mide **preferencia declarada**; este mide **equipamiento observado**. Uno pregunta, el otro cuenta. Y donde el primero necesita una muestra y trabajo de campo, el segundo necesita una capa de datos geográficos propia — que es exactamente el activo que Contexto construyó.

**Lo que este estudio NO puede hacer, y no finge hacer:** no dice cuántos dormitorios quiere la gente, ni su presupuesto, ni su momento de compra. Eso requiere encuesta. Aquí no hay ninguna cifra de intención declarada.

---

## 1. Ficha técnica

| | |
|---|---|
| **Universo** | 18 sectores de Quito (Norte, Centro y Sur), definidos por centroide aproximado |
| **Fuente de datos** | `pois_propios`: 8.499 puntos de interés en Quito — Overture Places + OpenStreetMap, conflados y curados |
| **Categorías** | transporte · supermercado · farmacia · salud · educación · parque · centro comercial · iglesia · seguridad (9) |
| **Radio de análisis** | **1.200 m en línea recta** (≈15 min a pie a 80 m/min) |
| **Fecha de medición** | 2026-08-04 |
| **Reproducibilidad** | Motor abierto en el repo; cualquiera con la capa puede re-correrlo |

**Tres límites que hay que decir en voz alta:**

1. **El radio es una aproximación generosa.** 1.200 m en línea recta cubre **más** área que una isócnona real por calles. Los conteos son un **techo**, no la cifra exacta caminable. *(El motor de isócronas reales —Valhalla— ya opera en producción; la edición 2 debe usarlo.)*
2. **Los centroides de sector son aproximados.** Sirven para comparar sectores entre sí, no para describir un punto exacto. Mover el centroide 300 m cambia los números.
3. **La capa mide presencia, no calidad ni horario.** Que haya 6 puntos de salud no dice si están abiertos, si atienden urgencias o si son consultorios pequeños.

---

## 2. La tabla

*Orden geográfico (Norte → Centro → Sur), nunca por cantidad. "Más escaso" = la categoría con menos puntos de la canasta cotidiana (supermercado, farmacia, salud, educación).*

| Sector | Zona | Total | Transp. | Súper | Farm. | Salud | Educ. | Parque | Más escaso | Masivo más cercano |
|---|---|---:|---:|---:|---:|---:|---:|---:|---|---|
| Carcelén | Norte | 100 | 28 | 23 | 16 | 6 | 9 | 5 | salud (6) | Terminal Carcelén (594 m) |
| Cotocollao | Norte | 204 | 36 | 54 | 34 | 20 | 25 | 8 | salud (20) | Rumihurco (381 m) |
| El Batán | Norte | 332 | 71 | 60 | 47 | 59 | 45 | 26 | educación (45) | La Carolina (670 m) |
| El Bosque | Norte | 225 | 30 | 14 | 34 | 89 | 24 | 18 | súper (14) | Iñaquito (1.803 m) |
| **El Labrador** | Norte | **399** | 90 | 65 | 73 | 60 | 53 | 26 | educación (53) | **Estación de Metro (601 m)** |
| González Suárez | Norte | 360 | 84 | 66 | 42 | 68 | 63 | 9 | farmacia (42) | Panamericana Int. (633 m) |
| Iñaquito | Norte | 430 | 88 | 68 | 74 | 87 | 61 | 20 | educación (61) | Estación Iñaquito (148 m) |
| La Carolina | Norte | 449 | 96 | 77 | 66 | 93 | 57 | 26 | educación (57) | Iñaquito (439 m) |
| **La Concepción** | Norte | **369** | 93 | 60 | 64 | 56 | 43 | 25 | educación (43) | **Estación de Metro (588 m)** |
| Ponceano | Norte | 137 | 41 | 36 | 14 | 17 | 16 | 1 | farmacia (14) | Flor del Valle (746 m) |
| Quito Tenis | Norte | 252 | 45 | 38 | 35 | 61 | 32 | 22 | educación (32) | Iñaquito (1.256 m) |
| La Floresta | Centro-N | 479 | 109 | 89 | 68 | 71 | 98 | 10 | farmacia (68) | Panamericana Int. (270 m) |
| La Mariscal | Centro-N | 569 | 133 | 90 | 87 | 91 | 113 | 13 | farmacia (87) | Cruz del Sur (410 m) |
| Centro Histórico | Centro | 398 | 82 | 92 | 52 | 27 | 36 | 22 | salud (27) | San Francisco (263 m) |
| Chillogallo | Sur | 192 | 34 | 90 | 17 | 12 | 20 | 3 | salud (12) | Santa Rosa 3 (939 m) |
| La Magdalena | Sur | 301 | 38 | 78 | 48 | 52 | 41 | 15 | educación (41) | Terminal de bus (331 m) |
| Quitumbe | Sur | 136 | 48 | 29 | 24 | 8 | 7 | 11 | educación (7) | Quitumbe (1.185 m) |
| Solanda | Sur | 271 | 30 | 92 | 51 | 37 | 19 | 21 | educación (19) | Solanda (410 m) |

---

## 3. Lo que muestran los números

### 3.1 El rango es de 5,7x

De **100** puntos de servicio a 15 min (Carcelén) a **569** (La Mariscal). Vivir en Quito no es una sola experiencia: entre dos sectores de la misma ciudad hay casi seis veces de diferencia en lo que se alcanza caminando.

### 3.2 Conectado no es lo mismo que abastecido

El hallazgo que un promedio esconde. Hay sectores con **transporte abundante y canasta cotidiana escasa**:

| Sector | Transporte | Pero solo… |
|---|---:|---|
| Carcelén | 28 | **6** puntos de salud |
| Quitumbe | 48 | **7** puntos de educación |
| Chillogallo | 34 | **12** puntos de salud |
| El Bosque | 30 | **14** supermercados |

**Quitumbe es el caso más claro:** tiene estación de Metro y 48 puntos de transporte, pero **7 de educación y 8 de salud**. Está construido para *salir*, no para *quedarse*. Un índice promedio lo mostraría como "bien conectado"; el eslabón débil muestra lo que realmente falta.

### 3.3 Cada sector tiene su carencia, y no es la misma

- **El Bosque** concentra salud (89, el máximo de la muestra) pero es el más escaso en supermercados (14).
- **Chillogallo y Solanda** tienen abundante comercio (90 y 92 súper) y poca salud o educación.
- **La Mariscal y La Floresta** — los dos totales más altos — tienen su punto débil en farmacias, no por escasez sino porque todo lo demás es aún más denso.
- **Ponceano** es el único sector sin **ningún** centro comercial a este radio.

Por eso el estudio no rankea: **el sector "más completo" depende de qué te falta a ti.**

### 3.4 El eje del Metro (Labrador–La Concepción)

Los dos sectores del eje quedan en el tercio superior de la muestra: **El Labrador 399** y **La Concepción 369** puntos de servicio, ambos a ~600 m de una estación de Metro. Su punto más escaso es educación (53 y 43). Es un sector de servicios densos y conexión masiva, con equipamiento educativo por debajo de La Floresta o La Mariscal.

---

## 4. Qué se puede hacer con esto (y qué no)

**Sirve para:**
- **Emparejar intención con lugar**: si alguien declara que necesita colegio cerca, los datos dicen dónde hay más — sin decirle dónde debe vivir.
- **Dar contexto verificable a un inmueble**: no "excelente ubicación", sino "a 15 min a pie tienes X, Y, Z — medido".
- **Detectar huecos de mercado**: un sector con transporte fuerte y servicios débiles es una oportunidad de desarrollo y una advertencia para el comprador.

**No sirve para** —y no debe usarse así—:
- Rankear barrios por calidad o deseabilidad.
- Segmentar personas por sector (proxy de clase protegida).
- Sustituir la verificación en terreno: esta capa dice qué existe según Overture/OSM, no qué encontró un corredor parado en la calle.

---

## 5. Metodología y próximas ediciones

**Cómo se calculó:** para cada centroide de sector, se cuentan los POIs operativos de `pois_propios` dentro de 1.200 m geodésicos (`ST_DWithin` sobre `geography`), agrupados por categoría. La estación masiva más cercana se busca sin límite de radio (metro, terminal, estación de tren). Motor completo y reproducible en el repo.

**Edición 2 — mejoras comprometidas:**
1. **Isócronas reales por calle** en vez de radio (el motor ya opera; elimina el sesgo del "techo").
2. **Más sectores y centroides mejor anclados** (por parroquia censal, no por punto aproximado).
3. **Cruce con oferta real** cuando haya inventario verificado suficiente.
4. **Verificación en terreno** de una muestra: el diferencial que ninguna capa descargada tiene.

**Lo que nunca va a tener:** un score único de zona.

---

## 6. Proveniencia y honestidad

- **Dato propio:** los 8.499 POIs son de Contexto (Overture Places + OSM, conflados y curados). **No están verificados en terreno** — eso es otra cosa y se rotula aparte cuando existe.
- **Comparación con el estudio de Lima:** *per CODIP/IPSOS Perú (7ª edición, campo oct-2025 a ene-2026, n=739, panel del portal Nexo Inmobiliario)*. Se cita como referencia de método, no como dato aplicable a Quito: otra ciudad, otra moneda, otro sistema hipotecario.
- **Cifras de mercado de terceros** (precio/m² de Quito, participación de gama media) **no se usan en este estudio** — se mencionan en la investigación de contexto pero no forman parte de las mediciones de aquí.
- Cada número de la tabla sale de una consulta reproducible sobre datos propios. Si alguien discrepa, puede correr el motor.

> **La frase que resume el método:** ellos preguntan qué quiere la gente; nosotros contamos qué hay. Las dos preguntas importan — pero solo una se puede verificar sin encuestar a nadie.
