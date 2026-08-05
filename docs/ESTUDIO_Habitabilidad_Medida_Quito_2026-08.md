# Estudio de Habitabilidad Medida — Quito

### Equipamiento urbano alcanzable a pie, medido en 40 parroquias del DMQ · **Edición 3**

**Fecha:** 2026-08-05 · **Autor:** Contexto AI · **Fuente:** capa propia (`pois_propios`, 8.499 puntos en Quito)
**Unidad de análisis:** **parroquia** (urbana y rural), centroide oficial de OpenStreetMap corregido al *centro vivido*
**Método:** isócrona real de **15 min a pie por calles** (Valhalla, `costing=pedestrian`)
**Motor:** [`scripts/estudio_habitabilidad_quito.py`](../scripts/estudio_habitabilidad_quito.py) · **Datos:** [`datos_estudio_habitabilidad_quito.json`](datos_estudio_habitabilidad_quito.json) · **Centroides:** [`parroquias_quito_centroides.json`](parroquias_quito_centroides.json)

> ⚠️ **Este estudio cuenta equipamiento medido. NO ordena parroquias por deseabilidad ni recomienda dónde vivir.** Más servicios no significa "mejor zona": significa más servicios. Quien pondera es cada persona, según su vida. La tabla va agrupada por tipo y en orden alfabético, nunca por cantidad.

---

## 0. Qué cambió en esta edición

| | ed.1 | ed.2 | **ed.3** |
|---|---|---|---|
| Área medida | radio de 1.200 m | isócrona real por calles | isócrona real por calles |
| Unidad | 18 sectores estimados a ojo | 18 sectores estimados a ojo | **40 parroquias oficiales del DMQ** |
| Cobertura | norte y centro | norte y centro | **+ valles y sur** |
| Verificación en terreno | — | — | **muestra diseñada (42 puntos)** |

**Advertencia de lectura:** los números de la ed.3 **no son comparables 1:1 con los de la ed.2**. No cambió solo la precisión: cambió la **unidad**. Una parroquia es más grande y más heterogénea que un "sector" o un barrio.

---

## 1. El hallazgo metodológico: el centro oficial no es donde vive la gente

La ed.2 medía desde 18 puntos que estimé a ojo. Para la ed.3 los reemplacé por el **centroide geométrico oficial** de cada parroquia (OpenStreetMap, `boundary=administrative`). Parecía una mejora obvia.

**Fue un desastre.** Con centroides oficiales, parroquias urbanas y céntricas devolvían **cero servicios**:

| Parroquia | Con centroide oficial | Distancia al centro vivido |
|---|---|---|
| Cochapamba | 0 puntos | **3.512 m** |
| Rumipamba | 0 puntos | **3.261 m** |
| Belisario Quevedo | 0 puntos | **3.035 m** |
| Cumbayá | 5 puntos | ~1.100 m |

La causa: **las parroquias de Quito trepan al Pichincha.** Su centro geométrico cae en la ladera o en la quebrada — sin red vial, sin comercio, sin gente. Y ahí la isócrona peatonal degenera a menos de medio km².

**La corrección — el "centro vivido":** el punto de medición se mueve al **centro de masa del equipamiento** dentro de 2,5 km del centroide oficial (dos iteraciones). Es decir, se mide desde donde la parroquia efectivamente *es ciudad*, no desde su centro geométrico. Ambos puntos quedan guardados en el archivo de centroides (`lat_oficial`/`lon_oficial` y `desplazamiento_m`), para que cualquiera verifique el movimiento.

> El dato "oficial" resultó **peor** que la estimación a ojo — porque al estimar a ojo, sin saberlo, yo elegía el centro vivido. La lección no es que el dato oficial sea malo: es que **un centroide geométrico no es un lugar donde alguien vive.**

---

## 2. La tabla

*Agrupada por tipo de parroquia y en orden alfabético. "Más escaso" = la categoría con menos puntos de la canasta cotidiana (supermercado, farmacia, salud, educación) — el eslabón débil. "Sesgo ed.1" = cuánto inflaba el método del círculo.*

### Parroquias urbanas

