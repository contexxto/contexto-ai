const pptxgen = require("pptxgenjs");

const pres = new pptxgen();
pres.layout = "LAYOUT_16x9";
pres.title = "Contexto AI — Pitch Deck";
pres.author = "Carlos Valencia";

// ── Palette ──────────────────────────────────────────────────────────────
const BG       = "0d1117";   // background dark
const SURFACE  = "161b22";   // card surface
const SURFACE2 = "1c2128";   // lighter card
const ACCENT   = "58a6ff";   // blue accent
const ACCENT2  = "388bfd";   // darker blue
const TEXT     = "e6edf3";   // primary text
const MUTED    = "8b949e";   // muted text
const GREEN    = "3fb950";   // success
const BORDER   = "30363d";   // border

// ── Helpers ───────────────────────────────────────────────────────────────
const mkShadow = () => ({ type:"outer", blur:10, offset:3, angle:135, color:"000000", opacity:0.3 });

function slideBase(slide) {
  slide.background = { color: BG };
}

function addTag(slide, text, x, y) {
  slide.addShape(pres.shapes.ROUNDED_RECTANGLE, {
    x, y, w:1.5, h:0.3, fill:{ color: ACCENT2 }, line:{ color: ACCENT2 }, rectRadius:0.05
  });
  slide.addText(text, {
    x, y, w:1.5, h:0.3, fontSize:9, bold:true, color:"ffffff",
    align:"center", valign:"middle", margin:0
  });
}

function addCard(slide, x, y, w, h) {
  slide.addShape(pres.shapes.RECTANGLE, {
    x, y, w, h, fill:{ color: SURFACE }, line:{ color: BORDER, width:0.5 },
    shadow: mkShadow()
  });
}

function sectionTitle(slide, text, y) {
  slide.addText(text, {
    x:0.5, y, w:9, h:0.5, fontSize:11, bold:true, color:ACCENT,
    charSpacing:3, align:"left"
  });
}

// ══════════════════════════════════════════════════════════════════════════
// SLIDE 1 — PORTADA
// ══════════════════════════════════════════════════════════════════════════
{
  const sl = pres.addSlide();
  slideBase(sl);

  // Gradient-like background accent blocks
  sl.addShape(pres.shapes.RECTANGLE, {
    x:7.5, y:0, w:2.5, h:5.625, fill:{ color: SURFACE2 }, line:{ color: SURFACE2 }
  });
  sl.addShape(pres.shapes.RECTANGLE, {
    x:8.5, y:0, w:1.5, h:5.625, fill:{ color: ACCENT2, transparency:88 }, line:{ color: ACCENT2, transparency:88 }
  });

  // Map pin icon (SVG-drawn with shapes)
  const px = 0.7, py = 0.7;
  sl.addShape(pres.shapes.OVAL, { x:px, y:py, w:0.55, h:0.55, fill:{ color: ACCENT }, line:{ color: ACCENT2 } });
  sl.addShape(pres.shapes.OVAL, { x:px+0.15, y:py+0.15, w:0.25, h:0.25, fill:{ color: BG }, line:{ color: BG } });
  sl.addShape(pres.shapes.RECTANGLE, { x:px+0.22, y:py+0.5, w:0.1, h:0.25, fill:{ color: ACCENT }, line:{ color: ACCENT } });

  // Tag
  addTag(sl, "PROPTECH · IA · LATAM", 0.7, 1.45);

  // Title
  sl.addText("Contexto AI", {
    x:0.6, y:1.9, w:7, h:1.1, fontSize:54, bold:true, color:TEXT, fontFace:"Calibri"
  });
  // Blue underline accent
  sl.addShape(pres.shapes.RECTANGLE, { x:0.6, y:2.95, w:3.2, h:0.05, fill:{ color: ACCENT }, line:{ color: ACCENT } });

  sl.addText("El Catastro Vivo de Latinoamérica", {
    x:0.6, y:3.1, w:7, h:0.6, fontSize:20, bold:false, color:ACCENT, fontFace:"Calibri"
  });
  sl.addText("Inteligencia geoespacial que elimina la asimetría\nde información inmobiliaria", {
    x:0.6, y:3.75, w:6.8, h:0.8, fontSize:13, color:MUTED, fontFace:"Calibri"
  });

  // Bottom URL
  sl.addText("contexto-ai-six.vercel.app  ·  MVP en Producción", {
    x:0.6, y:5.1, w:7, h:0.35, fontSize:10, color:MUTED
  });

  // Right panel content
  sl.addText("📍", { x:8.0, y:1.5, w:1.5, h:1, fontSize:48, align:"center" });
  sl.addText("Quito, Ecuador", { x:7.7, y:2.5, w:2.1, h:0.3, fontSize:10, color:MUTED, align:"center" });
  sl.addText("MVP Live", { x:7.7, y:2.85, w:2.1, h:0.3, fontSize:11, color:GREEN, bold:true, align:"center" });
}

