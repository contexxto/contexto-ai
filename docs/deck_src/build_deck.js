const pptxgen = require("pptxgenjs");
const path = require("path");
const A = (f) => path.join(__dirname, f);

const BG = "0E0D13", SURF = "16151E", SURF2 = "1E1D28", BORDER = "2E2D3A";
const TEAL = "2DBDB6", TEALB = "5EEAD4", GOLD = "E5C06A";
const TEXT = "F0ECE6", MID = "A8A3B3", DIM = "6B6778";
const FT = "Geist", FB = "Calibri";

const p = new pptxgen();
p.defineLayout({ name: "W", width: 13.333, height: 7.5 });
p.layout = "W";

// ---- helpers ----
function kicker(s, t, x = 0.7, y = 0.62) {
  s.addText(t, { x, y, w: 9, h: 0.35, fontFace: FT, fontSize: 12.5, bold: true, color: TEAL, charSpacing: 3, margin: 0, align: "left" });
}
function foot(s, n) {
  s.addText([{ text: "Contexto", options: { color: TEXT } }, { text: " AI", options: { color: TEAL } }],
    { x: 0.7, y: 6.98, w: 3, h: 0.3, fontFace: FT, fontSize: 11, bold: true, margin: 0 });
  s.addText(String(n).padStart(2, "0") + " / 12", { x: 11.4, y: 6.98, w: 1.5, h: 0.3, fontFace: FB, fontSize: 10, color: DIM, align: "right", margin: 0 });
}
function bullets(s, items, o) {
  const arr = items.map((it, i) => ({
    text: it, options: { bullet: { code: "2013", indent: 18 }, breakLine: true, paraSpaceAfter: 12, color: o.color || TEXT }
  }));
  s.addText(arr, { x: o.x, y: o.y, w: o.w, h: o.h, fontFace: FB, fontSize: o.fs || 16.5, valign: "top", lineSpacingMultiple: 1.05, margin: 0 });
}
function card(s, x, y, w, h, fill, line) {
  s.addShape(p.ShapeType.roundRect, { x, y, w, h, rectRadius: 0.12, fill: { color: fill }, line: line ? { color: line, width: 1 } : { type: "none" } });
}

// ===== S1 — Portada =====
let s = p.addSlide(); s.background = { path: A("bg_title.png") };
kicker(s, "CONTEXTO · VISIÓN", 0.7, 2.25);
s.addText([{ text: "Contexto", options: { color: TEXT } }, { text: " AI", options: { color: TEAL } }],
  { x: 0.7, y: 2.75, w: 8, h: 1.1, fontFace: FT, fontSize: 54, bold: true, margin: 0 });
s.addText("La IA honesta para la decisión más grande de tu vida.",
  { x: 0.72, y: 4.05, w: 6.9, h: 1.1, fontFace: FB, fontSize: 22, color: MID, margin: 0, lineSpacingMultiple: 1.1 });
s.addText("Quito · Ecuador", { x: 0.72, y: 6.98, w: 4, h: 0.3, fontFace: FB, fontSize: 11, color: DIM, margin: 0 });
s.addNotes("Portada. Tono calma y confianza. La marca + la promesa, sin ruido.");

// ===== S2 — La injusticia =====
s = p.addSlide(); s.background = { path: A("bg_content.png") };
kicker(s, "EL PROBLEMA");
s.addText("El que más arriesga es el que menos sabe.",
  { x: 0.7, y: 1.35, w: 5.7, h: 1.7, fontFace: FT, fontSize: 33, bold: true, color: TEXT, margin: 0, lineSpacingMultiple: 1.05 });
s.addText("El que vende tiene veinte herramientas. El que compra, una pestaña de buscador y su intuición.",
  { x: 0.72, y: 3.35, w: 5.4, h: 1.4, fontFace: FB, fontSize: 18, color: MID, margin: 0, lineSpacingMultiple: 1.15 });
s.addText("Toda la IA fue al lado de la oferta.",
  { x: 0.72, y: 4.95, w: 5.4, h: 0.6, fontFace: FB, fontSize: 18, bold: true, color: TEALB, margin: 0 });
s.addImage({ path: A("art_balance.png"), x: 6.85, y: 1.75, w: 6.0, h: 3.375 });
foot(s, 2); s.addNotes("El problema como injusticia, no como tema técnico. La balanza: toda la luz de un lado.");

