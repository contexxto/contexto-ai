-- ============================================================
-- Migration 042: el DESTINO de la evidencia de lugar deja de ser escribible desde fuera
-- (PLACE-EVIDENCE-TARGET-AUTHORITY)
--
--   QUÉ HACE: revoca TODO privilegio directo sobre `public.activos_inmutables` a `PUBLIC`, `anon`,
--   `authenticated` y `service_role`. Nada más: ni RLS, ni FORCE, ni políticas, ni dueño, ni otras
--   tablas, ni Storage, ni Auth, ni privilegios por defecto, ni funciones. Cero filas leídas o
--   tocadas fuera de un `count(*)` de compuerta.
--
--   POR QUÉ, MEDIDO EN PRODUCCIÓN el 2026-09-30 (PostgreSQL 17.6, `BEGIN READ ONLY`; informe
--   `RESULTADO_PLACE_EVIDENCE_TARGET_AUTHORITY_CODE_0.1.md`):
--
--     · la 041 ya está aplicada: `servicios_evidencia` / `conectividad_evidencia` (jsonb, 0 filas
--       con evidencia), sus dos CHECK y el trigger que anula la evidencia desfasada viven AQUÍ;
--     · dueño `postgres` (el rol del backend: NOSUPERUSER, BYPASSRLS), RLS activado sin FORCE, una
--       sola política (`audit_ro_select_activos`, SELECT para `contexto_audit_ro`);
--     · `anon`, `authenticated` y `service_role` con los 8 privilegios de tabla (`arwdDxtm`),
--       concedidos por `postgres`, sin ACL de columna. `service_role` tiene BYPASSRLS: con la
--       clave `service_role`, un PATCH por PostgREST fabrica, mueve o borra evidencia, texto legado
--       y `geom`. `anon`/`authenticated` hoy chocan con el RLS en SELECT/INSERT/UPDATE/DELETE, pero
--       TRUNCATE, REFERENCES, TRIGGER y MAINTAIN NO pasan por el RLS, y una política errónea
--       mañana volvería efectivo el resto;
--     · ningún consumidor legítimo por esos roles: el frontend solo usa `supabase.auth` y
--       `supabase.storage`; el backend y los scripts conectan directo como `postgres`; la única
--       clave `service_role` del repo (`scripts/subir_y_generar_payload.py`) solo llama a la API
--       REST de Storage; en `pg_stat_statements` (desde el 2026-06-06, sin desalojos)
--       `service_role` no tocó jamás esta tabla ni ninguna de `public`, `authenticated` tampoco, y
--       `anon`, 2 veces: la sonda de la auditoría de perímetro del 2026-09-23;
--     · ninguna vía indirecta: ninguna función nombra la tabla; las SECURITY DEFINER ejecutables
--       por un rol público son `ST_EstimatedExtent` (PostGIS, C, solo lectura) y dos de `vault`
--       (escriben `vault.secrets`); sin vistas, reglas, herencia, publicación, FDW ni pg_cron;
--       ningún rol público tiene CREATE en `public`.
--
--   MISMO CONTRATO QUE LA 040 (y la 039/038/037). `REVOKE ALL PRIVILEGES` y no una lista de verbos
--   (producción es 17 —MAINTAIN existe— y el CI es 15: `ALL` vale en las dos), transacción única,
--   `lock_timeout`, tolerancia a roles inexistentes (el PostgreSQL del CI no los tiene) y
--   verificación fail-closed dentro, que mira el ACL de tabla, el de COLUMNA y el privilegio
--   EFECTIVO verbo a verbo.
--
--   LO QUE AÑADE SOBRE LA 040:
--     1. LA 041 ES PRECONDICIÓN. Esta migración cierra el destino de la evidencia; sin la 041
--        exacta (columnas, CHECK, función y trigger) no hay destino que cerrar: aborta.
--     2. EVIDENCIA BAJO AUTORIDAD ABIERTA. Si algún rol público conserva privilegios y ya existe
--        evidencia estructurada, esa evidencia se escribió mientras cualquiera podía escribirla:
--        no es de fiar y la 042 no la «bendice» cerrando la puerta después. Aborta. Con la
--        autoridad ya cerrada (segunda aplicación), la evidencia existente es legítima y la 042
--        es un no-op.
--     3. EL ACL DEBE SER UNO CONOCIDO. Cada rol público tiene o TODOS los privilegios de tabla (lo
--        medido) o NINGUNO; `contexto_audit_ro`, exactamente SELECT; nadie más; todo concedido
--        por el dueño (un privilegio concedido por otro sobreviviría al REVOKE del dueño); sin
--        ACL de columna. Cualquier otra cosa es deriva y aborta sin tocar nada.
--     4. PUENTES. Aborta si aparece una vista, regla, herencia o publicación sobre la tabla, una
--        función que la nombre, o una SECURITY DEFINER ejecutable por un rol público con SQL
--        dinámico (`EXECUTE`, `query_to_xml`, `dblink`).
--
--   LO QUE NO TOCA, A PROPÓSITO:
--     · `contexto_audit_ro` conserva SELECT (por su política). `postgres` conserva toda su
--       autoridad: es el dueño y el único escritor server-side.
--     · El EXECUTE de `activos_invalida_evidencia_desfasada()` (privilegios por defecto de
--       Supabase). Una función `RETURNS trigger` no se puede invocar directamente («trigger
--       functions can only be called as triggers») y, sin el privilegio TRIGGER sobre la tabla,
--       nadie más que el dueño puede engancharla aquí. Cerrar TRIGGER elimina el vector material.
--     · RLS sigue ENABLE sin FORCE: el dueño no se sujeta y además tiene BYPASSRLS.
--     · Los privilegios por defecto: los de `postgres` en `public` ya no conceden tablas (034);
--       los de `supabase_admin` quedan FUERA DE AUTORIDAD (una tabla recreada por él nacería
--       abierta; ver el informe).
--
--   QUIÉN LA APLICA: el DUEÑO de la tabla (en producción, `postgres`). La primera compuerta lo
--   exige.
--
--   Idempotente, transaccional y reversible (ver ROLLBACK al final, que NO es un estado deseable).
-- ============================================================

