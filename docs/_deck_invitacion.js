/* Deck de INVITACIÓN A CONVERSAR — Contexto AI (no es deck de inversión).
   Tema oscuro premium, "aura" de marca, español limpio. Usa las 4 validaciones
   externas como prueba social. Genera .pptx con pptxgenjs.
   Correr:  NODE_PATH="C:/Users/DETPC/AppData/Roaming/npm/node_modules" node docs/_deck_invitacion.js
*/
const pptxgen = require('pptxgenjs');
const p = new pptxgen();
p.defineLayout({ name: 'W', width: 13.333, height: 7.5 });
p.layout = 'W';
p.author = 'Contexto AI';
p.title = 'Contexto AI — Invitación a conversar';

const BG='0E0D13', TEAL='2DBDB6', TEALL='5EEAD4', CORAL='E0685A', AMBER='E5C06A',
      TXT='F5F5F7', MUT='9AA0AE', CARD='17171F';
const F = 'Segoe UI';

function bg(s){ s.background = { color: BG }; }

// Marca "aura": dos círculos superpuestos (coral + teal) = la esfera de marca.
function aura(s, x, y, d){
  s.addShape(p.ShapeType.ellipse, { x:x+d*0.16, y:y, w:d*0.84, h:d*0.84, fill:{color:CORAL, transparency:20} });
  s.addShape(p.ShapeType.ellipse, { x:x, y:y+d*0.16, w:d*0.84, h:d*0.84, fill:{color:TEAL, transparency:8} });
}
function brand(s){
  aura(s, 0.6, 0.5, 0.34);
  s.addText('Contexto AI', { x:1.02, y:0.46, w:4, h:0.42, fontSize:13, color:TXT, bold:true, valign:'middle', fontFace:F });
}
function footer(s, t){
  s.addText(t || 'contexxto.com', { x:0.6, y:7.02, w:8, h:0.32, fontSize:10, color:MUT, fontFace:F });
}
function title(s, t, color){
  s.addText(t, { x:0.6, y:1.0, w:12.1, h:1.0, fontSize:30, bold:true, color:color||TXT, fontFace:F, valign:'middle' });
}
function card(s, x, y, w, h){
  s.addShape(p.ShapeType.roundRect, { x, y, w, h, rectRadius:0.09, fill:{color:CARD}, line:{color:TEAL, width:1, transparency:55} });
}

/* ---------- 1) PORTADA ---------- */
let s = p.addSlide(); bg(s);
aura(s, 6.07, 1.15, 1.7);
s.addText('Contexto AI', { x:0, y:3.05, w:13.333, h:0.8, align:'center', fontSize:42, bold:true, color:TXT, fontFace:F });
s.addText('Cada lugar tiene un aura', { x:0, y:3.95, w:13.333, h:0.7, align:'center', fontSize:26, color:TEALL, fontFace:F });
s.addText('El catastro vivo de Quito: la verdad de cómo es vivir en cada lugar.',
  { x:1.5, y:4.75, w:10.33, h:0.6, align:'center', fontSize:15, color:MUT, fontFace:F });
s.addText('Una invitación a conversar  ·  eXp Realty  ·  junio 2026',
  { x:0, y:6.5, w:13.333, h:0.4, align:'center', fontSize:12, color:MUT, fontFace:F });

/* ---------- 2) EL PROBLEMA ---------- */
s = p.addSlide(); bg(s); brand(s);
title(s, 'El anuncio muere. El lugar permanece.');
s.addText([
  { text:'Los portales muestran fotos y precio. Nadie te dice cómo es VIVIR ahí.', options:{ bullet:{code:'2022'}, color:TXT, breakLine:true } },
  { text:'El ruido real, el transporte que sí usas, la vida de barrio: invisibles.', options:{ bullet:{code:'2022'}, color:TXT, breakLine:true, paraSpaceBefore:10 } },
  { text:'Y cuando el inmueble se vende, el dato desaparece. Vuelves a empezar de cero.', options:{ bullet:{code:'2022'}, color:TXT, breakLine:true, paraSpaceBefore:10 } },
], { x:0.7, y:2.4, w:11.9, h:2.6, fontSize:19, color:TXT, fontFace:F, lineSpacingMultiple:1.1 });
s.addText('Cada propiedad nueva, empiezas de cero. El conocimiento no se acumula.',
  { x:0.7, y:5.4, w:11.9, h:0.6, fontSize:16, italic:true, color:CORAL, fontFace:F });
