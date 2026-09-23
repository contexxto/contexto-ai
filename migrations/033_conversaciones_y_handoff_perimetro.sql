-- ============================================================
-- Migration 033: las conversaciones y el handoff dejan de estar abiertos
--                (Incidente de perímetro · ola P0)
--
--   QUÉ HACE: activa RLS y revoca privilegios sobre CINCO tablas —`checkpoints`,
--   `checkpoint_blobs`, `checkpoint_writes`, `handoff_sesion` y `handoff_mensaje`— y sobre
--   las secuencias que les pertenecen. Nada más. Cero DDL de estructura, cero columnas,
--   **cero filas tocadas**, no lee un solo `blob` ni un solo `texto`.
--
--   POR QUÉ EXISTE, y no es higiene: es contención de un incidente. Medido en producción el
--   2026-09-23, veinte tablas de `public` estaban sin RLS y con `arwdDxtm` concedido a `anon`,
--   `authenticated` y `service_role`. Con la anon key que el frontend publica por diseño,
--   `anon` obtuvo por HTTPS el conteo real de `checkpoint_blobs`: `*/8927`. Estas cinco son
--   las que guardan lo más sensible de todo el esquema, y por eso van primero:
--
--     checkpoints · checkpoint_blobs · checkpoint_writes
--         el almacén del `AsyncPostgresSaver` de LangGraph — el estado serializado de las
--         conversaciones. 17 463 filas entre las tres.
--     handoff_sesion
--         la conexión entre un usuario y un corredor. Lleva `lead_email` y
--         `push_subscription`: datos personales y un canal de notificación.
--     handoff_mensaje
--         los mensajes entre el usuario y el corredor. Lleva `texto`.
--
--   LO QUE LA 032 YA DEJÓ MEDIDO, y aquí se hereda sin repetir el experimento: RLS sólo
--   gobierna los privilegios de fila. `arwdDxtm` son OCHO; `TRUNCATE`, `TRIGGER`,
--   `REFERENCES` y `MAINTAIN` se le escapan. Con RLS activo y cero políticas, `anon` truncó
--   una tabla, colgó un trigger que se ejecutó dentro del INSERT del dueño y exfiltró su
--   contenido, y creó una FK que bloqueó el TRUNCATE legítimo. Por eso aquí va `REVOKE ALL`,
--   y RLS es el complemento, no al revés.
--
--   POR QUÉ TAMBIÉN LAS SECUENCIAS, y esto SÍ es nuevo. La 032 no tuvo que resolverlo porque
--   el Buyer Store no tiene ninguna; `handoff_mensaje` sí (`handoff_mensaje_id_seq`, de su
--   `bigserial`). Medido en banco el 2026-09-23, cerrando la TABLA pero dejando la secuencia:
--
--       SET ROLE anon;  SELECT last_value FROM handoff_mensaje_id_seq   →  1
--       SET ROLE anon;  SELECT setval('handoff_mensaje_id_seq', 1, false) →  1
--       -- y acto seguido, el backend, como dueño:
--       INSERT INTO handoff_mensaje ...  →  ERROR: duplicate key value violates unique
--                                            constraint "handoff_mensaje_pkey"
--
--   Es decir: con la tabla cerrada, `anon` sigue pudiendo **retroceder el contador desde
--   internet y hacer que falle el siguiente mensaje al corredor**. No es lectura de datos, es
--   una negación de servicio sobre el camino de escritura del producto, y se dispara con una
--   sola petición. Las secuencias se descubren del catálogo, no se escriben a mano: si mañana
--   alguna de estas tablas gana una, queda cubierta sin tocar este fichero.
--
--   POR QUÉ `ENABLE` Y NO `FORCE`. Las cinco son propiedad de `postgres`, que es el rol con el
--   que conecta el backend, y `ENABLE` no sujeta al dueño. Aislado con control el 2026-09-23:
--   un dueño SIN `bypassrls` ve sus filas con `ENABLE` y deja de verlas con `FORCE`; con
--   `bypassrls` las ve en ambos. En producción el dueño tiene las dos propiedades, así que está
--   exento por dos caminos — y aun así aquí se usa `ENABLE`, que es lo que la unidad autoriza.
--
--   QUÉ NO TOCA, A PROPÓSITO. Ni las otras quince tablas expuestas, ni las doce que tienen RLS
--   pero conservan `TRUNCATE`, ni `checkpoint_migrations`. Radio pequeño: primero lo crítico.
--   La segunda ola las clasifica por sensibilidad y uso real. Tampoco toca
--   `ALTER DEFAULT PRIVILEGES` — eso es la 034, y va aparte porque es una decisión distinta:
--   ésta contiene el daño de hoy, aquélla impide el de mañana.
--
--   Idempotente, transaccional y reversible. No depende de ninguna migración previa: las cinco
--   tablas las crea el código en caliente (`AsyncPostgresSaver.setup()` y
--   `ensure_handoff_tables()`), no un fichero de `migrations/`.
-- ============================================================