// ===== S3 — El hueco estructural =====
s = p.addSlide(); s.background = { path: A("bg_content.png") };
kicker(s, "POR QUÉ NADIE LO RESOLVIÓ");
s.addText("El hueco no es un descuido. Es lo más difícil de resolver.",
  { x: 0.7, y: 1.25, w: 5.7, h: 1.6, fontFace: FT, fontSize: 28, bold: true, color: TEXT, margin: 0, lineSpacingMultiple: 1.05 });
bullets(s, [
  "El lado comprador es un cementerio: la economía mató a los que lo intentaron a escala.",
  "Todos describen; nadie verifica.",
  "En LATAM, además, el dato público no existe."
], { x: 0.72, y: 3.35, w: 5.5, h: 3.2, fs: 16.5 });
s.addImage({ path: A("art_void.png"), x: 6.85, y: 1.75, w: 6.0, h: 3.375 });
foot(s, 3); s.addNotes("El problema es real y no trivial. El hueco como ausencia de luz. Quien lo resuelva tiene foso.");

// ===== S4 — La tesis =====
s = p.addSlide(); s.background = { path: A("bg_content.png") };
kicker(s, "LA TESIS");
s.addText("Donde otros describen, nosotros verificamos.",
  { x: 0.7, y: 1.9, w: 8.4, h: 1.5, fontFace: FT, fontSize: 38, bold: true, color: TEXT, margin: 0, lineSpacingMultiple: 1.02 });
s.addText("«Donde otros dicen ‘confianza nula’, Contexto dice: verificado en el terreno.»",
  { x: 0.72, y: 3.55, w: 8.7, h: 1.1, fontFace: FB, fontSize: 21, italic: true, color: TEALB, margin: 0, lineSpacingMultiple: 1.1 });
s.addText("Eso no se copia scrapeando — requiere haber estado en el inmueble.",
  { x: 0.72, y: 5.0, w: 8, h: 0.7, fontFace: FB, fontSize: 16, color: MID, margin: 0 });
card(s, 9.55, 2.1, 3.1, 3.0, SURF2, BORDER);
s.addText([{ text: "✓", options: { color: GOLD, fontSize: 30, breakLine: true } },
  { text: "Verificado en terreno", options: { color: TEXT, fontSize: 15, bold: true, breakLine: true, paraSpaceBefore: 6 } },
  { text: "Tubería · 2023", options: { color: MID, fontSize: 12.5, breakLine: true, paraSpaceBefore: 8 } },
  { text: "Cédula · sí", options: { color: MID, fontSize: 12.5, breakLine: true } },
  { text: "2026-07 · con proveniencia", options: { color: DIM, fontSize: 11, breakLine: true, paraSpaceBefore: 6 } }],
  { x: 9.8, y: 2.35, w: 2.6, h: 2.5, fontFace: FB, valign: "top", margin: 0 });
foot(s, 4); s.addNotes("El diferenciador en una frase que se recuerda.");

// ===== S5 — Qué es =====
s = p.addSlide(); s.background = { path: A("bg_content.png") };
kicker(s, "QUÉ ES CONTEXTO");
s.addText("No es un buscador de inmuebles.",
  { x: 0.7, y: 1.25, w: 8.5, h: 0.9, fontFace: FT, fontSize: 33, bold: true, color: TEXT, margin: 0 });
s.addText("Es el sistema vivo de la verdad del lugar.",
  { x: 0.7, y: 2.2, w: 9, h: 0.9, fontFace: FT, fontSize: 26, bold: true, color: TEALB, margin: 0 });
s.addText("La asesora honesta que razona si vivir, rentar o invertir tiene sentido — sobre dato verificado — y te conecta con un humano que responde.",
  { x: 0.72, y: 3.25, w: 8.4, h: 1.4, fontFace: FB, fontSize: 18, color: MID, margin: 0, lineSpacingMultiple: 1.2 });
