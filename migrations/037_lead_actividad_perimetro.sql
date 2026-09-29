-- ============================================================
-- Migration 037: `lead_actividad` deja de estar abierta a PostgREST (SEC-PERIM-LEAD-ACTIVIDAD)
--
--   QUÉ HACE: activa RLS y revoca privilegios sobre UNA tabla, `public.lead_actividad`. Nada más.
--   Cero DDL de estructura. Cero filas leídas, contadas o tocadas.
--
--   POR QUÉ, MEDIDO EN PRODUCCIÓN el 2026-09-28 (solo catálogos, `BEGIN READ ONLY`; informe
--   `RESULTADO_PLAN1_1_SEC_PERIM_LEAD_ACTIVIDAD_0.1.md`):
--
--     · RLS desactivado, cero políticas;
--     · `anon` y `authenticated` con los 7 privilegios de tabla (SELECT, INSERT, UPDATE, DELETE,
--       TRUNCATE, REFERENCES, TRIGGER) y SELECT/INSERT/UPDATE sobre TODAS las columnas sensibles:
--       `lead_email`, `lead_telefono`, `lead_push`, `consent_reenganche_at`, `reenganche_*`.
--
--   Con la clave pública se podía LEER el correo, el teléfono y la suscripción push de cada
--   comprador, y ESCRIBIR su consentimiento y su contacto: plantar `consent_reenganche_at` y el
--   correo de un tercero en una fila bastaba para que el cron de reenganche le escribiera a
--   alguien que nunca consintió, y deshacer una revocación bastaba para vaciar TR-2. La tabla
--   la crea el backend en runtime (`ensure_lead_actividad`) y nació antes de que la 034 corrigiera
--   el privilegio por defecto; la 034 no corrige lo existente.
--
--   MISMO CONTRATO QUE LA 033 Y LA 035, Y A PROPÓSITO. `ENABLE` sin `FORCE`, cero políticas,
--   `REVOKE ALL PRIVILEGES` a los tres roles (autorizado por Carlos: anon, authenticated y
--   service_role), transacción única, `lock_timeout`, tolerancia a roles inexistentes (el
--   PostgreSQL del CI no los tiene) y verificación fail-closed dentro.
--
--   DOS DIFERENCIAS CON LA 035, las dos deliberadas:
--     1. NO se cuentan filas. La 035 hacía `count(*)` antes y después para demostrar que no
--        tocaba ninguna. Esta unidad tiene prohibido leer o contar filas de esta tabla (contiene
--        datos personales); la prueba de que no se tocan es que las únicas sentencias son
--        `ALTER TABLE … ENABLE ROW LEVEL SECURITY` y `REVOKE`, que no operan sobre filas.
--     2. DOS compuertas más: ninguna vista dependiente (un cierre FALSO por vista sin
--        `security_invoker` ya se detectó en la segunda ola, `pois_vivos`) y ninguna función
--        que la mencione (una RPC `SECURITY DEFINER` la dejaría alcanzable por otra puerta).
--
--   POR QUÉ `ENABLE` Y NO `FORCE`: la tabla es propiedad de `postgres`, el rol con el que conecta
--   el backend, y `ENABLE` no sujeta al dueño. Además ese rol tiene `rolbypassrls`: exento por
--   dos caminos. El DDL en runtime de `ensure_lead_actividad` (CREATE TABLE IF NOT EXISTS /
--   ADD COLUMN IF NOT EXISTS) lo ejecuta el dueño y sigue funcionando.
--
--   QUIÉN LA APLICA: el DUEÑO de la tabla (en producción, `postgres`). La primera compuerta lo
--   exige: si quien aplica no es el dueño, aborta.
--
--   QUÉ NO TOCA: ninguna otra tabla, ninguna fila, ninguna columna, ninguna política.
--
--   Idempotente, transaccional y reversible (ver ROLLBACK al final).
-- ============================================================

BEGIN;

