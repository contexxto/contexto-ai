// Genera la version editable en Word (.docx) del one-pager "Encaje Financiero"
// para Jose Luis de Linden (Puebla, Mexico) — mismo contenido que el PDF externo.
const {
  Document, Packer, Paragraph, TextRun, AlignmentType, LevelFormat,
  HeadingLevel, BorderStyle, ShadingType, WidthType, Table, TableRow, TableCell,
  Header, Footer, PageNumber, TabStopType, TabStopPosition,
} = require("docx");
const fs = require("fs");

const TEAL = "0E8C7F";
const TEAL_DARK = "0B6F65";
const INK = "1F2937";
const GRAY = "4B5563";
const CALLOUT_BG = "E8F6F4";

const FONT = "Calibri";

function bullet(text) {
  return new Paragraph({
    numbering: { reference: "bullets", level: 0 },
    spacing: { after: 60 },
    children: [new TextRun({ text, font: FONT, size: 20, color: INK })],
  });
}

function body(text, opts = {}) {
  return new Paragraph({
    spacing: { after: opts.after ?? 80 },
    children: [new TextRun({ text, font: FONT, size: 20, color: INK, bold: !!opts.bold })],
  });
}

function bodyRuns(runs, opts = {}) {
  return new Paragraph({ spacing: { after: opts.after ?? 80 }, children: runs });
}

function h2(text) {
  return new Paragraph({
    spacing: { before: 220, after: 60 },
    border: { bottom: { style: BorderStyle.SINGLE, size: 4, color: TEAL, space: 2 } },
    children: [new TextRun({ text, font: FONT, size: 24, bold: true, color: TEAL })],
  });
}

function step(n, title, text) {
  return new Paragraph({
    spacing: { after: 100 },
    indent: { left: 120 },
    children: [
      new TextRun({ text: `${n}.  `, font: FONT, size: 20, bold: true, color: TEAL }),
      new TextRun({ text: `${title} — `, font: FONT, size: 20, bold: true, color: INK }),
      new TextRun({ text, font: FONT, size: 20, color: INK }),
    ],
  });
}

// Callout como tabla de 1 celda con fondo (no como regla — es un bloque de enfasis)
function callout(text) {
  return new Table({
    width: { size: 9360, type: WidthType.DXA },
    columnWidths: [9360],
    borders: {
      top: { style: BorderStyle.NONE, size: 0, color: "FFFFFF" },
      bottom: { style: BorderStyle.NONE, size: 0, color: "FFFFFF" },
      right: { style: BorderStyle.NONE, size: 0, color: "FFFFFF" },
      left: { style: BorderStyle.SINGLE, size: 24, color: TEAL },
      insideHorizontal: { style: BorderStyle.NONE, size: 0, color: "FFFFFF" },
      insideVertical: { style: BorderStyle.NONE, size: 0, color: "FFFFFF" },
    },
    rows: [
      new TableRow({
        children: [
          new TableCell({
            width: { size: 9360, type: WidthType.DXA },
            shading: { fill: CALLOUT_BG, type: ShadingType.CLEAR },
            margins: { top: 160, bottom: 160, left: 220, right: 220 },
            children: [
              new Paragraph({
                children: [new TextRun({ text, font: FONT, size: 23, bold: true, color: TEAL_DARK })],
              }),
            ],
          }),
        ],
      }),
    ],
  });
}