const flow = [["Persona", "su intención"], ["Contexto", "la verdad del lugar"], ["Corredor", "cierra"]];
flow.forEach((f, i) => {
  const x = 0.7 + i * 4.15;
  card(s, x, 5.35, 3.5, 1.15, SURF, i === 1 ? TEAL : BORDER);
  s.addText([{ text: f[0], options: { color: i === 1 ? TEALB : TEXT, fontSize: 16, bold: true, breakLine: true } },
    { text: f[1], options: { color: MID, fontSize: 12, breakLine: true } }],
    { x: x + 0.2, y: 5.5, w: 3.1, h: 0.85, fontFace: FB, align: "center", valign: "middle", margin: 0 });
  if (i < 2) s.addText("→", { x: x + 3.5, y: 5.5, w: 0.65, h: 0.85, fontFace: FB, fontSize: 20, color: TEAL, align: "center", valign: "middle", margin: 0 });
});
foot(s, 5); s.addNotes("Definir la categoría en sus términos, no en los del portal. IA da contexto, humano cierra.");

// ===== S6 — El foso =====
s = p.addSlide(); s.background = { path: A("bg_content.png") };
kicker(s, "EL FOSO");
s.addText("No es una app. Es un activo que compone solo.",
  { x: 0.7, y: 1.2, w: 6.4, h: 1.3, fontFace: FT, fontSize: 28, bold: true, color: TEXT, margin: 0, lineSpacingMultiple: 1.05 });
const capas = [["Catastro Vivo verificado", "datos por coordenada, con fecha y proveniencia"],
["Inteligencia de inversión", "yield, margen y riesgo sobre dato real"],
["Confianza / honestidad", "distingue el dato verificado de la estimación"]];
capas.forEach((c, i) => {
  const y = 2.75 + i * 1.05;
  s.addShape(p.ShapeType.ellipse, { x: 0.72, y: y + 0.02, w: 0.5, h: 0.5, fill: { color: SURF2 }, line: { color: TEAL, width: 1.25 } });
  s.addText(String(i + 1), { x: 0.72, y: y + 0.02, w: 0.5, h: 0.5, fontFace: FT, fontSize: 16, bold: true, color: TEALB, align: "center", valign: "middle", margin: 0 });
  s.addText([{ text: c[0], options: { color: TEXT, fontSize: 17, bold: true, breakLine: true } },
    { text: c[1], options: { color: MID, fontSize: 13, breakLine: true } }],
    { x: 1.45, y: y - 0.05, w: 5.5, h: 0.95, fontFace: FB, valign: "middle", margin: 0 });
});
s.addText("El motor: el loop del corredor — más inteligente con cada cliente que lo toca.",
  { x: 0.72, y: 6.05, w: 7, h: 0.5, fontFace: FB, fontSize: 14.5, italic: true, color: TEALB, margin: 0 });
s.addImage({ path: A("art_rings.png"), x: 8.5, y: 1.95, w: 4.1, h: 4.1 });
foot(s, 6); s.addNotes("Lo defendible es el compounding del aprendizaje, no la interfaz.");

// ===== S7 — Ranking a recomendación =====
s = p.addSlide(); s.background = { path: A("bg_content.png") };
kicker(s, "EL CAMBIO DE JUEGO");
s.addText("No se compite por posición. Se compite por ser la verdad que la IA recomienda.",
  { x: 0.7, y: 1.2, w: 11.9, h: 1.4, fontFace: FT, fontSize: 29, bold: true, color: TEXT, margin: 0, lineSpacingMultiple: 1.05 });
card(s, 0.7, 3.35, 5.7, 2.7, SURF, BORDER);
s.addText([{ text: "ANTES · Ranking", options: { color: DIM, fontSize: 15, bold: true, charSpacing: 2, breakLine: true } },
  { text: "SEO, posición en el portal, pujar por estar arriba de la lista.", options: { color: MID, fontSize: 16, breakLine: true, paraSpaceBefore: 10 } }],
  { x: 1.0, y: 3.65, w: 5.1, h: 2.1, fontFace: FB, valign: "top", margin: 0, lineSpacingMultiple: 1.15 });
card(s, 6.9, 3.35, 5.7, 2.7, SURF2, TEAL);
s.addText([{ text: "AHORA · Recomendación", options: { color: TEALB, fontSize: 15, bold: true, charSpacing: 2, breakLine: true } },
  { text: "La verdad del lugar es el sustrato del emparejamiento de intención con una vida.", options: { color: TEXT, fontSize: 16, breakLine: true, paraSpaceBefore: 10 } }],
  { x: 7.2, y: 3.65, w: 5.1, h: 2.1, fontFace: FB, valign: "top", margin: 0, lineSpacingMultiple: 1.15 });
