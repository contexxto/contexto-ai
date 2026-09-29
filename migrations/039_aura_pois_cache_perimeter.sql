-- ============================================================
-- Migration 039: `aura_pois_cache` deja de estar abierta a PostgREST (AURA-CACHE-PERIMETER)
--
--   QUÉ HACE: activa RLS y revoca privilegios sobre UNA tabla, `public.aura_pois_cache`. Nada más.
--   Cero DDL de estructura. Cero filas leídas o tocadas.
--
--   POR QUÉ, MEDIDO EN PRODUCCIÓN el 2026-09-29 (PostgreSQL 17.6, solo catálogos, `BEGIN READ
--   ONLY`; informe `RESULTADO_AURA_CACHE_PERIMETER_0.1.md`):
--
--     · dueño `postgres` (el rol del backend: NOSUPERUSER, BYPASSRLS);
--     · RLS desactivado, cero políticas, sin publicación de replicación, sin vistas, funciones,
--       secuencias ni triggers que la toquen; 0 filas;
--     · `anon`, `authenticated` y `service_role` con los 8 privilegios de tabla
--       (`arwdDxtm`: SELECT, INSERT, UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER, MAINTAIN).
--
--   La tabla es la caché de POIs de AURA-SINGLE: `GET /api/v1/assets/{id}/aura` es PÚBLICO y SIRVE
--   lo que haya en ella mientras tenga menos de 30 días. Con la clave pública de Supabase bastaba
--   un INSERT vía PostgREST para que el mini-mapa de CUALQUIER anuncio mostrara «lugares»
--   inventados (nombre y posición a elección de quien escribe): envenenamiento de caché de una
--   página pública. Y TRUNCATE/DELETE para vaciarla. La lectura de /aura ya funcionaba; el fallo de
--   escritura del backend (PR #171) no cambia esta superficie. La tabla la crea el backend en
--   runtime (`ensure_aura_cache_table`, e545d1b, 2026-06-29) y nació con el privilegio por defecto
--   abierto; la 034 no corrige lo existente.
--
--   MISMO CONTRATO QUE LA 037, Y A PROPÓSITO. `ENABLE` sin `FORCE`, cero políticas, `REVOKE ALL
--   PRIVILEGES` a `PUBLIC` y a los tres roles, transacción única, `lock_timeout`, tolerancia a
--   roles inexistentes (el PostgreSQL del CI no los tiene) y verificación fail-closed dentro,
--   incluidas las compuertas de la 037 (vista dependiente, función que la mencione, publicación).
--
--   DOS AÑADIDOS SOBRE LA 037:
--     1. `REVOKE ALL … FROM PUBLIC` explícito (hoy PUBLIC no tiene nada; así queda escrito).
--     2. La verificación mira también los ACL DE COLUMNA (`pg_attribute.attacl`): un GRANT por
--        columna no lo quita el REVOKE de tabla.
--
--   POR QUÉ `ENABLE` Y NO `FORCE`: la tabla es propiedad de `postgres`, el rol con el que conecta
--   el backend, y `ENABLE` no sujeta al dueño. Además ese rol tiene `rolbypassrls`: exento por
--   dos caminos. La lectura, el UPSERT y el DDL en runtime de `_pois_geo_cached` /
--   `ensure_aura_cache_table` los ejecuta el dueño y siguen funcionando.
--
--   QUIÉN LA APLICA: el DUEÑO de la tabla (en producción, `postgres`). La primera compuerta lo
--   exige: si quien aplica no es el dueño, aborta.
--
--   QUÉ NO TOCA: ninguna otra tabla, ninguna fila, ninguna columna, ninguna política.
--
--   Idempotente, transaccional y reversible (ver ROLLBACK al final).
-- ============================================================

BEGIN;

-- `ENABLE ROW LEVEL SECURITY` pide un ACCESS EXCLUSIVE. La tabla la lee cada vista de /aura; el
-- tope evita que la migración quede en cola bloqueando a quien venga detrás.
SET LOCAL lock_timeout = '3s';

-- ── 0 · COMPROBACIONES PREVIAS, FAIL-CLOSED ─────────────────────────────────────────
DO $$
DECLARE
    dueno     TEXT;
    politicas INTEGER;
    publicada INTEGER;
    vistas    TEXT;
    funciones TEXT;
BEGIN
    IF to_regclass('public.aura_pois_cache') IS NULL THEN
        RAISE EXCEPTION '039 ABORTA: no existe public.aura_pois_cache. ¿Base equivocada?';
    END IF;

    SELECT pg_get_userbyid(c.relowner) INTO dueno
      FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
     WHERE n.nspname = 'public' AND c.relname = 'aura_pois_cache';
    IF dueno <> current_user THEN
        RAISE EXCEPTION
            '039 ABORTA: el dueño es % y aplica %. Usa el rol propietario (en producción, `postgres`).',
            dueno, current_user;
    END IF;

    SELECT count(*) INTO politicas
      FROM pg_policies WHERE schemaname = 'public' AND tablename = 'aura_pois_cache';
    IF politicas > 0 THEN
        RAISE EXCEPTION '039 ABORTA: ya existen % política(s). Revísalas antes.', politicas;
    END IF;

    SELECT count(*) INTO publicada
      FROM pg_publication_tables
     WHERE schemaname = 'public' AND tablename = 'aura_pois_cache';
    IF publicada > 0 THEN
        RAISE EXCEPTION '039 ABORTA: está en una publicación de replicación. Caracteriza el consumidor.';
    END IF;

    SELECT string_agg(DISTINCT v.oid::regclass::text, ', ') INTO vistas
      FROM pg_depend d
      JOIN pg_rewrite rw ON rw.oid = d.objid
      JOIN pg_class v ON v.oid = rw.ev_class
     WHERE d.refobjid = 'public.aura_pois_cache'::regclass
       AND v.oid <> d.refobjid;
    IF vistas IS NOT NULL THEN
        RAISE EXCEPTION '039 ABORTA: hay vistas que dependen de la tabla (%). Una vista sin '
                        'security_invoker cerraría en falso.', vistas;
    END IF;

    SELECT string_agg(format('%s.%s', n.nspname, p.proname), ', ') INTO funciones
      FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
     WHERE n.nspname NOT IN ('pg_catalog', 'information_schema')
       AND p.prosrc ILIKE '%aura_pois_cache%';
    IF funciones IS NOT NULL THEN
        RAISE EXCEPTION '039 ABORTA: hay funciones que mencionan la tabla (%). Caracterízalas antes: '
                        'una RPC SECURITY DEFINER la dejaría alcanzable.', funciones;
    END IF;
END $$;

-- ── 1 · RLS ─────────────────────────────────────────────────────────────────────────
ALTER TABLE public.aura_pois_cache ENABLE ROW LEVEL SECURITY;

-- ── 2 · REVOKE ──────────────────────────────────────────────────────────────────────
--
-- `REVOKE ALL PRIVILEGES` y no una lista de verbos: producción es PostgreSQL 17.6 (donde existe
-- MAINTAIN, y lo tienen los tres roles) y el CI es 15, donde ni existe como nombre. `ALL` vale en
-- las dos.
--
-- `PUBLIC` siempre existe: sin guarda. Los tres roles, con guarda de existencia: un `REVOKE` contra
-- un rol inexistente es un ERROR que, dentro de esta transacción, se llevaría por delante el
-- `ENABLE ROW LEVEL SECURITY` de arriba.
--
-- Sin secuencias: la clave primaria es `activo_id uuid` sin default. Se comprueba igual abajo.
REVOKE ALL PRIVILEGES ON TABLE public.aura_pois_cache FROM PUBLIC;

DO $$
DECLARE
    rol TEXT;
BEGIN
    FOREACH rol IN ARRAY ARRAY['anon', 'authenticated', 'service_role'] LOOP
        IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = rol) THEN
            RAISE NOTICE '039: el rol % no existe aquí; nada que revocar', rol;
            CONTINUE;
        END IF;
        EXECUTE format('REVOKE ALL PRIVILEGES ON TABLE public.aura_pois_cache FROM %I', rol);
        RAISE NOTICE '039: privilegios revocados a %', rol;
    END LOOP;
