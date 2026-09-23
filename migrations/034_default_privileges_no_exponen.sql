-- ============================================================
-- Migration 034: una tabla nueva ya no nace pública
--                (Incidente de perímetro · causa raíz)
--
--   QUÉ HACE: quita del `ALTER DEFAULT PRIVILEGES` del rol que la aplica la concesión
--   automática de privilegios sobre TABLAS a `anon`, `authenticated` y `service_role` en el
--   esquema `public`. Una línea de efecto, y todo lo demás es comprobación.
--
--   QUÉ **NO** HACE, y conviene que quede escrito antes que nada: **no corrige ni una sola
--   tabla existente**. Los privilegios por defecto sólo actúan en el momento de crear un
--   objeto; cambiarlos no reescribe el `relacl` de lo que ya está. Esta migración impide la
--   PRÓXIMA exposición, no repara las veinte de hoy. La 033 cerró cinco; el resto es la
--   segunda ola.
--
--   POR QUÉ EXISTE. Ninguna de las tablas expuestas pidió esos permisos: su DDL no menciona
--   ni un `GRANT`. Los heredaron al nacer. Reproducido en banco el 2026-09-23 con el
--   checkpointer REAL de LangGraph: se le dejó crear sus tablas contra una base con la misma
--   postura de privilegios por defecto, y salieron así —sin que la librería sepa que existen
--   `anon` ni `authenticated`:
--
--       checkpoints       {anon=arwdDxtm/…, authenticated=arwdDxtm/…, service_role=arwdDxtm/…}
--       checkpoint_blobs  {ídem}
--       checkpoint_writes {ídem}
--
--   Y no es historia antigua: `app/routers/chat.py` crea `handoff_sesion`,
--   `handoff_mensaje`, `lead_actividad` y `notificacion` EN CALIENTE, la primera vez que un
--   proceso las necesita. Mientras el default siga como está, cada tabla nueva del producto
--   nace publicada.
--
--   ALCANCE REAL, Y ES PARCIAL. En `public` hay privilegios por defecto de DOS concedentes:
--   `postgres` y `supabase_admin`. Sólo el propio concedente —o un superusuario— puede
--   cambiar los suyos, y en producción el rol de la aplicación es `postgres`, que **no es
--   superusuario ni miembro de `supabase_admin`** (medido: `pg_has_role` da false en ambos).
--   Así que esta migración cubre lo que cree `postgres` y no lo que cree `supabase_admin`.
--
--   Cuánto importa ese hueco, medido: de las 34 tablas de `public`, **33 son propiedad de
--   `postgres`** y una de `supabase_admin`. Todo lo que crea el producto —migraciones,
--   checkpointer, DDL en caliente— corre como `postgres`. El hueco es real y hay que
--   nombrarlo; cerrarlo exige credenciales que esta unidad no tiene.
--
--   SÓLO TABLAS. El mandato dice tablas y eso es lo que se toca. Queda medido y sin cambiar
--   que los mismos concedentes dan `rwU` sobre SECUENCIAS a los tres roles: una secuencia
--   abierta no filtra datos, pero permite `setval` desde fuera y con eso romper el siguiente
--   `INSERT` — está demostrado en la cabecera de la 033. Es un hueco, es pequeño, y es de
--   otra unidad.
--
--   UNA TRAMPA DEL CATÁLOGO, medida y evitada. `pg_default_acl.defaclnamespace` vale **0**
--   cuando la concesión se hizo SIN `IN SCHEMA`, es decir para todos los esquemas — y esa fila
--   no empareja con ninguna de `pg_namespace`. Una verificación con `JOIN` la pierde en
--   silencio y da verde con el agujero abierto: reproducido el 2026-09-23, con una concesión
--   global viva, el `JOIN` devolvía 0 filas mientras una tabla nueva nacía expuesta. Aquí se
--   usa `LEFT JOIN` y el 0 cuenta como «incluye public». En producción, medido hoy, no hay
--   ninguna entrada global — pero una comprobación que sólo funciona mientras el problema no
--   exista no es una comprobación.
--
--   Idempotente, transaccional y reversible. Se aplica DESPUÉS de la 033.
-- ============================================================

