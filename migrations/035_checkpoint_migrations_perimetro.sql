-- ============================================================
-- Migration 035: la tabla que decide si el backend arranca (Incidente de perímetro · P0, resto)
--
--   QUÉ HACE: activa RLS y revoca privilegios sobre UNA tabla, `checkpoint_migrations`, y sobre
--   las secuencias que le pertenezcan. Nada más. Cero DDL de estructura, **cero filas tocadas**.
--
--   POR QUÉ NO ES DEUDA ORDINARIA, SINO LO QUE FALTABA DEL P0. La 033 cerró las tres tablas del
--   checkpointer y dejó fuera su tabla de control, porque el alcance de aquella unidad eran
--   cinco tablas nombradas. Medir qué pasaba con ésta cambió su clasificación. Reproducido en
--   banco el 2026-09-23:
--
--     1. `anon` vacía `checkpoint_migrations` — una petición a PostgREST, sin autenticarse.
--     2. Al siguiente arranque, `AsyncPostgresSaver.setup()` lee la versión, encuentra 0, y
--        recorre las migraciones desde el principio.
--     3. La migración 9 de langgraph-checkpoint-postgres 2.0.13 es
--        `ALTER TABLE checkpoint_writes ADD COLUMN task_path TEXT NOT NULL DEFAULT ''`,
--        **sin `IF NOT EXISTS`**. Sobre una columna que ya existe:
--            ERROR: column "task_path" of relation "checkpoint_writes" already exists
--     4. `setup()` se llama dentro del `lifespan` de FastAPI (`main.py:40` → `graph.py:1071`).
--
--   Es decir: **una petición HTTP no autenticada impide que el servicio vuelva a arrancar**, y
--   no se repara solo — hay que restaurar la tabla a mano. No filtra datos; niega el servicio
--   entero y de forma persistente. Eso la pone en el mismo cajón que las cinco, no en el backlog.
--
--   Y no protege sólo al arranque: mientras esta tabla sea escribible desde fuera, cualquiera
--   puede insertar una versión falsa más alta y conseguir lo contrario — que `setup()` se salte
--   una migración real en un futuro despliegue.
--
--   MISMO CONTRATO QUE LA 033, Y A PROPÓSITO. `ENABLE` sin `FORCE`, cero políticas,
--   `REVOKE ALL PRIVILEGES` a los tres roles, transacción única, `lock_timeout`, tolerancia a
--   roles inexistentes y verificación fail-closed dentro. No se inventa nada: lo que ya está
--   demostrado se repite igual.
--
--   POR QUÉ `ENABLE` Y NO `FORCE`: la tabla es propiedad de `postgres`, el rol con el que
--   conecta el backend, y `ENABLE` no sujeta al dueño. Además ese rol tiene `rolbypassrls`:
--   exento por dos caminos.
--
--   QUÉ NO TOCA: ninguna otra tabla. La segunda ola tiene su inventario aparte.
--
--   Idempotente, transaccional y reversible.
-- ============================================================

BEGIN;

-- `ENABLE ROW LEVEL SECURITY` pide un ACCESS EXCLUSIVE. Esta tabla es diminuta y sólo se toca
-- al arrancar, así que la contención esperable es nula — pero el tope va igual, porque el coste
-- de ponerlo es cero y el de no ponerlo es una espera que bloquea a quien venga detrás.
SET LOCAL lock_timeout = '3s';

-- ── 0 · COMPROBACIONES PREVIAS, FAIL-CLOSED ─────────────────────────────────────────
DO $$
DECLARE
    dueno     TEXT;
    politicas INTEGER;
    publicada INTEGER;
BEGIN
    IF to_regclass('public.checkpoint_migrations') IS NULL THEN
        RAISE EXCEPTION '035 ABORTA: no existe public.checkpoint_migrations. ¿Base equivocada?';
    END IF;

    SELECT pg_get_userbyid(c.relowner) INTO dueno
      FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
     WHERE n.nspname = 'public' AND c.relname = 'checkpoint_migrations';
    IF dueno <> current_user THEN
        RAISE EXCEPTION
            '035 ABORTA: el dueño es % y aplica %. Usa el rol propietario (en producción, `postgres`).',
            dueno, current_user;
    END IF;

    SELECT count(*) INTO politicas
      FROM pg_policies WHERE schemaname = 'public' AND tablename = 'checkpoint_migrations';
    IF politicas > 0 THEN
        RAISE EXCEPTION '035 ABORTA: ya existen % política(s). Revísalas antes.', politicas;
    END IF;

    SELECT count(*) INTO publicada
      FROM pg_publication_tables
     WHERE schemaname = 'public' AND tablename = 'checkpoint_migrations';
    IF publicada > 0 THEN
        RAISE EXCEPTION '035 ABORTA: está en una publicación de replicación. Caracteriza el consumidor.';
    END IF;
END $$;

-- Conteo ANTES, para demostrar al final que no se tocó una sola fila.
CREATE TEMP TABLE _035_antes ON COMMIT DROP AS
SELECT count(*) AS filas FROM public.checkpoint_migrations;

-- ── 1 · RLS ─────────────────────────────────────────────────────────────────────────
ALTER TABLE public.checkpoint_migrations ENABLE ROW LEVEL SECURITY;