BEGIN;

-- `ENABLE ROW LEVEL SECURITY` pide un ACCESS EXCLUSIVE, y `checkpoints` es la tabla más
-- caliente de la base: 88 734 llamadas en la ventana medida. Sin tope, un ALTER que llegue
-- detrás de una transacción larga se queda esperando y bloquea a todo el que venga después,
-- incluidas las lecturas — o sea, congela la memoria del producto. Con el tope, la migración
-- entera se deshace y se reintenta en un momento más tranquilo.
--
-- Si esto vence, NO se sube el número: se busca la transacción que bloquea.
SET LOCAL lock_timeout = '3s';

-- ── 0 · COMPROBACIONES PREVIAS, FAIL-CLOSED ─────────────────────────────────────────
DO $$
DECLARE
    objetivo TEXT[] := ARRAY['checkpoints', 'checkpoint_blobs', 'checkpoint_writes',
                             'handoff_sesion', 'handoff_mensaje'];
    faltan    TEXT;
    no_dueno  TEXT;
    politicas INTEGER;
    publicadas TEXT;
BEGIN
    -- (a) Las cinco tienen que existir. Si falta alguna, esta migración no sabe en qué estado
    --     está el sistema y prefiere no aplicarse.
    SELECT string_agg(t, ', ') INTO faltan
      FROM unnest(objetivo) AS t
     WHERE to_regclass('public.' || t) IS NULL;
    IF faltan IS NOT NULL THEN
        RAISE EXCEPTION '033 ABORTA: no existen las tablas %. ¿Base equivocada?', faltan;
    END IF;

    -- (b) Quien aplica tiene que ser el DUEÑO de las cinco: es quien concedió estos
    --     privilegios y el único que puede revocarlos limpiamente.
    SELECT string_agg(c.relname, ', ') INTO no_dueno
      FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
     WHERE n.nspname = 'public' AND c.relname = ANY(objetivo)
       AND pg_get_userbyid(c.relowner) <> current_user;
    IF no_dueno IS NOT NULL THEN
        RAISE EXCEPTION
            '033 ABORTA: % no es dueño de %. Aplícala con el rol propietario (en producción, `postgres`).',
            current_user, no_dueno;
    END IF;

    -- (c) Si alguien ya creó una política, esta migración no sabe qué pretendía y no va a
    --     activar RLS por encima. Que lo mire una persona.
    SELECT count(*) INTO politicas
      FROM pg_policies WHERE schemaname = 'public' AND tablename = ANY(objetivo);
    IF politicas > 0 THEN
        RAISE EXCEPTION '033 ABORTA: ya existen % política(s) sobre estas tablas. Revísalas antes.', politicas;
    END IF;

    -- (d) Si estuvieran en una publicación de replicación, revocar `SELECT` cortaría en
    --     silencio a cualquier suscriptor. Medido hoy: ninguna. Si mañana la hay, que pare.
    SELECT string_agg(tablename, ', ') INTO publicadas
      FROM pg_publication_tables WHERE schemaname = 'public' AND tablename = ANY(objetivo);
    IF publicadas IS NOT NULL THEN
        RAISE EXCEPTION
            '033 ABORTA: % están en una publicación de replicación. Caracteriza quién consume Realtime antes.',
            publicadas;
    END IF;
END $$;

-- Conteos ANTES, para demostrar al final que esta migración no tocó una sola fila.
CREATE TEMP TABLE _033_conteos_antes ON COMMIT DROP AS
SELECT t AS tabla,
       (SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
         WHERE n.nspname = 'public' AND c.relname = t) AS existe
  FROM unnest(ARRAY['checkpoints', 'checkpoint_blobs', 'checkpoint_writes',
                    'handoff_sesion', 'handoff_mensaje']) AS t;

ALTER TABLE _033_conteos_antes ADD COLUMN filas BIGINT;
DO $$
DECLARE t TEXT; n BIGINT;
BEGIN
    FOR t IN SELECT tabla FROM _033_conteos_antes LOOP
        EXECUTE format('SELECT count(*) FROM public.%I', t) INTO n;
        UPDATE _033_conteos_antes SET filas = n WHERE tabla = t;
    END LOOP;
END $$;

-- ── 1 · RLS ─────────────────────────────────────────────────────────────────────────
--
-- Sin crear ninguna política: eso es lo que la deja cerrada para todo rol sujeto a RLS.
-- `ENABLE ROW LEVEL SECURITY` es idempotente; repetirlo no da error.
ALTER TABLE public.checkpoints        ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.checkpoint_blobs   ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.checkpoint_writes  ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.handoff_sesion     ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.handoff_mensaje    ENABLE ROW LEVEL SECURITY;