| Parroquia | Puntos a 15 min | Área (km²) | Más escaso (canasta) | Sin datos de | Sesgo ed.1 |
|---|---|---|---|---|---|
| Belisario Quevedo | 187 | 2.72 | salud (16) | — | +73% |
| Carcelén | 67 | 1.97 | salud (6) | centro_comercial | +42% |
| Centro Histórico | 308 | 3.30 | salud (22) | — | +13% |
| Chilibulo | 172 | 3.07 | educacion (28) | — | +37% |
| Chillogallo | 141 | 2.84 | salud (9) | — | +25% |
| Chimbacalle | 130 | 1.63 | salud (16) | — | +83% |
| Cochapamba | 79 | 1.83 | salud (7) | — | +109% |
| Cotocollao | 188 | 3.33 | educacion (19) | — | +23% |
| El Condado | 29 | 1.65 | salud (1) | seguridad | +138% |
| Guamaní | 34 | 2.68 | educacion (3) | parque, centro_comercial | +97% |
| Itchimbia | 459 | 3.32 | farmacia (66) | — | +24% |
| Iñaquito | 315 | 3.23 | farmacia (46) | — | +45% |
| Jipijapa | 291 | 2.98 | educacion (35) | — | +35% |
| Kennedy | 121 | 2.37 | educacion (7) | — | +125% |
| La Argelia | 201 | 3.13 | educacion (13) | — | +33% |
| La Concepción | 59 | 1.33 | salud (3) | — | +322% |
| La Ecuatoriana | 102 | 3.09 | educacion (5) | centro_comercial | +48% |
| La Ferroviaria | 198 | 2.83 | educacion (27) | — | +49% |
| La Libertad | 44 | 1.07 | farmacia (2) | — | +370% |
| La Magdalena | 221 | 3.29 | educacion (30) | — | +33% |
| La Mena | 179 | 3.05 | educacion (14) | — | +52% |
| Mariscal Sucre | 456 | 3.35 | supermercado (73) | — | +23% |
| Ponceano | 145 | 3.09 | educacion (15) | — | +35% |
| Puengasí | 137 | 1.97 | farmacia (9) | — | +93% |
| Quitumbe | 71 | 1.90 | salud (5) | centro_comercial | +90% |
| Rumipamba | 357 | 3.35 | supermercado (42) | — | +23% |
| San Bartolo | 128 | 3.04 | salud (15) | — | +72% |
| San Isidro del Inca | 124 | 3.52 | salud (5) | — | +28% |
| San Juan | 337 | 3.10 | educacion (31) | — | +34% |
| Solanda | 213 | 3.41 | salud (19) | — | +27% |
| Turubamba | 76 | 3.00 | educacion (4) | centro_comercial | +47% |

### Parroquias rurales / valles

| Parroquia | Puntos a 15 min | Área (km²) | Más escaso (canasta) | Sin datos de | Sesgo ed.1 |
|---|---|---|---|---|---|
| Alangasi | 77 | 2.65 | educacion (6) | seguridad | +75% |
| Calderon | 35 | 1.95 | salud (1) | seguridad | +100% |
| Conocoto | 64 | 1.91 | educacion (3) | centro_comercial | +53% |
| Cumbaya | 68 | 1.62 | educacion (5) | — | +119% |
| La Merced | 28 | 1.76 | salud (0) | salud, centro_comercial, seguridad | +25% |
| Llano Chico | 30 | 1.99 | salud (0) | salud, educacion, centro_comercial, seguridad | +43% |
| Pomasqui | 37 | 1.77 | salud (3) | — | +41% |
| Tumbaco | 108 | 2.46 | educacion (8) | — | +10% |
| Zambiza | 16 | 1.94 | supermercado (1) | parque, centro_comercial, seguridad | +144% |

---

## 3. Lo que muestran los números

### 3.1 La brecha es de 28.7x

De **16** puntos de servicio alcanzables a pie (Zambiza) a **459** (Itchimbia). Al ampliar la medición a 40 parroquias —incluyendo valles y sur— la desigualdad medida crece respecto de la ed.2 (19,7x sobre 18 sectores del norte y el centro).

### 3.2 Quince minutos siguen sin ser quince minutos

El área alcanzable varía **3.3x**: de **1.07 km²** (La Libertad) a **3.52 km²** (San Isidro del Inca). La traza urbana y la pendiente deciden cuánta ciudad alcanza una misma caminata.

### 3.3 Los valles: menos equipamiento a pie del que sugiere su fama

**Cumbayá alcanza 68 puntos de servicio caminando 15 minutos** — menos que buena parte de las parroquias urbanas. Es coherente con su morfología: valle de baja densidad, diseñado para moverse en auto. No es un juicio sobre el valle; es una descripción de lo que se alcanza **a pie**.

### 3.4 El sesgo del círculo se confirma y empeora

Mediana **+47%**, máximo **+370%**. Con más parroquias de traza irregular y pendiente, el método de la ed.1 se ve todavía peor de lo que ya sabíamos.

