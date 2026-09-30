-- ============================================================
-- Migration 040: la FUENTE del contexto de lugar deja de estar abierta a PostgREST
-- (PLACE-SOURCE-PERIMETER)
--
--   QUÉ HACE: activa RLS y revoca privilegios sobre las dos tablas de las que sale el contexto de
--   lugar —`public.pois_propios` (la capa propia) y `public.entorno_curacion` (la curación del
--   corredor)—, sobre sus secuencias y sobre la vista que las une, `public.pois_vivos`, a la que
--   además pone `security_invoker`. Cero DDL de estructura. Cero filas leídas o tocadas.
--
--   POR QUÉ, MEDIDO EN PRODUCCIÓN el 2026-09-30 (PostgreSQL 17.6, solo catálogos, `BEGIN READ
--   ONLY`; informe `RESULTADO_PLACE_SOURCE_PERIMETER_0.1.md`):
--
--     · dueño `postgres` de las dos tablas, sus dos secuencias y la vista (el rol del backend:
--       NOSUPERUSER, BYPASSRLS; el backend y el refresco semanal de POIs conectan con él);
--     · RLS desactivado en las dos tablas, cero políticas, sin publicación de replicación, sin
--       funciones ni triggers que las toquen; la única dependiente es `pois_vivos`;
--     · `anon`, `authenticated` y `service_role` con los 8 privilegios de tabla (`arwdDxtm`) sobre
--       las dos tablas y la vista, y `USAGE, SELECT, UPDATE` sobre las dos secuencias;
--     · ningún consumidor legítimo por PostgREST: el frontend solo usa auth y el bucket
--       `evidencias`; el backend no usa el cliente de Supabase; en `pg_stat_statements` (desde el
--       2026-06-06, sin desalojos) `service_role` no las tocó nunca y `anon`, 2 veces: la sonda de
--       la auditoría de perímetro del 2026-09-23.
--
--   Con la clave pública bastaba un INSERT o un UPDATE vía PostgREST para inventar, mover o
--   renombrar lugares de la capa propia, o una fila `cerrado` en `entorno_curacion` para que
--   `pois_vivos` ocultara un POI a TODOS los inmuebles de la ciudad. De esas dos tablas sale la
--   procedencia del contexto (PLACE-LEGACY-CONTEXT-BACKFILL, 041): no puede darse por demostrada
--   mientras la fuente sea escribible desde fuera.
--
--   MISMO CONTRATO QUE LA 039 (y la 037). `ENABLE` sin `FORCE`, cero políticas, `REVOKE ALL
--   PRIVILEGES` a `PUBLIC` y a los tres roles, transacción única, `lock_timeout`, tolerancia a roles
--   inexistentes (el PostgreSQL del CI no los tiene) y verificación fail-closed dentro, que mira el
--   ACL de tabla, el de COLUMNA y el privilegio EFECTIVO.
--
--   LO QUE AÑADE SOBRE LA 039 (porque aquí hay más que una tabla sola):
--     1. LAS SECUENCIAS. Con `UPDATE` sobre una secuencia, `setval` la mueve y el siguiente
--        INSERT del backend choca con la clave primaria. Se localizan por `pg_depend` (las que
--        dependen de las dos tablas), no por nombre.
--     2. LA VISTA `pois_vivos`, que es la ruta de lectura del producto (propia.py). Se creó sin
--        `security_invoker`: evalúa con la identidad de su DUEÑO y sortea el RLS de sus tablas
--        base, así que cerrar solo las tablas sería un CIERRE FALSO (`GET /rest/v1/pois_vivos`
--        seguiría devolviendo la capa entera). Se le revoca todo y se le pone
--        `security_invoker = true`: si alguien le devuelve SELECT a un rol público, ese rol choca
--        con las tablas base (sin privilegio, y con RLS sin políticas). Es la dependiente
--        ESPERADA; cualquier otra vista, función, publicación o trigger sobre el perímetro ABORTA.
--     3. `service_role` se revoca con evidencia, no por costumbre: ningún flujo del repo ni de
--        `pg_stat_statements` lo usa sobre estas relaciones.
--
--   POR QUÉ `ENABLE` Y NO `FORCE`: las relaciones son de `postgres`, el rol del backend y del
--   refresco de POIs, y `ENABLE` no sujeta al dueño; además ese rol tiene `rolbypassrls`. La
--   lectura de `pois_vivos` (con `security_invoker`, se evalúa con el dueño), el UPSERT del
--   refresco, el alta y la baja de curaciones y el DDL en runtime (`ensure_curacion_table`) los
--   ejecuta el dueño y siguen funcionando.
--
--   QUIÉN LA APLICA: el DUEÑO de las cinco relaciones (en producción, `postgres`). La primera
--   compuerta lo exige: si quien aplica no es el dueño de alguna, aborta.
--
--   QUÉ NO TOCA: ninguna otra relación —ni `activos_inmutables` ni el respaldo
--   `pois_propios_backup_20260727`—, ninguna fila, ninguna columna, ninguna política.
--
--   Idempotente, transaccional y reversible (ver ROLLBACK al final).
-- ============================================================