// ══════════════════════════════════════════════════════════════════════════
// SLIDE 2 — EL PROBLEMA
// ══════════════════════════════════════════════════════════════════════════
{
  const sl = pres.addSlide();
  slideBase(sl);

  sectionTitle(sl, "EL PROBLEMA", 0.3);
  sl.addText("Los portales inmobiliarios están construidos\nsobre cimientos de arena", {
    x:0.5, y:0.65, w:9, h:0.9, fontSize:26, bold:true, color:TEXT
  });

  // Big stat
  addCard(sl, 0.4, 1.7, 2.8, 1.5);
  sl.addText("73%", { x:0.4, y:1.75, w:2.8, h:0.75, fontSize:52, bold:true, color:ACCENT, align:"center" });
  sl.addText("de compradores lamenta no haber\ninvestigado más el entorno", {
    x:0.4, y:2.45, w:2.8, h:0.7, fontSize:9.5, color:MUTED, align:"center"
  });

  // Problem cards
  const problems = [
    { icon:"🗑️", title:"Datos Efímeros", body:"Un aviso se publica, se alquila, desaparece.\nEl portal pierde el dato y vuelve a gastar." },
    { icon:"💸", title:"CAC Infinito", body:"Cada propiedad debe re-capturarse.\nCosto de Adquisición de Dato no converge a cero." },
    { icon:"🔇", title:"Cero Contexto", body:"El usuario no sabe: ¿Hay ruido?\n¿Obras futuras? ¿Estado de tuberías?" },
  ];

  problems.forEach((p, i) => {
    const cx = 3.5 + i * 2.15;
    addCard(sl, cx, 1.7, 2.0, 3.0);
    sl.addText(p.icon, { x:cx, y:1.8, w:2.0, h:0.6, fontSize:28, align:"center" });
    sl.addText(p.title, { x:cx+0.1, y:2.45, w:1.8, h:0.35, fontSize:12, bold:true, color:TEXT, align:"center" });
    sl.addText(p.body, { x:cx+0.1, y:2.85, w:1.8, h:1.7, fontSize:9.5, color:MUTED, align:"center" });
  });

  sl.addText("El modelo actual garantiza que nadie acumule ventaja competitiva en datos — hasta ahora.", {
    x:0.5, y:4.9, w:9, h:0.4, fontSize:11, italic:true, color:ACCENT, align:"center"
  });
}

// ══════════════════════════════════════════════════════════════════════════
// SLIDE 3 — LA SOLUCIÓN
// ══════════════════════════════════════════════════════════════════════════
{
  const sl = pres.addSlide();
  slideBase(sl);

  sectionTitle(sl, "LA SOLUCIÓN", 0.3);
  sl.addText("El Catastro Vivo e Inmutable", {
    x:0.5, y:0.65, w:9, h:0.7, fontSize:28, bold:true, color:TEXT
  });

  // Key insight box
  addCard(sl, 0.4, 1.45, 9.2, 0.85);
  sl.addShape(pres.shapes.RECTANGLE, { x:0.4, y:1.45, w:0.07, h:0.85, fill:{ color: ACCENT }, line:{ color: ACCENT } });
  sl.addText("Una coordenada física (Lat, Lon, Piso) es permanente. Los inquilinos son transitorios.\nLos datos pertenecen al ACTIVO, no al anuncio.", {
    x:0.6, y:1.5, w:8.8, h:0.75, fontSize:12, color:TEXT, bold:false
  });

  // Features grid
  const features = [
    { icon:"🗺️", title:"Caminabilidad", body:"Distancia real peatonal\na puntos de interés clave" },
    { icon:"🔊", title:"Score de Ruido", body:"Predictivo por tráfico vehicular,\nsin sensores físicos" },
    { icon:"🌳", title:"Cobertura Vegetal", body:"% árboles via visión\ncomputacional aérea" },
    { icon:"🔧", title:"Ficha Técnica", body:"Tuberías, impermeabilización,\ncableado — como un auto" },
  ];

  features.forEach((f, i) => {
    const col = i % 2, row = Math.floor(i / 2);
    const cx = 0.4 + col * 4.7, cy = 2.5 + row * 1.45;
    addCard(sl, cx, cy, 4.5, 1.3);
    sl.addText(f.icon, { x:cx+0.15, y:cy+0.25, w:0.7, h:0.7, fontSize:24, align:"center" });
    sl.addText(f.title, { x:cx+0.95, y:cy+0.15, w:3.4, h:0.35, fontSize:13, bold:true, color:TEXT });
    sl.addText(f.body, { x:cx+0.95, y:cy+0.52, w:3.4, h:0.65, fontSize:10, color:MUTED });
  });
}