-- `ENABLE ROW LEVEL SECURITY` pide un ACCESS EXCLUSIVE. La tabla la toca el chat en cada turno
-- de un lead de QR (`marcar_actividad_lead`) y el cron; el tope evita que la migración quede en
-- cola bloqueando a quien venga detrás.
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
    IF to_regclass('public.lead_actividad') IS NULL THEN
        RAISE EXCEPTION '037 ABORTA: no existe public.lead_actividad. ¿Base equivocada?';
    END IF;

    SELECT pg_get_userbyid(c.relowner) INTO dueno
      FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
     WHERE n.nspname = 'public' AND c.relname = 'lead_actividad';
    IF dueno <> current_user THEN
        RAISE EXCEPTION
            '037 ABORTA: el dueño es % y aplica %. Usa el rol propietario (en producción, `postgres`).',
            dueno, current_user;
    END IF;

    SELECT count(*) INTO politicas
      FROM pg_policies WHERE schemaname = 'public' AND tablename = 'lead_actividad';
    IF politicas > 0 THEN
        RAISE EXCEPTION '037 ABORTA: ya existen % política(s). Revísalas antes.', politicas;
    END IF;

    SELECT count(*) INTO publicada
      FROM pg_publication_tables
     WHERE schemaname = 'public' AND tablename = 'lead_actividad';
    IF publicada > 0 THEN
        RAISE EXCEPTION '037 ABORTA: está en una publicación de replicación. Caracteriza el consumidor.';
    END IF;

    SELECT string_agg(DISTINCT v.oid::regclass::text, ', ') INTO vistas
      FROM pg_depend d
      JOIN pg_rewrite rw ON rw.oid = d.objid
      JOIN pg_class v ON v.oid = rw.ev_class
     WHERE d.refobjid = 'public.lead_actividad'::regclass
       AND v.oid <> d.refobjid;
    IF vistas IS NOT NULL THEN
        RAISE EXCEPTION '037 ABORTA: hay vistas que dependen de la tabla (%). Una vista sin '
                        'security_invoker cerraría en falso.', vistas;
    END IF;

    SELECT string_agg(format('%s.%s', n.nspname, p.proname), ', ') INTO funciones
      FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
     WHERE n.nspname NOT IN ('pg_catalog', 'information_schema')
       AND p.prosrc ILIKE '%lead_actividad%';
    IF funciones IS NOT NULL THEN
        RAISE EXCEPTION '037 ABORTA: hay funciones que mencionan la tabla (%). Caracterízalas antes: '
                        'una RPC SECURITY DEFINER la dejaría alcanzable.', funciones;
    END IF;
END $$;

-- ── 1 · RLS ─────────────────────────────────────────────────────────────────────────
ALTER TABLE public.lead_actividad ENABLE ROW LEVEL SECURITY;

-- ── 2 · REVOKE ──────────────────────────────────────────────────────────────────────
--
-- `REVOKE ALL PRIVILEGES` y no una lista de verbos: producción es PostgreSQL 17.6 y el CI es 15,
-- donde `MAINTAIN` ni existe como nombre de privilegio. `ALL` vale en las dos.
--
-- Con guarda de existencia del rol: un `REVOKE` contra un rol inexistente es un ERROR que, dentro
-- de esta transacción, se llevaría por delante el `ENABLE ROW LEVEL SECURITY` de arriba.
--
-- Sin secuencias: la clave primaria es `session_id text`. Se comprueba igual en la verificación.
DO $$
DECLARE
    rol TEXT;
BEGIN
    FOREACH rol IN ARRAY ARRAY['anon', 'authenticated', 'service_role'] LOOP
        IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = rol) THEN
            RAISE NOTICE '037: el rol % no existe aquí; nada que revocar', rol;
            CONTINUE;
        END IF;
        EXECUTE format('REVOKE ALL PRIVILEGES ON TABLE public.lead_actividad FROM %I', rol);
        RAISE NOTICE '037: privilegios revocados a %', rol;
    END LOOP;
END $$;

-- ── 3 · VERIFICACIÓN FAIL-CLOSED (mide el efecto; no lo declara) ───────────────────
DO $$
DECLARE
    rls      BOOLEAN;
    force    BOOLEAN;
    pols     INTEGER;
    quedan   TEXT;
    rol      TEXT;
    priv     TEXT;
    secs     INTEGER;
