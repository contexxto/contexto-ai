# Estudio de Habitabilidad Medida — Quito

### Equipamiento urbano alcanzable a pie, medido en 18 sectores · **Edición 2**

**Fecha:** 2026-08-04 · **Autor:** Contexto AI · **Fuente:** capa propia (`pois_propios`, 8.499 puntos en Quito)
**Método:** isócrona real de **15 min a pie por calles** (Valhalla, `costing=pedestrian`)
**Motor reproducible:** [`scripts/estudio_habitabilidad_quito.py`](../scripts/estudio_habitabilidad_quito.py) · **Datos crudos:** [`datos_estudio_habitabilidad_quito.json`](datos_estudio_habitabilidad_quito.json)

> ⚠️ **Este estudio cuenta equipamiento medido. NO ordena sectores por deseabilidad ni recomienda dónde vivir.** Más servicios no significa "mejor zona": significa más servicios. Quien pondera es cada persona, según su vida — no valora igual quien trabaja desde casa que quien lleva hijos al colegio. La tabla está ordenada **geográficamente**, nunca por cantidad.

---

## 0. Por qué existe este estudio (y en qué se diferencia)

En Lima, **CODIP + IPSOS** publican desde hace 7 ediciones el *Estudio del Perfil del Comprador* (n=739, IC ±4%, panel del portal Nexo Inmobiliario). Es un buen estudio y responde una pregunta legítima: **qué dice la gente que quiere.** Entre sus preguntas está *"¿qué atributos te hacen elegir un distrito?"*.

Este documento responde una pregunta distinta y complementaria:

> **¿Qué se alcanza realmente a pie desde cada sector?**

La diferencia no es de presupuesto, es de método. Un estudio de perfil mide **preferencia declarada**; este mide **equipamiento alcanzable**. Uno pregunta, el otro camina. Y donde el primero necesita muestra y trabajo de campo, el segundo necesita una capa geográfica propia y un motor de rutas — que es exactamente el activo que Contexto construyó.

**Lo que este estudio NO puede hacer, y no finge hacer:** no dice cuántos dormitorios quiere la gente, ni su presupuesto, ni su momento de compra. Eso requiere encuesta. Aquí no hay ninguna cifra de intención declarada.

---

## 1. Ficha técnica

| | |
|---|---|
| **Universo** | 18 sectores de Quito (Norte, Centro y Sur), definidos por centroide aproximado |
| **Fuente de datos** | `pois_propios`: 8.499 puntos de interés en Quito — Overture Places + OpenStreetMap, conflados y curados |
| **Categorías** | transporte · supermercado · farmacia · salud · educación · parque · centro comercial · iglesia · seguridad (9) |
| **Área de análisis** | **Isócrona real de 15 min a pie**, calculada por la red de calles (Valhalla auto-hospedado, `costing=pedestrian`) |
| **Fecha de medición** | 2026-08-04 |
| **Reproducibilidad** | Motor abierto en el repo; con la capa y Valhalla, cualquiera lo re-corre |

**Dos límites que hay que decir en voz alta:**

1. **Los centroides de sector son aproximados.** Sirven para comparar sectores entre sí, no para describir un punto exacto. Mover el centroide 300 m cambia los números.
2. **La capa mide presencia, no calidad ni horario.** Que haya 6 puntos de salud no dice si están abiertos, si atienden urgencias o si son consultorios pequeños. Y **nada aquí está verificado en terreno** — eso es otra cosa, y se rotula aparte cuando existe.

---

## 2. Lo primero: esta edición corrige a la anterior

La **edición 1** de este estudio usó un radio de 1.200 m en línea recta como aproximación de "15 minutos a pie". Era una aproximación declarada, pero resultó ser **mucho peor de lo que suponíamos**.

Un círculo no conoce quebradas, ni avenidas sin cruce, ni manzanas cerradas, ni la ladera. Al medir con la red de calles real:

| | Sesgo del radio |
|---|---|
| **Mediana** | el círculo contaba **+37%** de más |
| **Mínimo** | +15% (Centro Histórico — traza regular, plana, muy conectada) |
| **Máximo** | **+471%** (Ponceano — el radio prometía 137 servicios; a pie se alcanzan **24**) |

Y la consecuencia sobre el hallazgo principal:

> La brecha entre el sector con más y con menos equipamiento pasó de **5,7x** (radio) a **19,7x** (isócrona real). **La desigualdad real es 3,5 veces mayor de la que mostraba el método aproximado.**