// ══════════════════════════════════════════════════════════════════════════
// SLIDE 4 — EL PRODUCTO
// ══════════════════════════════════════════════════════════════════════════
{
  const sl = pres.addSlide();
  slideBase(sl);

  sectionTitle(sl, "EL PRODUCTO", 0.3);
  sl.addText("Agente Conversacional Geoespacial", {
    x:0.5, y:0.65, w:9, h:0.6, fontSize:26, bold:true, color:TEXT
  });

  // Chat mockup
  const chatX = 0.4, chatY = 1.4, chatW = 5.5, chatH = 3.8;
  addCard(sl, chatX, chatY, chatW, chatH);

  // Header
  sl.addShape(pres.shapes.RECTANGLE, { x:chatX, y:chatY, w:chatW, h:0.45, fill:{ color: SURFACE2 }, line:{ color: BORDER } });
  sl.addText("● API conectada   Contexto AI — Catastro Vivo", {
    x:chatX+0.2, y:chatY+0.08, w:chatW-0.3, h:0.3, fontSize:9, color:MUTED
  });

  // User message
  sl.addShape(pres.shapes.ROUNDED_RECTANGLE, {
    x:chatX+1.2, y:chatY+0.65, w:4.1, h:0.55, fill:{ color: ACCENT2 }, line:{ color: ACCENT2 }, rectRadius:0.08
  });
  sl.addText("¿Opciones tranquilas cerca de La Carolina en Quito?", {
    x:chatX+1.3, y:chatY+0.72, w:3.95, h:0.4, fontSize:9, color:"ffffff"
  });

  // Tool badges
  sl.addShape(pres.shapes.ROUNDED_RECTANGLE, {
    x:chatX+0.2, y:chatY+1.35, w:1.5, h:0.25, fill:{ color: SURFACE2 }, line:{ color: BORDER }, rectRadius:0.04
  });
  sl.addText("📍 Búsqueda espacial", {
    x:chatX+0.2, y:chatY+1.35, w:1.5, h:0.25, fontSize:7.5, color:MUTED, align:"center", valign:"middle"
  });
  sl.addShape(pres.shapes.ROUNDED_RECTANGLE, {
    x:chatX+1.85, y:chatY+1.35, w:1.4, h:0.25, fill:{ color: SURFACE2 }, line:{ color: BORDER }, rectRadius:0.04
  });
  sl.addText("🔧 Ficha técnica", {
    x:chatX+1.85, y:chatY+1.35, w:1.4, h:0.25, fontSize:7.5, color:MUTED, align:"center", valign:"middle"
  });

  // AI response
  sl.addShape(pres.shapes.OVAL, { x:chatX+0.15, y:chatY+1.75, w:0.3, h:0.3, fill:{ color: ACCENT2 }, line:{ color: ACCENT2 } });
  sl.addText("C", { x:chatX+0.15, y:chatY+1.75, w:0.3, h:0.3, fontSize:9, bold:true, color:"ffffff", align:"center", valign:"middle", margin:0 });
  sl.addShape(pres.shapes.ROUNDED_RECTANGLE, {
    x:chatX+0.6, y:chatY+1.72, w:4.6, h:1.3, fill:{ color: SURFACE2 }, line:{ color: BORDER }, rectRadius:0.08
  });
  sl.addText([
    { text: "🏆 Isla Fernandina N44-28", options:{ bold:true, breakLine:true, color:TEXT } },
    { text: "Ruido: BAJO · Tráfico: 980 veh/día · Vegetal: 51%\n", options:{ color:MUTED } },
    { text: "Caminabilidad 87 · Impermeabilización: Jun 2023 ✓", options:{ color:MUTED } },
  ], { x:chatX+0.75, y:chatY+1.8, w:4.3, h:1.15, fontSize:9 });

  // Input bar mockup
  sl.addShape(pres.shapes.ROUNDED_RECTANGLE, {
    x:chatX+0.2, y:chatY+3.2, w:5.0, h:0.38, fill:{ color: BG }, line:{ color: BORDER }, rectRadius:0.08
  });
  sl.addText("Pregunta sobre habitabilidad...", {
    x:chatX+0.4, y:chatY+3.22, w:4.4, h:0.34, fontSize:9, color:BORDER, valign:"middle"
  });

  // Right panel — capabilities
  const caps = [
    { icon:"🗣️", text:"Lenguaje natural → coordenadas" },
    { icon:"🗺️", text:"ST_DWithin en PostGIS en tiempo real" },
    { icon:"🔗", text:"3 tools encadenadas autónomamente" },
    { icon:"💾", text:"Memoria de sesión multi-turno" },
    { icon:"🌐", text:"Deployado en Vercel + Render" },
  ];

  sl.addText("Capacidades del Agente", {
    x:6.2, y:1.4, w:3.6, h:0.4, fontSize:13, bold:true, color:TEXT
  });
  caps.forEach((c, i) => {
    addCard(sl, 6.2, 1.9 + i * 0.68, 3.5, 0.58);
    sl.addText(c.icon, { x:6.3, y:1.95 + i*0.68, w:0.45, h:0.45, fontSize:18, align:"center" });
    sl.addText(c.text, { x:6.85, y:1.97 + i*0.68, w:2.75, h:0.42, fontSize:10, color:TEXT, valign:"middle" });
  });
}

