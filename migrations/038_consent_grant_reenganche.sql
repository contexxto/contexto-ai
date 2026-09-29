-- ============================================================
-- Migration 038: `consent_grant` — el permiso del reenganche al comprador (Plan 1.1 · TR-5)
--
--   QUÉ HACE: crea UNA tabla, `public.consent_grant`, y la cierra en la MISMA transacción:
--   RLS activado sin FORCE, cero políticas y `REVOKE ALL` a `anon`, `authenticated` y
--   `service_role`. Ninguna tabla de autoridad nace expuesta: la 037 demostró que una tabla
--   creada por el dueño hereda privilegios de PostgREST, y aquí no hay ventana en la que exista
--   abierta. Cero filas leídas o escritas en otras tablas: NO hay backfill ni grants sintéticos
--   a partir de `lead_actividad.consent_reenganche_at` (canon `03_` §5.4, regla 2).
--
--   QUÉ GUARDA: `ConsentGrantV0` (`03_` §5.3/§5.4) — un grant por canal de salida (TR5-D), con
--   `purpose = REENGAGEMENT`, `audience = PRINCIPAL_SELF`, `action = NOTIFY_VERIFIED_UPDATE`
--   (TR5-C), `expires_at = granted_at + 30 días` (TR5-A, lo fija el productor) y `used_at` como
--   metadato de ciclo de vida para `once` (TR5-B: GRANTED → USED → EXPIRED / REVOKED).
--   `session_id` es la sesión sobre la que recae el efecto (el lead de `lead_actividad`), no la
--   identidad: el principal va en `principal_*` y nunca es un correo, un teléfono ni un aparato.
--
--   QUIÉN ESCRIBE: sólo el backend, como dueño. El productor es `POST /lead-contacto` con
--   `consent=true` (acción explícita de la persona, nunca el agente: G7f); el consumo y la
--   revocación los hace el mismo backend (`app/grant_reenganche.py`).
--
--   MISMO CONTRATO DE PERÍMETRO QUE LA 037: transacción única, `lock_timeout`, tolerancia a roles
--   inexistentes (el PostgreSQL del CI no los tiene) y verificación fail-closed dentro. Clave
--   primaria `uuid` con `gen_random_uuid()`: SIN secuencia (la lección de la 036).
--
--   QUIÉN LA APLICA: el rol dueño (en producción, `postgres`). Se aplica ANTES de desplegar el
--   backend de TR-5 y por hash, como la 037. Sin runner de migraciones.
--
--   Idempotente (re-aplicarla no cambia nada) y reversible (ver ROLLBACK al final).
-- ============================================================

BEGIN;

SET LOCAL lock_timeout = '3s';

-- ── 0 · COMPROBACIONES PREVIAS, FAIL-CLOSED ─────────────────────────────────────────
-- Si la tabla ya existe (re-aplicación), tiene que seguir siendo nuestra y seguir cerrada por
-- construcción: sin políticas, sin publicación, sin vistas ni funciones que la alcancen.
DO $$
DECLARE
    tipo      "char";
    dueno     TEXT;
    politicas INTEGER;
    publicada INTEGER;
    vistas    TEXT;
    funciones TEXT;
BEGIN
    SELECT c.relkind INTO tipo
      FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
     WHERE n.nspname = 'public' AND c.relname = 'consent_grant';
    IF tipo IS NOT NULL AND tipo <> 'r' THEN
        RAISE EXCEPTION '038 ABORTA: public.consent_grant existe y no es una tabla (relkind %).', tipo;
    END IF;

    SELECT string_agg(format('%s.%s', n.nspname, p.proname), ', ') INTO funciones
      FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
     WHERE n.nspname NOT IN ('pg_catalog', 'information_schema')
       AND p.prosrc ILIKE '%consent_grant%';
    IF funciones IS NOT NULL THEN
        RAISE EXCEPTION '038 ABORTA: hay funciones que mencionan la tabla (%). Una RPC SECURITY '
                        'DEFINER la dejaría alcanzable.', funciones;
    END IF;

    IF tipo IS NULL THEN
        RETURN;   -- primera aplicación: se crea abajo, ya cerrada
    END IF;

    SELECT pg_get_userbyid(c.relowner) INTO dueno
      FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
     WHERE n.nspname = 'public' AND c.relname = 'consent_grant';
    IF dueno <> current_user THEN
        RAISE EXCEPTION
            '038 ABORTA: el dueño es % y aplica %. Usa el rol propietario (en producción, `postgres`).',
            dueno, current_user;
    END IF;

    SELECT count(*) INTO politicas
      FROM pg_policies WHERE schemaname = 'public' AND tablename = 'consent_grant';
    IF politicas > 0 THEN
        RAISE EXCEPTION '038 ABORTA: ya existen % política(s). Revísalas antes.', politicas;
    END IF;

    SELECT count(*) INTO publicada
      FROM pg_publication_tables
     WHERE schemaname = 'public' AND tablename = 'consent_grant';
    IF publicada > 0 THEN
        RAISE EXCEPTION '038 ABORTA: está en una publicación de replicación.';
    END IF;

    SELECT string_agg(DISTINCT v.oid::regclass::text, ', ') INTO vistas
      FROM pg_depend d
      JOIN pg_rewrite rw ON rw.oid = d.objid
      JOIN pg_class v ON v.oid = rw.ev_class
     WHERE d.refobjid = 'public.consent_grant'::regclass
       AND v.oid <> d.refobjid;
    IF vistas IS NOT NULL THEN
        RAISE EXCEPTION '038 ABORTA: hay vistas que dependen de la tabla (%). Una vista sin '
                        'security_invoker cerraría en falso.', vistas;
    END IF;