BEGIN;

-- ── 0 · FOTO DEL ESTADO ACTUAL ──────────────────────────────────────────────────────
--
-- Se mide antes de tocar, y se deja en el log: si alguien audita esto dentro de un año,
-- quiere saber qué había, no sólo qué quedó.
DO $$
DECLARE r RECORD;
BEGIN
    RAISE NOTICE '034: privilegios por defecto en `public` ANTES ─────────────────────';
    FOR r IN
        SELECT pg_get_userbyid(d.defaclrole) AS concedente,
               d.defaclobjtype::text AS tipo,
               d.defaclacl::text AS acl
          FROM pg_default_acl d JOIN pg_namespace n ON n.oid = d.defaclnamespace
         WHERE n.nspname = 'public'
         ORDER BY 1, 2
    LOOP
        RAISE NOTICE '034:   concedente=% tipo=% acl=%', r.concedente, r.tipo, r.acl;
    END LOOP;
    RAISE NOTICE '034: aplica el rol %, que sólo puede cambiar SUS propios defaults', current_user;
END $$;

-- ── 1 · EL CAMBIO ───────────────────────────────────────────────────────────────────
--
-- Sin `FOR ROLE`: así actúa sobre los defaults del rol que ejecuta, que es exactamente el
-- alcance que esta migración puede y debe tener. Nombrar otro rol fallaría con «permission
-- denied to change default privileges», y fallar ruidosamente sería mejor que fallar en
-- silencio — pero ni siquiera hace falta intentarlo.
--
-- `REVOKE ALL ON TABLES` a los tres roles. No se toca el default de `postgres` sobre sí
-- mismo, ni el de SECUENCIAS, ni el de FUNCIONES.
--
-- El bloque tolera que el rol no exista, por la misma razón que en la 033: un REVOKE contra
-- un rol inexistente es un ERROR que, dentro de esta transacción, tumbaría todo.
DO $$
DECLARE rol TEXT;
BEGIN
    FOREACH rol IN ARRAY ARRAY['anon', 'authenticated', 'service_role'] LOOP
        IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = rol) THEN
            EXECUTE format(
                'ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE ALL ON TABLES FROM %I', rol);
            RAISE NOTICE '034: retirado el privilegio por defecto sobre TABLAS para %', rol;
        ELSE
            RAISE NOTICE '034: el rol % no existe aquí; nada que retirar', rol;
        END IF;
    END LOOP;
END $$;

-- ── 2 · VERIFICACIÓN FAIL-CLOSED ────────────────────────────────────────────────────
--
-- Dos comprobaciones. La primera lee el catálogo. La segunda es la que de verdad importa:
-- **crea una tabla de prueba y mira con qué privilegios nace**. Un catálogo puede leerse mal;
-- una tabla recién nacida no miente. La tabla se destruye antes del COMMIT, así que no queda
-- rastro de ella.
DO $$
DECLARE
    quedan TEXT;
    acl_sonda TEXT;
    intrusos TEXT;