BEGIN;

-- `ENABLE ROW LEVEL SECURITY` pide un ACCESS EXCLUSIVE. Las tablas las lee cada consulta de
-- entorno; el tope evita que la migración quede en cola bloqueando a quien venga detrás.
SET LOCAL lock_timeout = '3s';

-- ── 0 · COMPROBACIONES PREVIAS, FAIL-CLOSED ─────────────────────────────────────────
DO $$
DECLARE
    rel   TEXT;
    lista TEXT;
    n     INTEGER;
BEGIN
    FOREACH rel IN ARRAY ARRAY['public.pois_propios', 'public.entorno_curacion', 'public.pois_vivos'] LOOP
        IF to_regclass(rel) IS NULL THEN
            RAISE EXCEPTION '040 ABORTA: no existe %. ¿Base equivocada?', rel;
        END IF;
    END LOOP;

    IF (SELECT relkind FROM pg_class WHERE oid = 'public.pois_vivos'::regclass) <> 'v' THEN
        RAISE EXCEPTION '040 ABORTA: public.pois_vivos existe pero no es una vista';
    END IF;

    -- El dueño de las dos tablas, de la vista y de cada secuencia de las tablas es quien aplica.
    SELECT string_agg(format('%s (dueño %s)', c.oid::regclass, pg_get_userbyid(c.relowner)), ', ')
      INTO lista
      FROM pg_class c
     WHERE (c.oid IN ('public.pois_propios'::regclass, 'public.entorno_curacion'::regclass,
                      'public.pois_vivos'::regclass)
            OR c.oid IN (SELECT d.objid
                           FROM pg_depend d JOIN pg_class s ON s.oid = d.objid AND s.relkind = 'S'
                          WHERE d.classid = 'pg_class'::regclass
                            AND d.refobjid IN ('public.pois_propios'::regclass,
                                               'public.entorno_curacion'::regclass)))
       AND pg_get_userbyid(c.relowner) <> current_user;
    IF lista IS NOT NULL THEN
        RAISE EXCEPTION
            '040 ABORTA: el dueño no es quien aplica (%): %. Usa el rol propietario (en producción, `postgres`).',
            current_user, lista;
    END IF;

    SELECT count(*) INTO n
      FROM pg_policies WHERE schemaname = 'public' AND tablename IN ('pois_propios', 'entorno_curacion');
    IF n > 0 THEN
        RAISE EXCEPTION '040 ABORTA: ya existen % política(s) en el perímetro. Revísalas antes.', n;
    END IF;

    SELECT string_agg(format('%s:%s', pubname, tablename), ', ') INTO lista
      FROM pg_publication_tables
     WHERE schemaname = 'public' AND tablename IN ('pois_propios', 'entorno_curacion', 'pois_vivos');
    IF lista IS NOT NULL THEN
        RAISE EXCEPTION '040 ABORTA: el perímetro está en una publicación de replicación (%). '
                        'Caracteriza el consumidor.', lista;
    END IF;

    -- `pois_vivos` es la dependiente esperada. Cualquier OTRA vista (de las tablas o de la propia
    -- `pois_vivos`) seguiría sirviendo la capa con los privilegios de su dueño.
    SELECT string_agg(DISTINCT v.oid::regclass::text, ', ') INTO lista
      FROM pg_depend d
      JOIN pg_rewrite rw ON rw.oid = d.objid
      JOIN pg_class v ON v.oid = rw.ev_class
     WHERE d.classid = 'pg_rewrite'::regclass
       AND d.refobjid IN ('public.pois_propios'::regclass, 'public.entorno_curacion'::regclass,
                          'public.pois_vivos'::regclass)
       AND v.oid <> d.refobjid
       AND v.oid <> 'public.pois_vivos'::regclass;
    IF lista IS NOT NULL THEN
        RAISE EXCEPTION '040 ABORTA: hay vistas que dependen del perímetro además de pois_vivos (%). '
                        'Sin caracterizarlas, el cierre sería falso.', lista;
    END IF;

    SELECT string_agg(format('%s.%s', ns.nspname, p.proname), ', ') INTO lista
      FROM pg_proc p JOIN pg_namespace ns ON ns.oid = p.pronamespace
     WHERE ns.nspname NOT IN ('pg_catalog', 'information_schema')
       AND (p.prosrc ILIKE '%pois_propios%' OR p.prosrc ILIKE '%entorno_curacion%'
            OR p.prosrc ILIKE '%pois_vivos%');
    IF lista IS NOT NULL THEN
        RAISE EXCEPTION '040 ABORTA: hay funciones que mencionan el perímetro (%). Caracterízalas antes: '
                        'una RPC SECURITY DEFINER lo dejaría alcanzable.', lista;
    END IF;

    SELECT string_agg(format('%s.%s', t.tgrelid::regclass, t.tgname), ', ') INTO lista
      FROM pg_trigger t
     WHERE NOT t.tgisinternal
       AND t.tgrelid IN ('public.pois_propios'::regclass, 'public.entorno_curacion'::regclass,
                         'public.pois_vivos'::regclass);
    IF lista IS NOT NULL THEN
        RAISE EXCEPTION '040 ABORTA: hay triggers en el perímetro (%). Caracterízalos antes.', lista;
    END IF;