END $$;

-- ── 1 · LA TABLA ────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.consent_grant (
    grant_id                uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    contract_version        text        NOT NULL CHECK (contract_version = 'consent_grant_v0'),
    -- La sesión sobre la que recae el efecto (el lead). No es el principal.
    session_id              text        NOT NULL,
    -- principal_ref : PrincipalRefV0
    principal_kind          text        NOT NULL
        CHECK (principal_kind IN ('AUTHENTICATED_PRINCIPAL', 'PSEUDONYMOUS_SESSION_PRINCIPAL')),
    principal_auth_user_id  uuid,
    principal_session_id    text,
    proof_basis             text
        CHECK (proof_basis IN ('OWNER_SESSION', 'RESUME_SECRET_POSSESSION')),
    audience                text        NOT NULL CHECK (audience IN ('PRINCIPAL_SELF')),
    purpose                 text        NOT NULL CHECK (purpose IN ('REENGAGEMENT')),
    action                  text        NOT NULL CHECK (action IN ('NOTIFY_VERIFIED_UPDATE')),
    channel                 text        NOT NULL CHECK (channel IN ('EMAIL', 'PUSH')),
    mode                    text        NOT NULL CHECK (mode IN ('once', 'standing')),
    granted_at              timestamptz NOT NULL DEFAULT now(),
    expires_at              timestamptz NOT NULL,
    used_at                 timestamptz,
    revoked_at              timestamptz,
    case_ref                uuid,
    provenance              jsonb       NOT NULL,
    CONSTRAINT consent_grant_principal_forma CHECK (
        (principal_kind = 'AUTHENTICATED_PRINCIPAL'
            AND principal_auth_user_id IS NOT NULL
            AND principal_session_id IS NULL AND proof_basis IS NULL)
     OR (principal_kind = 'PSEUDONYMOUS_SESSION_PRINCIPAL'
            AND principal_auth_user_id IS NULL
            AND principal_session_id IS NOT NULL AND proof_basis IS NOT NULL)),
    CONSTRAINT consent_grant_expira_despues CHECK (expires_at > granted_at),
    CONSTRAINT consent_grant_used_solo_once CHECK (used_at IS NULL OR mode = 'once'),
    CONSTRAINT consent_grant_used_tras_grant CHECK (used_at IS NULL OR used_at >= granted_at),
    CONSTRAINT consent_grant_revoked_tras_grant CHECK (revoked_at IS NULL OR revoked_at >= granted_at),
    CONSTRAINT consent_grant_provenance_objeto CHECK (jsonb_typeof(provenance) = 'object')
);

-- Un solo grant VIVO por (sesión, propósito, canal): un nuevo «sí» sustituye al anterior (el
-- productor lo revoca en la misma transacción) en lugar de acumular permisos. También es el
-- índice que usa la frontera de autoridad.
CREATE UNIQUE INDEX IF NOT EXISTS consent_grant_vivo_por_canal
    ON public.consent_grant (session_id, purpose, channel)
    WHERE revoked_at IS NULL AND used_at IS NULL;

-- ── 2 · RLS (sin FORCE: el dueño —el backend— no queda sujeto) ─────────────────────
ALTER TABLE public.consent_grant ENABLE ROW LEVEL SECURITY;

-- ── 3 · REVOKE ──────────────────────────────────────────────────────────────────────
-- `ALL PRIVILEGES` (vale en PG15 y PG17) y con guarda de existencia del rol: un `REVOKE` contra
-- un rol inexistente sería un ERROR que se llevaría por delante todo lo anterior.
DO $$
DECLARE
    rol TEXT;