-- ── 2 · REVOKE, sobre la tabla y sobre cualquier secuencia suya ─────────────────────
--
-- `REVOKE ALL PRIVILEGES` y no una lista de verbos: producción es PostgreSQL 17.6 y el CI es 15,
-- donde `MAINTAIN` ni existe como nombre de privilegio. `ALL` vale en las dos.
--
-- Y con guarda de existencia del rol: un `REVOKE` contra un rol inexistente es un ERROR que,
-- dentro de esta transacción, se llevaría por delante el `ENABLE ROW LEVEL SECURITY` de arriba.
-- El PostgreSQL del CI no tiene `anon`, `authenticated` ni `service_role`.
--
-- Hoy esta tabla no tiene secuencias —su única columna es `v INTEGER PRIMARY KEY`—, pero se
-- descubren del catálogo igual: si mañana la tuviera, queda cubierta sin tocar este fichero.
DO $$
DECLARE
    rol TEXT;
    seq TEXT;
    n   INTEGER;
BEGIN
    FOREACH rol IN ARRAY ARRAY['anon', 'authenticated', 'service_role'] LOOP
        IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = rol) THEN
            RAISE NOTICE '035: el rol % no existe aquí; nada que revocar', rol;
            CONTINUE;
        END IF;
        EXECUTE format(
            'REVOKE ALL PRIVILEGES ON TABLE public.checkpoint_migrations FROM %I', rol);
        n := 0;
        FOR seq IN
            SELECT s.relname
              FROM pg_class s
              JOIN pg_depend d ON d.objid = s.oid AND d.classid = 'pg_class'::regclass
              JOIN pg_class t ON t.oid = d.refobjid
              JOIN pg_namespace ns ON ns.oid = s.relnamespace
             WHERE s.relkind = 'S' AND ns.nspname = 'public'
               AND t.relname = 'checkpoint_migrations'
        LOOP
            EXECUTE format('REVOKE ALL PRIVILEGES ON SEQUENCE public.%I FROM %I', seq, rol);
            n := n + 1;
        END LOOP;
        RAISE NOTICE '035: privilegios revocados a % (1 tabla y % secuencia(s))', rol, n;
    END LOOP;
END $$;

-- ── 3 · VERIFICACIÓN FAIL-CLOSED ────────────────────────────────────────────────────
DO $$
DECLARE
    rls    BOOLEAN;
    force  BOOLEAN;
    pols   INTEGER;
    quedan TEXT;
    ahora  BIGINT;
BEGIN
    SELECT c.relrowsecurity, c.relforcerowsecurity INTO rls, force
      FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
     WHERE n.nspname = 'public' AND c.relname = 'checkpoint_migrations';
    IF NOT rls THEN
        RAISE EXCEPTION '035 FALLA: RLS no quedó activado';
    END IF;
    IF force THEN
        RAISE EXCEPTION '035 FALLA: apareció FORCE, y esta unidad no lo autoriza';
    END IF;

    SELECT count(*) INTO pols
      FROM pg_policies WHERE schemaname = 'public' AND tablename = 'checkpoint_migrations';
    IF pols > 0 THEN
        RAISE EXCEPTION '035 FALLA: aparecieron % política(s); se esperaban 0', pols;
    END IF;

    -- Sobre `aclexplode`, que enumera lo que REALMENTE hay, en vez de preguntar por una lista de
    -- privilegios que habría que mantener al día con cada versión. Incluye `PUBLIC`: un
    -- privilegio concedido a PUBLIC no lo quita ningún `REVOKE ... FROM <rol>`.
    SELECT string_agg(format('%s:%s(%s)', x.relname, x.quien, x.priv), ', ') INTO quedan
      FROM (
        SELECT c.relname,
               CASE WHEN a.grantee = 0 THEN 'PUBLIC' ELSE pg_get_userbyid(a.grantee) END AS quien,
               a.privilege_type AS priv
          FROM pg_class c
          JOIN pg_namespace n ON n.oid = c.relnamespace,
               aclexplode(c.relacl) a
         WHERE n.nspname = 'public'
           AND (c.relname = 'checkpoint_migrations'
                OR (c.relkind = 'S' AND EXISTS (
                      SELECT 1 FROM pg_depend d JOIN pg_class t ON t.oid = d.refobjid
                       WHERE d.objid = c.oid AND d.classid = 'pg_class'::regclass
                         AND t.relname = 'checkpoint_migrations')))
      ) x
     WHERE x.quien IN ('anon', 'authenticated', 'service_role', 'PUBLIC');
    IF quedan IS NOT NULL THEN
        RAISE EXCEPTION '035 FALLA: quedan privilegios en pie -> %', quedan;
    END IF;

    SELECT count(*) INTO ahora FROM public.checkpoint_migrations;
    IF ahora <> (SELECT filas FROM _035_antes) THEN
        RAISE EXCEPTION '035 FALLA: cambió el número de filas -> % -> %',
            (SELECT filas FROM _035_antes), ahora;
    END IF;

    RAISE NOTICE '035 OK: RLS activado, 0 políticas, 0 privilegios externos, % filas intactas', ahora;
END $$;

-- Verificación legible (debe devolver true, false, 0).
SELECT c.relrowsecurity AS con_rls,
       c.relforcerowsecurity AS con_force,
       (SELECT count(*) FROM pg_policies p
         WHERE p.schemaname = 'public' AND p.tablename = 'checkpoint_migrations') AS politicas
  FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
 WHERE n.nspname = 'public' AND c.relname = 'checkpoint_migrations';

COMMIT;

-- ── ROLLBACK ────────────────────────────────────────────────────────────────────────
--
-- Devuelve la postura que permite tumbar el arranque del backend desde internet. Se incluye por
-- completitud, no como opción razonable.
--
--   BEGIN;
--   ALTER TABLE public.checkpoint_migrations DISABLE ROW LEVEL SECURITY;
--   GRANT ALL PRIVILEGES ON TABLE public.checkpoint_migrations
--       TO anon, authenticated, service_role;
--   COMMIT;