// ══════════════════════════════════════════════════════════════════════════
// SLIDE 5 — ARQUITECTURA TÉCNICA
// ══════════════════════════════════════════════════════════════════════════
{
  const sl = pres.addSlide();
  slideBase(sl);

  sectionTitle(sl, "ARQUITECTURA TÉCNICA", 0.3);
  sl.addText("Stack de producción deployado hoy", {
    x:0.5, y:0.65, w:9, h:0.55, fontSize:24, bold:true, color:TEXT
  });

  const layers = [
    { label:"FRONTEND", tech:"React + Vite", host:"Vercel", color:ACCENT, icon:"🌐", note:"contexto-ai-six.vercel.app" },
    { label:"API BACKEND", tech:"FastAPI + LangGraph ReAct", host:"Render", color:"3fb950", icon:"⚙️", note:"claude-sonnet-4-5 · 3 tools" },
    { label:"GEOCODING", tech:"Nominatim OSM", host:"Free", color:"f0883e", icon:"📍", note:"Sin API key · Fallback progresivo" },
    { label:"BASE DE DATOS", tech:"PostgreSQL + PostGIS", host:"Supabase", color:"a371f7", icon:"🗄️", note:"ST_DWithin · 35 activos · GiST index" },
  ];

  layers.forEach((l, i) => {
    const y = 1.35 + i * 1.0;
    // Track arrow
    if (i < layers.length - 1) {
      sl.addShape(pres.shapes.LINE, {
        x:2.5, y:y+0.88, w:0, h:0.12, line:{ color: BORDER, width:1, dashType:"dash" }
      });
    }
    addCard(sl, 0.4, y, 9.2, 0.88);
    sl.addShape(pres.shapes.RECTANGLE, { x:0.4, y, w:0.07, h:0.88, fill:{ color:l.color }, line:{ color:l.color } });

    sl.addText(l.icon, { x:0.6, y:y+0.18, w:0.55, h:0.5, fontSize:22, align:"center" });
    sl.addText(l.label, { x:1.25, y:y+0.08, w:1.7, h:0.28, fontSize:8.5, bold:true, color:l.color, charSpacing:2 });
    sl.addText(l.tech, { x:1.25, y:y+0.38, w:2.8, h:0.35, fontSize:13, bold:true, color:TEXT });

    sl.addShape(pres.shapes.ROUNDED_RECTANGLE, {
      x:4.4, y:y+0.25, w:1.1, h:0.35, fill:{ color: SURFACE2 }, line:{ color: BORDER }, rectRadius:0.05
    });
    sl.addText(l.host, { x:4.4, y:y+0.25, w:1.1, h:0.35, fontSize:9.5, color:MUTED, align:"center", valign:"middle" });

    sl.addText(l.note, { x:5.7, y:y+0.28, w:3.7, h:0.35, fontSize:10, color:MUTED, italic:true });
  });
}

