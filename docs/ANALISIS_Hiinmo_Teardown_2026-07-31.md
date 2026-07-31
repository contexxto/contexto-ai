# ANÁLISIS — Hiinmo (hiinmo.com) · Teardown competitivo

**Fecha:** 2026-07-31
**Sujeto:** Hiinmo S.A.S. — Quito, Edificio Silva Nuñez, Av. Shyris y Naciones Unidas. Miembro de CAINEC.
**Método:** recorrido del sitio público (home, planes, CRM, marketing, nosotros, FAQ, directorios de aliados,
fichas de inmueble, simulador). Dos consultas reales al asistente "Inmo". Conteos de inventario tomados de los
títulos de página que el propio buscador genera. **No se accedió a ninguna cuenta ni área privada.**

---

## Veredicto

Hiinmo **no es un portal que monetiza demanda** — es un SaaS de captación para agentes vestido de portal.
El buscador con IA funciona bien cuando se le habla en su idioma (tipo, zona, precio, dormitorios) y descarta
explícitamente todo lo demás. El inventario real ronda las **1.250 propiedades en todo el país**, y las fichas
revisadas acumulan **0 y 13 visitas tras 51 y 98 días** publicadas.

**La amenaza para Contexto no está en el producto: está en la distribución.** Son miembros de CAINEC y ya
tienen ~28 agentes y 22 inmobiliarias firmadas. Compiten por el corredor, no por el habitante.

---

## 1. Inventario (conteos del propio sitio)

| Categoría | Publicaciones |
|---|---|
| Quito — venta | 902 |
| Quito — alquiler | 139 |
| Estadía temporal (nacional) | 131 |
| Guayaquil — venta + alquiler | 71 |
| Proyectos de obra nueva (nacional) | 4 |

Desglose Quito:

| Tipo | Publicaciones |
|---|---|
| Departamentos en venta | 297 |
| Casas en venta | 277 |
| **Departamentos en alquiler** | **37** |

**Lectura:** 6,5× más venta que alquiler. Están construidos para el ticket alto y la comisión del corredor,
no para quien busca dónde vivir el próximo año. **Ese hueco de arriendo es donde vive el wedge de Contexto**
(ver `ICP_Contexto_2026-07.md`). Guayaquil con 71 fichas no es cobertura nacional. Solo 4 proyectos de obra
nueva significa que las constructoras — quienes más pagan publicidad inmobiliaria — todavía no llegan.

---

## 2. La prueba de la IA

Consulta enviada al asistente "Inmo":

> "Quiero arrendar un departamento en Quito para vivir un año. Trabajo desde casa, tengo un perro y no tengo
> carro. Necesito zona tranquila donde pueda caminar al supermercado y a un parque. Presupuesto 700 dólares
> al mes."

Respuesta:

> "No hay departamentos en alquiler en Quito que cumplan con todos tus criterios en este momento. Te sugiero
> ajustar la zona o ampliar ligeramente el presupuesto."

Y su propia nota al pie del sistema:

> **"Ignoramos ubicación de referencia, e ignoramos: `Apto para ganadería`, cercanía a: supermercado,
> cercanía a: parque (7 resultados)."**

Dos fallos estructurales en una frase:

1. **Declara en voz alta que descarta** los criterios de entorno — no los pondera ni los aproxima, los bota,
   porque no existen como campo en su base.
2. **"Tengo un perro" → filtro "Apto para ganadería".** Hizo match de texto contra la única casilla de su
   catálogo que hablaba de animales.

La URL final generada fue un filtro plano: `alquiler · departamento · Quito · hasta 700`.

### Control (para ser justos)

> "Departamento de 2 dormitorios en venta en Cumbayá hasta 150000 dólares"
>
> → "Encontré 3 departamentos en venta en Cumbayá con 2 dormitorios dentro de tu presupuesto."

**En su terreno funciona.** Extrajo tipo, zona, techo y dormitorios sin error. Inmo es un buen parser de
lenguaje natural. Es un mejor campo de búsqueda — no es conocimiento sobre lugares.

---

## 3. Promesa contra medición

| Lo que dicen | Lo que se midió |
|---|---|
| "El primer buscador inmobiliario con IA" | Traductor de texto a filtros; descarta explícitamente el entorno |
| "Inventario en tiempo real" | ~1.250 publicaciones en todo Ecuador |
| Simulador de precio referencial por m² | Su propio aviso: calcula *"solo… los anuncios publicados en Hiinmo"* — precio de pedida sobre muestra mínima |
| "Servicios cerca de ti: escuelas, clínicas, lavanderías" | Etiquetado **"Próximamente"**. La sección "Alrededores y conveniencia" de una ficha viene vacía |
| "CRM Inteligente" propio | Sus formularios corren en `leadconnectorhq.com` (**GoHighLevel**). Niveles Starter/Growth + WhatsApp/Zapier/Meta/llamadas IA = set de GHL. Reventa white-label |
| FAQ: "hasta 5 anuncios gratuitos indefinidos" | Página de planes: Starter = **1 anuncio, 2 meses**. Se contradicen |

