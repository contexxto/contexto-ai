-- ============================================================
-- Migration 036: una secuencia nueva tampoco nace pública
--                (Incidente de perímetro · causa raíz, segunda mitad)
--
--   QUÉ HACE: quita del `ALTER DEFAULT PRIVILEGES` del rol que la aplica la concesión
--   automática sobre SECUENCIAS a `anon`, `authenticated` y `service_role`. Cubre **las dos
--   formas** de esa concesión: la global y la de `public`.
--
--   QUÉ **NO** HACE, y va primero porque es lo que más fácil se malentiende: **no corrige
--   ninguna secuencia existente**. Los privilegios por defecto sólo actúan al crear el objeto;
--   cambiarlos no reescribe el `relacl` de lo que ya está. Esta migración impide la PRÓXIMA
--   secuencia expuesta, no repara las de hoy. El inventario de las actuales va al backlog de R2.
--   `handoff_mensaje_id_seq` ya quedó cerrada por la 033 y aquí no se toca.
--
--   POR QUÉ EXISTE, Y NO ES TEÓRICO. La 034 cerró el default de TABLAS. El de SECUENCIAS quedó
--   abierto a propósito, porque aquel mandato decía tablas. Lo que se midió entretanto convierte
--   ese hueco en un agujero con nombre: reproducido el 2026-09-23, cerrando la TABLA
--   `handoff_mensaje` pero dejando su secuencia,
--
--       SET ROLE anon;  SELECT last_value FROM handoff_mensaje_id_seq        →  1
--       SET ROLE anon;  SELECT setval('handoff_mensaje_id_seq', 1, false)    →  1
--       -- y acto seguido, el backend como dueño:
--       INSERT INTO handoff_mensaje ...  →  ERROR: duplicate key value violates ..._pkey
--
--   Una secuencia abierta no filtra datos: **rompe la siguiente escritura**, desde internet y
--   con una petición. Mientras el default siga como está, cada tabla nueva con un `serial` nace
--   con esa puerta puesta.
--
--   LAS DOS FORMAS, Y POR QUÉ NO BASTA UNA. `pg_default_acl.defaclnamespace` vale **0** cuando
--   la concesión se hizo SIN `IN SCHEMA` — es decir, para todos los esquemas — y esa fila no
--   empareja con ninguna de `pg_namespace`. Un `REVOKE ... IN SCHEMA public` **no la toca**, y
--   una verificación con `INNER JOIN` **ni siquiera la ve**: da verde con el agujero abierto.
--   Eso ya mordió una vez en el borrador de la 034 y se corrigió allí; aquí se ataca de frente,
--   revocando por los dos caminos y comprobando por `LEFT JOIN`. Hoy, medido, producción sólo
--   tiene la forma `public` — pero una migración que sólo funciona mientras el otro caso no
--   exista no es una migración, es una casualidad.
--
--   ALCANCE, DECLARADO SIN ADORNOS:
--
--       SUPABASE_ADMIN_SEQUENCE_DEFAULTS = OPEN / OUTSIDE AUTHORITY
--
--   En `public` hay defaults de dos concedentes. Sólo el propio concedente —o un superusuario—
--   puede cambiar los suyos, y `postgres` no es superusuario ni miembro de `supabase_admin`
--   (medido: `pg_has_role` da false en ambos). Una secuencia creada POR `supabase_admin` seguiría
--   naciendo abierta. De las 34 tablas de `public`, 33 son de `postgres`, así que en la práctica
--   esto cubre lo que crea el producto; el hueco es real y cerrarlo exige una acción
--   administrativa con otras credenciales.
--
--   Idempotente, transaccional y reversible. Se aplica DESPUÉS de la 035.
-- ============================================================

BEGIN;