Se publica el error en vez de sustituirlo en silencio, porque el método es parte del dato. Un estudio que corrige su propia medición vale más que uno que nunca dice cómo midió.

---

## 3. La tabla

*Orden geográfico (Norte → Centro → Sur), nunca por cantidad. "Más escaso" = la categoría con menos puntos de la canasta cotidiana (supermercado, farmacia, salud, educación). "ed.1" = cuánto inflaba el método anterior.*

| Sector | Zona | km² a pie | Total | Transp. | Súper | Farm. | Salud | Educ. | Parque | Más escaso | ed.1 |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---|---:|
| Carcelén | Norte | 2,62 | 73 | 21 | 19 | 15 | 6 | 5 | 2 | educación (5) | +37% |
| Cotocollao | Norte | 2,84 | 165 | 31 | 44 | 28 | 18 | 18 | 6 | salud (18) | +24% |
| El Batán | Norte | 2,54 | 232 | 53 | 45 | 35 | 39 | 31 | 13 | educación (31) | +43% |
| El Bosque | Norte | 1,76 | 64 | 12 | 10 | 13 | 10 | 8 | 6 | educación (8) | **+252%** |
| **El Labrador** | Norte | **3,55** | **334** | 88 | 53 | 59 | 52 | 45 | 13 | educación (45) | +19% |
| González Suárez | Norte | 2,58 | 203 | 43 | 38 | 27 | 31 | 42 | 5 | farmacia (27) | +77% |
| Iñaquito | Norte | 3,48 | 346 | 69 | 53 | 56 | 77 | 47 | 15 | educación (47) | +24% |
| La Carolina | Norte | 3,27 | 327 | 75 | 53 | 47 | 70 | 39 | 16 | educación (39) | +37% |
| **La Concepción** | Norte | **3,23** | **274** | 66 | 41 | 53 | 42 | 34 | 18 | educación (34) | +35% |
| Ponceano | Norte | **1,22** | **24** | 10 | 6 | 2 | 3 | 2 | 0 | farmacia (2) | **+471%** |
| Quito Tenis | Norte | 2,70 | 166 | 33 | 29 | 28 | 38 | 18 | 10 | educación (18) | +52% |
| La Floresta | Centro-N | 3,46 | 385 | 90 | 78 | 59 | 39 | 82 | 8 | salud (39) | +24% |
| La Mariscal | Centro-N | 3,51 | **472** | 108 | 76 | 70 | 76 | 91 | 11 | farmacia (70) | +21% |
| Centro Histórico | Centro | **3,70** | 347 | 69 | 74 | 50 | 27 | 33 | 16 | salud (27) | +15% |
| Chillogallo | Sur | 3,31 | 157 | 29 | 75 | 16 | 10 | 14 | 2 | salud (10) | +22% |
| La Magdalena | Sur | 2,81 | 204 | 31 | 47 | 34 | 35 | 30 | 12 | educación (30) | +48% |
| Quitumbe | Sur | 2,63 | 84 | 30 | 14 | 17 | 6 | 6 | 4 | salud (6) | +62% |
| Solanda | Sur | 2,87 | 192 | 24 | 65 | 36 | 27 | 9 | 14 | educación (9) | +41% |

---

## 4. Lo que muestran los números

### 4.1 Quince minutos no son quince minutos

El hallazgo que solo aparece al medir por calles: **el área alcanzable a pie varía 3x entre sectores.**

- **Centro Histórico: 3,70 km²** — traza regular, plana, muy conectada.
- **Ponceano: 1,22 km²** — la misma caminata de 15 minutos cubre **un tercio** de ciudad.

En una ciudad de ladera y quebradas como Quito, *"a 15 minutos a pie"* no describe una distancia: describe **cuánta ciudad te deja alcanzar la traza urbana**. Dos personas caminando lo mismo, en sectores distintos, viven ciudades de tamaño diferente.

### 4.2 El rango real es de 19,7x

De **24** puntos de servicio alcanzables (Ponceano) a **472** (La Mariscal). No es una diferencia de matiz: es una diferencia de vida cotidiana dentro de la misma ciudad.

### 4.3 Conectado no es lo mismo que abastecido

Hay sectores con transporte y sin canasta cotidiana:

