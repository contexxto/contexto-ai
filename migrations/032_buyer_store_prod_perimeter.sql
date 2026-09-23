-- ============================================================
-- Migration 032: la memoria del comprador deja de estar abierta (Buyer Store · perímetro)
--
--   QUÉ HACE: activa RLS y revoca privilegios sobre DOS tablas —`buyer_context_heads` y
--   `buyer_context_revisions`— y nada más. Cero DDL de estructura, cero columnas, cero
--   índices, cero triggers. **No toca una sola fila**, no lee `context_json`, no borra nada.
--
--   POR QUÉ EXISTE, y no es una mejora: es el cierre de una exposición vigente. Medido en
--   producción el 2026-09-23, estas dos tablas —que guardan `BuyerContextV0`, la memoria
--   personal de un comprador, anclada a `auth.users.id`— estaban con `relrowsecurity=false`,
--   cero políticas, y `arwdDxtm` concedido a `anon`, `authenticated` y `service_role`. Con
--   la anon key que el frontend publica por diseño, `anon` obtuvo por HTTPS el conteo real
--   de filas de ambas, mientras las tablas de control con RLS devolvían cero a esa misma
--   clave. No es una inferencia sobre permisos: es el dato saliendo.
--
--   POR QUÉ NO BASTA CON RLS, Y ESTO ESTÁ MEDIDO, NO RAZONADO. La 030 activó RLS sin
--   revocar nada, y para lectura funciona: un rol sujeto a RLS y sin política no ve ninguna
--   fila. Pero **RLS no se aplica a TRUNCATE**. Reproducido en PostgreSQL 17 el 2026-09-23,
--   con RLS activado, cero políticas y el GRANT intacto:
--
--       SET ROLE anon;  SELECT count(*) → 0        (RLS filtra: parece seguro)
--       SET ROLE anon;  TRUNCATE tabla  → ÉXITO    (3 filas → 0)
--
--   Es decir: RLS a solas deja en pie el privilegio que destruye el dato. Mientras nadie
--   encuentre un camino para emitir un TRUNCATE con ese rol la puerta no se usa, pero seguir
--   dependiendo de que nadie lo encuentre no es una frontera. El REVOKE quita el privilegio
--   en vez de confiar en que no haya ruta hasta él. Por eso van los dos, y por eso el orden
--   de esta migración no es «RLS y además, por si acaso, un REVOKE».
--
--   Y TRUNCATE no es ni siquiera el peor. `arwdDxtm` son OCHO privilegios, y RLS sólo
--   gobierna los que operan sobre filas. Los otros cuatro quedan intactos, y uno de ellos es
--   ejecución de código. Reproducido en banco el 2026-09-23, con RLS activo todo el tiempo:
--
--     TRIGGER (t)     `anon` colgó un trigger con SU propia función sobre la tabla ajena.
--                     Cuando el DUEÑO insertó una fila, el código de `anon` corrió DENTRO de
--                     esa transacción, con `current_user` = el dueño, y copió la memoria del
--                     comprador a una tabla de `anon`. Antes de eso, el mismo trigger tumbó
--                     la escritura del backend con un `permission denied` — o sea, también
--                     es una negación de servicio sobre el producto
--     REFERENCES (x)  `anon` creó una clave foránea apuntando a la tabla protegida, y esa FK
--                     luego impidió el TRUNCATE legítimo del dueño
--     MAINTAIN (m)    `anon` ejecutó VACUUM y ANALYZE sobre la tabla
--
--   Nada de esto lo toca RLS. Por eso el REVOKE es la medida que cierra el perímetro y RLS
--   es el complemento que cubre el descuido de mañana, y no al revés.
--
--   POR QUÉ `service_role` TAMBIÉN, y es una decisión, no un descuido. `service_role` tiene
--   `rolbypassrls = true`: RLS no le aplica **en absoluto**. Medido en el mismo banco, con
--   RLS activado, `service_role` vio las 3 filas y pudo hacer UPDATE y DELETE. Para él, lo
--   único que existe es el GRANT. Dejarlo intacto habría significado que la memoria personal
--   de los compradores sigue legible y borrable para cualquiera que tenga la service key.
--   Se comprobó qué usa esa clave en este proyecto: sólo `scripts/subir_y_generar_payload.py`,
--   y sólo contra Supabase Storage (`/storage/v1/object/...`) — nunca contra estas tablas.
--   Revocarle estas dos no le quita nada que use.
--
--   POR QUÉ `ENABLE` Y NO `FORCE`. Porque el backend es el DUEÑO de ambas tablas y `ENABLE`
--   no sujeta al dueño. Aislado con control el 2026-09-23, sobre PostgreSQL 17:
--
--       dueño SIN bypassrls, ENABLE  → ve 3     dueño SIN bypassrls, FORCE → ve 0
--       dueño CON bypassrls, ENABLE  → ve 3     dueño CON bypassrls, FORCE → ve 3
--
--   En producción el backend conecta como `postgres`, que es dueño **y** tiene
--   `rolbypassrls`: está exento por dos caminos independientes. Aun así aquí se usa `ENABLE`,
--   que es lo que la unidad autoriza; `FORCE` es una decisión distinta y merece la suya.
--
--   QUÉ DEJA FUERA A PROPÓSITO. No toca `ALTER DEFAULT PRIVILEGES` del esquema. Eso
--   significa que una tabla NUEVA creada mañana en `public` volvería a nacer con DML para
--   los tres roles — la causa raíz sigue en pie y es de otra unidad, con su autorización.
--   Tampoco toca `inventory_source` ni `inventory_ingestion_event`, que por lo dicho arriba
--   siguen siendo truncables por `anon`. Mismo motivo: alcance.
--
--   Idempotente, transaccional y reversible. Depende de 028 y 029.
-- ============================================================