-- ── 2 · REVOKE, sobre las tablas Y sobre sus secuencias ─────────────────────────────
--
-- `REVOKE ALL PRIVILEGES` y no una lista de verbos, por portabilidad y por cobertura:
-- producción es PostgreSQL 17.6 y el CI es 15, donde `MAINTAIN` no existe como nombre de
-- privilegio (`ERROR: unrecognized privilege type`); y en 17, nombrar sólo los siete clásicos
-- dejaría `MAINTAIN` concedido.
--
-- El bloque comprueba que el rol EXISTE antes de revocar, y no por cortesía con el entorno
-- local: `REVOKE ... FROM rol_inexistente` es un ERROR, y dentro de esta transacción se
-- llevaría por delante el `ENABLE ROW LEVEL SECURITY` de arriba. Medido: la tabla quedaría con
-- `relrowsecurity = false` y la migración en rojo — el peor de los dos mundos. El PostgreSQL
-- del CI no tiene `anon`, `authenticated` ni `service_role`.
--
-- Las secuencias se DESCUBREN del catálogo (`pg_depend`), no se escriben a mano: hoy sólo
-- `handoff_mensaje` tiene una, pero si mañana otra gana un `serial`, queda cubierta sola.
DO $$
DECLARE
    objetivo TEXT[] := ARRAY['checkpoints', 'checkpoint_blobs', 'checkpoint_writes',
                             'handoff_sesion', 'handoff_mensaje'];
    rol TEXT;
    seq TEXT;
    n   INTEGER;
BEGIN
    FOREACH rol IN ARRAY ARRAY['anon', 'authenticated', 'service_role'] LOOP
        IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = rol) THEN
            RAISE NOTICE '033: el rol % no existe aquí; nada que revocar', rol;
            CONTINUE;
        END IF;

        EXECUTE format(
            'REVOKE ALL PRIVILEGES ON TABLE public.checkpoints, public.checkpoint_blobs, '
            'public.checkpoint_writes, public.handoff_sesion, public.handoff_mensaje FROM %I',
            rol);

        n := 0;
        FOR seq IN
            SELECT s.relname
              FROM pg_class s
              JOIN pg_depend d ON d.objid = s.oid AND d.classid = 'pg_class'::regclass
              JOIN pg_class t ON t.oid = d.refobjid
              JOIN pg_namespace ns ON ns.oid = s.relnamespace
             WHERE s.relkind = 'S' AND ns.nspname = 'public' AND t.relname = ANY(objetivo)
        LOOP
            EXECUTE format('REVOKE ALL PRIVILEGES ON SEQUENCE public.%I FROM %I', seq, rol);
            n := n + 1;
        END LOOP;

        RAISE NOTICE '033: privilegios revocados a % (5 tablas y % secuencia(s))', rol, n;
    END LOOP;
END $$;

-- ── 3 · VERIFICACIÓN FAIL-CLOSED ────────────────────────────────────────────────────
--
-- Dentro de la transacción a propósito: si algo de esto no se cumple, la excepción aborta y
-- el COMMIT nunca llega. El estado queda como estaba, nunca a medias.
DO $$
DECLARE
    objetivo TEXT[] := ARRAY['checkpoints', 'checkpoint_blobs', 'checkpoint_writes',
                             'handoff_sesion', 'handoff_mensaje'];
    sin_rls  TEXT;
    con_pol  INTEGER;
    quedan   TEXT;
    cambio   TEXT;
    t        TEXT;
    n        BIGINT;
