# -*- coding: utf-8 -*-
"""Genera el PDF de una pagina (externo, para socio) del feature Encaje Financiero
de Contexto AI, dirigido a Jose Luis de Linden (Puebla, Mexico)."""
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import cm
from reportlab.lib.colors import HexColor, white
from reportlab.lib.enums import TA_LEFT
from reportlab.platypus import (BaseDocTemplate, PageTemplate, Frame, Paragraph,
                                Spacer, Table, TableStyle, ListFlowable, ListItem,
                                HRFlowable)
from reportlab.lib.styles import ParagraphStyle

OUT = r"C:\Users\DETPC\Desktop\Contexto_Encaje_Financiero_Linden.pdf"

TEAL      = HexColor("#0E8C7F")
TEAL_DARK = HexColor("#0B6F65")
INK       = HexColor("#1F2937")
GRAY      = HexColor("#4B5563")
CALLOUT   = HexColor("#E8F6F4")

PW, PH = letter

# ---- estilos ----
st_title = ParagraphStyle("title", fontName="Helvetica-Bold", fontSize=21, textColor=INK, leading=24, spaceAfter=1)
st_sub   = ParagraphStyle("sub", fontName="Helvetica-Oblique", fontSize=11.5, textColor=GRAY, leading=14.5, spaceAfter=4)
st_meta  = ParagraphStyle("meta", fontName="Helvetica", fontSize=9, textColor=GRAY, leading=12, spaceAfter=1)
st_h2    = ParagraphStyle("h2", fontName="Helvetica-Bold", fontSize=12, textColor=TEAL, leading=14, spaceBefore=8.5, spaceAfter=2)
st_body  = ParagraphStyle("body", fontName="Helvetica", fontSize=9.7, textColor=INK, leading=13, spaceAfter=2.5, alignment=TA_LEFT)
st_bull  = ParagraphStyle("bull", fontName="Helvetica", fontSize=9.7, textColor=INK, leading=13,
                          leftIndent=15, bulletIndent=3, spaceAfter=2)
st_call  = ParagraphStyle("call", fontName="Helvetica-Bold", fontSize=11.5, textColor=TEAL_DARK, leading=14.5)
st_step  = ParagraphStyle("step", fontName="Helvetica", fontSize=9.7, textColor=INK, leading=13, spaceAfter=2.5)


def bullets(items):
    return [Paragraph(t, st_bull, bulletText="•") for t in items]


def callout(text):
    p = Paragraph(text, st_call)
    t = Table([[p]], colWidths=[PW - 4.2 * cm])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), CALLOUT),
        ("LINEBEFORE", (0, 0), (0, -1), 3, TEAL),
        ("TOPPADDING", (0, 0), (-1, -1), 9),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 9),
        ("LEFTPADDING", (0, 0), (-1, -1), 12),
        ("RIGHTPADDING", (0, 0), (-1, -1), 12),
    ]))
    return t


def step(n, title, body):
    p = Paragraph('<font color="#0E8C7F"><b>%d.</b></font>  <b>%s</b> &mdash; %s' % (n, title, body), st_step)
    return p


def masthead(c, doc):
    # banda superior teal a sangre
    c.setFillColor(TEAL)
    c.rect(0, PH - 2.15 * cm, PW, 2.15 * cm, fill=1, stroke=0)
    c.setFillColor(white)
    c.setFont("Helvetica-Bold", 15)
    c.drawString(2.1 * cm, PH - 1.35 * cm, "CONTEXTO AI")
    c.setFont("Helvetica", 9.5)
    c.setFillColor(HexColor("#CFF0EB"))
    c.drawRightString(PW - 2.1 * cm, PH - 1.32 * cm, "Cada lugar tiene un aura")
    footer(c, doc)


def footer(c, doc):
    c.setFillColor(GRAY)
    c.setFont("Helvetica", 8)
    c.drawString(2.1 * cm, 1.15 * cm, "Contexto AI  ·  contexxto.com")
    c.drawRightString(PW - 2.1 * cm, 1.15 * cm, "Documento para Linden  ·  Confidencial")
    c.setStrokeColor(HexColor("#E5E7EB"))
    c.setLineWidth(0.5)
    c.line(2.1 * cm, 1.45 * cm, PW - 2.1 * cm, 1.45 * cm)


doc = BaseDocTemplate(OUT, pagesize=letter,
                      leftMargin=2.0 * cm, rightMargin=2.0 * cm,
                      topMargin=2.5 * cm, bottomMargin=1.7 * cm,
                      title="Encaje Financiero - Contexto AI para Linden",
                      author="Contexto AI")