END $$;

-- ── 1 · RLS ─────────────────────────────────────────────────────────────────────────
ALTER TABLE public.pois_propios ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.entorno_curacion ENABLE ROW LEVEL SECURITY;

-- ── 2 · LA VISTA SE EVALÚA CON QUIEN PREGUNTA ───────────────────────────────────────
ALTER VIEW public.pois_vivos SET (security_invoker = true);

-- ── 3 · REVOKE ──────────────────────────────────────────────────────────────────────
--
-- `REVOKE ALL PRIVILEGES` y no una lista de verbos: producción es PostgreSQL 17.6 (MAINTAIN
-- existe, y lo tienen los tres roles) y el CI es 15. `ALL` vale en las dos.
--
-- `PUBLIC` siempre existe: sin guarda. Los tres roles, con guarda de existencia: un `REVOKE`
-- contra un rol inexistente es un ERROR que, dentro de esta transacción, se llevaría por delante
-- el `ENABLE ROW LEVEL SECURITY` de arriba.
REVOKE ALL PRIVILEGES ON TABLE public.pois_propios, public.entorno_curacion, public.pois_vivos FROM PUBLIC;

DO $$
DECLARE
    rol TEXT;
    seq REGCLASS;
BEGIN
    FOR seq IN SELECT d.objid::regclass
                 FROM pg_depend d JOIN pg_class s ON s.oid = d.objid AND s.relkind = 'S'
                WHERE d.classid = 'pg_class'::regclass
                  AND d.refobjid IN ('public.pois_propios'::regclass, 'public.entorno_curacion'::regclass)
    LOOP
        EXECUTE format('REVOKE ALL PRIVILEGES ON SEQUENCE %s FROM PUBLIC', seq);
    END LOOP;

    FOREACH rol IN ARRAY ARRAY['anon', 'authenticated', 'service_role'] LOOP
        IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = rol) THEN
            RAISE NOTICE '040: el rol % no existe aquí; nada que revocar', rol;
            CONTINUE;
        END IF;
        EXECUTE format('REVOKE ALL PRIVILEGES ON TABLE public.pois_propios, public.entorno_curacion, '
                       'public.pois_vivos FROM %I', rol);
        FOR seq IN SELECT d.objid::regclass
                     FROM pg_depend d JOIN pg_class s ON s.oid = d.objid AND s.relkind = 'S'
                    WHERE d.classid = 'pg_class'::regclass
                      AND d.refobjid IN ('public.pois_propios'::regclass, 'public.entorno_curacion'::regclass)
        LOOP
            EXECUTE format('REVOKE ALL PRIVILEGES ON SEQUENCE %s FROM %I', seq, rol);
        END LOOP;
        RAISE NOTICE '040: privilegios revocados a % (dos tablas, la vista y sus secuencias)', rol;
    END LOOP;
END $$;