const doc = new Document({
  creator: "Contexto AI",
  title: "Encaje Financiero — Contexto AI para Linden",
  numbering: {
    config: [
      {
        reference: "bullets",
        levels: [{
          level: 0, format: LevelFormat.BULLET, text: "•",
          alignment: AlignmentType.LEFT,
          style: { paragraph: { indent: { left: 480, hanging: 260 } } },
        }],
      },
    ],
  },
  styles: {
    default: { document: { run: { font: FONT, size: 20, color: INK } } },
  },
  sections: [{
    properties: {
      page: {
        size: { width: 12240, height: 15840 }, // US Letter
        margin: { top: 1080, right: 1130, bottom: 900, left: 1130 },
      },
    },
    headers: {
      default: new Header({
        children: [
          new Paragraph({
            tabStops: [{ type: TabStopType.RIGHT, position: TabStopPosition.MAX }],
            border: { bottom: { style: BorderStyle.SINGLE, size: 10, color: TEAL, space: 6 } },
            children: [
              new TextRun({ text: "CONTEXTO AI", font: FONT, size: 22, bold: true, color: TEAL_DARK }),
              new TextRun({ text: "\tCada lugar tiene un aura", font: FONT, size: 17, italics: true, color: GRAY }),
            ],
          }),
        ],
      }),
    },
    footers: {
      default: new Footer({
        children: [
          new Paragraph({
            border: { top: { style: BorderStyle.SINGLE, size: 4, color: "CBD5E1", space: 4 } },
            tabStops: [{ type: TabStopType.RIGHT, position: TabStopPosition.MAX }],
            children: [
              new TextRun({ text: "Contexto AI  ·  contexxto.com", font: FONT, size: 15, color: GRAY }),
              new TextRun({ text: "\tDocumento para Linden  ·  Confidencial", font: FONT, size: 15, color: GRAY }),
            ],
          }),
        ],
      }),
    },
    children: [
      new Paragraph({
        spacing: { after: 20 },
        children: [new TextRun({ text: "Encaje Financiero", font: FONT, size: 40, bold: true, color: INK })],
      }),
      new Paragraph({
        spacing: { after: 40 },
        children: [new TextRun({
          text: "Sabe en 30 segundos qué puede pagar tu cliente — antes de la primera visita.",
          font: FONT, size: 22, italics: true, color: GRAY,
        })],
      }),
      new Paragraph({
        spacing: { after: 160 },
        children: [new TextRun({
          text: "Preparado para José Luis  ·  Linden  ·  Puebla  ·  Julio 2026",
          font: FONT, size: 17, color: GRAY,
        })],
      }),

      h2("El problema que te hace trabajar de más"),
      body("Los mejores esfuerzos del corredor se mueren en el financiamiento:"),
      bullet("Le muestras casas a clientes que al final no califican: visitas y semanas perdidas."),
      bullet("El trato se cae en la recta final, cuando el banco cambia las condiciones o no aprueba."),
      bullet("No sabes, desde el inicio, si tu cliente es sujeto de crédito ni por cuánto."),
      body("Trabajas mucho; cierras solo una parte de lo que trabajas.", { after: 100 }),

      h2("La solución: Encaje Financiero"),
      body("En 30 segundos, con datos mínimos (ingreso, deudas, ahorro) y sin consultar buró, Contexto le dice a tu cliente —y a ti— qué puede pagar y qué le aprobarían."),
      body("Junto al “% de encaje con tu vida” (caminabilidad, servicios, ruido y verde — cada uno con su fuente clara: medido, estimado por zona, o confirmado por el corredor) ahora aparece el “% de encaje financiero”: ¿esta casa entra en tu bolsillo? Le muestras al cliente casas que encajan con su vida y con su bolsillo desde el primer clic.", { after: 140 }),
      callout("Dejas de adivinar si tu cliente califica. Lo sabes antes de subir al auto."),
      new Paragraph({ spacing: { after: 100 }, children: [] }),

      h2("Cómo funciona (3 pasos)"),
      step(1, "Estimación instantánea", "sin buró ni datos sensibles. Con 3 datos: cuota estimada, cuánto crédito le alcanzaría y el enganche aproximado."),
      step(2, "Comparador neutral de financiamiento", "bancos e instituciones de vivienda (INFONAVIT, FOVISSSTE, Cofinavit) compiten por tu cliente, lado a lado: tasa, mensualidad y plazo. Contexto no empuja a ninguno."),
      step(3, "Pre-aprobación real", "cuando el cliente lo decide, los prestamistas responden con una oferta y él elige. Tú acompañas; nosotros orquestamos."),

      h2("Por qué genera confianza (y por eso cierra más)"),
      bullet("Neutral: Contexto no te vende la casa ni te presta el dinero; hace que los prestamistas compitan por tu cliente."),
      bullet("Honesto: siempre “estimación, no oferta”; ningún número aparece sin decir quién lo emite."),
      bullet("Justo: no usamos datos personales del cliente para decidir qué casas ve. Todos ven el mismo inventario."),
      body("Esa neutralidad es lo que hace que el cliente te crea. Y la confianza es la que cierra.", { after: 100 }),

      h2("Qué ganas tú y tu equipo en Linden"),
      bullet("Menos leads muertos: enfocas tu tiempo en compradores reales."),
      bullet("Cierres más rápidos y más seguros: menos tratos que se caen en el crédito."),
      bullet("Te ves como el asesor completo: resuelves la casa y el crédito en un solo lugar."),
      bullet("Herramienta gratuita dentro de Contexto, lista para tu equipo."),

      new Paragraph({
        spacing: { before: 200, after: 0 },
        border: { top: { style: BorderStyle.SINGLE, size: 4, color: "CBD5E1", space: 4 } },
        children: [],
      }),
      new Paragraph({
        spacing: { before: 140 },
        children: [
          new TextRun({ text: "Próximo paso: ", font: FONT, size: 20, bold: true, color: INK }),
          new TextRun({ text: "lo activamos en el piloto de Linden en Puebla. Cuando quieras, lo montamos con tu equipo esta semana.", font: FONT, size: 20, color: INK }),
        ],
      }),
    ],
  }],
});

Packer.toBuffer(doc).then((buffer) => {
  const out = "C:\\Users\\DETPC\\Desktop\\Contexto_Encaje_Financiero_Linden.docx";
  fs.writeFileSync(out, buffer);
  console.log("DOCX generado:", out);
});