frame = Frame(doc.leftMargin, doc.bottomMargin,
              PW - doc.leftMargin - doc.rightMargin,
              PH - doc.topMargin - doc.bottomMargin, id="main")
doc.addPageTemplates([PageTemplate(id="first", frames=[frame], onPage=masthead)])

S = []
S.append(Paragraph("Encaje Financiero", st_title))
S.append(Paragraph("Sabe en 30 segundos qué puede pagar tu cliente &mdash; antes de la primera visita.", st_sub))
S.append(Paragraph("Preparado para <b>José Luis</b> &nbsp;·&nbsp; Linden &nbsp;·&nbsp; Puebla &nbsp;·&nbsp; Julio 2026", st_meta))
S.append(HRFlowable(width="100%", thickness=1.2, color=TEAL, spaceBefore=6, spaceAfter=2))

S.append(Paragraph("El problema que te hace trabajar de más", st_h2))
S.append(Paragraph("Los mejores esfuerzos del corredor se mueren en el financiamiento:", st_body))
S.extend(bullets([
    "Le muestras casas a clientes que al final <b>no califican</b>: visitas y semanas perdidas.",
    "El trato <b>se cae en la recta final</b>, cuando el banco cambia las condiciones o no aprueba.",
    "No sabes, desde el inicio, si tu cliente es sujeto de crédito ni por cuánto.",
]))
S.append(Paragraph("Trabajas mucho; cierras solo una parte de lo que trabajas.", st_body))

S.append(Paragraph("La solución: Encaje Financiero", st_h2))
S.append(Paragraph("En 30 segundos, con datos mínimos (ingreso, deudas, ahorro) y <b>sin consultar buró</b>, "
                   "Contexto le dice a tu cliente &mdash;y a ti&mdash; qué puede pagar y qué le aprobarían.", st_body))
S.append(Paragraph("Junto al <b>“% de encaje con tu vida”</b> (caminabilidad, servicios, ruido y verde &mdash; cada uno "
                   "con su fuente clara: medido, estimado por zona, o confirmado por el corredor) ahora aparece el "
                   "<b>“% de encaje financiero”</b>: ¿esta casa entra en tu bolsillo? Le muestras al cliente casas que "
                   "encajan con su vida <b>y</b> con su bolsillo desde el primer clic.", st_body))
S.append(Spacer(1, 4))
S.append(callout("Dejas de adivinar si tu cliente califica. Lo sabes antes de subir al auto."))

S.append(Paragraph("Cómo funciona (3 pasos)", st_h2))
S.append(step(1, "Estimación instantánea", "sin buró ni datos sensibles. Con 3 datos: cuota estimada, cuánto crédito le alcanzaría y el enganche aproximado."))
S.append(step(2, "Comparador neutral de financiamiento", "bancos e instituciones de vivienda (INFONAVIT, FOVISSSTE, Cofinavit) compiten por tu cliente, lado a lado: tasa, mensualidad y plazo. Contexto no empuja a ninguno."))
S.append(step(3, "Pre-aprobación real", "cuando el cliente lo decide, los prestamistas responden con una oferta y él elige. Tú acompañas; nosotros orquestamos."))

S.append(Paragraph("Por qué genera confianza (y por eso cierra más)", st_h2))
S.extend(bullets([
    "<b>Neutral:</b> Contexto no te vende la casa ni te presta el dinero; hace que los prestamistas <b>compitan por tu cliente</b>.",
    "<b>Honesto:</b> siempre “estimación, no oferta”; ningún número aparece sin decir quién lo emite.",
    "<b>Justo:</b> no usamos datos personales del cliente para decidir qué casas ve. Todos ven el mismo inventario.",
]))
S.append(Paragraph("Esa neutralidad es lo que hace que el cliente te crea. Y la confianza es la que cierra.", st_body))

S.append(Paragraph("Qué ganas tú y tu equipo en Linden", st_h2))
S.extend(bullets([
    "<b>Menos leads muertos:</b> enfocas tu tiempo en compradores reales.",
    "<b>Cierres más rápidos y más seguros:</b> menos tratos que se caen en el crédito.",
    "<b>Te ves como el asesor completo:</b> resuelves la casa y el crédito en un solo lugar.",
    "<b>Herramienta gratuita</b> dentro de Contexto, lista para tu equipo.",
]))

S.append(Spacer(1, 6))
S.append(HRFlowable(width="100%", thickness=0.8, color=HexColor("#CBD5E1"), spaceBefore=2, spaceAfter=6))
S.append(Paragraph("<b>Próximo paso:</b> lo activamos en el piloto de Linden en Puebla. Cuando quieras, lo montamos con tu equipo esta semana.", st_body))

doc.build(S)
print("PDF generado:", OUT)