BEGIN;

-- Un REVOKE sobre la tabla puede esperar a lectores largos; el tope evita la cola.
SET LOCAL lock_timeout = '3s';

-- ── 0 · COMPROBACIONES PREVIAS, FAIL-CLOSED ─────────────────────────────────────────
DO $$
DECLARE
    tabla     CONSTANT regclass := to_regclass('public.activos_inmutables');
    dueno     TEXT;
    rls       BOOLEAN;
    force     BOOLEAN;
    lista     TEXT;
    n         INTEGER;
    rol       TEXT;
    privs_d   TEXT[];
    privs_r   TEXT[];
    abierta   BOOLEAN := false;
BEGIN
    IF tabla IS NULL THEN
        RAISE EXCEPTION '042 ABORTA: no existe public.activos_inmutables. ¿Base equivocada?';
    END IF;

    SELECT pg_get_userbyid(relowner), relrowsecurity, relforcerowsecurity INTO dueno, rls, force
      FROM pg_class WHERE oid = tabla;
    IF dueno <> current_user THEN
        RAISE EXCEPTION '042 ABORTA: el dueño de activos_inmutables no es quien aplica (% ≠ %). '
                        'Usa el rol propietario (en producción, `postgres`).', dueno, current_user;
    END IF;
    IF NOT rls THEN
        RAISE EXCEPTION '042 ABORTA: RLS está desactivado en activos_inmutables. No es el estado medido '
                        'y esta unidad no lo enciende.';
    END IF;
    IF force THEN
        RAISE EXCEPTION '042 ABORTA: activos_inmutables tiene FORCE activado. No es el estado medido.';
    END IF;

    -- La política: exactamente la de auditoría, y nada más.
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'contexto_audit_ro') THEN
        RAISE EXCEPTION '042 ABORTA: no existe el rol contexto_audit_ro, el único lector que se conserva.';
    END IF;
    SELECT count(*) INTO n FROM pg_policies WHERE schemaname = 'public' AND tablename = 'activos_inmutables';
    IF n <> 1 OR NOT EXISTS (
        SELECT 1 FROM pg_policies
         WHERE schemaname = 'public' AND tablename = 'activos_inmutables'
           AND policyname = 'audit_ro_select_activos' AND cmd = 'SELECT'
           AND roles = '{contexto_audit_ro}'::name[] AND permissive = 'PERMISSIVE'
           AND qual = 'true' AND with_check IS NULL) THEN
        RAISE EXCEPTION '042 ABORTA: las políticas de activos_inmutables no son las medidas '
                        '(una sola: audit_ro_select_activos, SELECT para contexto_audit_ro). Hay %.', n;
    END IF;

    -- La 041, exacta: es el destino que esta migración cierra.
    SELECT count(*) INTO n
      FROM pg_attribute a
     WHERE a.attrelid = tabla AND NOT a.attisdropped
       AND a.attname IN ('servicios_evidencia', 'conectividad_evidencia')
       AND a.atttypid = 'jsonb'::regtype AND NOT a.attnotnull AND NOT a.atthasdef;
    IF n <> 2 THEN
        RAISE EXCEPTION '042 ABORTA: la 041 no está aplicada (columnas de evidencia jsonb, nullable, sin '
                        'default: % de 2). Sin destino no hay nada que cerrar.', n;
    END IF;
    SELECT count(*) INTO n FROM pg_constraint
     WHERE conrelid = tabla AND contype = 'c' AND convalidated
       AND conname IN ('ck_activos_servicios_evidencia', 'ck_activos_conectividad_evidencia');
    IF n <> 2 THEN
        RAISE EXCEPTION '042 ABORTA: faltan los CHECK validados de la 041 (% de 2).', n;
    END IF;
    IF to_regprocedure('public.activos_invalida_evidencia_desfasada()') IS NULL
       OR (SELECT prosecdef FROM pg_proc
            WHERE oid = to_regprocedure('public.activos_invalida_evidencia_desfasada()')) THEN
        RAISE EXCEPTION '042 ABORTA: la función de la 041 no existe o dejó de ser SECURITY INVOKER.';
    END IF;
    SELECT count(*) INTO n FROM pg_trigger t
     WHERE t.tgrelid = tabla AND NOT t.tgisinternal;
    IF n <> 1 OR NOT EXISTS (
        SELECT 1 FROM pg_trigger t
         WHERE t.tgrelid = tabla AND t.tgname = 'trg_activos_invalida_evidencia_desfasada'
           AND t.tgtype = 19 AND t.tgenabled = 'O'
           AND t.tgfoid = to_regprocedure('public.activos_invalida_evidencia_desfasada()')
           AND (SELECT array_agg(a.attname::text ORDER BY a.attname) FROM pg_attribute a
                 WHERE a.attrelid = t.tgrelid AND a.attnum = ANY (t.tgattr::int2[]))
               = ARRAY['conectividad', 'geom', 'servicios_cercanos']) THEN
        RAISE EXCEPTION '042 ABORTA: los triggers de activos_inmutables no son el de la 041 exacto (hay %).', n;
    END IF;

    -- El ACL de tabla: uno CONOCIDO. Todo concedido por el dueño y sin opción de concesión.
    SELECT string_agg(format('%s por %s', CASE WHEN a.grantee = 0 THEN 'PUBLIC' ELSE pg_get_userbyid(a.grantee) END,
                             pg_get_userbyid(a.grantor)), ', ')
      INTO lista
      FROM pg_class c, aclexplode(c.relacl) a
     WHERE c.oid = tabla AND (a.grantor <> c.relowner OR (a.is_grantable AND a.grantee <> c.relowner));
    IF lista IS NOT NULL THEN
        RAISE EXCEPTION '042 ABORTA: hay privilegios concedidos por otro rol o con opción de concesión (%). '
                        'Sobrevivirían al REVOKE del dueño.', lista;
    END IF;
    SELECT string_agg(DISTINCT CASE WHEN a.grantee = 0 THEN 'PUBLIC' ELSE pg_get_userbyid(a.grantee) END, ', ')
      INTO lista
      FROM pg_class c, aclexplode(c.relacl) a
     WHERE c.oid = tabla
       AND (a.grantee = 0 OR (a.grantee <> c.relowner
            AND pg_get_userbyid(a.grantee) NOT IN ('anon', 'authenticated', 'service_role', 'contexto_audit_ro')));
    IF lista IS NOT NULL THEN
        RAISE EXCEPTION '042 ABORTA: el ACL de activos_inmutables tiene destinatarios no medidos (%). '
                        'Caracterízalos antes: podrían ser un consumidor.', lista;
    END IF;
    SELECT array_agg(a.privilege_type ORDER BY a.privilege_type) INTO privs_d
      FROM pg_class c, aclexplode(c.relacl) a WHERE c.oid = tabla AND a.grantee = c.relowner;
    SELECT array_agg(a.privilege_type ORDER BY a.privilege_type) INTO privs_r
      FROM pg_class c, aclexplode(c.relacl) a
     WHERE c.oid = tabla AND pg_get_userbyid(a.grantee) = 'contexto_audit_ro';
    IF privs_r IS DISTINCT FROM ARRAY['SELECT'] THEN
        RAISE EXCEPTION '042 ABORTA: contexto_audit_ro no tiene exactamente SELECT (%).', privs_r;
    END IF;
    FOREACH rol IN ARRAY ARRAY['anon', 'authenticated', 'service_role'] LOOP
        CONTINUE WHEN NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = rol);
        SELECT array_agg(a.privilege_type ORDER BY a.privilege_type) INTO privs_r
          FROM pg_class c, aclexplode(c.relacl) a WHERE c.oid = tabla AND pg_get_userbyid(a.grantee) = rol;
        IF privs_r IS NOT NULL AND privs_r IS DISTINCT FROM privs_d THEN
            RAISE EXCEPTION '042 ABORTA: % tiene un subconjunto de privilegios (%), ni todos ni ninguno: '
                            'estado intermedio o ajeno.', rol, privs_r;
        END IF;
        abierta := abierta OR privs_r IS NOT NULL;
    END LOOP;
    SELECT string_agg(format('%s:%s', a.attname, a.attacl), ', ') INTO lista
      FROM pg_attribute a WHERE a.attrelid = tabla AND a.attnum > 0 AND NOT a.attisdropped AND a.attacl IS NOT NULL;
    IF lista IS NOT NULL THEN
        RAISE EXCEPTION '042 ABORTA: hay ACL de columna en activos_inmutables (%). No es el estado medido.', lista;
    END IF;

    -- Evidencia escrita mientras la autoridad estaba abierta: no es de fiar; no se bendice.
    SELECT count(*) INTO n FROM public.activos_inmutables
     WHERE servicios_evidencia IS NOT NULL OR conectividad_evidencia IS NOT NULL;
    IF abierta AND n > 0 THEN
        RAISE EXCEPTION '042 ABORTA: ya hay % fila(s) con evidencia estructurada y la autoridad sigue abierta. '
                        'Esa evidencia se escribió cuando cualquiera podía escribirla: investígala antes.', n;
    END IF;

    -- Puentes que el REVOKE no cerraría.
    SELECT string_agg(DISTINCT v.oid::regclass::text, ', ') INTO lista
      FROM pg_depend d JOIN pg_rewrite rw ON rw.oid = d.objid JOIN pg_class v ON v.oid = rw.ev_class
     WHERE d.classid = 'pg_rewrite'::regclass AND d.refobjid = tabla AND v.oid <> tabla;
    IF lista IS NOT NULL THEN
        RAISE EXCEPTION '042 ABORTA: hay vistas que dependen de activos_inmutables (%). Servirían la tabla '
                        'con los privilegios de su dueño.', lista;
    END IF;
    SELECT string_agg(rulename::text, ', ') INTO lista
      FROM pg_rewrite WHERE ev_class = tabla AND rulename <> '_RETURN';
    IF lista IS NOT NULL THEN
        RAISE EXCEPTION '042 ABORTA: hay reglas sobre activos_inmutables (%).', lista;
    END IF;
    SELECT string_agg(format('%s→%s', inhrelid::regclass, inhparent::regclass), ', ') INTO lista
      FROM pg_inherits WHERE inhrelid = tabla OR inhparent = tabla;
    IF lista IS NOT NULL THEN
        RAISE EXCEPTION '042 ABORTA: activos_inmutables participa en herencia o particiones (%).', lista;
    END IF;
    SELECT string_agg(pubname, ', ') INTO lista
      FROM pg_publication_tables WHERE schemaname = 'public' AND tablename = 'activos_inmutables';
    IF lista IS NOT NULL THEN
        RAISE EXCEPTION '042 ABORTA: activos_inmutables está en una publicación de replicación (%). '
                        'Caracteriza el consumidor.', lista;
    END IF;
    SELECT string_agg(format('%s.%s', ns.nspname, p.proname), ', ') INTO lista
      FROM pg_proc p JOIN pg_namespace ns ON ns.oid = p.pronamespace
     WHERE ns.nspname NOT IN ('pg_catalog', 'information_schema')
       AND p.prosrc ILIKE '%activos_inmutables%';
    IF lista IS NOT NULL THEN
        RAISE EXCEPTION '042 ABORTA: hay funciones que nombran activos_inmutables (%). Caracterízalas antes: '
                        'una RPC SECURITY DEFINER la dejaría alcanzable.', lista;
    END IF;
    -- Solo roles que EXISTEN: `has_function_privilege` con un rol inexistente es un ERROR, y SQL
    -- no garantiza el orden de evaluación de un OR/AND que lo guardara.
    SELECT string_agg(format('%s.%s', ns.nspname, p.proname), ', ') INTO lista
      FROM pg_proc p JOIN pg_namespace ns ON ns.oid = p.pronamespace JOIN pg_language l ON l.oid = p.prolang
     WHERE p.prosecdef AND ns.nspname NOT IN ('pg_catalog', 'information_schema')
       AND l.lanname NOT IN ('c', 'internal')
       AND EXISTS (SELECT 1
                     FROM (SELECT 'public'::text AS r
                           UNION ALL SELECT rolname::text FROM pg_roles
                            WHERE rolname IN ('anon', 'authenticated', 'service_role')) roles_publicos
                    WHERE has_function_privilege(roles_publicos.r, p.oid, 'EXECUTE'))
       AND (p.prosrc ~* '\mexecute\M' OR p.prosrc ILIKE '%query_to_xml%' OR p.prosrc ILIKE '%dblink%');
    IF lista IS NOT NULL THEN
        RAISE EXCEPTION '042 ABORTA: hay funciones SECURITY DEFINER con SQL dinámico ejecutables por un rol '
                        'público (%). Podrían escribir activos_inmutables con la autoridad de su dueño.', lista;
    END IF;