-- ── 0 · FOTO DEL ESTADO ACTUAL ──────────────────────────────────────────────────────
DO $$
DECLARE r RECORD;
BEGIN
    RAISE NOTICE '036: privilegios por defecto sobre SECUENCIAS, ANTES ──────────────';
    FOR r IN
        SELECT pg_get_userbyid(d.defaclrole) AS concedente,
               CASE WHEN d.defaclnamespace = 0 THEN '<TODOS LOS ESQUEMAS>'
                    ELSE n.nspname END AS ambito,
               d.defaclacl::text AS acl
          FROM pg_default_acl d LEFT JOIN pg_namespace n ON n.oid = d.defaclnamespace
         WHERE d.defaclobjtype = 'S'
           AND (d.defaclnamespace = 0 OR n.nspname = 'public')
         ORDER BY 1, 2
    LOOP
        RAISE NOTICE '036:   concedente=% ambito=% acl=%', r.concedente, r.ambito, r.acl;
    END LOOP;
    RAISE NOTICE '036: aplica el rol %, que sólo puede cambiar SUS propios defaults', current_user;
END $$;

-- ── 1 · EL CAMBIO, POR LOS DOS CAMINOS ──────────────────────────────────────────────
--
-- Sin `FOR ROLE`: actúa sobre los defaults del rol que ejecuta, que es el alcance que esta
-- migración puede y debe tener.
--
-- Las dos sentencias NO son redundantes: la primera toca la entrada global
-- (`defaclnamespace = 0`) y la segunda la de `public`. Ninguna sustituye a la otra. Ejecutar la
-- que corresponde a una entrada inexistente es inofensivo — PostgreSQL simplemente no deja nada.
DO $$
DECLARE rol TEXT;
BEGIN
    FOREACH rol IN ARRAY ARRAY['anon', 'authenticated', 'service_role'] LOOP
        IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = rol) THEN
            RAISE NOTICE '036: el rol % no existe aquí; nada que retirar', rol;
            CONTINUE;
        END IF;
        EXECUTE format(
            'ALTER DEFAULT PRIVILEGES REVOKE ALL ON SEQUENCES FROM %I', rol);
        EXECUTE format(
            'ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE ALL ON SEQUENCES FROM %I', rol);
        RAISE NOTICE '036: retirado el default de SECUENCIAS para % (global y public)', rol;
    END LOOP;
END $$;

-- ── 2 · VERIFICACIÓN FAIL-CLOSED ────────────────────────────────────────────────────
--
-- Dos comprobaciones. La primera lee el catálogo, con `LEFT JOIN` para que la entrada global no
-- se pierda. La segunda es la que de verdad importa: **crea una secuencia y le pide a `anon` que
-- la toque**. Un catálogo puede leerse mal; un `permission denied` no se discute.
DO $$
DECLARE
    quedan    TEXT;
    acl_sonda TEXT;
    intrusos  TEXT;
    pudo_leer BOOLEAN := true;
    pudo_set  BOOLEAN := true;
    pudo_next BOOLEAN := true;
    hay_anon  BOOLEAN;