-- ── 4 · VERIFICACIÓN FAIL-CLOSED (mide el efecto; no lo declara) ───────────────────
DO $$
DECLARE
    tabla   TEXT;
    rls     BOOLEAN;
    force   BOOLEAN;
    pols    INTEGER;
    quedan  TEXT;
    cols    TEXT;
    rol     TEXT;
    priv    TEXT;
    rel     TEXT;
    seq     REGCLASS;
    nsecs   INTEGER := 0;
BEGIN
    FOREACH tabla IN ARRAY ARRAY['pois_propios', 'entorno_curacion'] LOOP
        SELECT c.relrowsecurity, c.relforcerowsecurity INTO rls, force
          FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
         WHERE n.nspname = 'public' AND c.relname = tabla;
        IF NOT rls THEN
            RAISE EXCEPTION '040 FALLA: RLS no quedó activado en %', tabla;
        END IF;
        IF force THEN
            RAISE EXCEPTION '040 FALLA: apareció FORCE en %, y esta unidad no lo autoriza', tabla;
        END IF;
    END LOOP;

    SELECT count(*) INTO pols
      FROM pg_policies WHERE schemaname = 'public' AND tablename IN ('pois_propios', 'entorno_curacion');
    IF pols > 0 THEN
        RAISE EXCEPTION '040 FALLA: aparecieron % política(s); se esperaban 0', pols;
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_class
                    WHERE oid = 'public.pois_vivos'::regclass
                      AND 'security_invoker=true' = ANY (coalesce(reloptions, '{}'))) THEN
        RAISE EXCEPTION '040 FALLA: pois_vivos no quedó con security_invoker = true';
    END IF;

    -- Lo que REALMENTE hay en el ACL de las tablas, la vista y las secuencias, incluido `PUBLIC`.
    SELECT string_agg(format('%s:%s(%s)', x.rel, x.quien, x.priv), ', ') INTO quedan
      FROM (
        SELECT c.oid::regclass::text AS rel,
               CASE WHEN a.grantee = 0 THEN 'PUBLIC' ELSE pg_get_userbyid(a.grantee) END AS quien,
               a.privilege_type AS priv
          FROM pg_class c, aclexplode(c.relacl) a
         WHERE c.oid IN ('public.pois_propios'::regclass, 'public.entorno_curacion'::regclass,
                         'public.pois_vivos'::regclass)
            OR c.oid IN (SELECT d.objid
                           FROM pg_depend d JOIN pg_class s ON s.oid = d.objid AND s.relkind = 'S'
                          WHERE d.classid = 'pg_class'::regclass
                            AND d.refobjid IN ('public.pois_propios'::regclass,
                                               'public.entorno_curacion'::regclass))
      ) x
     WHERE x.quien IN ('anon', 'authenticated', 'service_role', 'PUBLIC');
    IF quedan IS NOT NULL THEN
        RAISE EXCEPTION '040 FALLA: quedan privilegios en pie -> %', quedan;
    END IF;

    -- Y el ACL de CADA COLUMNA: un GRANT por columna sobrevive al REVOKE de tabla.
    SELECT string_agg(format('%s.%s:%s(%s)', x.rel, x.col, x.quien, x.priv), ', ') INTO cols
      FROM (
        SELECT att.attrelid::regclass::text AS rel, att.attname AS col,
               CASE WHEN a.grantee = 0 THEN 'PUBLIC' ELSE pg_get_userbyid(a.grantee) END AS quien,
               a.privilege_type AS priv
          FROM pg_attribute att, aclexplode(att.attacl) a
         WHERE att.attrelid IN ('public.pois_propios'::regclass, 'public.entorno_curacion'::regclass,
                                'public.pois_vivos'::regclass)
           AND att.attnum > 0 AND NOT att.attisdropped
      ) x
     WHERE x.quien IN ('anon', 'authenticated', 'service_role', 'PUBLIC');
    IF cols IS NOT NULL THEN
        RAISE EXCEPTION '040 FALLA: quedan privilegios de columna -> %', cols;
    END IF;

    -- El privilegio EFECTIVO de cada rol, verbo a verbo (cubre herencias que el ACL no enseña).
    FOREACH rol IN ARRAY ARRAY['anon', 'authenticated', 'service_role'] LOOP
        CONTINUE WHEN NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = rol);
        FOREACH rel IN ARRAY ARRAY['public.pois_propios', 'public.entorno_curacion', 'public.pois_vivos'] LOOP
            FOREACH priv IN ARRAY ARRAY['SELECT', 'INSERT', 'UPDATE', 'DELETE', 'TRUNCATE',
                                        'REFERENCES', 'TRIGGER'] LOOP
                IF has_table_privilege(rol, rel, priv) THEN
                    RAISE EXCEPTION '040 FALLA: % conserva % efectivo sobre %', rol, priv, rel;
                END IF;
            END LOOP;
        END LOOP;
        FOR seq IN SELECT d.objid::regclass
                     FROM pg_depend d JOIN pg_class s ON s.oid = d.objid AND s.relkind = 'S'
                    WHERE d.classid = 'pg_class'::regclass
                      AND d.refobjid IN ('public.pois_propios'::regclass, 'public.entorno_curacion'::regclass)
        LOOP
            FOREACH priv IN ARRAY ARRAY['USAGE', 'SELECT', 'UPDATE'] LOOP
                IF has_sequence_privilege(rol, seq, priv) THEN
                    RAISE EXCEPTION '040 FALLA: % conserva % efectivo sobre la secuencia %', rol, priv, seq;
                END IF;
            END LOOP;
        END LOOP;
    END LOOP;

    -- El dueño (quien aplica: el backend en producción) conserva el acceso que necesita.
    FOREACH rel IN ARRAY ARRAY['public.pois_propios', 'public.entorno_curacion'] LOOP
        FOREACH priv IN ARRAY ARRAY['SELECT', 'INSERT', 'UPDATE', 'DELETE'] LOOP
            IF NOT has_table_privilege(current_user, rel, priv) THEN
                RAISE EXCEPTION '040 FALLA: el dueño % perdió % sobre %', current_user, priv, rel;
            END IF;
        END LOOP;
    END LOOP;
    IF NOT has_table_privilege(current_user, 'public.pois_vivos', 'SELECT') THEN
        RAISE EXCEPTION '040 FALLA: el dueño % perdió SELECT sobre pois_vivos', current_user;
    END IF;
    FOR seq IN SELECT d.objid::regclass
                 FROM pg_depend d JOIN pg_class s ON s.oid = d.objid AND s.relkind = 'S'
                WHERE d.classid = 'pg_class'::regclass
                  AND d.refobjid IN ('public.pois_propios'::regclass, 'public.entorno_curacion'::regclass)
    LOOP
        nsecs := nsecs + 1;
        IF NOT has_sequence_privilege(current_user, seq, 'USAGE') THEN
            RAISE EXCEPTION '040 FALLA: el dueño % perdió USAGE sobre la secuencia %', current_user, seq;
        END IF;
    END LOOP;

    RAISE NOTICE '040 OK: RLS activado en 2 tablas, sin FORCE, 0 políticas, pois_vivos con security_invoker, '
                 '0 privilegios externos (tablas, vista, % secuencia(s) y columnas), dueño intacto', nsecs;
