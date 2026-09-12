# Registro de Experimentos de Comunicación Multicanal · v0.2

Estado: **operativo**

Este registro extiende el v0.1 para tratar la **idea canónica** como unidad experimental y las expresiones por red como observaciones distintas. No compara números brutos entre plataformas como si fueran equivalentes.

## 1. Ficha canónica obligatoria

- `id`:
- `semana`:
- `estado`: idea / seleccionada / borrador / aprobada / publicada / medida / cerrada
- `objetivo`: O1 / O2 / O3 / O4
- `audiencia_prioritaria`:
- `capitulo_narrativo`:
- `tipo_editorial`:
- `hipotesis`:
- `hecho_o_evidencia`:
- `clasificacion_evidencia`: VERIFICADO / OBSERVADO / INFERIDO / HIPÓTESIS / DESCONOCIDO
- `idea_unica`:
- `accion_o_conversacion_buscada`:
- `consecuencia_buscada`:
- `riesgo_de_interpretacion`:
- `que_no_podemos_afirmar`:

Sin objetivo, hipótesis, evidencia o métrica primaria, no pasa a borrador.

## 2. Ficha por canal

Crear una fila únicamente para los canales donde exista una razón explícita para adaptar la idea.

- `canal`: linkedin / instagram / facebook / youtube
- `rol_del_canal`:
- `fecha_hora_prevista`:
- `fecha_hora_real`:
- `formato`:
- `gancho_usado`:
- `cta_o_pregunta`:
- `metrica_primaria`:
- `metrica_secundaria`:
- `url_publicacion`:
- `auto_publicacion`: sí / no
- `notas_contexto`:

## 3. Atención

Registrar por canal solo lo que la plataforma exponga:

- impresiones / alcance;
- vistas;
- visitas al perfil;
- seguidores/suscriptores atribuibles cuando exista evidencia.

## 4. Resonancia

- reacciones;
- comentarios;
- compartidos/reposts;
- guardados;
- envíos;
- retención / porcentaje visto para video;
- clics cuando sean relevantes.

Clasificar comentarios:

- superficial;
- sustantivo;
- cualificado;
- objeción;
- pregunta no prevista;
- reformulación correcta de la tesis;
- interpretación incorrecta.

## 5. Consecuencia

Registrar solo cuando exista atribución razonable:

- DM relevante;
- conversación cualificada;
- reunión;
- introducción a tercero;
- propuesta de integración;
- lead/oportunidad;
- invitación a evento/prensa/colaboración;
- aprendizaje de producto/distribución;
- cambio de hipótesis.

Añadir siempre `evidencia_de_atribucion`.

## 6. Comparación correcta entre canales

No comparar directamente:
- 1.000 vistas de Reel vs 1.000 impresiones de LinkedIn;
- suscriptores de YouTube vs seguidores de Instagram;
- reacciones absolutas entre redes.

Comparar dentro del propósito de cada canal:

- **LinkedIn**: comprensión, comentarios sustantivos, DMs, reuniones, integraciones.
- **Instagram**: guardados, compartidos, retención, visitas al perfil, respuestas.
- **Facebook**: comentarios prácticos, compartidos, mensajes, conversación local.
- **YouTube**: retención, porcentaje visto, comentarios sustantivos, retorno de espectadores, conversaciones derivadas.

## 7. Cierre por experimento

### Resultado canónico

- `ATENCION`:
- `RESONANCIA`:
- `CONSECUENCIA`:
- `COMPRENSION_CORRECTA`:
- `AUDIENCIA_CORRECTA`:

### Veredicto

- `DOBLAR_APUESTA`
- `MANTENER_EN_PRUEBA`
- `REFORMULAR`
- `DETENER`
- `MUESTRA_INSUFICIENTE`

### Aprendizaje falsable

> En N expresiones del experimento X, la audiencia/canal Y mostró Z frente a W. La muestra es/no es suficiente para cambiar la estrategia. Siguiente prueba: ...

## 8. Tabla maestra canónica

| ID | Semana | Objetivo | Capítulo | Hipótesis | Canal primario | Adaptaciones | Evidencia | Consecuencia buscada | Estado | Veredicto |
|---|---|---|---|---|---|---|---|---|---|---|
| EXP-001 | 01 | O1 | 1 | Buscar ≠ decidir mejora comprensión | LinkedIn | Instagram + Facebook | Posición/Hipótesis | Factores de decisión + DMs | BORRADOR | — |
| EXP-002 | 01 | O1+O2 | 2 | Ejemplo concreto hace recordable el marco | YouTube/Instagram | LinkedIn en espera | Marco de diseño | Casos + contraejemplos | BORRADOR | — |
| EXP-003 | 01 | O2+O3 | 4 | Prueba real genera conversación cualificada | Pendiente | Pendiente | PENDIENTE | DMs/integraciones | HOLD | — |

## 9. Línea base

Las primeras 6 publicaciones/expresiones forman la línea base exploratoria. No cambiar reglas estructurales por una sola pieza.

A las 12 observaciones pueden formularse señales provisionales. A las 20–30, comparar patrones con mayor utilidad, controlando cambios de audiencia, tema, formato y canal.