BEGIN
    FOREACH rol IN ARRAY ARRAY['anon', 'authenticated', 'service_role'] LOOP
        IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = rol) THEN
            RAISE NOTICE '038: el rol % no existe aquí; nada que revocar', rol;
            CONTINUE;
        END IF;
        EXECUTE format('REVOKE ALL PRIVILEGES ON TABLE public.consent_grant FROM %I', rol);
        RAISE NOTICE '038: privilegios revocados a %', rol;
    END LOOP;
    -- Un privilegio concedido a PUBLIC no lo quita ningún REVOKE ... FROM <rol>.
    REVOKE ALL PRIVILEGES ON TABLE public.consent_grant FROM PUBLIC;
END $$;

-- ── 4 · VERIFICACIÓN FAIL-CLOSED (mide el efecto; no lo declara) ───────────────────
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
     WHERE n.nspname = 'public' AND c.relname = 'consent_grant';
    IF NOT rls THEN
        RAISE EXCEPTION '038 FALLA: RLS no quedó activado';
    END IF;
    IF force THEN
        RAISE EXCEPTION '038 FALLA: apareció FORCE, y esta unidad no lo autoriza';
    END IF;

    SELECT count(*) INTO pols
      FROM pg_policies WHERE schemaname = 'public' AND tablename = 'consent_grant';
    IF pols > 0 THEN
        RAISE EXCEPTION '038 FALLA: aparecieron % política(s); se esperaban 0', pols;
    END IF;

    SELECT string_agg(format('%s(%s)', x.quien, x.priv), ', ') INTO quedan
      FROM (
        SELECT CASE WHEN a.grantee = 0 THEN 'PUBLIC' ELSE pg_get_userbyid(a.grantee) END AS quien,
               a.privilege_type AS priv
          FROM pg_class c
          JOIN pg_namespace n ON n.oid = c.relnamespace,
               aclexplode(c.relacl) a
         WHERE n.nspname = 'public' AND c.relname = 'consent_grant'
      ) x
     WHERE x.quien IN ('anon', 'authenticated', 'service_role', 'PUBLIC');
    IF quedan IS NOT NULL THEN
        RAISE EXCEPTION '038 FALLA: quedan privilegios en pie -> %', quedan;
    END IF;

    FOREACH rol IN ARRAY ARRAY['anon', 'authenticated', 'service_role'] LOOP
        CONTINUE WHEN NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = rol);
        FOREACH priv IN ARRAY ARRAY['SELECT', 'INSERT', 'UPDATE', 'DELETE', 'TRUNCATE',
                                    'REFERENCES', 'TRIGGER'] LOOP
            IF has_table_privilege(rol, 'public.consent_grant', priv) THEN
                RAISE EXCEPTION '038 FALLA: % conserva % efectivo', rol, priv;
            END IF;
        END LOOP;
    END LOOP;

    FOREACH priv IN ARRAY ARRAY['SELECT', 'INSERT', 'UPDATE', 'DELETE'] LOOP
        IF NOT has_table_privilege(current_user, 'public.consent_grant', priv) THEN
            RAISE EXCEPTION '038 FALLA: el dueño % perdió %', current_user, priv;
        END IF;
    END LOOP;

    SELECT count(*) INTO secs
      FROM pg_class s JOIN pg_depend d ON d.objid = s.oid AND d.classid = 'pg_class'::regclass
     WHERE s.relkind = 'S' AND d.refobjid = 'public.consent_grant'::regclass;
    IF secs > 0 THEN
        RAISE EXCEPTION '038 FALLA: la tabla tiene % secuencia(s) que esta migración no cubre', secs;
    END IF;

    RAISE NOTICE '038 OK: consent_grant creada y cerrada (RLS sin FORCE, 0 políticas, 0 privilegios externos)';
END $$;

-- Verificación legible (debe devolver true, false, 0).
SELECT c.relrowsecurity AS con_rls,
       c.relforcerowsecurity AS con_force,
       (SELECT count(*) FROM pg_policies p
         WHERE p.schemaname = 'public' AND p.tablename = 'consent_grant') AS politicas
  FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
 WHERE n.nspname = 'public' AND c.relname = 'consent_grant';

COMMIT;

-- ── ROLLBACK ────────────────────────────────────────────────────────────────────────
--
-- Borra la tabla y con ella TODOS los permisos de reenganche concedidos. Consecuencia: el cron
-- no encuentra la tabla, la frontera responde ERROR y NO sale ningún aviso al comprador (ni se
-- desvía al corredor). Sólo con autorización explícita, y con el backend de TR-5 retirado antes.
--
--   BEGIN;
--   DROP TABLE IF EXISTS public.consent_grant;
--   COMMIT;
