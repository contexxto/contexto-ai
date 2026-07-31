-- Baseline del embudo de intención — el "ritual cero" de docs/RITUALES_DE_DATOS_CONTEXTO.md
--
-- Responde: ¿cuántas intenciones capturamos, cuántas pidieron corredor, y cuántas ATENDIÓ
-- un humano dentro de 24h? Esa última es la métrica de activación.
--
-- Uso:  psql "$DATABASE_URL" -f scripts/baseline_intencion.sql
--
-- DISCIPLINA (heredada de app/lift.py, que ya la aplica bien): con N bajo NO se reportan
-- ratios, solo conteos. Un % sobre N=4 miente porque *parece* dato. Por eso cada bloque
-- devuelve conteos crudos; el ratio se calcula a mano cuando N >= 5 (lift.UMBRAL_N).
--
-- Tablas: intencion_sesion + intencion_evento (migration 018), handoff_mensaje (DDL lazy
-- en app/routers/chat.py:1150 — puede no existir todavía; el bloque 4 lo verifica).

\echo '== 1. Embudo por estado (foto actual, una fila por sesión) =='
SELECT estado,
       nivel,
       count(*)                                AS sesiones,
       count(*) FILTER (WHERE handoff_sugerido) AS con_handoff_sugerido,
       round(avg(turnos), 1)                   AS turnos_prom
FROM intencion_sesion
GROUP BY estado, nivel
ORDER BY sesiones DESC;

\echo ''
\echo '== 2. Volumen por semana (¿ya hay N suficiente para leer ratios?) =='
SELECT date_trunc('week', primer_visto)::date AS semana,
       count(*)                                AS sesiones_nuevas,
       count(*) FILTER (WHERE handoff_sugerido) AS handoffs_sugeridos
FROM intencion_sesion
GROUP BY 1
ORDER BY 1 DESC
LIMIT 12;

\echo ''
\echo '== 3. Transiciones del embudo (serie del lift, append-only) =='
SELECT estado,
       count(*)                     AS transiciones,
       count(DISTINCT session_id)   AS sesiones_distintas,
       min(creado_en)::date         AS desde,
       max(creado_en)::date         AS hasta
FROM intencion_evento
GROUP BY estado
ORDER BY transiciones DESC;

\echo ''
\echo '== 4. LA METRICA: intencion atendida (primer mensaje del lead -> primera respuesta del corredor) =='
-- Si handoff_mensaje no existe todavia, este bloque avisa en vez de reventar.
DO $$
BEGIN
  IF to_regclass('public.handoff_mensaje') IS NULL THEN
    RAISE NOTICE 'handoff_mensaje NO existe todavia: nadie ha abierto un handoff. Baseline = 0.';
  END IF;
END $$;

WITH primer_lead AS (
    SELECT session_id, min(creado_en) AS t_lead
    FROM handoff_mensaje
    WHERE autor = 'lead'
    GROUP BY session_id
),
primer_corredor AS (
    SELECT session_id, min(creado_en) AS t_corredor
    FROM handoff_mensaje
    WHERE autor = 'corredor'
    GROUP BY session_id
),
pareado AS (
    SELECT l.session_id,
           l.t_lead,
           c.t_corredor,
           c.t_corredor - l.t_lead AS espera
    FROM primer_lead l
    LEFT JOIN primer_corredor c USING (session_id)
)
SELECT count(*)                                                          AS leads_que_escribieron,
       count(t_corredor)                                                 AS atendidos_alguna_vez,
       count(*) FILTER (WHERE espera <= interval '24 hours')             AS atendidos_menos_24h,
       count(*) FILTER (WHERE t_corredor IS NULL)                        AS nunca_atendidos,
       -- percentiles solo informativos; con N bajo son anecdota, no estadistica
       percentile_disc(0.5) WITHIN GROUP (ORDER BY espera)               AS espera_mediana,
       max(espera)                                                       AS espera_peor
FROM pareado;

\echo ''
\echo '== 5. Cola viva: leads esperando AHORA (esto se mira en el ritual diario) =='
WITH primer_lead AS (
    SELECT session_id, min(creado_en) AS t_lead
    FROM handoff_mensaje WHERE autor = 'lead' GROUP BY session_id
),
primer_corredor AS (
    SELECT session_id, min(creado_en) AS t_corredor
    FROM handoff_mensaje WHERE autor = 'corredor' GROUP BY session_id
)
SELECT l.session_id,
       l.t_lead,
       now() - l.t_lead AS esperando_hace,
       s.estado,
       s.nivel,
       s.score
FROM primer_lead l
LEFT JOIN primer_corredor c USING (session_id)
LEFT JOIN intencion_sesion s ON s.session_id = l.session_id
WHERE c.t_corredor IS NULL
ORDER BY l.t_lead ASC;

\echo ''
\echo '== 6. Salud de la instrumentacion (ver docs/AUDITORIA_Fallos_Silenciosos_2026-07-31.md) =='
-- Si esto cae a cero con oferta activa, NO es poca demanda: es que registrar_intencion
-- esta fallando en silencio (chat.py:1313 se traga la excepcion). Cero = roto hasta probar
-- lo contrario.
SELECT max(actualizado_en)               AS ultima_escritura_intencion,
       now() - max(actualizado_en)       AS hace,
       count(*) FILTER (WHERE actualizado_en > now() - interval '24 hours') AS escrituras_24h
FROM intencion_sesion;