END $$;

-- Verificación legible (debe devolver, por tabla: true, false, 0; y la vista con security_invoker).
SELECT c.relname AS relacion,
       c.relrowsecurity AS con_rls,
       c.relforcerowsecurity AS con_force,
       (SELECT count(*) FROM pg_policies p
         WHERE p.schemaname = 'public' AND p.tablename = c.relname) AS politicas,
       c.reloptions AS opciones
  FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
 WHERE n.nspname = 'public' AND c.relname IN ('pois_propios', 'entorno_curacion', 'pois_vivos')
 ORDER BY c.relname;

COMMIT;

-- ── ROLLBACK ────────────────────────────────────────────────────────────────────────
--
-- Deshace exactamente lo de arriba y devuelve la exposición medida el 2026-09-30. Sólo con
-- autorización explícita: reabre la escritura pública de la fuente del contexto de lugar.
--
--   BEGIN;
--   ALTER TABLE public.pois_propios DISABLE ROW LEVEL SECURITY;
--   ALTER TABLE public.entorno_curacion DISABLE ROW LEVEL SECURITY;
--   ALTER VIEW public.pois_vivos RESET (security_invoker);
--   GRANT ALL PRIVILEGES ON TABLE public.pois_propios, public.entorno_curacion, public.pois_vivos
--         TO anon, authenticated, service_role;
--   GRANT ALL PRIVILEGES ON SEQUENCE public.pois_propios_id_seq, public.entorno_curacion_id_seq
--         TO anon, authenticated, service_role;
--   COMMIT;