BEGIN
    -- (a) RLS activado en las cinco, y ninguna con FORCE.
    SELECT string_agg(c.relname, ', ') INTO sin_rls
      FROM pg_class c JOIN pg_namespace n2 ON n2.oid = c.relnamespace
     WHERE n2.nspname = 'public' AND c.relname = ANY(objetivo) AND NOT c.relrowsecurity;
    IF sin_rls IS NOT NULL THEN
        RAISE EXCEPTION '033 FALLA: RLS no quedó activado en %', sin_rls;
    END IF;

    SELECT string_agg(c.relname, ', ') INTO sin_rls
      FROM pg_class c JOIN pg_namespace n2 ON n2.oid = c.relnamespace
     WHERE n2.nspname = 'public' AND c.relname = ANY(objetivo) AND c.relforcerowsecurity;
    IF sin_rls IS NOT NULL THEN
        RAISE EXCEPTION '033 FALLA: apareció FORCE en %, y esta unidad no lo autoriza', sin_rls;
    END IF;

    -- (b) Cero políticas: una permisiva devolvería el acceso por la otra puerta.
    SELECT count(*) INTO con_pol
      FROM pg_policies WHERE schemaname = 'public' AND tablename = ANY(objetivo);
    IF con_pol > 0 THEN
        RAISE EXCEPTION '033 FALLA: aparecieron % política(s); se esperaban 0', con_pol;
    END IF;

    -- (c) Ni un privilegio en pie, ni en las tablas ni en sus secuencias. Se comprueba sobre
    --     `aclexplode`, que enumera lo que REALMENTE hay, en vez de preguntar por una lista de
    --     privilegios que habría que mantener al día con cada versión de PostgreSQL.
    SELECT string_agg(format('%s:%s(%s)', x.relname, x.quien, x.priv), ', ') INTO quedan
      FROM (
        SELECT c.relname,
               CASE WHEN a.grantee = 0 THEN 'PUBLIC' ELSE pg_get_userbyid(a.grantee) END AS quien,
               a.privilege_type AS priv
          FROM pg_class c
          JOIN pg_namespace n2 ON n2.oid = c.relnamespace,
               aclexplode(c.relacl) a
         WHERE n2.nspname = 'public'
           AND (c.relname = ANY(objetivo)
                OR (c.relkind = 'S' AND EXISTS (
                      SELECT 1 FROM pg_depend d JOIN pg_class t2 ON t2.oid = d.refobjid
                       WHERE d.objid = c.oid AND d.classid = 'pg_class'::regclass
                         AND t2.relname = ANY(objetivo))))
      ) x
     WHERE x.quien IN ('anon', 'authenticated', 'service_role', 'PUBLIC');
    IF quedan IS NOT NULL THEN
        RAISE EXCEPTION '033 FALLA: quedan privilegios en pie -> %', quedan;
    END IF;

    -- (d) Ni una fila tocada. La promesa más fácil de dar y la que más conviene demostrar.
    FOR t IN SELECT tabla FROM _033_conteos_antes LOOP
        EXECUTE format('SELECT count(*) FROM public.%I', t) INTO n;
        IF n <> (SELECT filas FROM _033_conteos_antes WHERE tabla = t) THEN
            cambio := coalesce(cambio || ', ', '') ||
                      format('%s: %s -> %s', t, (SELECT filas FROM _033_conteos_antes WHERE tabla = t), n);
        END IF;
    END LOOP;
    IF cambio IS NOT NULL THEN
        RAISE EXCEPTION '033 FALLA: cambió el número de filas -> %', cambio;
    END IF;

    RAISE NOTICE '033 OK: RLS en las 5, 0 políticas, 0 privilegios externos (tablas y secuencias), 0 filas tocadas';
END $$;

-- Verificación legible, al estilo de las migraciones anteriores (debe devolver 5, 5 y 0).
SELECT count(*) FILTER (WHERE c.relrowsecurity)      AS con_rls,
       count(*)                                       AS tablas_del_perimetro_p0,
       count(*) FILTER (WHERE c.relforcerowsecurity)   AS con_force
  FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
 WHERE n.nspname = 'public'
   AND c.relname IN ('checkpoints', 'checkpoint_blobs', 'checkpoint_writes',
                     'handoff_sesion', 'handoff_mensaje');

COMMIT;

-- ── ROLLBACK ────────────────────────────────────────────────────────────────────────
--
-- Restaura EXACTAMENTE la postura medida el 2026-09-23, que es la postura EXPUESTA: vuelve a
-- publicar las conversaciones y los mensajes al corredor. No se ejecuta por costumbre.
--
-- Y si el motivo fuera que apareció un consumidor externo legítimo, esto NO es el remedio:
-- lo correcto es identificarlo y darle el privilegio mínimo que necesite, en una migración
-- correctiva propia. Devolver `ALL` a `anon` para desatascar un incidente es cambiar un
-- problema por el mismo problema.
--
--   BEGIN;
--   ALTER TABLE public.checkpoints       DISABLE ROW LEVEL SECURITY;
--   ALTER TABLE public.checkpoint_blobs  DISABLE ROW LEVEL SECURITY;
--   ALTER TABLE public.checkpoint_writes DISABLE ROW LEVEL SECURITY;
--   ALTER TABLE public.handoff_sesion    DISABLE ROW LEVEL SECURITY;
--   ALTER TABLE public.handoff_mensaje   DISABLE ROW LEVEL SECURITY;
--   GRANT ALL PRIVILEGES ON TABLE public.checkpoints, public.checkpoint_blobs,
--       public.checkpoint_writes, public.handoff_sesion, public.handoff_mensaje
--       TO anon, authenticated, service_role;
--   GRANT ALL PRIVILEGES ON SEQUENCE public.handoff_mensaje_id_seq
--       TO anon, authenticated, service_role;
--   COMMIT;
