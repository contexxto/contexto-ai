// "ANTES DE DECIDIR" — las intenciones de entrada de la home.
//
// FUENTE ÚNICA. Los textos viven aquí y no incrustados en el Launcher porque cada uno
// rinde en cuatro lugares: el chip, la conversación que siembra, la página indexable
// (AEO) y el guion del canal. Repetirlos garantizaba que se desincronizaran.
//
// ── LA REGLA (docs/PLAN_Onboarding_Ecosistema.md §F3) ──────────────────────────────
// Procedimental o de NECESIDAD DECLARADA. Nunca evaluativo, nunca sobre quién eres.
//
//   ✅ "¿Podría vivir aquí un año?"      → el producto: el lugar, medido
//   ✅ "Con área verde cerca"            → una necesidad de la whitelist de encaje.py
//   ❌ "¿Qué barrio me conviene?"        → pide un veredicto sobre la persona
//   ❌ "Para mi familia"                 → estado familiar: clase protegida
//
// ── POR QUÉ CAMBIARON DOS CHIPS (hallazgo 2026-08-17) ─────────────────────────────
// El chip "Para mi familia" no era una etiqueta: INYECTABA en boca del usuario
// «Busco para mi familia: tranquilo, con colegios y parque cerca» — tres proxies de
// Fair Housing en una línea (estado familiar, colegios como filtro, "tranquilo" como
// eufemismo). Y el sistema los ponía ahí para después tratarlos como declaración de la
// persona, que es justo lo que `fair_housing.detectar_steering` está calibrado para NO
// marcar ("NO la cita del usuario"). El encuadre entraba lavado por la única puerta que
// el guardrail deja abierta a propósito.
//
// La garantía estructural aguantaba —`encaje.DIMENSIONES` no puede puntuar por
// "familia"— pero la conversación quedaba encuadrada ahí y el agente tenía toda la
// superficie de prosa para derivar.
//
// El arreglo NO es dejar de servir a quien tiene hijos: es dejar de nombrarla. La
// necesidad (área verde cerca, espacio) se declara igual y sí puntúa; la persona no se
// menciona. Igual con "Mi presupuesto", que pedía un veredicto («dime qué me conviene»)
// en vez de declarar un dato.

export const INTENCIONES = [
  { id: 'zona', label: 'Analiza mi zona', accion: 'geo' },
  { id: 'mapa', label: 'Explorar el mapa', accion: 'map' },
  {
    id: 'vivir-un-ano',
    label: '¿Podría vivir aquí un año?',
    accion: 'send',
    // No es un consejo: es el producto. La pregunta que el Place Graph responde con
    // dato medido y citado, y la que ningún portal puede contestar.
    intent: '¿Cómo es vivir un año en esta zona? Cuéntame con datos verificados: ruido, ' +
            'qué resuelvo a pie, transporte y áreas verdes.',
  },
  {
    id: 'transporte',
    label: 'Cerca del Metro',
    accion: 'send',
    intent: '🚇 Quiero vivir cerca del Metro o de mi trabajo',
  },
  {
    id: 'area-verde',
    label: 'Con área verde cerca',
    accion: 'send',
    // Reemplaza a "Para mi familia". Sirve a la misma persona sin nombrarla: `area_verde`
    // y `dormitorios` son necesidades de la whitelist y SÍ mueven el encaje.
    intent: 'Busco con área verde o parque cerca, y espacio suficiente. ' +
            '¿Qué hay y qué tan cerca queda?',
  },
  {
    id: 'presupuesto',
    label: 'Dentro de mi presupuesto',
    accion: 'send',
    // Antes decía «Dime qué me conviene para mi presupuesto» — pedía un veredicto.
    // Ahora declara el dato y pide lo que el motor sí puede responder.
    intent: '💰 Quiero ver qué entra en mi presupuesto. Te digo mi tope y me muestras ' +
            'lo que sí calza, sin pasarte.',
  },
  { id: 'corredor', label: 'Soy corredor', accion: 'broker' },
  {
    id: 'aura',
    label: 'El aura de un lugar',
    accion: 'send',
    intent: '¿Qué es el aura de un lugar y cómo la lees en Contexto?',
  },
]

// Filas escalonadas 2-2-2-2 (el patrón visual del Launcher).
export const FILAS = [[0, 1], [2, 3], [4, 5], [6, 7]]