BEGIN
    -- (a) El catálogo: ninguno de los tres puede seguir en el default de TABLAS de este rol.
    SELECT string_agg(format('%s(%s)', x.quien, x.priv), ', ') INTO quedan
      FROM (
        SELECT CASE WHEN a.grantee = 0 THEN 'PUBLIC' ELSE pg_get_userbyid(a.grantee) END AS quien,
               a.privilege_type AS priv
          FROM pg_default_acl d
          LEFT JOIN pg_namespace n ON n.oid = d.defaclnamespace,
               aclexplode(d.defaclacl) a
         -- `defaclnamespace = 0` significa «todos los esquemas», y esa entrada NO empareja
         -- con ninguna fila de pg_namespace. Con un INNER JOIN desaparecía en silencio: la
         -- comprobación daba verde con el agujero abierto. Medido el 2026-09-23 en banco —
         -- con una concesión global viva, la consulta con INNER JOIN devolvía 0 filas
         -- mientras una tabla nueva nacía con `anon2=arwdDxtm`. Fail-OPEN, y por eso
         -- aquí va LEFT JOIN y el 0 cuenta como «incluye public».
         WHERE (d.defaclnamespace = 0 OR n.nspname = 'public')
           AND d.defaclobjtype = 'r'
           AND d.defaclrole = (SELECT oid FROM pg_roles WHERE rolname = current_user)
      ) x
     WHERE x.quien IN ('anon', 'authenticated', 'service_role', 'PUBLIC');
    IF quedan IS NOT NULL THEN
        RAISE EXCEPTION '034 FALLA: el default de TABLAS todavía concede -> %', quedan;
    END IF;

    -- (b) La prueba real: una tabla nueva, creada aquí mismo, no puede nacer con privilegios
    --     para los tres roles. Se crea, se mira y se destruye dentro de la transacción.
    EXECUTE 'CREATE TABLE public._034_sonda_nacimiento (x int)';
    SELECT coalesce(c.relacl::text, '(sin acl: sólo el dueño)') INTO acl_sonda
      FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
     WHERE n.nspname = 'public' AND c.relname = '_034_sonda_nacimiento';

    SELECT string_agg(DISTINCT x.quien, ', ') INTO intrusos
      FROM (
        SELECT CASE WHEN a.grantee = 0 THEN 'PUBLIC' ELSE pg_get_userbyid(a.grantee) END AS quien
          FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace,
               aclexplode(c.relacl) a
         WHERE n.nspname = 'public' AND c.relname = '_034_sonda_nacimiento'
      ) x
     WHERE x.quien IN ('anon', 'authenticated', 'service_role', 'PUBLIC');

    EXECUTE 'DROP TABLE public._034_sonda_nacimiento';

    IF intrusos IS NOT NULL THEN
        RAISE EXCEPTION
            '034 FALLA: una tabla nueva SIGUE naciendo con privilegios para % (acl: %)',
            intrusos, acl_sonda;
    END IF;
    RAISE NOTICE '034 OK: una tabla nueva nace con acl = %', acl_sonda;

    -- (c) Aviso, no fallo: lo que esta migración NO puede cerrar.
    IF EXISTS (
        SELECT 1 FROM pg_default_acl d
          LEFT JOIN pg_namespace n ON n.oid = d.defaclnamespace,
               aclexplode(d.defaclacl) a
         WHERE (d.defaclnamespace = 0 OR n.nspname = 'public') AND d.defaclobjtype = 'r'
           AND d.defaclrole <> (SELECT oid FROM pg_roles WHERE rolname = current_user)
           AND pg_get_userbyid(a.grantee) IN ('anon', 'authenticated', 'service_role')
    ) THEN
        RAISE NOTICE '034 AVISO: OTRO concedente sigue dando privilegios por defecto sobre';
        RAISE NOTICE '034 AVISO: TABLAS. Una tabla creada POR ÉL nacería expuesta. Cerrarlo';
        RAISE NOTICE '034 AVISO: exige credenciales de ese rol o de un superusuario.';
    END IF;
END $$;

-- Verificación legible (debe devolver 0).
SELECT count(*) AS concesiones_externas_por_defecto
  FROM pg_default_acl d
  LEFT JOIN pg_namespace n ON n.oid = d.defaclnamespace,
       aclexplode(d.defaclacl) a
 WHERE (d.defaclnamespace = 0 OR n.nspname = 'public')
   AND d.defaclobjtype = 'r'
   AND d.defaclrole = (SELECT oid FROM pg_roles WHERE rolname = current_user)
   AND pg_get_userbyid(a.grantee) IN ('anon', 'authenticated', 'service_role');

COMMIT;

-- ── ROLLBACK ────────────────────────────────────────────────────────────────────────
--
-- Devuelve el comportamiento que causó el incidente: que toda tabla nueva de `public` nazca
-- legible, modificable y truncable desde internet. Se incluye por completitud, no como opción
-- razonable.
--
--   BEGIN;
--   ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES
--       TO anon, authenticated, service_role;
--   COMMIT;