foot(s, 7); s.addNotes("Reposiciona a los incumbentes sin nombrarlos con desdén. La verdad del lugar es el sustrato.");

// ===== S8 — Cómo se siente =====
s = p.addSlide(); s.background = { path: A("bg_content.png") };
kicker(s, "EL OFICIO");
s.addText("Una conversación honesta, no un volcado de datos.",
  { x: 0.7, y: 1.2, w: 7.3, h: 1.4, fontFace: FT, fontSize: 30, bold: true, color: TEXT, margin: 0, lineSpacingMultiple: 1.05 });
bullets(s, [
  "Cápsulas que llevan a la siguiente pregunta — tú conduces.",
  "La ficha verificada que revela lo que el anuncio esconde.",
  "El handoff al corredor en el pico de intención."
], { x: 0.72, y: 3.15, w: 6.4, h: 3, fs: 16.5 });
card(s, 8.35, 1.75, 4.25, 4.5, SURF2, BORDER);
s.addText("Ficha verificada", { x: 8.6, y: 2.0, w: 3.7, h: 0.4, fontFace: FT, fontSize: 15, bold: true, color: TEXT, margin: 0 });
const rows = [["Tubería renovada", "2023 ✓", GOLD], ["Cédula", "sí ✓", GOLD], ["Ruido real 7pm", "medio", MID], ["A pie al Metro", "7 min ✓", GOLD], ["Impermeabilización", "al día ✓", GOLD]];
rows.forEach((r, i) => {
  const y = 2.6 + i * 0.62;
  s.addText(r[0], { x: 8.6, y, w: 2.5, h: 0.5, fontFace: FB, fontSize: 13.5, color: MID, valign: "middle", margin: 0 });
  s.addText(r[1], { x: 11.1, y, w: 1.25, h: 0.5, fontFace: FB, fontSize: 13.5, bold: true, color: r[2], align: "right", valign: "middle", margin: 0 });
});
foot(s, 8); s.addNotes("Mostrar producto real — que exista, no que se prometa. Cápsulas, no informes.");

// ===== S9 — Por qué LATAM / ahora =====
s = p.addSlide(); s.background = { path: A("bg_content.png") };
kicker(s, "POR QUÉ AQUÍ, POR QUÉ AHORA");
s.addText("La escasez que frena a los gigantes es la que nos protege.",
  { x: 0.7, y: 1.2, w: 11.9, h: 1.0, fontFace: FT, fontSize: 30, bold: true, color: TEXT, margin: 0 });
const cols = [["Dato público pobre", "el dato verificado es el único moat."],
["Verdad hiperlocal", "los LLM genéricos fallan donde importa."],
["AI-nativo", "iteramos en horas lo que a otros les toma meses."]];
cols.forEach((c, i) => {
  const x = 0.7 + i * 4.05;
  card(s, x, 3.0, 3.75, 2.5, SURF, i === 0 ? TEAL : BORDER);
  s.addText([{ text: c[0], options: { color: TEALB, fontSize: 17, bold: true, breakLine: true } },
    { text: c[1], options: { color: MID, fontSize: 14.5, breakLine: true, paraSpaceBefore: 8 } }],
    { x: x + 0.28, y: 3.28, w: 3.2, h: 2.0, fontFace: FB, valign: "top", margin: 0, lineSpacingMultiple: 1.15 });
});
s.addShape(p.ShapeType.roundRect, { x: 0.7, y: 5.95, w: 3.7, h: 0.55, rectRadius: 0.27, fill: { color: SURF2 }, line: { color: TEAL, width: 1 } });
s.addText("Ya en producción · Quito", { x: 0.7, y: 5.95, w: 3.7, h: 0.55, fontFace: FB, fontSize: 14, bold: true, color: TEALB, align: "center", valign: "middle", margin: 0 });
foot(s, 9); s.addNotes("El porqué-ahora honesto, sin cifras infladas.");

// ===== S10 — Honestidad =====
s = p.addSlide(); s.background = { path: A("bg_content.png") };
kicker(s, "EL CIMIENTO (Y LA DEFENSA)");
s.addText("Distinguimos el dato verificado de la estimación. En voz alta.",
  { x: 0.7, y: 1.2, w: 8.0, h: 1.4, fontFace: FT, fontSize: 28, bold: true, color: TEXT, margin: 0, lineSpacingMultiple: 1.05 });