END $$;

-- ── 1 · REVOKE ──────────────────────────────────────────────────────────────────────
--
-- `REVOKE ALL PRIVILEGES` y no una lista de verbos: producción es PostgreSQL 17.6 (MAINTAIN
-- existe, y lo tienen los tres roles) y el CI es 15. `ALL` vale en las dos, y un REVOKE de tabla
-- retira también los privilegios de columna.
--
-- `PUBLIC` siempre existe: sin guarda. Los tres roles, con guarda de existencia: un `REVOKE`
-- contra un rol inexistente es un ERROR que tumbaría la transacción.
REVOKE ALL PRIVILEGES ON TABLE public.activos_inmutables FROM PUBLIC;

DO $$
DECLARE
    rol TEXT;
BEGIN
    FOREACH rol IN ARRAY ARRAY['anon', 'authenticated', 'service_role'] LOOP
        IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = rol) THEN
            RAISE NOTICE '042: el rol % no existe aquí; nada que revocar', rol;
            CONTINUE;
        END IF;
        EXECUTE format('REVOKE ALL PRIVILEGES ON TABLE public.activos_inmutables FROM %I', rol);
        RAISE NOTICE '042: privilegios directos revocados a % sobre activos_inmutables', rol;
    END LOOP;
END $$;

-- ── 2 · VERIFICACIÓN FAIL-CLOSED (mide el efecto; no lo declara) ───────────────────
DO $$
DECLARE
    tabla  CONSTANT regclass := 'public.activos_inmutables'::regclass;
    verbos TEXT[] := ARRAY['SELECT', 'INSERT', 'UPDATE', 'DELETE', 'TRUNCATE', 'REFERENCES', 'TRIGGER'];
    rol    TEXT;
    priv   TEXT;
    lista  TEXT;
    n      INTEGER;