BEGIN
    -- (a) Catálogo, por los dos ámbitos.
    SELECT string_agg(format('%s/%s(%s)', x.ambito, x.quien, x.priv), ', ') INTO quedan
      FROM (
        SELECT CASE WHEN d.defaclnamespace = 0 THEN 'global' ELSE 'public' END AS ambito,
               CASE WHEN a.grantee = 0 THEN 'PUBLIC' ELSE pg_get_userbyid(a.grantee) END AS quien,
               a.privilege_type AS priv
          FROM pg_default_acl d
          LEFT JOIN pg_namespace n ON n.oid = d.defaclnamespace,
               aclexplode(d.defaclacl) a
         WHERE d.defaclobjtype = 'S'
           AND (d.defaclnamespace = 0 OR n.nspname = 'public')
           AND d.defaclrole = (SELECT oid FROM pg_roles WHERE rolname = current_user)
      ) x
     WHERE x.quien IN ('anon', 'authenticated', 'service_role', 'PUBLIC');
    IF quedan IS NOT NULL THEN
        RAISE EXCEPTION '036 FALLA: el default de SECUENCIAS todavía concede -> %', quedan;
    END IF;

    -- (b) La sonda viva. Se crea, se prueba, se destruye — todo dentro de la transacción.
    EXECUTE 'CREATE SEQUENCE public._036_sonda_secuencia';
    SELECT coalesce(c.relacl::text, '(sin acl: sólo el dueño)') INTO acl_sonda
      FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
     WHERE n.nspname = 'public' AND c.relname = '_036_sonda_secuencia';

    SELECT string_agg(DISTINCT x.quien, ', ') INTO intrusos
      FROM (
        SELECT CASE WHEN a.grantee = 0 THEN 'PUBLIC' ELSE pg_get_userbyid(a.grantee) END AS quien
          FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace,
               aclexplode(c.relacl) a
         WHERE n.nspname = 'public' AND c.relname = '_036_sonda_secuencia'
      ) x
     WHERE x.quien IN ('anon', 'authenticated', 'service_role', 'PUBLIC');

    -- Y ahora el intento real, si `anon` existe en esta base.
    SELECT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') INTO hay_anon;
    IF hay_anon THEN
        SET LOCAL ROLE anon;
        BEGIN
            PERFORM last_value FROM public._036_sonda_secuencia;
        EXCEPTION WHEN insufficient_privilege THEN pudo_leer := false;
        END;
        BEGIN
            PERFORM setval('public._036_sonda_secuencia', 99, false);
        EXCEPTION WHEN insufficient_privilege THEN pudo_set := false;
        END;
        BEGIN
            PERFORM nextval('public._036_sonda_secuencia');
        EXCEPTION WHEN insufficient_privilege THEN pudo_next := false;
        END;
        RESET ROLE;
    ELSE
        pudo_leer := false; pudo_set := false; pudo_next := false;
        RAISE NOTICE '036: no hay rol `anon` aquí; la sonda viva se salta';
    END IF;

    EXECUTE 'DROP SEQUENCE public._036_sonda_secuencia';

    IF intrusos IS NOT NULL THEN
        RAISE EXCEPTION
            '036 FALLA: una secuencia nueva SIGUE naciendo con privilegios para % (acl: %)',
            intrusos, acl_sonda;
    END IF;
    IF pudo_leer OR pudo_set OR pudo_next THEN
        RAISE EXCEPTION
            '036 FALLA: `anon` pudo tocar la secuencia nueva (leer=% setval=% nextval=%)',
            pudo_leer, pudo_set, pudo_next;
    END IF;
    RAISE NOTICE '036 OK: una secuencia nueva nace con acl = % y `anon` recibe permission denied en las tres operaciones',
        acl_sonda;

    -- (c) Aviso, no fallo: lo que esta migración no puede cerrar.
    IF EXISTS (
        SELECT 1 FROM pg_default_acl d
          LEFT JOIN pg_namespace n ON n.oid = d.defaclnamespace,
               aclexplode(d.defaclacl) a
         WHERE d.defaclobjtype = 'S'
           AND (d.defaclnamespace = 0 OR n.nspname = 'public')
           AND d.defaclrole <> (SELECT oid FROM pg_roles WHERE rolname = current_user)
           AND pg_get_userbyid(a.grantee) IN ('anon', 'authenticated', 'service_role')
    ) THEN
        RAISE NOTICE '036 AVISO: SUPABASE_ADMIN_SEQUENCE_DEFAULTS = OPEN / OUTSIDE AUTHORITY.';
        RAISE NOTICE '036 AVISO: otro concedente sigue dando privilegios por defecto sobre';
        RAISE NOTICE '036 AVISO: SECUENCIAS. Una creada POR ÉL nacería abierta. Cerrarlo exige';
        RAISE NOTICE '036 AVISO: credenciales de ese rol o de un superusuario.';
    ELSE
        RAISE NOTICE '036: no queda ningún otro concedente con defaults de SECUENCIAS aquí.';
    END IF;
END $$;

-- Verificación legible (debe devolver 0).
SELECT count(*) AS concesiones_externas_por_defecto_en_secuencias
  FROM pg_default_acl d
  LEFT JOIN pg_namespace n ON n.oid = d.defaclnamespace,
       aclexplode(d.defaclacl) a
 WHERE d.defaclobjtype = 'S'
   AND (d.defaclnamespace = 0 OR n.nspname = 'public')
   AND d.defaclrole = (SELECT oid FROM pg_roles WHERE rolname = current_user)
   AND pg_get_userbyid(a.grantee) IN ('anon', 'authenticated', 'service_role');

COMMIT;

-- ── ROLLBACK ────────────────────────────────────────────────────────────────────────
--
--   BEGIN;
--   ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES
--       TO anon, authenticated, service_role;
--   COMMIT;
--
-- (No se restaura la forma global salvo que se haya comprobado que existía antes: en producción,
--  medido el 2026-09-23, sólo existía la de `public`.)