-- La migración entera va en UNA transacción, y no es adorno: en PostgreSQL el DDL es
-- transaccional, así que si cualquiera de las comprobaciones del final falla, el RLS y los
-- REVOKE se deshacen solos. Una aplicación a medias —RLS puesto, REVOKE caído— es
-- exactamente el peor resultado posible: el perímetro parecería cerrado sin estarlo.
BEGIN;

-- ── 0 · COMPROBACIONES PREVIAS, FAIL-CLOSED ─────────────────────────────────────────
--
-- Antes de tocar nada, esta migración se niega a correr si el terreno no es el que espera.
-- Prefiere no aplicarse a aplicarse mal.
DO $$
DECLARE
    faltan   TEXT;
    no_dueno TEXT;
    politicas INTEGER;
    secuencias INTEGER;
BEGIN
    -- (a) Las dos tablas tienen que existir. Sin 028/029 no hay nada que cerrar, y activar
    --     RLS sobre una tabla inexistente fallaría con un error mucho menos claro que éste.
    SELECT string_agg(t, ', ') INTO faltan
      FROM unnest(ARRAY['buyer_context_heads', 'buyer_context_revisions']) AS t
     WHERE to_regclass('public.' || t) IS NULL;
    IF faltan IS NOT NULL THEN
        RAISE EXCEPTION
            '032 ABORTA: faltan las tablas %. Aplica antes 028 y 029.', faltan;
    END IF;

    -- (b) Quien aplica tiene que ser el DUEÑO de ambas. Esta es la lección que dejó escrita
    --     la 030: «un REVOKE fallido tumbaría la migración entera». Aquí no se acepta el
    --     riesgo, se comprueba antes — porque además el dueño es quien concedió esos
    --     privilegios, y sólo el concedente puede revocarlos limpiamente.
    SELECT string_agg(c.relname, ', ') INTO no_dueno
      FROM pg_class c
      JOIN pg_namespace n ON n.oid = c.relnamespace
     WHERE n.nspname = 'public'
       AND c.relname IN ('buyer_context_heads', 'buyer_context_revisions')
       AND pg_get_userbyid(c.relowner) <> current_user;
    IF no_dueno IS NOT NULL THEN
        RAISE EXCEPTION
            '032 ABORTA: % no es dueño de %. Aplícala con el rol propietario (en producción, `postgres`).',
            current_user, no_dueno;
    END IF;

    -- (c) Si alguien ya creó una política sobre estas tablas, esta migración NO sabe qué
    --     pretendía y no va a activar RLS por encima. Que lo mire una persona.
    SELECT count(*) INTO politicas
      FROM pg_policies
     WHERE schemaname = 'public'
       AND tablename IN ('buyer_context_heads', 'buyer_context_revisions');
    IF politicas > 0 THEN
        RAISE EXCEPTION
            '032 ABORTA: ya existen % política(s) sobre el Buyer Store. Revísalas antes.',
            politicas;
    END IF;

    -- (d) Un REVOKE sobre la tabla no alcanza a una secuencia asociada. Hoy no hay ninguna
    --     (ninguna columna es serial), pero si mañana la hubiera, revocar sólo las tablas
    --     dejaría una puerta abierta sin que nadie se enterara.
    SELECT count(*) INTO secuencias
      FROM pg_class s
      JOIN pg_depend d  ON d.objid = s.oid AND d.classid = 'pg_class'::regclass
      JOIN pg_class t   ON t.oid = d.refobjid
      JOIN pg_namespace n ON n.oid = t.relnamespace
     WHERE s.relkind = 'S' AND n.nspname = 'public'
       AND t.relname IN ('buyer_context_heads', 'buyer_context_revisions');
    IF secuencias > 0 THEN
        RAISE EXCEPTION
            '032 ABORTA: hay % secuencia(s) asociadas al Buyer Store. Esta migración sólo cierra tablas.',
            secuencias;
    END IF;