END $$;

-- ── 3 · VERIFICACIÓN FAIL-CLOSED (mide el efecto; no lo declara) ───────────────────
DO $$
DECLARE
    rls      BOOLEAN;
    force    BOOLEAN;
    pols     INTEGER;
    quedan   TEXT;
    columnas TEXT;
    rol      TEXT;
    priv     TEXT;
    secs     INTEGER;
BEGIN
    SELECT c.relrowsecurity, c.relforcerowsecurity INTO rls, force
      FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
     WHERE n.nspname = 'public' AND c.relname = 'aura_pois_cache';
    IF NOT rls THEN
        RAISE EXCEPTION '039 FALLA: RLS no quedó activado';
    END IF;
    IF force THEN
        RAISE EXCEPTION '039 FALLA: apareció FORCE, y esta unidad no lo autoriza';
    END IF;

    SELECT count(*) INTO pols
      FROM pg_policies WHERE schemaname = 'public' AND tablename = 'aura_pois_cache';
    IF pols > 0 THEN
        RAISE EXCEPTION '039 FALLA: aparecieron % política(s); se esperaban 0', pols;
    END IF;

    -- Lo que REALMENTE hay en el ACL de la tabla, incluido `PUBLIC`.
    SELECT string_agg(format('%s(%s)', x.quien, x.priv), ', ') INTO quedan
      FROM (
        SELECT CASE WHEN a.grantee = 0 THEN 'PUBLIC' ELSE pg_get_userbyid(a.grantee) END AS quien,
               a.privilege_type AS priv
          FROM pg_class c
          JOIN pg_namespace n ON n.oid = c.relnamespace,
               aclexplode(c.relacl) a
         WHERE n.nspname = 'public' AND c.relname = 'aura_pois_cache'
      ) x
     WHERE x.quien IN ('anon', 'authenticated', 'service_role', 'PUBLIC');
    IF quedan IS NOT NULL THEN
        RAISE EXCEPTION '039 FALLA: quedan privilegios en pie -> %', quedan;
    END IF;

    -- Y el ACL de CADA COLUMNA: un GRANT por columna sobrevive al REVOKE de tabla.
    SELECT string_agg(format('%s.%s(%s)', x.col, x.quien, x.priv), ', ') INTO columnas
      FROM (
        SELECT att.attname AS col,
               CASE WHEN a.grantee = 0 THEN 'PUBLIC' ELSE pg_get_userbyid(a.grantee) END AS quien,
               a.privilege_type AS priv
          FROM pg_attribute att, aclexplode(att.attacl) a
         WHERE att.attrelid = 'public.aura_pois_cache'::regclass
           AND att.attnum > 0 AND NOT att.attisdropped
      ) x
     WHERE x.quien IN ('anon', 'authenticated', 'service_role', 'PUBLIC');
    IF columnas IS NOT NULL THEN
        RAISE EXCEPTION '039 FALLA: quedan privilegios de columna -> %', columnas;
    END IF;

    -- El privilegio EFECTIVO de cada rol, verbo a verbo (cubre herencias que el ACL no enseña).
    FOREACH rol IN ARRAY ARRAY['anon', 'authenticated', 'service_role'] LOOP
        CONTINUE WHEN NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = rol);
        FOREACH priv IN ARRAY ARRAY['SELECT', 'INSERT', 'UPDATE', 'DELETE', 'TRUNCATE',
                                    'REFERENCES', 'TRIGGER'] LOOP
            IF has_table_privilege(rol, 'public.aura_pois_cache', priv) THEN
                RAISE EXCEPTION '039 FALLA: % conserva % efectivo', rol, priv;
            END IF;
        END LOOP;
    END LOOP;

    -- El dueño (quien aplica: el backend en producción) conserva el acceso que necesita.
    FOREACH priv IN ARRAY ARRAY['SELECT', 'INSERT', 'UPDATE', 'DELETE'] LOOP
        IF NOT has_table_privilege(current_user, 'public.aura_pois_cache', priv) THEN
            RAISE EXCEPTION '039 FALLA: el dueño % perdió %', current_user, priv;
        END IF;
    END LOOP;

    SELECT count(*) INTO secs
      FROM pg_class s JOIN pg_depend d ON d.objid = s.oid AND d.classid = 'pg_class'::regclass
     WHERE s.relkind = 'S' AND d.refobjid = 'public.aura_pois_cache'::regclass;
    IF secs > 0 THEN
        RAISE EXCEPTION '039 FALLA: la tabla tiene % secuencia(s) que esta migración no cubre', secs;
    END IF;

    RAISE NOTICE '039 OK: RLS activado, sin FORCE, 0 políticas, 0 privilegios externos (tabla y columnas), dueño intacto';
END $$;

-- Verificación legible (debe devolver true, false, 0).
SELECT c.relrowsecurity AS con_rls,
       c.relforcerowsecurity AS con_force,
       (SELECT count(*) FROM pg_policies p
         WHERE p.schemaname = 'public' AND p.tablename = 'aura_pois_cache') AS politicas
  FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
 WHERE n.nspname = 'public' AND c.relname = 'aura_pois_cache';

COMMIT;

-- ── ROLLBACK ────────────────────────────────────────────────────────────────────────
--
-- Deshace exactamente lo de arriba y devuelve la exposición medida el 2026-09-29. Sólo con
-- autorización explícita: reabre la escritura de una caché que se sirve en una página pública.
--
--   BEGIN;
--   ALTER TABLE public.aura_pois_cache DISABLE ROW LEVEL SECURITY;
--   GRANT ALL PRIVILEGES ON TABLE public.aura_pois_cache TO anon, authenticated, service_role;
--   COMMIT;