// ══════════════════════════════════════════════════════════════════════════
// SLIDE 6 — LOS 3 FOSOS DEFENSIVOS
// ══════════════════════════════════════════════════════════════════════════
{
  const sl = pres.addSlide();
  slideBase(sl);

  sectionTitle(sl, "VENTAJA COMPETITIVA", 0.3);
  sl.addText("Los 3 Fosos Defensivos", {
    x:0.5, y:0.65, w:9, h:0.6, fontSize:28, bold:true, color:TEXT
  });

  const moats = [
    {
      icon:"🗄️", color:ACCENT, label:"DATA MOAT",
      title:"Catastro Inmutable",
      body:"Pre-hidratación asíncrona de la ciudad ANTES de la interacción comercial. El activo acumula datos compuestos en el tiempo. El CAC tiende a cero.",
      kpi:"CAC → $0 a mediano plazo"
    },
    {
      icon:"💰", color:GREEN, label:"COST MOAT",
      title:"Caché PostGIS Propia",
      body:"Reducción estimada del 95% en consumo de APIs comerciales mediante caché geoespacial vectorial propietaria y OSM local sin costo.",
      kpi:"95% reducción en APIs"
    },
    {
      icon:"🔄", color:"f0883e", label:"SAAS MOAT",
      title:"Bitácora de Mantenimiento",
      body:"La Ficha Técnica del activo crea retención recurrente del propietario y certifica el valor del bien ante futuras transacciones — como el historial de servicio de un auto.",
      kpi:"Retención propietario recurrente"
    },
  ];

  moats.forEach((m, i) => {
    const cy = 1.5 + i * 1.35;
    addCard(sl, 0.4, cy, 9.2, 1.2);
    sl.addShape(pres.shapes.RECTANGLE, { x:0.4, y:cy, w:0.07, h:1.2, fill:{ color:m.color }, line:{ color:m.color } });
    sl.addText(m.icon, { x:0.6, y:cy+0.28, w:0.7, h:0.6, fontSize:30, align:"center" });

    sl.addText(m.label, { x:1.45, y:cy+0.1, w:1.5, h:0.25, fontSize:8, bold:true, color:m.color, charSpacing:2 });
    sl.addText(m.title, { x:1.45, y:cy+0.35, w:2.5, h:0.35, fontSize:14, bold:true, color:TEXT });

    sl.addText(m.body, { x:4.1, y:cy+0.12, w:4.3, h:0.95, fontSize:10, color:MUTED });

    sl.addShape(pres.shapes.ROUNDED_RECTANGLE, {
      x:8.55, y:cy+0.28, w:0.95, h:0.6, fill:{ color: m.color, transparency:85 }, line:{ color:m.color }, rectRadius:0.05
    });
    sl.addText(m.kpi, { x:8.52, y:cy+0.22, w:1.0, h:0.72, fontSize:7.5, color:m.color, bold:true, align:"center", wrap:true });
  });
}

// ══════════════════════════════════════════════════════════════════════════
// SLIDE 7 — TRACCIÓN Y MVP
// ══════════════════════════════════════════════════════════════════════════
{
  const sl = pres.addSlide();
  slideBase(sl);

  sectionTitle(sl, "TRACCIÓN", 0.3);
  sl.addText("MVP 100% operativo en producción", {
    x:0.5, y:0.65, w:9, h:0.6, fontSize:26, bold:true, color:TEXT
  });

  // Live badge
  sl.addShape(pres.shapes.ROUNDED_RECTANGLE, {
    x:0.5, y:1.35, w:9.0, h:0.55, fill:{ color: "0d2d0d" }, line:{ color: GREEN }, rectRadius:0.07
  });
  sl.addText('● LIVE: contexto-ai-six.vercel.app  ·  API: {"status":"healthy"}  ·  Backend: contexto-ai.onrender.com', {
    x:0.6, y:1.38, w:8.8, h:0.48, fontSize:10.5, color:GREEN, bold:true, align:"center", valign:"middle"
  });

  // KPI cards
  const kpis = [
    { num:"35", label:"Activos\nIndexados", sub:"6 sectores de Quito" },
    { num:"3",  label:"Tools\nEncadenadas", sub:"Geocoding + PostGIS + Fichas" },
    { num:"6",  label:"Semanas\nde Build", sub:"Idea → Producción" },
    { num:"0",  label:"Costo\nAPI keys", sub:"OSM local sin costo" },
  ];

  kpis.forEach((k, i) => {
    const cx = 0.4 + i * 2.35;
    addCard(sl, cx, 2.1, 2.15, 1.55);
    sl.addText(k.num, { x:cx, y:2.18, w:2.15, h:0.7, fontSize:46, bold:true, color:ACCENT, align:"center" });
    sl.addText(k.label, { x:cx, y:2.88, w:2.15, h:0.4, fontSize:10, bold:true, color:TEXT, align:"center" });
    sl.addText(k.sub, { x:cx+0.1, y:3.3, w:1.95, h:0.28, fontSize:8, color:MUTED, align:"center" });
  });

  // Sector list
  sl.addText("Sectores cubiertos en Quito:", {
    x:0.5, y:3.85, w:4, h:0.3, fontSize:10, bold:true, color:TEXT
  });
  const sectors = ["La Carolina", "González Suárez", "Cumbayá", "Norte / El Condado", "Centro Histórico", "Sur / El Camal"];
  sectors.forEach((s, i) => {
    const col = i % 3, row = Math.floor(i / 3);
    sl.addShape(pres.shapes.OVAL, { x:0.5+col*3.1, y:4.22+row*0.45, w:0.12, h:0.12, fill:{ color:ACCENT }, line:{ color:ACCENT } });
    sl.addText(s, { x:0.7+col*3.1, y:4.17+row*0.45, w:2.8, h:0.25, fontSize:10, color:TEXT });
  });

  sl.addText("Tech: Python · FastAPI · LangGraph · Claude Sonnet 4.5 · PostGIS · React · Docker", {
    x:0.5, y:5.22, w:9, h:0.28, fontSize:9, color:MUTED, italic:true, align:"center"
  });
}