---

## 4. Lo que NO se reporta (y por qué)

**16 parroquias quedan fuera de la tabla** por cobertura insuficiente (menos de 15 puntos dentro de su isócrona):

Amaguaña, Calacali, Checa - Chilpa, Comite del Pueblo, El Quinche, Guangopolo, Guayllabamba, Lloa, Nayon, Nono, Pifo, Pintag, Puembo, San Antonio, Tababela, Yaruqui.

**No se afirma que estén desabastecidas.** Puede ser un territorio genuinamente rural o un hueco de nuestra capa — y no lo sabemos. Decir "no hay servicios" cuando la verdad es "no tenemos datos" sería difamar un territorio con una carencia nuestra.

Esa distinción —**"no hay" vs "no tenemos"**— es la línea que separa un dato honesto de una afirmación irresponsable.

---

## 5. Verificación en terreno: la muestra ya está diseñada

Nada de este estudio está verificado en terreno. La capa dice qué existe según Overture y OSM; **nadie ha ido a pararse en la puerta.**

Para que salir a campo rinda, la muestra no es aleatoria. [`muestra_verificacion_terreno.csv`](muestra_verificacion_terreno.csv) selecciona **42 puntos** con este criterio:

1. **Solo canasta cotidiana** (salud, farmacia, educación, supermercado) — las categorías que definen el eslabón débil, que es el hallazgo accionable.
2. **Las 6 parroquias extremas** — las 3 con menos equipamiento y las 3 con más. Un dato falso ahí desplaza la conclusión mucho más que en el medio de la distribución.
3. **Ficha pobre primero** (sin nombre o con nombre genérico) y **dato más antiguo primero** — los más propensos a haber cerrado.

El archivo trae coordenadas, enlace a Maps y columnas vacías para llenar en la calle: *existe / nombre real / abierto / categoría correcta / notas / quién verificó / fecha*. Se genera con [`scripts/muestra_verificacion_terreno.py`](../scripts/muestra_verificacion_terreno.py).

**Qué se hace con el resultado:** cada punto verificado entra al sistema de curación (que ya propaga la verificación al resto del barrio), y la tasa de error medida se publica en la ed.4. Si de 42 puntos fallan 8, eso es un **19% de error de capa** — y ese número, dicho en voz alta, vale más que cualquier afirmación de exactitud.

---

## 6. Metodología

Para cada parroquia: se toma el centroide oficial de OSM, se corrige al centro vivido (centro de masa de los POIs a ≤2,5 km, dos iteraciones), se pide a Valhalla la isócrona peatonal de 15 minutos y se cuentan los POIs operativos dentro del polígono (`ST_Contains`). El área se calcula en `geography`. En paralelo se cuenta el total dentro del radio de 1.200 m de la ed.1, únicamente para cuantificar el sesgo. **Si Valhalla no responde para una parroquia, esa parroquia se omite en vez de sustituirse por radio.**

**Límites vigentes:**
- La capa mide **presencia, no calidad ni horario**. Seis puntos de salud no dicen si atienden urgencias.
- El centro vivido es una **corrección defendible, no una verdad**: en parroquias bimodales (dos núcleos separados) el centro de masa puede caer entre ambos.
- **Nada está verificado en terreno** — ver §5.

**Edición 4 — comprometida:** resultados de la verificación en terreno con su tasa de error, y cobertura de las parroquias hoy excluidas.

---

## 7. Proveniencia

- **Dato propio:** 8.499 POIs en Quito (Overture Places + OpenStreetMap, conflados y curados). No verificados en terreno.
- **Centroides:** OpenStreetMap, relaciones `boundary=administrative` (admin_level 9 urbanas, 8 rurales), consultadas vía Overpass el 2026-08-05. Se excluyen parroquias de cantones vecinos (Mejía, Rumiñahui, Cayambe, Pedro Moncayo).
- **Motor de isócronas:** Valhalla auto-hospedado con tiles de Ecuador. Sin llaves de terceros.
- **Correcciones publicadas:** la ed.1 sobreestimaba entre +10% y +370% (radio vs calles). La ed.3 corrige además el punto de medición de la ed.2. Los datos viejos no se borran: se miden y se reportan.
- **Referencia de método (no de dato):** *Estudio del Perfil del Comprador*, 7ª ed. — **per CODIP + IPSOS Perú**, Lima, n=739, IC ±4%, campo oct-2025 a ene-2026.

> **El método es parte del dato.** Esta es la tercera edición y la tercera corrección publicada. Si la cuarta encuentra otro error, también se dirá.