END $$;

-- Conteos ANTES, para poder demostrar al final que esta migración no tocó una sola fila.
CREATE TEMP TABLE _032_conteos_antes ON COMMIT DROP AS
SELECT 'buyer_context_heads'     AS tabla, count(*) AS filas FROM public.buyer_context_heads
UNION ALL
SELECT 'buyer_context_revisions' AS tabla, count(*) AS filas FROM public.buyer_context_revisions;

-- ── 1 · RLS ─────────────────────────────────────────────────────────────────────────
--
-- Sin crear ninguna política, que es lo que la deja cerrada para todo rol sujeto a RLS.
-- `ALTER TABLE ... ENABLE ROW LEVEL SECURITY` es idempotente: repetirlo no da error.
--
-- `lock_timeout` antes del ALTER, y no es precaución de manual: `ENABLE ROW LEVEL SECURITY`
-- pide un ACCESS EXCLUSIVE sobre la tabla, y esto se aplica contra una base viva con el
-- backend manteniendo su pool abierto. Sin el tope, un ALTER que llegue detrás de una
-- transacción larga se queda esperando — y mientras espera, bloquea a todo el que venga
-- después, incluidas las lecturas. Con el tope, la migración falla rápido, la transacción
-- entera se deshace, y se reintenta en un momento más tranquilo. Fallar es barato aquí;
-- congelar la tabla del comprador en producción, no.
SET LOCAL lock_timeout = '3s';

ALTER TABLE public.buyer_context_heads     ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.buyer_context_revisions ENABLE ROW LEVEL SECURITY;