bullets(s, [
  "Perfilamos lugares e inmuebles — nunca personas.",
  "Fair Housing por construcción, no por obligación.",
  "La honestidad dejó de ser ética: es defensa legal y comercial frente al ‘AI slop’."
], { x: 0.72, y: 3.2, w: 7.7, h: 3, fs: 16.5 });
card(s, 9.0, 2.5, 3.6, 2.3, SURF2, BORDER);
s.addText([{ text: "✓  Verificado", options: { color: GOLD, fontSize: 18, bold: true, breakLine: true } },
  { text: "dato medido, con proveniencia", options: { color: MID, fontSize: 12.5, breakLine: true, paraSpaceBefore: 3 } },
  { text: "~  Estimación", options: { color: MID, fontSize: 18, bold: true, breakLine: true, paraSpaceBefore: 14 } },
  { text: "siempre rotulada como tal", options: { color: DIM, fontSize: 12.5, breakLine: true, paraSpaceBefore: 3 } }],
  { x: 9.3, y: 2.75, w: 3.1, h: 1.9, fontFace: FB, valign: "top", margin: 0 });
foot(s, 10); s.addNotes("Convertir la ética en ventaja, no en disclaimer.");

// ===== S11 — El humano cierra =====
s = p.addSlide(); s.background = { path: A("bg_content.png") };
kicker(s, "EL HANDOFF");
s.addText("La IA da el contexto. El humano cierra.",
  { x: 0.7, y: 1.7, w: 10, h: 1.1, fontFace: FT, fontSize: 36, bold: true, color: TEXT, margin: 0 });
s.addText("No reemplazamos al corredor: le entregamos un comprador que llega informado y tranquilo. Vender es un deporte de contacto humano.",
  { x: 0.72, y: 3.0, w: 8.7, h: 1.4, fontFace: FB, fontSize: 20, color: MID, margin: 0, lineSpacingMultiple: 1.2 });
card(s, 0.7, 4.9, 4.3, 1.2, SURF2, TEAL);
s.addText([{ text: "IA", options: { color: TEALB, fontSize: 17, bold: true, breakLine: true } }, { text: "da el contexto", options: { color: MID, fontSize: 13, breakLine: true } }],
  { x: 0.9, y: 5.05, w: 3.9, h: 0.9, fontFace: FB, align: "center", valign: "middle", margin: 0 });
s.addText("→", { x: 5.1, y: 5.05, w: 0.9, h: 0.9, fontFace: FB, fontSize: 26, color: TEAL, align: "center", valign: "middle", margin: 0 });
card(s, 6.2, 4.9, 4.3, 1.2, SURF2, GOLD);
s.addText([{ text: "Humano", options: { color: GOLD, fontSize: 17, bold: true, breakLine: true } }, { text: "cierra", options: { color: MID, fontSize: 13, breakLine: true } }],
  { x: 6.4, y: 5.05, w: 3.9, h: 0.9, fontFace: FB, align: "center", valign: "middle", margin: 0 });
foot(s, 11); s.addNotes("Pro-corredor explícito; desactiva el miedo al reemplazo por IA.");

// ===== S12 — La postura / cierre =====
s = p.addSlide(); s.background = { path: A("bg_title.png") };
kicker(s, "LA POSTURA", 0.7, 1.9);
s.addText("No vinimos a listar casas.\nVinimos a cambiar de qué lado está la verdad.",
  { x: 0.7, y: 2.4, w: 7.6, h: 2.1, fontFace: FT, fontSize: 36, bold: true, color: TEXT, margin: 0, lineSpacingMultiple: 1.06 });
s.addText("En la compra más grande de tu vida, ¿de qué lado ha estado la información?",
  { x: 0.72, y: 4.7, w: 6.9, h: 1.1, fontFace: FB, fontSize: 20, italic: true, color: TEALB, margin: 0, lineSpacingMultiple: 1.15 });
s.addText([{ text: "Contexto", options: { color: TEXT } }, { text: " AI", options: { color: TEAL } }],
  { x: 0.7, y: 6.7, w: 4, h: 0.4, fontFace: FT, fontSize: 15, bold: true, margin: 0 });
s.addNotes("Cerrar con convicción, no con CTA. El manifiesto como sello.");

p.writeFile({ fileName: A("Contexto_Vision_Deck.pptx") }).then((f) => console.log("WROTE", f));