footer(s);

/* ---------- 3) LA IDEA — CATASTRO VIVO ---------- */
s = p.addSlide(); bg(s); brand(s);
title(s, 'Cada lugar, una coordenada permanente', TEALL);
s.addText([
  { text:'No indexamos anuncios efímeros.', options:{ bullet:{code:'2022'}, color:TXT, breakLine:true } },
  { text:'Cada lugar acumula la verdad de cómo es vivir ahí — y se vuelve más inteligente con cada corredor que la enriquece.', options:{ bullet:{code:'2022'}, color:TXT, breakLine:true, paraSpaceBefore:10 } },
], { x:0.7, y:2.4, w:11.9, h:2.2, fontSize:19, color:TXT, fontFace:F, lineSpacingMultiple:1.1 });
card(s, 0.7, 5.0, 11.9, 1.2);
s.addText('El dato pertenece al LUGAR, no al anuncio. Eso lo cambia todo.',
  { x:1.0, y:5.0, w:11.3, h:1.2, fontSize:20, bold:true, color:TEALL, valign:'middle', fontFace:F });
footer(s);

/* ---------- 4) LO QUE HACE ---------- */
s = p.addSlide(); bg(s); brand(s);
title(s, 'Entiende. Dice la verdad. Te conecta con tu corredor.');
const c4 = [
  ['🎯  Entiende qué buscas', 'Te escucha y empareja tu vida con un lugar — no te vuelca una lista de anuncios.'],
  ['✅  Dice la verdad del lugar', 'Lo bueno y lo que cede: caminabilidad, ruido, transporte real. Evidencia, no relato.'],
  ['🤝  No inventa: te entrega al corredor', 'Cuando no sabe algo, lo dice y te conecta con quien conoce la zona de verdad.'],
];
let x4 = 0.7; const w4 = 3.83, gap4 = 0.2;
c4.forEach(([h, b]) => {
  card(s, x4, 2.3, w4, 2.55);
  s.addText(h, { x:x4+0.25, y:2.55, w:w4-0.5, h:0.7, fontSize:16, bold:true, color:TEALL, fontFace:F, valign:'top' });
  s.addText(b, { x:x4+0.25, y:3.3, w:w4-0.5, h:1.4, fontSize:13.5, color:TXT, fontFace:F, valign:'top', lineSpacingMultiple:1.05 });
  x4 += w4 + gap4;
});
card(s, 0.7, 5.15, 11.86, 1.25);
s.addText([
  { text:'Le preguntamos: "¿es súper segura, con cero delincuencia?"  ', options:{ color:MUT } },
  { text:'Se negó a mentir.', options:{ color:AMBER, bold:true } },
  { text:'  En un mercado escéptico de la IA, la que NO miente gana.', options:{ color:TXT } },
], { x:1.0, y:5.15, w:11.26, h:1.25, fontSize:15, valign:'middle', fontFace:F });
footer(s);

/* ---------- 5) EL MUNDO CONVERGE (validaciones) ---------- */
s = p.addSlide(); bg(s); brand(s);
title(s, 'No es solo idea nuestra — el mundo va hacia aquí');
const v = [
  ['Satya Nadella · Microsoft', 'Los sistemas que se automejoran ganan a los estáticos.'],
  ['Esri · líder mundial en mapas', 'Lanzó un agente inmobiliario geoespacial.'],
  ['Realtor.com · EE.UU.', 'Búsqueda de vivienda con IA conversacional.'],
  ['Eva / Aino', 'Inteligencia de ubicación para decisiones de inversión.'],
];
const cw=5.83, ch=1.62, gx=0.2, gy=0.22, x0=0.7, y0=2.25;
v.forEach((it, i) => {
  const cx = x0 + (i % 2) * (cw + gx);
  const cy = y0 + Math.floor(i / 2) * (ch + gy);
  card(s, cx, cy, cw, ch);
  s.addText(it[0], { x:cx+0.25, y:cy+0.16, w:cw-0.5, h:0.45, fontSize:15, bold:true, color:TEALL, fontFace:F });
  s.addText(it[1], { x:cx+0.25, y:cy+0.66, w:cw-0.5, h:0.85, fontSize:13.5, color:TXT, fontFace:F, lineSpacingMultiple:1.05 });
});
s.addText('La ubicación es el motor #1 del valor. Cuatro señales en pocas semanas.',
  { x:0.7, y:6.35, w:11.9, h:0.5, fontSize:15, italic:true, color:MUT, fontFace:F });