// ══════════════════════════════════════════════════════════════════════════
// SLIDE 8 — MODELO DE NEGOCIO
// ══════════════════════════════════════════════════════════════════════════
{
  const sl = pres.addSlide();
  slideBase(sl);

  sectionTitle(sl, "MODELO DE NEGOCIO", 0.3);
  sl.addText("Tres fuentes de ingreso desde el día uno", {
    x:0.5, y:0.65, w:9, h:0.55, fontSize:24, bold:true, color:TEXT
  });

  const models = [
    {
      type:"B2C", icon:"🏠", color:ACCENT, price:"$15/mes",
      title:"Propietarios",
      items:["Dashboard de plusvalía estructural","Alertas de mantenimiento preventivo","Bitácora técnica verificable","Notificaciones de obras SERCOP"],
      target:"Propietarios e inquilinos"
    },
    {
      type:"B2B", icon:"🏢", color:GREEN, price:"$299/mes",
      title:"Inmobiliarias",
      items:["API de inteligencia de activos","Integración con portales existentes","Análisis comparativo de zonas","Score de habitabilidad embebido"],
      target:"Portales y agencias"
    },
    {
      type:"DATA", icon:"📊", color:"a371f7", price:"$5K-50K/proyecto",
      title:"Fondos de Inversión",
      items:["Informes de habitabilidad a escala","Due diligence inmobiliario con IA","Mapas de riesgo de plusvalía","Dataset histórico de activos"],
      target:"Real Estate Investment"
    },
  ];

  models.forEach((m, i) => {
    const cx = 0.35 + i * 3.25;
    addCard(sl, cx, 1.35, 3.05, 3.8);
    sl.addShape(pres.shapes.RECTANGLE, { x:cx, y:1.35, w:3.05, h:0.06, fill:{ color:m.color }, line:{ color:m.color } });

    sl.addText(m.type, { x:cx+0.15, y:1.5, w:0.7, h:0.28, fontSize:9, bold:true, color:m.color, charSpacing:2 });
    sl.addText(m.icon + " " + m.title, { x:cx+0.15, y:1.8, w:2.7, h:0.4, fontSize:15, bold:true, color:TEXT });
    sl.addText(m.price, { x:cx+0.15, y:2.25, w:2.7, h:0.38, fontSize:22, bold:true, color:m.color });

    m.items.forEach((it, j) => {
      sl.addText([{ text:it, options:{ bullet:true } }], {
        x:cx+0.15, y:2.75+j*0.38, w:2.75, h:0.35, fontSize:9.5, color:MUTED
      });
    });

    sl.addShape(pres.shapes.ROUNDED_RECTANGLE, {
      x:cx+0.15, y:4.85, w:2.72, h:0.22, fill:{ color:m.color, transparency:85 }, line:{ color:m.color }, rectRadius:0.04
    });
    sl.addText(m.target, {
      x:cx+0.15, y:4.85, w:2.72, h:0.22, fontSize:8.5, color:m.color, align:"center", valign:"middle"
    });
  });

  // ARR projection
  addCard(sl, 0.35, 5.2, 9.3, 0.25);
  sl.addText("Revenue potencial: $0 (MVP actual)  →  $15K ARR (Q4 2026)  →  $50K ARR (Q2 2027)  →  $500K+ ARR (Expansión Latam)", {
    x:0.5, y:5.22, w:9.0, h:0.22, fontSize:9.5, color:MUTED, align:"center", italic:true
  });
}