---

## 4. Demanda — el dato más duro

Cada ficha publica sus visitas:

| Ficha | Plan | Precio | Días | Visitas |
|---|---|---|---|---|
| Penthouse dúplex 307 m², La Carolina | Pro | $290.000 | 51 | **0** |
| Departamento 2 dorm., El Condado | Elite | $96.000 | 98 | **13** |

Un penthouse de casi $300.000 en la mejor zona de Quito, en plan pagado, con **cero visitas en 51 días**.
Una ficha en plan *premium* promediando una visita cada ocho días. **El portal no genera el tráfico que vende.**
Ese es el punto donde su modelo de renovación se rompe.

---

## 5. Modelo de negocio

| Plan | Anuncios | Agentes | Posición | Precio |
|---|---|---|---|---|
| Starter | 1 · 2 meses | 1 | Estándar | $0 |
| Pro | hasta 100 | hasta 7 | Destacado | no publicado |
| Elite | hasta 50 | hasta 5 | Premium + Home | no publicado |

**Rareza:** Elite es el plan caro y trae la mitad de anuncios que Pro. No venden volumen, venden exposición —
y como el tráfico es el de arriba, están vendiendo una escasez que ellos mismos fabrican.

Ningún precio de Pro, Elite, CRM ni marketing aparece publicado: todo pasa por formulario de ventas. Encima
del portal venden tres paquetes de marketing (fotografía, tours 360°, landing pages, rebranding, Meta Ads,
chatbots de WhatsApp). **Retrato: una agencia de marketing inmobiliario que usa el portal como carnada.**

### Lado de la oferta (tracción real)

| Directorio | Perfiles |
|---|---|
| Agentes | 28 |
| Inmobiliarias | 22 |
| Corredores | 4 |
| Agencias | 2 |
| Constructoras | 1 |

---

## 6. Stack técnico observado

- **Frontend:** Next.js
- **Mapas / POI:** Google Maps JS + Places API (de caja — sin datos propios)
- **Imágenes:** Cloudinary
- **Auth:** Google Sign-In
- **CRM / formularios:** GoHighLevel (`api.leadconnectorhq.com`)

**No hay foso de datos.** Su entorno es Google Places; el Place Graph de Contexto no tiene equivalente aquí.

---

## 7. Implicaciones para Contexto

**No competir — el portal no es el campo de batalla.**
Pelear por inventario contra Hiinmo es pelear por 1.250 fichas que nadie visita. Su lado débil no es el
catálogo, es que no tienen nada que decir sobre el lugar. *"Ignoramos: cercanía a supermercado, cercanía a
parque"* es, textualmente, la frase que separa a Contexto de ellos.

**Aprovechar — su hoja de ruta dice dónde apurar.**
"Próximamente: servicios cerca de ti — decoración, reparación, lavanderías, escuelas, clínicas" es el Place
Graph anunciado sin construir. Publicaron su intención. El tiempo que tarden en armarlo con Google Places es
la ventana para que Contexto lo tenga con datos propios y profundidad real de barrio.

**Vigilar — la distribución sí es una amenaza.**
28 agentes, 22 inmobiliarias, membresía CAINEC y venta consultiva uno a uno. Están construyendo la relación
con el corredor mientras el producto madura. Ese es su activo, y es el mismo canal que necesita el CRM de
Whaber. **Ahí sí hay colisión.**

**Probar — el arriendo largo está desierto.**
37 departamentos en arriendo en todo Quito contra 902 en venta. El "vivir un año" — corazón del wedge del
habitante de Quito y de la tesis de aura del canal — no tiene dueño en este mercado. Hiinmo lo dejó vacío por
decisión económica, y esa decisión es difícil de revertir.

---

## Advertencias de método

- Conteos de inventario y contadores de visita son los que el propio sitio publica; pueden variar.
- Las citas del asistente Inmo son transcripciones literales de dos consultas del 31-jul-2026.
- La inferencia sobre GoHighLevel se basa en el dominio de sus formularios públicos y en la coincidencia del
  set de funciones, **no en una confirmación de la empresa**.

**Ver también:** `BATALLA_Hiinmo_vs_Contexto_2026-07-31.md` (prueba pareada con la misma consulta).