BEGIN
    IF current_setting('server_version_num')::int >= 170000 THEN
        verbos := array_append(verbos, 'MAINTAIN');
    END IF;

    -- Lo que REALMENTE queda en el ACL de tabla: el dueño (todo) y contexto_audit_ro (SELECT).
    SELECT string_agg(format('%s(%s)', CASE WHEN a.grantee = 0 THEN 'PUBLIC' ELSE pg_get_userbyid(a.grantee) END,
                             a.privilege_type), ', ')
      INTO lista
      FROM pg_class c, aclexplode(c.relacl) a
     WHERE c.oid = tabla AND a.grantee <> c.relowner
       AND NOT (pg_get_userbyid(a.grantee) = 'contexto_audit_ro' AND a.privilege_type = 'SELECT');
    IF lista IS NOT NULL THEN
        RAISE EXCEPTION '042 FALLA: quedan privilegios de tabla en pie -> %', lista;
    END IF;
    SELECT string_agg(format('%s:%s', a.attname, a.attacl), ', ') INTO lista
      FROM pg_attribute a WHERE a.attrelid = tabla AND a.attnum > 0 AND NOT a.attisdropped AND a.attacl IS NOT NULL;
    IF lista IS NOT NULL THEN
        RAISE EXCEPTION '042 FALLA: quedan privilegios de columna -> %', lista;
    END IF;

    -- El privilegio EFECTIVO, verbo a verbo y por columna (cubre herencias que el ACL no enseña).
    FOREACH rol IN ARRAY ARRAY['public', 'anon', 'authenticated', 'service_role'] LOOP
        CONTINUE WHEN rol <> 'public' AND NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = rol);
        FOREACH priv IN ARRAY verbos LOOP
            IF has_table_privilege(rol, tabla, priv) THEN
                RAISE EXCEPTION '042 FALLA: % conserva % efectivo sobre activos_inmutables', rol, priv;
            END IF;
        END LOOP;
        FOREACH priv IN ARRAY ARRAY['SELECT', 'INSERT', 'UPDATE', 'REFERENCES'] LOOP
            IF has_any_column_privilege(rol, tabla, priv) THEN
                RAISE EXCEPTION '042 FALLA: % conserva % efectivo sobre alguna columna de activos_inmutables', rol, priv;
            END IF;
        END LOOP;
    END LOOP;

    -- El lector de auditoría: SELECT y nada más.
    IF NOT has_table_privilege('contexto_audit_ro', tabla, 'SELECT') THEN
        RAISE EXCEPTION '042 FALLA: contexto_audit_ro perdió SELECT sobre activos_inmutables';
    END IF;
    FOREACH priv IN ARRAY verbos LOOP
        CONTINUE WHEN priv = 'SELECT';
        IF has_table_privilege('contexto_audit_ro', tabla, priv) THEN
            RAISE EXCEPTION '042 FALLA: contexto_audit_ro tiene % sobre activos_inmutables', priv;
        END IF;
    END LOOP;

    -- El dueño (quien aplica: el backend en producción) conserva toda su autoridad.
    FOREACH priv IN ARRAY verbos LOOP
        IF NOT has_table_privilege(current_user, tabla, priv) THEN
            RAISE EXCEPTION '042 FALLA: el dueño % perdió % sobre activos_inmutables', current_user, priv;
        END IF;
    END LOOP;

    -- Lo que no debía moverse, no se movió: RLS sin FORCE, la política, y la 041 exacta.
    IF NOT (SELECT relrowsecurity AND NOT relforcerowsecurity FROM pg_class WHERE oid = tabla) THEN
        RAISE EXCEPTION '042 FALLA: cambió el RLS o el FORCE de activos_inmutables';
    END IF;
    SELECT count(*) INTO n FROM pg_policies
     WHERE schemaname = 'public' AND tablename = 'activos_inmutables'
       AND NOT (policyname = 'audit_ro_select_activos' AND cmd = 'SELECT'
                AND roles = '{contexto_audit_ro}'::name[] AND qual = 'true' AND with_check IS NULL);
    IF n > 0 OR NOT EXISTS (SELECT 1 FROM pg_policies
                             WHERE schemaname = 'public' AND tablename = 'activos_inmutables'
                               AND policyname = 'audit_ro_select_activos') THEN
        RAISE EXCEPTION '042 FALLA: cambiaron las políticas de activos_inmutables';
    END IF;
    SELECT count(*) INTO n FROM pg_trigger t
     WHERE t.tgrelid = tabla AND NOT t.tgisinternal AND t.tgname = 'trg_activos_invalida_evidencia_desfasada'
       AND t.tgenabled = 'O' AND t.tgtype = 19
       AND t.tgfoid = to_regprocedure('public.activos_invalida_evidencia_desfasada()');
    IF n <> 1 OR (SELECT count(*) FROM pg_trigger WHERE tgrelid = tabla AND NOT tgisinternal) <> 1
       OR (SELECT count(*) FROM pg_constraint WHERE conrelid = tabla AND convalidated
            AND conname IN ('ck_activos_servicios_evidencia', 'ck_activos_conectividad_evidencia')) <> 2 THEN
        RAISE EXCEPTION '042 FALLA: la 041 (trigger o CHECK) no quedó intacta';
    END IF;

    RAISE NOTICE '042 OK: PUBLIC, anon, authenticated y service_role sin ningún privilegio directo ni efectivo '
                 'sobre activos_inmutables (tabla y columnas); contexto_audit_ro solo SELECT; dueño intacto; '
                 'RLS sin FORCE, política y 041 intactas';