// ══════════════════════════════════════════════════════════════════════════
// SLIDE 9 — ROADMAP
// ══════════════════════════════════════════════════════════════════════════
{
  const sl = pres.addSlide();
  slideBase(sl);

  sectionTitle(sl, "ROADMAP", 0.3);
  sl.addText("De MVP a plataforma Latam en 12 meses", {
    x:0.5, y:0.65, w:9, h:0.55, fontSize:24, bold:true, color:TEXT
  });

  const phases = [
    {
      q:"Q3 2026", color:GREEN, status:"NOW",
      title:"Consolidación Quito",
      items:["500 activos indexados","Bot SERCOP en producción","Importador CSV para agencias","Seed round / primeros clientes"]
    },
    {
      q:"Q4 2026", color:ACCENT, status:"NEXT",
      title:"Monetización",
      items:["Auth propietarios + pagos","Módulo mantenimiento preventivo","Dashboard B2C live","Primeros $5K MRR"]
    },
    {
      q:"Q1 2027", color:"f0883e", status:"PLANNED",
      title:"Expansión Ecuador",
      items:["Guayaquil + Cuenca","API B2B para 3 portales","Integración Google Maps 3D","Ronda Seed $500K"]
    },
    {
      q:"Q2 2027", color:"a371f7", status:"VISION",
      title:"Expansión Latam",
      items:["Medellín + Bogotá","Modelo de franquicia de datos","Serie A preparación",">$500K ARR"]
    },
  ];

  // Timeline bar
  sl.addShape(pres.shapes.LINE, {
    x:0.8, y:2.0, w:8.5, h:0, line:{ color: BORDER, width:1.5 }
  });

  phases.forEach((p, i) => {
    const cx = 0.5 + i * 2.3;

    // Dot on timeline
    sl.addShape(pres.shapes.OVAL, {
      x:cx+0.85, y:1.85, w:0.3, h:0.3, fill:{ color:p.color }, line:{ color:p.color }
    });

    // Quarter label
    sl.addText(p.q, {
      x:cx+0.3, y:1.45, w:1.5, h:0.3, fontSize:11, bold:true, color:p.color, align:"center"
    });

    // Status badge
    sl.addShape(pres.shapes.ROUNDED_RECTANGLE, {
      x:cx+0.5, y:1.15, w:0.9, h:0.22, fill:{ color:p.color, transparency:80 }, line:{ color:p.color }, rectRadius:0.04
    });
    sl.addText(p.status, {
      x:cx+0.5, y:1.15, w:0.9, h:0.22, fontSize:7, bold:true, color:p.color, align:"center", valign:"middle"
    });

    // Card below timeline
    addCard(sl, cx+0.1, 2.3, 2.1, 2.95);
    sl.addText(p.title, {
      x:cx+0.2, y:2.42, w:1.95, h:0.4, fontSize:12, bold:true, color:TEXT, align:"center"
    });

    p.items.forEach((it, j) => {
      sl.addText([{ text:it, options:{ bullet:true } }], {
        x:cx+0.2, y:2.9 + j*0.52, w:1.85, h:0.45, fontSize:9.5, color:MUTED
      });
    });
  });
}

// ══════════════════════════════════════════════════════════════════════════
// SLIDE 10 — Q&A PREGUNTAS DIFÍCILES
// ══════════════════════════════════════════════════════════════════════════
{
  const sl = pres.addSlide();
  slideBase(sl);

  sectionTitle(sl, "PREGUNTAS FRECUENTES DE INVERSORES", 0.3);
  sl.addText("Las preguntas difíciles — respondidas", {
    x:0.5, y:0.65, w:9, h:0.55, fontSize:24, bold:true, color:TEXT
  });

  const qas = [
    {
      q:"¿Cómo obtienen datos si los portales no los comparten?",
      a:"No dependemos de portales. Scrapeamos coordenadas de fuentes públicas y las enriquecemos con OSM local, APIs de Roads/Population de Google Earth y archivos SHP municipales. El dato es nuestro desde el momento de ingesta."
    },
    {
      q:"¿Qué impide que un portal grande copie esto?",
      a:"El tiempo y los datos acumulados. Construir un PostGIS con 35 activos tarda semanas; con 50,000 activos tomará años. Cada mes que operamos amplía el foso. Además, la bitácora de mantenimiento requiere que propietarios nos confíen sus datos activamente."
    },
    {
      q:"¿Por qué Quito primero?",
      a:"Mercado de $3.2B, alta densidad urbana, datos municipales (SERCOP, DMQ) estructurados y públicos. Carlos tiene red local y contexto regulatorio. Es el laboratorio perfecto antes de escalar a mercados más grandes."
    },
    {
      q:"¿Cómo escala sin que los costos de LLM exploten?",
      a:"El agente usa Claude solo para la respuesta final. Las tools son consultas PostGIS nativas (milisegundos, costo cero). Con caché de resultados frecuentes, el costo de LLM por query se mantiene por debajo de $0.02."
    },
    {
      q:"¿Qué pasa si Google Maps o Airbnb entra al mercado?",
      a:"Google Maps captura ubicación, no historial técnico ni mantenimiento predictivo. Airbnb indexa estancias, no activos permanentes. Somos el sistema de registro técnico del inmueble — una capa que incluso Google necesitaría comprar o asociarse."
    },
  ];

  qas.forEach((qa, i) => {
    const cy = 1.35 + i * 0.84;
    addCard(sl, 0.4, cy, 9.2, 0.76);
    sl.addShape(pres.shapes.OVAL, {
      x:0.45, y:cy+0.23, w:0.28, h:0.28, fill:{ color:ACCENT }, line:{ color:ACCENT }
    });
    sl.addText("?", { x:0.45, y:cy+0.23, w:0.28, h:0.28, fontSize:11, bold:true, color:"ffffff", align:"center", valign:"middle", margin:0 });
    sl.addText(qa.q, { x:0.85, y:cy+0.07, w:8.6, h:0.26, fontSize:10.5, bold:true, color:TEXT });
    sl.addText(qa.a, { x:0.85, y:cy+0.35, w:8.5, h:0.36, fontSize:9.5, color:MUTED });
  });
}