| Sector | Transporte | Pero solo… |
|---|---:|---|
| Ponceano | 10 | **2** farmacias |
| Carcelén | 21 | **5** puntos de educación |
| Quitumbe | 30 | **6** puntos de salud |
| El Bosque | 12 | **8** puntos de educación |

**Quitumbe sigue siendo el caso más nítido:** tiene estación de Metro y 30 puntos de transporte alcanzables, pero **6 de salud y 6 de educación**. Está construido para *salir*, no para *quedarse*. Un promedio lo llamaría "bien conectado"; el eslabón débil muestra lo que falta.

### 4.4 Sectores sin ninguna presencia de una categoría

A 15 minutos a pie, medidos por calle:

- **Ponceano:** ningún parque, ningún centro comercial, ningún punto de seguridad.
- **Carcelén:** ningún centro comercial.

### 4.5 El eje del Metro (Labrador–La Concepción)

**El Labrador** es el sector con **menor sesgo de toda la muestra (+19%)**: su traza es tan caminable que el círculo casi acertaba. Alcanza **334** puntos de servicio en **3,55 km²** — de las áreas peatonales más grandes medidas. **La Concepción** alcanza **274** en 3,23 km². En ambos, la categoría más escasa es educación.

Traducido: es un eje de **alta conectividad y servicios densos, con equipamiento educativo por debajo** de La Floresta o La Mariscal.

---

## 5. Qué se puede hacer con esto (y qué no)

**Sirve para:**
- **Emparejar intención con lugar**: si alguien declara que necesita colegio cerca, los datos dicen dónde hay más — sin decirle dónde debe vivir.
- **Dar contexto verificable a un inmueble**: no "excelente ubicación", sino "a 15 min caminando por calles reales alcanzas X, Y, Z — medido".
- **Detectar huecos de mercado**: transporte fuerte con servicios débiles es a la vez una oportunidad de desarrollo y una advertencia para el comprador.

**No sirve para** —y no debe usarse así—:
- Rankear barrios por calidad o deseabilidad.
- Segmentar personas por sector (proxy de clase protegida).
- Sustituir la verificación en terreno: esta capa dice qué existe según Overture/OSM, no qué encontró un corredor parado en la calle.

---

## 6. Metodología y próximas ediciones

**Cómo se calculó:** para cada centroide de sector se pide a Valhalla la isócrona peatonal de 15 minutos (`costing=pedestrian`, polígonos cerrados) y se cuentan los POIs operativos de `pois_propios` **dentro del polígono** (`ST_Contains`). El área se calcula en `geography` (km² reales). En paralelo se cuenta el total dentro del radio de 1.200 m de la ed.1, solo para cuantificar el sesgo del método anterior. Si Valhalla no responde para un sector, **el sector se omite** en vez de sustituirse por radio: mezclar dos métodos en la misma tabla la invalidaría.

**Edición 3 — mejoras pendientes:**
1. **Centroides por parroquia censal**, no por punto aproximado.
2. **Más sectores** y cobertura de valles (Cumbayá, Tumbaco).
3. **Cruce con oferta real** cuando haya inventario verificado suficiente.
4. **Verificación en terreno** de una muestra: el diferencial que ninguna capa descargada tiene.

**Lo que nunca va a tener:** un score único de zona.

---

## 7. Proveniencia y honestidad

- **Dato propio:** los 8.499 POIs son de Contexto (Overture Places + OSM, conflados y curados). **No están verificados en terreno.**
- **Motor de isócronas propio:** Valhalla auto-hospedado con tiles de Ecuador. Sin llaves de terceros — y sin el problema legal de almacenar isócronas de Google (sus términos lo prohíben; la licencia ODbL de OSM no).
- **Comparación con el estudio de Lima:** *per CODIP/IPSOS Perú (7ª edición, campo oct-2025 a ene-2026, n=739, panel del portal Nexo Inmobiliario)*. Se cita como referencia de método, no como dato aplicable a Quito: otra ciudad, otra moneda, otro sistema hipotecario.
- **Corrección publicada:** la ed.1 de este mismo documento sobreestimaba entre 15% y 471%. El dato viejo no se borró: se midió y se reporta.
- Cada número sale de una consulta reproducible sobre datos propios. Si alguien discrepa, puede correr el motor.

> **La frase que resume el método:** ellos preguntan qué quiere la gente; nosotros medimos qué se alcanza caminando. Las dos preguntas importan — pero solo una se puede verificar sin encuestar a nadie.
