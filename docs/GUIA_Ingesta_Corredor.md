# 📸 Guía de Ingesta para Corredores — Contexto AI (Piloto)

**Para:** corredor del piloto · **Objetivo:** capturar ~10 inmuebles reales para que el agente 24/7 los conozca.
**Idea clave:** entre mejores sean las **fotos**, mejor será la **ficha técnica** que la IA genera (tuberías, cableado, humedad, acabados). Esta guía asegura que **no se quede nada suelto**.

---

## Parte A · Qué llevar y cómo capturar

- **Celular** con cámara y datos/Wi-Fi.
- **Google Maps** abierto (para sacar las coordenadas).
- Tomar fotos **horizontales**, con **buena luz** (abre cortinas, prende luces).
- Una **carpeta por inmueble** en el celular, o nombrar las fotos con un prefijo (ver Parte D).

### Cómo sacar las COORDENADAS (lat, lon) — importante
1. En **Google Maps**, mantén presionado el punto exacto del inmueble → aparece un **pin rojo**.
2. Arriba sale algo como `-0.180700, -78.467800`.
3. Cópialo y pégalo en el formulario (campo *Coordenadas*). Eso nos da ubicación exacta.

---

## Parte B · Protocolo de FOTOS (lo más importante) 📷

Toma **todas** las que apliquen. Marca ✅ a medida que las haces. (8–12 fotos por inmueble es lo ideal.)

### 1) Exterior y entorno
- [ ] **Fachada completa** del edificio/casa (de frente).
- [ ] **Entrada / portal / número** de la casa o edificio.
- [ ] **La calle** hacia ambos lados (para ver tráfico, comercios, ruido del entorno).

### 2) Ambientes (visión general)
- [ ] **Sala** (vista amplia).
- [ ] **Comedor**.
- [ ] **Cada dormitorio** (uno por foto).
- [ ] **Vista desde la ventana** principal (qué se ve afuera).

### 3) Detalles técnicos (de estos sale la FICHA — no los saltes)
- [ ] **Cocina de cerca:** mesón, grifería y debajo del lavaplatos (conexiones de agua).
- [ ] **Baño(s) de cerca:** sanitario, grifería, ducha; busca **manchas de humedad**.
- [ ] **Techos / cielo raso:** especial atención a **manchas, filtraciones o burbujas** (impermeabilización).
- [ ] **Tablero eléctrico** (caja de breakers) abierto → la IA estima el estado del **cableado**.
- [ ] **Medidor de agua / cisterna / bomba** si hay acceso (estado de **tuberías**).
- [ ] **Piso y acabados** (un par de tomas — material y estado).

### 4) Señales de problemas (si las hay, fotografíalas)
- [ ] **Grietas** en paredes, **humedad**, **filtraciones**, óxido, instalaciones improvisadas.
> Esto NO resta valor al anuncio: hace la ficha **honesta y confiable**, que es nuestra diferencia.

---

## Parte C · FORMULARIO por inmueble (uno por propiedad)

Llena uno de estos por cada inmueble. Los campos con ⭐ son obligatorios.

```
────────────────────────────────────────────────
INMUEBLE Nº: ____   ·   Referencia/alias: ________________

⭐ Dirección completa (calle, número, sector, "Quito"):
   _______________________________________________________

⭐ Coordenadas (pin de Google Maps, lat, lon):
   _______________________ , _______________________

⭐ Tipo:  ☐ Departamento  ☐ Casa  ☐ Local comercial  ☐ Oficina  ☐ Quinta

⭐ Operación:  ☐ Arriendo   ☐ Venta
⭐ Precio (USD):  _______________

   Piso / altura (si aplica): _______
   Área aproximada (m²): _______   Habitaciones: ___   Baños: ___
   Antigüedad aproximada (años): _______

   Notas del corredor (lo que NO se ve en fotos pero tú sabes):
   ¿remodelaciones?, ¿se cambió tubería/cableado?, ¿problemas conocidos?,
   ¿qué destaca del entorno (parques, transporte, comercios)?
   _______________________________________________________
   _______________________________________________________

   Fotos tomadas (nº aprox.): _____   Carpeta/prefijo: ____________
────────────────────────────────────────────────
```

> **El campo "Notas del corredor" es clave:** tú sabes cosas que la foto no muestra
> (que se cambió la tubería hace 2 años, que el techo se impermeabilizó, etc.).
> Eso alimenta el **historial de mantenimiento** de la ficha.

---

## Parte D · Cómo nombrar las fotos (para no mezclarlas)

Usa un **prefijo por inmueble** + qué es. Ejemplo para el inmueble 1:

```
casa1_fachada.jpg      casa1_sala.jpg        casa1_cocina.jpg
casa1_bano.jpg         casa1_dormitorio1.jpg casa1_techo.jpg
casa1_tablero.jpg      casa1_cisterna.jpg    casa1_calle.jpg
```

Para el inmueble 2 → `casa2_...`, y así. (Si no alcanzas a renombrar, basta con **una carpeta por inmueble**.)

---

## Parte E · Qué pasa después (lo hago yo)

1. Tú me pasas las **fotos + los formularios** (o el CSV ya lleno).
2. Yo: geocodifico, asigno la **capa base de habitabilidad** (ruido/tráfico/caminabilidad por zona) y la **IA de visión** extrae la **ficha técnica** de las fotos.
3. **Revisión humana:** cada inmueble se revisa y aprueba antes de quedar visible (calidad garantizada).
4. Genero el **QR + letrero imprimible** de cada inmueble.
5. Pegas el letrero → el cliente escanea a cualquier hora → **tu agente 24/7** lo atiende y te entrega el lead.

---

## Apéndice · Versión digital (CSV) — opcional
Si prefieres consolidar en computador, usa la plantilla `plantilla_corredor.csv`
(columnas: dirección, latitude, longitude, tipo_activo, piso_altura, operación, precio,
foto1, foto2, foto3). El formulario de papel y el CSV piden lo mismo; usa el que te sea cómodo.

---

*Contexto AI — Cada lugar tiene un aura. Tu agente inmobiliario que nunca duerme.*