// ══════════════════════════════════════════════════════════════════════════
// SLIDE 11 — CIERRE / CONTACTO
// ══════════════════════════════════════════════════════════════════════════
{
  const sl = pres.addSlide();
  slideBase(sl);

  // Background accent
  sl.addShape(pres.shapes.RECTANGLE, {
    x:0, y:0, w:4.5, h:5.625, fill:{ color: SURFACE }, line:{ color: SURFACE }
  });
  sl.addShape(pres.shapes.RECTANGLE, {
    x:0, y:0, w:0.07, h:5.625, fill:{ color: ACCENT }, line:{ color: ACCENT }
  });

  // Left — value props
  sl.addText("¿Por qué ahora?", { x:0.4, y:0.5, w:3.8, h:0.5, fontSize:18, bold:true, color:ACCENT });
  const whyNow = [
    "PostGIS + LLMs maduros permiten escalar datos geoespaciales con IA por primera vez",
    "El mercado PropTech Latam creció 340% post-pandemia",
    "Datos municipales abiertos (SERCOP, DMQ) ahora disponibles vía API",
    "MVP funcional en producción — riesgo técnico eliminado",
  ];
  whyNow.forEach((w, i) => {
    sl.addText([{ text:w, options:{ bullet:true } }], {
      x:0.4, y:1.15 + i*0.75, w:3.9, h:0.65, fontSize:11, color:TEXT
    });
  });

  // Right — CTA
  // Map pin icon
  sl.addShape(pres.shapes.OVAL, { x:5.5, y:0.5, w:0.65, h:0.65, fill:{ color: ACCENT }, line:{ color: ACCENT2 } });
  sl.addShape(pres.shapes.OVAL, { x:5.72, y:0.72, w:0.22, h:0.22, fill:{ color: BG }, line:{ color: BG } });
  sl.addShape(pres.shapes.RECTANGLE, { x:5.79, y:1.08, w:0.1, h:0.28, fill:{ color: ACCENT }, line:{ color: ACCENT } });

  sl.addText("Contexto AI", { x:6.3, y:0.55, w:3.3, h:0.55, fontSize:28, bold:true, color:TEXT });
  sl.addText("El Catastro Vivo de Latinoamérica", { x:5.5, y:1.1, w:4.1, h:0.35, fontSize:12, color:ACCENT });

  sl.addShape(pres.shapes.LINE, { x:5.5, y:1.55, w:4.1, h:0, line:{ color: BORDER, width:0.5 } });

  // Contact info
  const contacts = [
    { icon:"👤", label:"Carlos Valencia", note:"Founder & CEO" },
    { icon:"📧", label:"contexxto.ai@gmail.com", note:"" },
    { icon:"🌐", label:"contexto-ai-six.vercel.app", note:"Demo en vivo" },
    { icon:"⚙️", label:"contexto-ai.onrender.com/health", note:"API live" },
  ];
  contacts.forEach((c, i) => {
    sl.addText(c.icon, { x:5.5, y:1.75 + i*0.65, w:0.4, h:0.5, fontSize:18, align:"center" });
    sl.addText(c.label, { x:6.0, y:1.82 + i*0.65, w:3.5, h:0.28, fontSize:11, bold:false, color:TEXT });
    if (c.note) sl.addText(c.note, { x:6.0, y:2.1 + i*0.65, w:3.5, h:0.22, fontSize:9, color:MUTED });
  });

  // CTA button
  sl.addShape(pres.shapes.RECTANGLE, {
    x:5.5, y:4.55, w:4.1, h:0.72, fill:{ color: ACCENT }, line:{ color: ACCENT }
  });
  sl.addText("Agenda una Demo de 20 minutos", {
    x:5.5, y:4.55, w:4.1, h:0.72, fontSize:14, bold:true, color:"ffffff", align:"center", valign:"middle"
  });

  sl.addText("MVP vivo. Datos reales. Agente funcionando.", {
    x:5.4, y:5.28, w:4.3, h:0.28, fontSize:9.5, color:MUTED, align:"center", italic:true
  });
}

// ── Save ──────────────────────────────────────────────────────────────────
const out = "C:\\Users\\DETPC\\Desktop\\ContextoAI_PitchDeck.pptx";
pres.writeFile({ fileName: out }).then(() => console.log("Deck guardado en:", out));