END $$;

-- Verificación legible (debe devolver false en todo salvo contexto_audit_ro.select y el dueño).
SELECT r.rol,
       has_table_privilege(r.rol, 'public.activos_inmutables', 'SELECT') AS lee,
       has_table_privilege(r.rol, 'public.activos_inmutables', 'INSERT')
         OR has_table_privilege(r.rol, 'public.activos_inmutables', 'UPDATE')
         OR has_table_privilege(r.rol, 'public.activos_inmutables', 'DELETE')
         OR has_table_privilege(r.rol, 'public.activos_inmutables', 'TRUNCATE') AS muta,
       has_table_privilege(r.rol, 'public.activos_inmutables', 'TRIGGER') AS engancha_triggers
  FROM (SELECT 'public' AS rol
        UNION ALL SELECT rolname::text FROM pg_roles
         WHERE rolname IN ('anon', 'authenticated', 'service_role', 'contexto_audit_ro')
        UNION ALL SELECT current_user::text) r
 ORDER BY r.rol;

COMMIT;

-- ── ROLLBACK ────────────────────────────────────────────────────────────────────────
--
-- EMERGENCY REVERSAL TO PRIOR KNOWN-INSECURE AUTHORITY STATE. NO es un estado deseable: devuelve
-- a `anon`, `authenticated` y `service_role` TODOS los privilegios de tabla que tenían el
-- 2026-09-30 (`arwdDxtm` en PostgreSQL 17; `arwdDxt` en 15), con los que `service_role` —BYPASSRLS—
-- vuelve a poder fabricar, mover o borrar evidencia, texto legado y `geom` por PostgREST. Sólo con
-- autorización explícita y separada. `PUBLIC` no tenía nada y no recibe nada; `contexto_audit_ro`
-- y el dueño no se tocan. El texto del ACL queda en otro ORDEN (`contexto_audit_ro` antes que los
-- tres), pero los privilegios efectivos son exactamente los medidos.
--
--   BEGIN;
--   GRANT ALL PRIVILEGES ON TABLE public.activos_inmutables TO anon, authenticated, service_role;
--   COMMIT;