BEGIN
    SELECT c.relrowsecurity, c.relforcerowsecurity INTO rls, force
      FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
     WHERE n.nspname = 'public' AND c.relname = 'lead_actividad';
    IF NOT rls THEN
        RAISE EXCEPTION '037 FALLA: RLS no quedó activado';
    END IF;
    IF force THEN
        RAISE EXCEPTION '037 FALLA: apareció FORCE, y esta unidad no lo autoriza';
    END IF;

    SELECT count(*) INTO pols
      FROM pg_policies WHERE schemaname = 'public' AND tablename = 'lead_actividad';
    IF pols > 0 THEN
        RAISE EXCEPTION '037 FALLA: aparecieron % política(s); se esperaban 0', pols;
    END IF;

    -- Lo que REALMENTE hay en el ACL, incluido `PUBLIC` (un privilegio concedido a PUBLIC no lo
    -- quita ningún `REVOKE ... FROM <rol>`).
    SELECT string_agg(format('%s(%s)', x.quien, x.priv), ', ') INTO quedan
      FROM (
        SELECT CASE WHEN a.grantee = 0 THEN 'PUBLIC' ELSE pg_get_userbyid(a.grantee) END AS quien,
               a.privilege_type AS priv
          FROM pg_class c
          JOIN pg_namespace n ON n.oid = c.relnamespace,
               aclexplode(c.relacl) a
         WHERE n.nspname = 'public' AND c.relname = 'lead_actividad'
      ) x
     WHERE x.quien IN ('anon', 'authenticated', 'service_role', 'PUBLIC');
    IF quedan IS NOT NULL THEN
        RAISE EXCEPTION '037 FALLA: quedan privilegios en pie -> %', quedan;
    END IF;

    -- Y el privilegio EFECTIVO de cada rol, verbo a verbo (cubre herencias que el ACL no enseña).
    FOREACH rol IN ARRAY ARRAY['anon', 'authenticated', 'service_role'] LOOP
        CONTINUE WHEN NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = rol);
        FOREACH priv IN ARRAY ARRAY['SELECT', 'INSERT', 'UPDATE', 'DELETE', 'TRUNCATE',
                                    'REFERENCES', 'TRIGGER'] LOOP
            IF has_table_privilege(rol, 'public.lead_actividad', priv) THEN
                RAISE EXCEPTION '037 FALLA: % conserva % efectivo', rol, priv;
            END IF;
        END LOOP;
    END LOOP;

    -- El dueño (quien aplica: el backend en producción) conserva el acceso que necesita.
    FOREACH priv IN ARRAY ARRAY['SELECT', 'INSERT', 'UPDATE', 'DELETE'] LOOP
        IF NOT has_table_privilege(current_user, 'public.lead_actividad', priv) THEN
            RAISE EXCEPTION '037 FALLA: el dueño % perdió %', current_user, priv;
        END IF;
    END LOOP;

    SELECT count(*) INTO secs
      FROM pg_class s JOIN pg_depend d ON d.objid = s.oid AND d.classid = 'pg_class'::regclass
     WHERE s.relkind = 'S' AND d.refobjid = 'public.lead_actividad'::regclass;
    IF secs > 0 THEN
        RAISE EXCEPTION '037 FALLA: la tabla tiene % secuencia(s) que esta migración no cubre', secs;
    END IF;

    RAISE NOTICE '037 OK: RLS activado, sin FORCE, 0 políticas, 0 privilegios externos, dueño intacto';
END $$;

-- Verificación legible (debe devolver true, false, 0).
SELECT c.relrowsecurity AS con_rls,
       c.relforcerowsecurity AS con_force,
       (SELECT count(*) FROM pg_policies p
         WHERE p.schemaname = 'public' AND p.tablename = 'lead_actividad') AS politicas
  FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
 WHERE n.nspname = 'public' AND c.relname = 'lead_actividad';

COMMIT;

-- ── ROLLBACK ────────────────────────────────────────────────────────────────────────
--
-- Deshace exactamente lo de arriba y devuelve la exposición medida el 2026-09-28. Sólo con
-- autorización explícita: reabre la lectura y la escritura de datos personales desde fuera.
--
--   BEGIN;
--   ALTER TABLE public.lead_actividad DISABLE ROW LEVEL SECURITY;
--   GRANT ALL PRIVILEGES ON TABLE public.lead_actividad TO anon, authenticated, service_role;
--   COMMIT;