-- ── 2 · REVOKE ──────────────────────────────────────────────────────────────────────
--
-- `REVOKE ALL PRIVILEGES` y no la lista de los siete clásicos, por una razón concreta:
-- PostgreSQL 17 añadió el privilegio `MAINTAIN` (VACUUM, ANALYZE, REINDEX, CLUSTER, REFRESH
-- MATERIALIZED VIEW), y la producción es 17.6. Nombrar SELECT, INSERT, UPDATE, DELETE,
-- TRUNCATE, REFERENCES y TRIGGER habría dejado `MAINTAIN` concedido a `anon`. Comprobado en
-- banco: tras `REVOKE ALL`, `has_table_privilege('anon', tabla, 'MAINTAIN')` es `false`.
--
-- Los privilegios de producción son NOMINALES —`anon=arwdDxtm/postgres`, concedidos por el
-- dueño—, no heredados de `PUBLIC`. Se verificó con `aclexplode` que `PUBLIC` no tiene ni un
-- privilegio aquí; si lo tuviera, revocar a los roles por su nombre no habría quitado nada.
--
-- Va dentro de un bloque que comprueba que el rol EXISTE, y eso no es cortesía con el
-- entorno local: `REVOKE ... FROM un_rol_inexistente` es un ERROR, y como todo esto va en
-- una transacción, ese error se llevaría por delante el `ENABLE ROW LEVEL SECURITY` de
-- arriba. Medido: tras `BEGIN; ALTER TABLE ... ENABLE RLS; REVOKE ... FROM rol_que_no_existe;`
-- la tabla queda con `relrowsecurity = false`. El CI corre sobre un PostgreSQL de servicio
-- donde `anon`, `authenticated` y `service_role` no existen; sin esta guarda, la migración
-- reventaría allí y además dejaría un rastro engañoso.
--
-- Por la misma razón de portabilidad, el REVOKE dice `ALL PRIVILEGES` y no enumera verbos:
-- producción es 17.6 y el CI es PostgreSQL 15, donde `MAINTAIN` ni siquiera existe como
-- nombre de privilegio (`ERROR: unrecognized privilege type`). `ALL` vale en las dos.
DO $$
DECLARE
    rol TEXT;
BEGIN
    FOREACH rol IN ARRAY ARRAY['anon', 'authenticated', 'service_role'] LOOP
        IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = rol) THEN
            EXECUTE format(
                'REVOKE ALL PRIVILEGES ON TABLE public.buyer_context_heads, public.buyer_context_revisions FROM %I',
                rol);
            RAISE NOTICE '032: privilegios revocados a %', rol;
        ELSE
            RAISE NOTICE '032: el rol % no existe aquí; nada que revocar', rol;
        END IF;
    END LOOP;
END $$;

-- ── 3 · VERIFICACIÓN FAIL-CLOSED ────────────────────────────────────────────────────
--
-- Dentro de la transacción a propósito: si algo de esto no se cumple, la excepción aborta y
-- el COMMIT nunca llega. El estado queda como estaba, no a medias.
DO $$
DECLARE
    sin_rls      TEXT;
    con_politica INTEGER;
    quedan       TEXT;
    cambiaron    TEXT;
    priv         TEXT;
    rol          TEXT;