footer(s);

/* ---------- 6) EL FOSO (LatAm) ---------- */
s = p.addSlide(); bg(s); brand(s);
title(s, 'Ellos AGREGAN datos. Nosotros los CONSTRUIMOS.');
s.addText([
  { text:'Todos son de Estados Unidos, sobre datos que allá ya existen: censos, registros de parcelas, listados.', options:{ bullet:{code:'2022'}, color:TXT, breakLine:true } },
  { text:'En Quito esos datos NO existen.', options:{ bullet:{code:'2022'}, color:AMBER, bold:true, breakLine:true, paraSpaceBefore:10 } },
  { text:'La única forma de tener la verdad de los lugares de Quito es CREARLA — con corredores que conocen el territorio.', options:{ bullet:{code:'2022'}, color:TXT, breakLine:true, paraSpaceBefore:10 } },
], { x:0.7, y:2.35, w:11.9, h:2.6, fontSize:18, color:TXT, fontFace:F, lineSpacingMultiple:1.12 });
card(s, 0.7, 5.25, 11.86, 1.1);
s.addText('Ese dato no lo tiene Google. No lo tienen ellos. Lo construimos nosotros — contigo.',
  { x:1.0, y:5.25, w:11.26, h:1.1, fontSize:18, bold:true, color:TEALL, valign:'middle', fontFace:F });
footer(s);

/* ---------- 7) QUÉ GANA TU INMOBILIARIA ---------- */
s = p.addSlide(); bg(s); brand(s);
title(s, 'Lo que esto hace por tu inmobiliaria');
const g = [
  'Cierras objeciones en la visita, no después.',
  'Diferencias un inmueble sin inventar: la ficha que justifica el precio.',
  'Traduces la zona a vida real — el cliente se imagina viviendo ahí.',
  'Tus inmuebles se vuelven un activo de datos que posees — y que atrae interesados.',
];
let gy2 = 2.35; const gh = 0.96;
g.forEach((t) => {
  card(s, 0.7, gy2, 11.86, gh);
  s.addText('✓', { x:0.95, y:gy2, w:0.6, h:gh, fontSize:22, bold:true, color:TEALL, align:'center', valign:'middle', fontFace:F });
  s.addText(t, { x:1.6, y:gy2, w:10.7, h:gh, fontSize:17, color:TXT, valign:'middle', fontFace:F });
  gy2 += gh + 0.16;
});
footer(s);

/* ---------- 8) LA INVITACIÓN ---------- */
s = p.addSlide(); bg(s);
aura(s, 11.0, 4.9, 2.4); // aura grande, esquina inferior derecha
s.addText('Conversemos.', { x:0.8, y:1.6, w:11, h:1.1, fontSize:46, bold:true, color:TXT, fontFace:F });
s.addText('Te propongo un piloto de 2 semanas, sin costo:\nsubimos tus inmuebles y ves qué interesados llegan.',
  { x:0.82, y:3.0, w:10.5, h:1.4, fontSize:20, color:TXT, fontFace:F, lineSpacingMultiple:1.15 });
s.addText([
  { text:'contexxto.com', options:{ color:TEALL, bold:true } },
  { text:'     ·     ', options:{ color:MUT } },
  { text:'contexxto.ai@gmail.com', options:{ color:TEALL, bold:true } },
], { x:0.82, y:4.7, w:11, h:0.5, fontSize:18, fontFace:F });
s.addText('Cada lugar tiene un aura. Mostrémosla.',
  { x:0.82, y:6.4, w:11, h:0.5, fontSize:16, italic:true, color:MUT, fontFace:F });

const OUT = 'C:/Users/DETPC/Desktop/Contexxto/Contexto_Invitacion_eXp.pptx';
p.writeFile({ fileName: OUT }).then(f => console.log('OK ->', f)).catch(e => { console.error('ERR', e); process.exit(1); });