BEGIN
    -- (a) RLS activado en las dos.
    SELECT string_agg(c.relname, ', ') INTO sin_rls
      FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
     WHERE n.nspname = 'public'
       AND c.relname IN ('buyer_context_heads', 'buyer_context_revisions')
       AND NOT c.relrowsecurity;
    IF sin_rls IS NOT NULL THEN
        RAISE EXCEPTION '032 FALLA: RLS no quedó activado en %', sin_rls;
    END IF;

    -- (b) Cero políticas. Una política permisiva devolvería el acceso por la otra puerta.
    SELECT count(*) INTO con_politica
      FROM pg_policies
     WHERE schemaname = 'public'
       AND tablename IN ('buyer_context_heads', 'buyer_context_revisions');
    IF con_politica > 0 THEN
        RAISE EXCEPTION '032 FALLA: aparecieron % política(s); se esperaban 0', con_politica;
    END IF;

    -- (c) Ni un privilegio en pie para los tres roles. Se comprueba sobre `aclexplode`, que
    --     enumera lo que realmente hay, en vez de preguntar por una lista de privilegios que
    --     habría que mantener al día con cada versión de PostgreSQL.
    SELECT string_agg(format('%s:%s(%s)', t.relname, g, a.privilege_type), ', ')
      INTO quedan
      FROM pg_class t
      JOIN pg_namespace n ON n.oid = t.relnamespace,
           aclexplode(t.relacl) a,
           LATERAL (SELECT CASE WHEN a.grantee = 0 THEN 'PUBLIC'
                                ELSE pg_get_userbyid(a.grantee) END) AS x(g)
     WHERE n.nspname = 'public'
       AND t.relname IN ('buyer_context_heads', 'buyer_context_revisions')
       AND g IN ('anon', 'authenticated', 'service_role', 'PUBLIC');
    IF quedan IS NOT NULL THEN
        RAISE EXCEPTION '032 FALLA: quedan privilegios en pie -> %', quedan;
    END IF;

    -- (d) Por si acaso, la pregunta directa: ninguno de los tres puede leer.
    FOREACH rol IN ARRAY ARRAY['anon', 'authenticated', 'service_role'] LOOP
        IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = rol) THEN
            FOREACH priv IN ARRAY ARRAY['SELECT','INSERT','UPDATE','DELETE','TRUNCATE','REFERENCES','TRIGGER'] LOOP
                IF has_table_privilege(rol, 'public.buyer_context_heads', priv)
                   OR has_table_privilege(rol, 'public.buyer_context_revisions', priv) THEN
                    RAISE EXCEPTION '032 FALLA: % conserva % sobre el Buyer Store', rol, priv;
                END IF;
            END LOOP;
        END IF;
    END LOOP;

    -- (e) Ni una fila tocada. La promesa más fácil de dar y la que más conviene demostrar.
    SELECT string_agg(format('%s: %s -> %s', a.tabla, a.filas, d.filas), ', ')
      INTO cambiaron
      FROM _032_conteos_antes a
      JOIN (SELECT 'buyer_context_heads' AS tabla, count(*) AS filas FROM public.buyer_context_heads
            UNION ALL
            SELECT 'buyer_context_revisions', count(*) FROM public.buyer_context_revisions) d
        ON d.tabla = a.tabla
     WHERE d.filas <> a.filas;
    IF cambiaron IS NOT NULL THEN
        RAISE EXCEPTION '032 FALLA: cambió el número de filas -> %', cambiaron;
    END IF;

    RAISE NOTICE '032 OK: RLS activado, 0 políticas, 0 privilegios para anon/authenticated/service_role, 0 filas tocadas';
END $$;

-- Verificación legible, al estilo de las migraciones anteriores (debe devolver 2 y 2).
SELECT count(*) FILTER (WHERE c.relrowsecurity)                  AS tablas_con_rls,
       count(*)                                                  AS tablas_del_buyer_store,
       count(*) FILTER (WHERE c.relforcerowsecurity)              AS tablas_con_force
  FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
 WHERE n.nspname = 'public'
   AND c.relname IN ('buyer_context_heads', 'buyer_context_revisions');

COMMIT;

-- ── ROLLBACK ────────────────────────────────────────────────────────────────────────
--
-- Restaura EXACTAMENTE la postura medida en producción el 2026-09-23 —`arwdDxtm` para los
-- tres roles, RLS apagado—, que es la postura EXPUESTA. No se ejecuta por costumbre: sólo si
-- se demuestra que el cierre rompió algo, y sabiendo que deshacerlo vuelve a publicar la
-- memoria de los compradores.
--
--   BEGIN;
--   ALTER TABLE public.buyer_context_heads     DISABLE ROW LEVEL SECURITY;
--   ALTER TABLE public.buyer_context_revisions DISABLE ROW LEVEL SECURITY;
--   GRANT ALL PRIVILEGES ON TABLE public.buyer_context_heads, public.buyer_context_revisions
--       TO anon, authenticated, service_role;
--   COMMIT;
