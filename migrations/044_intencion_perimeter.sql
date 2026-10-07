-- ============================================================
-- Migration 044: el Motor de Intención deja de estar abierto a los roles externos
-- (SEC-PERIM-INTENCION-R0)
--
--   QUÉ HACE: activa RLS y revoca privilegios sobre las dos tablas del Motor de Intención
--   —`public.intencion_sesion` (estado actual por sesión) y `public.intencion_evento` (la serie
--   append-only del lift)— y sobre la secuencia de la segunda. Cero DDL de estructura. Cero filas
--   leídas o tocadas: ninguna sentencia de esta migración lee esas tablas ni su secuencia.
--
--   POR QUÉ, MEDIDO EN PRODUCCIÓN (PostgreSQL 17.6, solo catálogos, rol de auditoría de solo
--   lectura, `BEGIN READ ONLY` … `ROLLBACK`, 0 filas leídas; informes
--   `RESULTADO_SEC_PERIM_INTENCION_PREFLIGHT_0.1.md` —2026-10-07 05:19Z— y
--   `RESULTADO_SEC_PERIM_INTENCION_R0_0.1.md` —14:07Z y 15:02Z—):
--
--     · dueño `postgres` de las dos tablas y de `intencion_evento_id_seq` (el rol del backend:
--       NOSUPERUSER, BYPASSRLS);
--     · RLS desactivado, cero políticas; sin publicación, vistas, reglas, herencia, funciones,
--       triggers ni FK entrantes; sin ACL de columna (tampoco en columnas de sistema ni en la
--       secuencia); todo concedido por `postgres`, sin opción de concesión;
--     · `anon`, `authenticated` y `service_role` con los 8 privilegios de tabla (`arwdDxtm`)
--       sobre las dos, y USAGE, SELECT y UPDATE sobre la secuencia; `PUBLIC`, nada;
--     · ningún rol externo es miembro de nada (`authenticator`, solo de los tres);
--     · las únicas SECURITY DEFINER alcanzables por un externo con un dueño con autoridad son
--       las tres `ST_EstimatedExtent` (PostGIS, C) y `vault.create_secret` / `vault.update_secret`
--       (extensión `supabase_vault`, escriben `vault.secrets`); ningún event trigger es DEFINER;
--     · los privilegios por defecto de `postgres` en `public` ya no conceden nada (034/036).
--
--   EXPOSICIÓN EN LA CAPA DE PRIVILEGIOS DE LA BASE = VERIFICADA.
--   ALCANCE POR INTERNET (Data API / PostgREST) = INFERIDO: no se sondeó.
--   EXPLOTACIÓN O EXTRACCIÓN = DESCONOCIDA: esta migración no afirma ninguna.
--
--   Lo que esos privilegios dan a un rol externo: leer el resumen, las razones y las señales de
--   intención de cada sesión; inventar, editar o borrar filas (falsear la serie del lift y la
--   semántica interna del embudo); TRUNCATE y MAINTAIN, que RLS no gobierna; mover la secuencia
--   con `setval` y romper el siguiente INSERT del backend; y, como `intencion_sesion.activo_id`
--   tiene una FK saliente, usar el INSERT como oráculo de existencia de ids de inmuebles en una
--   tabla que ya está cerrada (042).
--
--   MISMO CONTRATO QUE LA 037/039/040 (y la 042). `ENABLE` sin `FORCE`, cero políticas, `REVOKE
--   ALL PRIVILEGES` a `PUBLIC` y a los tres roles, transacción única, `lock_timeout`, tolerancia a
--   roles inexistentes (el PostgreSQL del CI no los tiene) y verificación fail-closed dentro, que
--   mide el ACL de tabla, el de COLUMNA y el privilegio EFECTIVO verbo a verbo (MAINTAIN incluido
--   donde existe).
--
--   LO QUE AÑADE (la revisión adversarial lo pidió, y se midió antes en producción):
--     1. LA SECUENCIA se descubre en el catálogo (dependencia de propiedad y DEFAULT), no se supone
--        por el nombre, tiene que ser exactamente la medida, y todo DEFAULT tiene que ser de una forma
--        medida (lista blanca): ninguno alcanza otra secuencia ni llama a una función.
--     2. EL ACL TIENE QUE SER UNO CONOCIDO: todo concedido por el dueño, sin opción de concesión,
--        a nadie fuera del dueño, `PUBLIC` y los tres roles; sin ACL en NINGUNA columna (también
--        las de sistema y las de la secuencia: un REVOKE del dueño no retira lo que otro concedió).
--     3. NINGÚN CAMINO CON LA AUTORIDAD DE OTRO: ninguna SECURITY DEFINER (en cualquier lenguaje)
--        alcanzable por un externo —por EXECUTE, como trigger de una tabla que pueda escribir, como
--        event trigger o como soporte de un agregado— cuyo dueño sea superusuario o miembro del dueño de las tablas o de un
--        rol predefinido de datos, salvo cinco medidas en producción con su firma exacta (dos de
--        `supabase_vault`, tres `ST_EstimatedExtent` de PostGIS); ningún externo (ni `authenticator`)
--        miembro del dueño, de un superusuario o de un rol predefinido de datos o de servidor;
--        ninguna FK entrante (oráculo). Se enumera, no se busca por el texto del cuerpo: un texto se
--        puede disfrazar.
--     4. LOS PRIVILEGIOS POR DEFECTO del rol que aplica tienen que estar YA cerrados para TABLAS y
--        SECUENCIAS (034/036). Eso es lo que garantiza que una recreación en runtime
--        (`_INTENCION_DDL` de `app/routers/chat.py`, que no se toca) no herede privilegios
--        externos. Esta unidad no los cambia: si no lo están, aborta.
--     5. HUELLA ESTRUCTURAL: dueños, privilegios del dueño, restricciones (incluida la FK
--        saliente), columnas y DEFAULT se fotografían antes del efecto y se comparan después.
--     6. `search_path` fijado a `pg_catalog`: ninguna vista o función de otro esquema puede tapar
--        un catálogo y dar una compuerta en verde.
--
--   POR QUÉ `ENABLE` Y NO `FORCE`: el backend conecta como `postgres`, el dueño —el upsert de
--   `registrar_intencion`, la lectura del lift en `app/routers/assets.py`, el DDL en runtime de
--   `ensure_intencion_tables` y `scripts/baseline_intencion.py`— y `ENABLE` no sujeta al dueño;
--   además ese rol tiene `rolbypassrls`. Exento por dos caminos.
--
--   QUIÉN LA APLICA: el DUEÑO de las dos tablas y de la secuencia (en producción, `postgres`). La
--   segunda compuerta lo exige.
--
--   QUÉ NO TOCA: ninguna otra relación (tampoco la tabla a la que apunta la FK), ninguna fila,
--   ninguna columna, ninguna política, los privilegios del dueño, los privilegios por defecto,
--   `_INTENCION_DDL`.
--
--   Idempotente, transaccional y reversible (ver ROLLBACK al final, que NO es un estado deseable).
-- ============================================================

BEGIN;

-- `ENABLE ROW LEVEL SECURITY` pide un ACCESS EXCLUSIVE, y `registrar_intencion` escribe en las dos
-- tablas en cada turno de chat. El tope evita que la migración quede en cola bloqueando a quien
-- venga detrás: si no consigue un bloqueo en 3 s, aborta entera y no deja nada a medias. El tope es
-- POR ESPERA y son dos tablas: en el peor caso un escritor espera unos 6 s. `registrar_intencion`
-- corre en una tarea aparte (`create_task`): la respuesta del chat no espera, pero esa tarea ocupa
-- una conexión del pool mientras tanto. Aplicar en horario de poco tráfico.
SET LOCAL lock_timeout = '3s';
-- Solo el catálogo del sistema resuelve nombres sin esquema (y `pg_temp`, al final, nunca funciones).
SET LOCAL search_path = pg_catalog, pg_temp;

-- ── 0 · COMPROBACIONES PREVIAS, FAIL-CLOSED ─────────────────────────────────────────
DO $$
DECLARE
    nombre  TEXT;
    tablas  OID[];
    secs    OID[];
    dueno   OID;
    lista   TEXT;
    n       INTEGER;
    huella  TEXT;
BEGIN
    -- 1 · Las dos tablas existen y son tablas ordinarias.
    FOREACH nombre IN ARRAY ARRAY['public.intencion_sesion', 'public.intencion_evento'] LOOP
        IF to_regclass(nombre) IS NULL THEN
            RAISE EXCEPTION '044 ABORTA: no existe %. ¿Base equivocada?', nombre;
        END IF;
        IF (SELECT relkind FROM pg_class WHERE oid = to_regclass(nombre)) <> 'r' THEN
            RAISE EXCEPTION '044 ABORTA: % existe pero no es una tabla ordinaria', nombre;
        END IF;
    END LOOP;
    tablas := ARRAY[to_regclass('public.intencion_sesion'), to_regclass('public.intencion_evento')]::oid[];
    dueno := (SELECT relowner FROM pg_class WHERE oid = tablas[1]);

    -- 3 · La secuencia, DESCUBIERTA en el catálogo: la de propiedad (serial / identity) y la que use
    --     un DEFAULT. Tiene que ser exactamente la medida: `intencion_evento_id_seq`, y ninguna más.
    secs := ARRAY(
        SELECT s.oid FROM pg_class s
         WHERE s.relkind = 'S'
           AND (s.oid IN (SELECT d.objid FROM pg_depend d
                           WHERE d.classid = 'pg_class'::regclass AND d.refclassid = 'pg_class'::regclass
                             AND d.refobjid = ANY (tablas) AND d.deptype IN ('a', 'i'))
                OR s.oid IN (SELECT d.refobjid FROM pg_attrdef ad
                               JOIN pg_depend d ON d.classid = 'pg_attrdef'::regclass AND d.objid = ad.oid
                                               AND d.refclassid = 'pg_class'::regclass
                              WHERE ad.adrelid = ANY (tablas)))
         ORDER BY s.oid);
    IF to_regclass('public.intencion_evento_id_seq') IS NULL
       OR secs IS DISTINCT FROM ARRAY[to_regclass('public.intencion_evento_id_seq')]::oid[] THEN
        RAISE EXCEPTION '044 ABORTA: las secuencias de las tablas no son las medidas (se esperaba solo '
                        'intencion_evento_id_seq; hay: %)',
                        coalesce((SELECT string_agg(x::regclass::text, ', ') FROM unnest(secs) x), 'ninguna');
    END IF;
    --     …y todo DEFAULT es de una forma MEDIDA (lista blanca, no lista negra): `now()`, un entero, un
    --     booleano, un literal `jsonb`, o el `nextval` exacto de esa secuencia en `intencion_evento.id`. Así
    --     ninguna secuencia se alcanza por nombre (enlace tardío, sin dependencia) ni a través de una función.
    SELECT string_agg(format('%s.%s = %s', ad.adrelid::regclass, a.attname, pg_get_expr(ad.adbin, ad.adrelid)), ', ')
      INTO lista
      FROM pg_attrdef ad JOIN pg_attribute a ON a.attrelid = ad.adrelid AND a.attnum = ad.adnum
     WHERE ad.adrelid = ANY (tablas)
       AND NOT (pg_get_expr(ad.adbin, ad.adrelid) ~ '^(now\(\)|-?[0-9]+|true|false|''[^'']*''::jsonb)$'
                OR (ad.adrelid = tablas[2] AND a.attname = 'id'
                    AND pg_get_expr(ad.adbin, ad.adrelid) = format('nextval(%L::regclass)', secs[1]::regclass)));
    IF lista IS NOT NULL THEN
        RAISE EXCEPTION '044 ABORTA: hay DEFAULT que usan secuencias o funciones no medidas (%). Una secuencia '
                        'que no se descubre no se cierra.', lista;
    END IF;

    -- 2 · El dueño de las dos tablas y de la secuencia es quien aplica. (Un REVOKE de quien no es
    --     dueño ni concedente no revoca nada y solo emite un WARNING: cerraría en falso.)
    SELECT string_agg(format('%s (dueño %s)', c.oid::regclass, pg_get_userbyid(c.relowner)), ', ') INTO lista
      FROM pg_class c
     WHERE c.oid = ANY (tablas || secs)
       AND c.relowner <> (SELECT oid FROM pg_roles WHERE rolname = current_user);
    IF lista IS NOT NULL THEN
        RAISE EXCEPTION '044 ABORTA: el dueño no es quien aplica (%): %. Usa el rol propietario '
                        '(en producción, `postgres`).', current_user, lista;
    END IF;

    -- 4 · Sin políticas RLS y sin FORCE. (RLS ya activado se admite: reaplicación, o el botón del
    --     panel de Supabase, que solo lo enciende y no revoca nada.)
    SELECT count(*) INTO n FROM pg_policy WHERE polrelid = ANY (tablas);
    IF n > 0 THEN
        RAISE EXCEPTION '044 ABORTA: ya existen % política(s) RLS en las tablas de intención. Revísalas '
                        'antes: una política permisiva reabriría filas.', n;
    END IF;
    SELECT string_agg(c.oid::regclass::text, ', ') INTO lista
      FROM pg_class c WHERE c.oid = ANY (tablas) AND c.relforcerowsecurity;
    IF lista IS NOT NULL THEN
        RAISE EXCEPTION '044 ABORTA: FORCE ROW LEVEL SECURITY ya activado en (%). No es el estado medido.', lista;
    END IF;

    -- 5 · Ninguna publicación de replicación.
    SELECT string_agg(format('%s:%s', pubname, tablename), ', ') INTO lista
      FROM pg_publication_tables
     WHERE schemaname = 'public' AND tablename IN ('intencion_sesion', 'intencion_evento');
    IF lista IS NOT NULL THEN
        RAISE EXCEPTION '044 ABORTA: las tablas están en una publicación de replicación (%). '
                        'Caracteriza el consumidor.', lista;
    END IF;

    -- 6 · Nada que dependa de ellas: vistas o materializadas (sobre las tablas o la secuencia),
    --     reglas, herencia o particiones, FK entrantes. Una vista sin security_invoker serviría filas
    --     con los privilegios de su dueño; una FK entrante es un oráculo de existencia que el REVOKE
    --     no retira (REFERENCES solo se comprueba al crearla).
    SELECT string_agg(DISTINCT rw.ev_class::regclass::text, ', ') INTO lista
      FROM pg_depend d JOIN pg_rewrite rw ON rw.oid = d.objid
     WHERE d.classid = 'pg_rewrite'::regclass AND d.refclassid = 'pg_class'::regclass
       AND d.refobjid = ANY (tablas || secs) AND NOT (rw.ev_class = ANY (tablas));
    IF lista IS NOT NULL THEN
        RAISE EXCEPTION '044 ABORTA: hay vistas que dependen de las tablas o de la secuencia (%). '
                        'Sin caracterizarlas, el cierre sería falso.', lista;
    END IF;
    SELECT string_agg(format('%s.%s', ev_class::regclass, rulename), ', ') INTO lista
      FROM pg_rewrite WHERE ev_class = ANY (tablas) AND rulename <> '_RETURN';
    IF lista IS NOT NULL THEN
        RAISE EXCEPTION '044 ABORTA: hay reglas sobre las tablas de intención (%).', lista;
    END IF;
    SELECT string_agg(format('%s→%s', inhrelid::regclass, inhparent::regclass), ', ') INTO lista
      FROM pg_inherits WHERE inhrelid = ANY (tablas) OR inhparent = ANY (tablas);
    IF lista IS NOT NULL THEN
        RAISE EXCEPTION '044 ABORTA: las tablas participan en herencia o particiones (%).', lista;
    END IF;
    SELECT string_agg(format('%s.%s', conrelid::regclass, conname), ', ') INTO lista
      FROM pg_constraint
     WHERE contype = 'f' AND confrelid = ANY (tablas) AND NOT (conrelid = ANY (tablas));
    IF lista IS NOT NULL THEN
        RAISE EXCEPTION '044 ABORTA: hay FK entrantes hacia las tablas de intención (%). Son un oráculo de '
                        'existencia que el REVOKE no retira.', lista;
    END IF;

    -- 7 · Ninguna función (RPC) que las nombre o dependa de ellas: por TEXTO (plpgsql y SQL clásico
    --     no registran dependencias) y por DEPENDENCIA (cuerpo SQL estándar, tipo fila de la tabla
    --     o su arreglo, la secuencia).
    SELECT string_agg(DISTINCT p.oid::regprocedure::text, ', ') INTO lista
      FROM pg_proc p JOIN pg_namespace ns ON ns.oid = p.pronamespace
     WHERE ns.nspname NOT IN ('pg_catalog', 'information_schema')
       AND (p.prosrc ~* '\m(intencion_sesion|intencion_evento|intencion_evento_id_seq)\M'
            OR EXISTS (SELECT 1 FROM pg_depend d
                        WHERE d.classid = 'pg_proc'::regclass AND d.objid = p.oid
                          AND ((d.refclassid = 'pg_class'::regclass AND d.refobjid = ANY (tablas || secs))
                               OR (d.refclassid = 'pg_type'::regclass AND d.refobjid IN (
                                       SELECT t.oid FROM pg_type t JOIN pg_class c ON c.reltype = t.oid
                                        WHERE c.oid = ANY (tablas)
                                       UNION ALL
                                       SELECT t.typarray FROM pg_type t JOIN pg_class c ON c.reltype = t.oid
                                        WHERE c.oid = ANY (tablas))))));
    IF lista IS NOT NULL THEN
        RAISE EXCEPTION '044 ABORTA: hay funciones que nombran las tablas de intención o dependen de ellas '
                        '(%). Caracterízalas antes: una RPC SECURITY DEFINER las dejaría alcanzables.', lista;
    END IF;

    -- 8 · Ningún camino con la autoridad de otro: TODA SECURITY DEFINER, en cualquier lenguaje,
    --     alcanzable por un rol externo —por EXECUTE, como trigger de una tabla que pueda escribir,
    --     como event trigger o como función de soporte de un agregado que pueda ejecutar— cuyo dueño tenga autoridad sobre las tablas (superusuario, miembro de su
    --     dueño o de un rol predefinido de datos o de servidor). Se ENUMERA, sin mirar el cuerpo:
    --     `BEGIN ATOMIC`, `*_to_xml`, una cadena hacia una INVOKER dinámica o un nombre disfrazado no la
    --     sacan de la lista. Excepciones EXACTAS, MEDIDAS en producción (firma y extensión): las dos de
    --     `supabase_vault` (escriben `vault.secrets`) y las tres `ST_EstimatedExtent` de PostGIS (C, leen
    --     estadísticas de columnas geométricas, que estas tablas no tienen). Solo roles que EXISTEN:
    --     `has_*_privilege` con un rol inexistente es un ERROR.
    SELECT string_agg(DISTINCT format('%s [%s; dueño %s]', p.oid::regprocedure, x.via, pg_get_userbyid(p.proowner)), ', ')
      INTO lista
      FROM (SELECT p.oid AS f, 'EXECUTE' AS via
              FROM pg_proc p
             WHERE p.prosecdef AND p.prorettype NOT IN ('trigger'::regtype, 'event_trigger'::regtype)
               AND EXISTS (SELECT 1
                             FROM (SELECT 'public'::text AS r
                                   UNION ALL SELECT rolname::text FROM pg_roles
                                    WHERE rolname IN ('anon', 'authenticated', 'service_role')) externos
                            WHERE has_function_privilege(externos.r, p.oid, 'EXECUTE'))
            UNION ALL
            SELECT t.tgfoid, format('trigger de %s', t.tgrelid::regclass)
              FROM pg_trigger t JOIN pg_proc p ON p.oid = t.tgfoid
             WHERE NOT t.tgisinternal AND p.prosecdef
               AND EXISTS (SELECT 1
                             FROM (SELECT 'public'::text AS r
                                   UNION ALL SELECT rolname::text FROM pg_roles
                                    WHERE rolname IN ('anon', 'authenticated', 'service_role')) externos
                            WHERE has_table_privilege(externos.r, t.tgrelid, 'INSERT')
                               OR has_table_privilege(externos.r, t.tgrelid, 'UPDATE')
                               OR has_table_privilege(externos.r, t.tgrelid, 'DELETE')
                               OR has_table_privilege(externos.r, t.tgrelid, 'TRUNCATE')
                               OR has_any_column_privilege(externos.r, t.tgrelid, 'INSERT')
                               OR has_any_column_privilege(externos.r, t.tgrelid, 'UPDATE'))
            UNION ALL
            SELECT ev.evtfoid, format('event trigger %s', ev.evtname)
              FROM pg_event_trigger ev JOIN pg_proc p ON p.oid = ev.evtfoid
             WHERE ev.evtenabled <> 'D' AND p.prosecdef
            UNION ALL
            -- Las funciones de soporte de un agregado corren sin comprobar EXECUTE sobre ellas: basta
            -- con poder ejecutar el agregado.
            SELECT soporte.f, format('soporte del agregado %s', a.aggfnoid::regprocedure)
              FROM pg_aggregate a,
                   unnest(ARRAY[a.aggtransfn, a.aggfinalfn, a.aggcombinefn, a.aggserialfn, a.aggdeserialfn,
                                a.aggmtransfn, a.aggminvtransfn, a.aggmfinalfn]::oid[]) AS soporte (f)
              JOIN pg_proc p ON p.oid = soporte.f
             WHERE p.prosecdef
               AND EXISTS (SELECT 1
                             FROM (SELECT 'public'::text AS r
                                   UNION ALL SELECT rolname::text FROM pg_roles
                                    WHERE rolname IN ('anon', 'authenticated', 'service_role')) externos
                            WHERE has_function_privilege(externos.r, a.aggfnoid, 'EXECUTE'))) x
      JOIN pg_proc p ON p.oid = x.f
      JOIN pg_namespace ns ON ns.oid = p.pronamespace
      JOIN pg_roles o ON o.oid = p.proowner
     WHERE ns.nspname NOT IN ('pg_catalog', 'information_schema')
       AND (o.rolsuper OR pg_has_role(p.proowner, dueno, 'MEMBER')
            OR EXISTS (SELECT 1 FROM pg_roles r
                        WHERE r.rolname IN ('pg_read_all_data', 'pg_write_all_data', 'pg_maintain',
                                            'pg_execute_server_program', 'pg_read_server_files',
                                            'pg_write_server_files')
                          AND pg_has_role(p.proowner, r.oid, 'MEMBER')))
       AND NOT EXISTS (SELECT 1
                         FROM pg_depend d JOIN pg_extension e ON e.oid = d.refobjid,
                              (VALUES ('supabase_vault', 'vault.create_secret(text,text,text,uuid)'),
                                      ('supabase_vault', 'vault.update_secret(uuid,text,text,text,uuid)'),
                                      ('postgis', 'public.st_estimatedextent(text,text,text,boolean)'),
                                      ('postgis', 'public.st_estimatedextent(text,text,text)'),
                                      ('postgis', 'public.st_estimatedextent(text,text)')) medidas (ext, firma)
                        WHERE d.classid = 'pg_proc'::regclass AND d.objid = p.oid
                          AND d.refclassid = 'pg_extension'::regclass AND d.deptype = 'e'
                          AND e.extname = medidas.ext AND p.oid::regprocedure::text = medidas.firma);
    IF lista IS NOT NULL THEN
        RAISE EXCEPTION '044 ABORTA: hay funciones SECURITY DEFINER alcanzables por un rol externo cuyo dueño '
                        'tiene autoridad sobre las tablas (%). Podrían leerlas o escribirlas con esa autoridad; '
                        'caracterízalas antes.', lista;
    END IF;

    -- 9 · Ningún trigger sobre las tablas (los internos de la FK no cuentan).
    SELECT string_agg(format('%s.%s', t.tgrelid::regclass, t.tgname), ', ') INTO lista
      FROM pg_trigger t WHERE NOT t.tgisinternal AND t.tgrelid = ANY (tablas);
    IF lista IS NOT NULL THEN
        RAISE EXCEPTION '044 ABORTA: hay triggers sobre las tablas de intención (%). Caracterízalos antes.', lista;
    END IF;

    -- 10 · El ACL es uno CONOCIDO. (a) Todo concedido por el dueño y sin opción de concesión: lo que
    --      concedió otro sobreviviría al REVOKE del dueño. (b) Nadie fuera del dueño, PUBLIC y los
    --      tres roles: otro destinatario podría ser un consumidor. (c) Sin ACL en NINGUNA columna
    --      —también las de sistema y las de la secuencia—. (d) Ningún externo (ni `authenticator`,
    --      el rol con el que entra PostgREST) es miembro, con o sin herencia, del dueño, de un
    --      superusuario o de un rol predefinido de datos o de servidor.
    SELECT string_agg(format('%s:%s por %s', c.oid::regclass,
                             CASE WHEN a.grantee = 0 THEN 'PUBLIC' ELSE pg_get_userbyid(a.grantee) END,
                             pg_get_userbyid(a.grantor)), ', ') INTO lista
      FROM pg_class c, aclexplode(c.relacl) a
     WHERE c.oid = ANY (tablas || secs)
       AND (a.grantor <> c.relowner OR (a.is_grantable AND a.grantee <> c.relowner));
    IF lista IS NOT NULL THEN
        RAISE EXCEPTION '044 ABORTA: hay privilegios concedidos por otro rol o con opción de concesión (%). '
                        'Sobrevivirían al REVOKE del dueño.', lista;
    END IF;
    SELECT string_agg(DISTINCT format('%s:%s', c.oid::regclass, pg_get_userbyid(a.grantee)), ', ') INTO lista
      FROM pg_class c, aclexplode(c.relacl) a
     WHERE c.oid = ANY (tablas || secs)
       AND a.grantee <> 0 AND a.grantee <> c.relowner
       AND pg_get_userbyid(a.grantee) NOT IN ('anon', 'authenticated', 'service_role');
    IF lista IS NOT NULL THEN
        RAISE EXCEPTION '044 ABORTA: el ACL tiene destinatarios no medidos (%). Caracterízalos antes: '
                        'podrían ser un consumidor.', lista;
    END IF;
    SELECT string_agg(format('%s.%s:%s', a.attrelid::regclass, a.attname, a.attacl), ', ') INTO lista
      FROM pg_attribute a
     WHERE a.attrelid = ANY (tablas || secs) AND NOT a.attisdropped AND a.attacl IS NOT NULL;
    IF lista IS NOT NULL THEN
        RAISE EXCEPTION '044 ABORTA: hay ACL de columna en las tablas de intención o su secuencia (%). No es el '
                        'estado medido.', lista;
    END IF;
    SELECT string_agg(DISTINCT format('%s∈%s', m.rolname, r.rolname), ', ') INTO lista
      FROM pg_roles m, pg_roles r
     WHERE m.rolname IN ('anon', 'authenticated', 'service_role', 'authenticator')
       AND r.oid <> m.oid
       AND (r.oid = dueno OR r.rolsuper
            OR r.rolname IN ('pg_read_all_data', 'pg_write_all_data', 'pg_maintain',
                             'pg_execute_server_program', 'pg_read_server_files', 'pg_write_server_files'))
       AND pg_has_role(m.oid, r.oid, 'MEMBER');
    IF lista IS NOT NULL THEN
        RAISE EXCEPTION '044 ABORTA: un rol externo es miembro del dueño, de un superusuario o de un rol '
                        'predefinido de datos (%): alcanzaría las tablas sin estar en el ACL.', lista;
    END IF;

    -- 11 · Los privilegios por defecto del rol que aplica ya no conceden TABLAS ni SECUENCIAS a nadie
    --      (034/036), por los dos ámbitos: global (`defaclnamespace = 0`, que un INNER JOIN perdería)
    --      y `public`. Es la garantía de que `_INTENCION_DDL` no recree las tablas abiertas.
    SELECT string_agg(format('%s/%s:%s(%s)',
                             CASE WHEN d.defaclnamespace = 0 THEN 'global' ELSE ns.nspname END,
                             CASE d.defaclobjtype WHEN 'r' THEN 'TABLAS' ELSE 'SECUENCIAS' END,
                             CASE WHEN a.grantee = 0 THEN 'PUBLIC' ELSE pg_get_userbyid(a.grantee) END,
                             a.privilege_type), ', ') INTO lista
      FROM pg_default_acl d
      LEFT JOIN pg_namespace ns ON ns.oid = d.defaclnamespace,
           aclexplode(d.defaclacl) a
     WHERE d.defaclobjtype IN ('r', 'S')
       AND (d.defaclnamespace = 0 OR ns.nspname = 'public')
       AND d.defaclrole = (SELECT oid FROM pg_roles WHERE rolname = current_user)
       AND a.grantee <> d.defaclrole;
    IF lista IS NOT NULL THEN
        RAISE EXCEPTION '044 ABORTA: los privilegios por defecto de % todavía conceden (%). Sin 034/036 una '
                        'recreación en runtime nacería abierta; esta unidad no los cambia.', current_user, lista;
    END IF;

    -- Huella estructural (dueños, privilegios del dueño, restricciones con su definición, columnas y
    -- DEFAULT) y el conjunto de secuencias, para el efecto y la verificación de abajo. Locales a la
    -- transacción.
    SELECT string_agg(h.x, ' | ' ORDER BY h.x) INTO huella FROM (
        SELECT format('rel %s %s %s', c.oid::regclass, c.relkind, pg_get_userbyid(c.relowner)) AS x
          FROM pg_class c WHERE c.oid = ANY (tablas || secs)
        UNION ALL
        SELECT format('own %s %s', c.oid::regclass, string_agg(a.privilege_type, ',' ORDER BY a.privilege_type))
          FROM pg_class c,
               aclexplode(coalesce(c.relacl, acldefault(CASE WHEN c.relkind = 'S' THEN 's' ELSE 'r' END::"char",
                                                        c.relowner))) a
         WHERE c.oid = ANY (tablas || secs) AND a.grantee = c.relowner
         GROUP BY c.oid
        UNION ALL
        SELECT format('con %s %s %s', co.conrelid::regclass, co.conname, pg_get_constraintdef(co.oid))
          FROM pg_constraint co WHERE co.conrelid = ANY (tablas) OR co.confrelid = ANY (tablas)
        UNION ALL
        SELECT format('col %s %s %s %s', a.attrelid::regclass, a.attnum, a.attname,
                      format_type(a.atttypid, a.atttypmod))
          FROM pg_attribute a WHERE a.attrelid = ANY (tablas) AND a.attnum > 0 AND NOT a.attisdropped
        UNION ALL
        SELECT format('def %s %s %s', ad.adrelid::regclass, ad.adnum, pg_get_expr(ad.adbin, ad.adrelid))
          FROM pg_attrdef ad WHERE ad.adrelid = ANY (tablas)
    ) h;
    PERFORM set_config('contexto_044.huella', huella, true);
    PERFORM set_config('contexto_044.secuencias', array_to_string(secs, ','), true);
    RAISE NOTICE '044: comprobaciones previas superadas (2 tablas, 1 secuencia, dueño %)', current_user;
END $$;

-- ── 1 · RLS ─────────────────────────────────────────────────────────────────────────
ALTER TABLE public.intencion_sesion ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.intencion_evento ENABLE ROW LEVEL SECURITY;

-- ── 2 · REVOKE ──────────────────────────────────────────────────────────────────────
--
-- `REVOKE ALL PRIVILEGES` y no una lista de verbos: producción es PostgreSQL 17.6 (MAINTAIN existe,
-- y lo tienen los tres roles) y el CI es 15. `ALL` vale en las dos, y un REVOKE de tabla retira
-- también los privilegios de columna que concedió el mismo dueño.
--
-- `PUBLIC` siempre existe: sin guarda. Los tres roles, con guarda de existencia: un `REVOKE` contra
-- un rol inexistente es un ERROR que, dentro de esta transacción, se llevaría por delante el
-- `ENABLE ROW LEVEL SECURITY` de arriba. La secuencia es la que descubrió la compuerta 3.
REVOKE ALL PRIVILEGES ON TABLE public.intencion_sesion, public.intencion_evento FROM PUBLIC;

DO $$
DECLARE
    rol TEXT;
    seq REGCLASS;
BEGIN
    FOR seq IN SELECT x::oid::regclass FROM unnest(string_to_array(current_setting('contexto_044.secuencias'), ',')) x
    LOOP
        EXECUTE format('REVOKE ALL PRIVILEGES ON SEQUENCE %s FROM PUBLIC', seq);
    END LOOP;

    FOREACH rol IN ARRAY ARRAY['anon', 'authenticated', 'service_role'] LOOP
        IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = rol) THEN
            RAISE NOTICE '044: el rol % no existe aquí; nada que revocar', rol;
            CONTINUE;
        END IF;
        EXECUTE format('REVOKE ALL PRIVILEGES ON TABLE public.intencion_sesion, public.intencion_evento FROM %I', rol);
        FOR seq IN SELECT x::oid::regclass FROM unnest(string_to_array(current_setting('contexto_044.secuencias'), ',')) x
        LOOP
            EXECUTE format('REVOKE ALL PRIVILEGES ON SEQUENCE %s FROM %I', seq, rol);
        END LOOP;
        RAISE NOTICE '044: privilegios revocados a % (dos tablas y su secuencia)', rol;
    END LOOP;
END $$;

-- ── 3 · VERIFICACIÓN FAIL-CLOSED (mide el efecto; no lo declara) ───────────────────
DO $$
DECLARE
    tablas  OID[] := ARRAY[to_regclass('public.intencion_sesion'), to_regclass('public.intencion_evento')]::oid[];
    secs    OID[];
    dueno   OID;
    verbos  TEXT[] := ARRAY['SELECT', 'INSERT', 'UPDATE', 'DELETE', 'TRUNCATE', 'REFERENCES', 'TRIGGER'];
    rel     OID;
    rol     TEXT;
    priv    TEXT;
    lista   TEXT;
    n       INTEGER;
    huella  TEXT;
BEGIN
    IF current_setting('server_version_num')::int >= 170000 THEN
        verbos := array_append(verbos, 'MAINTAIN');
    END IF;
    dueno := (SELECT relowner FROM pg_class WHERE oid = tablas[1]);

    -- El conjunto de secuencias no cambió (se vuelve a descubrir, no se arrastra).
    secs := ARRAY(
        SELECT s.oid FROM pg_class s
         WHERE s.relkind = 'S'
           AND (s.oid IN (SELECT d.objid FROM pg_depend d
                           WHERE d.classid = 'pg_class'::regclass AND d.refclassid = 'pg_class'::regclass
                             AND d.refobjid = ANY (tablas) AND d.deptype IN ('a', 'i'))
                OR s.oid IN (SELECT d.refobjid FROM pg_attrdef ad
                               JOIN pg_depend d ON d.classid = 'pg_attrdef'::regclass AND d.objid = ad.oid
                                               AND d.refclassid = 'pg_class'::regclass
                              WHERE ad.adrelid = ANY (tablas)))
         ORDER BY s.oid);
    IF array_to_string(secs, ',') IS DISTINCT FROM current_setting('contexto_044.secuencias') THEN
        RAISE EXCEPTION '044 FALLA: cambió el conjunto de secuencias de las tablas';
    END IF;

    -- RLS activado, sin FORCE, cero políticas.
    SELECT string_agg(c.oid::regclass::text, ', ') INTO lista
      FROM pg_class c WHERE c.oid = ANY (tablas) AND NOT c.relrowsecurity;
    IF lista IS NOT NULL THEN
        RAISE EXCEPTION '044 FALLA: RLS no quedó activado en %', lista;
    END IF;
    SELECT string_agg(c.oid::regclass::text, ', ') INTO lista
      FROM pg_class c WHERE c.oid = ANY (tablas) AND c.relforcerowsecurity;
    IF lista IS NOT NULL THEN
        RAISE EXCEPTION '044 FALLA: apareció FORCE en %, y esta unidad no lo autoriza', lista;
    END IF;
    SELECT count(*) INTO n FROM pg_policy WHERE polrelid = ANY (tablas);
    IF n > 0 THEN
        RAISE EXCEPTION '044 FALLA: aparecieron % política(s); se esperaban 0', n;
    END IF;

    -- Lo que REALMENTE queda en el ACL de las tablas y la secuencia: el dueño, y nadie más. Y en
    -- ninguna columna (de usuario, de sistema o de la secuencia), nadie.
    SELECT string_agg(format('%s:%s(%s)', c.oid::regclass,
                             CASE WHEN a.grantee = 0 THEN 'PUBLIC' ELSE pg_get_userbyid(a.grantee) END,
                             a.privilege_type), ', ') INTO lista
      FROM pg_class c, aclexplode(c.relacl) a
     WHERE c.oid = ANY (tablas || secs) AND a.grantee <> c.relowner;
    IF lista IS NOT NULL THEN
        RAISE EXCEPTION '044 FALLA: quedan privilegios en pie -> %', lista;
    END IF;
    SELECT string_agg(format('%s.%s:%s', a.attrelid::regclass, a.attname, a.attacl), ', ') INTO lista
      FROM pg_attribute a
     WHERE a.attrelid = ANY (tablas || secs) AND NOT a.attisdropped AND a.attacl IS NOT NULL;
    IF lista IS NOT NULL THEN
        RAISE EXCEPTION '044 FALLA: quedan privilegios de columna -> %', lista;
    END IF;

    -- El privilegio EFECTIVO de PUBLIC y de cada rol externo, verbo a verbo, por columna y sobre la
    -- secuencia (cubre herencias y membresías que el ACL no enseña). `service_role` tiene BYPASSRLS:
    -- RLS no lo detiene, solo el REVOKE.
    FOREACH rol IN ARRAY ARRAY['public', 'anon', 'authenticated', 'service_role'] LOOP
        CONTINUE WHEN rol <> 'public' AND NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = rol);
        FOREACH rel IN ARRAY tablas LOOP
            FOREACH priv IN ARRAY verbos LOOP
                IF has_table_privilege(rol, rel, priv) THEN
                    RAISE EXCEPTION '044 FALLA: % conserva % efectivo sobre %', rol, priv, rel::regclass;
                END IF;
            END LOOP;
            FOREACH priv IN ARRAY ARRAY['SELECT', 'INSERT', 'UPDATE', 'REFERENCES'] LOOP
                IF has_any_column_privilege(rol, rel, priv) THEN
                    RAISE EXCEPTION '044 FALLA: % conserva % efectivo sobre alguna columna de %', rol, priv, rel::regclass;
                END IF;
            END LOOP;
        END LOOP;
        FOREACH rel IN ARRAY secs LOOP
            FOREACH priv IN ARRAY ARRAY['USAGE', 'SELECT', 'UPDATE'] LOOP
                IF has_sequence_privilege(rol, rel, priv) THEN
                    RAISE EXCEPTION '044 FALLA: % conserva % efectivo sobre la secuencia %', rol, priv, rel::regclass;
                END IF;
            END LOOP;
        END LOOP;
    END LOOP;

    -- El dueño (quien aplica: el backend en producción) conserva lo que el backend usa. Que sus
    -- privilegios no cambiaron en absoluto lo dice la huella de abajo.
    FOREACH rel IN ARRAY tablas LOOP
        FOREACH priv IN ARRAY ARRAY['SELECT', 'INSERT', 'UPDATE', 'DELETE'] LOOP
            IF NOT has_table_privilege(current_user, rel, priv) THEN
                RAISE EXCEPTION '044 FALLA: el dueño % perdió % sobre %', current_user, priv, rel::regclass;
            END IF;
        END LOOP;
    END LOOP;
    FOREACH rel IN ARRAY secs LOOP
        FOREACH priv IN ARRAY ARRAY['USAGE', 'SELECT', 'UPDATE'] LOOP
            IF NOT has_sequence_privilege(current_user, rel, priv) THEN
                RAISE EXCEPTION '044 FALLA: el dueño % perdió % sobre la secuencia %', current_user, priv, rel::regclass;
            END IF;
        END LOOP;
    END LOOP;

    -- Ningún puente apareció: vistas, reglas, herencia, FK entrantes, publicaciones, triggers,
    -- funciones que las nombren o dependan de ellas (tipo fila incluido).
    SELECT (SELECT count(*) FROM pg_depend d JOIN pg_rewrite rw ON rw.oid = d.objid
             WHERE d.classid = 'pg_rewrite'::regclass AND d.refclassid = 'pg_class'::regclass
               AND d.refobjid = ANY (tablas || secs) AND NOT (rw.ev_class = ANY (tablas)))
         + (SELECT count(*) FROM pg_rewrite WHERE ev_class = ANY (tablas) AND rulename <> '_RETURN')
         + (SELECT count(*) FROM pg_inherits WHERE inhrelid = ANY (tablas) OR inhparent = ANY (tablas))
         + (SELECT count(*) FROM pg_constraint
             WHERE contype = 'f' AND confrelid = ANY (tablas) AND NOT (conrelid = ANY (tablas)))
         + (SELECT count(*) FROM pg_publication_tables
             WHERE schemaname = 'public' AND tablename IN ('intencion_sesion', 'intencion_evento'))
         + (SELECT count(*) FROM pg_trigger WHERE NOT tgisinternal AND tgrelid = ANY (tablas))
         + (SELECT count(*) FROM pg_proc p JOIN pg_namespace ns ON ns.oid = p.pronamespace
             WHERE ns.nspname NOT IN ('pg_catalog', 'information_schema')
               AND (p.prosrc ~* '\m(intencion_sesion|intencion_evento|intencion_evento_id_seq)\M'
                    OR EXISTS (SELECT 1 FROM pg_depend d
                                WHERE d.classid = 'pg_proc'::regclass AND d.objid = p.oid
                                  AND ((d.refclassid = 'pg_class'::regclass AND d.refobjid = ANY (tablas || secs))
                                       OR (d.refclassid = 'pg_type'::regclass AND d.refobjid IN (
                                               SELECT t.oid FROM pg_type t JOIN pg_class c ON c.reltype = t.oid
                                                WHERE c.oid = ANY (tablas)
                                               UNION ALL
                                               SELECT t.typarray FROM pg_type t JOIN pg_class c ON c.reltype = t.oid
                                                WHERE c.oid = ANY (tablas)))))))
      INTO n;
    IF n > 0 THEN
        RAISE EXCEPTION '044 FALLA: apareció un puente (vista, regla, herencia, FK entrante, publicación, '
                        'trigger o función): %', n;
    END IF;

    -- Ningún camino con la autoridad de otro apareció (la misma enumeración que la compuerta 8 y la
    -- 10d).
    SELECT string_agg(DISTINCT format('%s [%s]', p.oid::regprocedure, x.via), ', ') INTO lista
      FROM (SELECT p.oid AS f, 'EXECUTE' AS via
              FROM pg_proc p
             WHERE p.prosecdef AND p.prorettype NOT IN ('trigger'::regtype, 'event_trigger'::regtype)
               AND EXISTS (SELECT 1
                             FROM (SELECT 'public'::text AS r
                                   UNION ALL SELECT rolname::text FROM pg_roles
                                    WHERE rolname IN ('anon', 'authenticated', 'service_role')) externos
                            WHERE has_function_privilege(externos.r, p.oid, 'EXECUTE'))
            UNION ALL
            SELECT t.tgfoid, format('trigger de %s', t.tgrelid::regclass)
              FROM pg_trigger t JOIN pg_proc p ON p.oid = t.tgfoid
             WHERE NOT t.tgisinternal AND p.prosecdef
               AND EXISTS (SELECT 1
                             FROM (SELECT 'public'::text AS r
                                   UNION ALL SELECT rolname::text FROM pg_roles
                                    WHERE rolname IN ('anon', 'authenticated', 'service_role')) externos
                            WHERE has_table_privilege(externos.r, t.tgrelid, 'INSERT')
                               OR has_table_privilege(externos.r, t.tgrelid, 'UPDATE')
                               OR has_table_privilege(externos.r, t.tgrelid, 'DELETE')
                               OR has_table_privilege(externos.r, t.tgrelid, 'TRUNCATE')
                               OR has_any_column_privilege(externos.r, t.tgrelid, 'INSERT')
                               OR has_any_column_privilege(externos.r, t.tgrelid, 'UPDATE'))
            UNION ALL
            SELECT ev.evtfoid, format('event trigger %s', ev.evtname)
              FROM pg_event_trigger ev JOIN pg_proc p ON p.oid = ev.evtfoid
             WHERE ev.evtenabled <> 'D' AND p.prosecdef
            UNION ALL
            -- Las funciones de soporte de un agregado corren sin comprobar EXECUTE sobre ellas: basta
            -- con poder ejecutar el agregado.
            SELECT soporte.f, format('soporte del agregado %s', a.aggfnoid::regprocedure)
              FROM pg_aggregate a,
                   unnest(ARRAY[a.aggtransfn, a.aggfinalfn, a.aggcombinefn, a.aggserialfn, a.aggdeserialfn,
                                a.aggmtransfn, a.aggminvtransfn, a.aggmfinalfn]::oid[]) AS soporte (f)
              JOIN pg_proc p ON p.oid = soporte.f
             WHERE p.prosecdef
               AND EXISTS (SELECT 1
                             FROM (SELECT 'public'::text AS r
                                   UNION ALL SELECT rolname::text FROM pg_roles
                                    WHERE rolname IN ('anon', 'authenticated', 'service_role')) externos
                            WHERE has_function_privilege(externos.r, a.aggfnoid, 'EXECUTE'))) x
      JOIN pg_proc p ON p.oid = x.f
      JOIN pg_namespace ns ON ns.oid = p.pronamespace
      JOIN pg_roles o ON o.oid = p.proowner
     WHERE ns.nspname NOT IN ('pg_catalog', 'information_schema')
       AND (o.rolsuper OR pg_has_role(p.proowner, dueno, 'MEMBER')
            OR EXISTS (SELECT 1 FROM pg_roles r
                        WHERE r.rolname IN ('pg_read_all_data', 'pg_write_all_data', 'pg_maintain',
                                            'pg_execute_server_program', 'pg_read_server_files',
                                            'pg_write_server_files')
                          AND pg_has_role(p.proowner, r.oid, 'MEMBER')))
       AND NOT EXISTS (SELECT 1
                         FROM pg_depend d JOIN pg_extension e ON e.oid = d.refobjid,
                              (VALUES ('supabase_vault', 'vault.create_secret(text,text,text,uuid)'),
                                      ('supabase_vault', 'vault.update_secret(uuid,text,text,text,uuid)'),
                                      ('postgis', 'public.st_estimatedextent(text,text,text,boolean)'),
                                      ('postgis', 'public.st_estimatedextent(text,text,text)'),
                                      ('postgis', 'public.st_estimatedextent(text,text)')) medidas (ext, firma)
                        WHERE d.classid = 'pg_proc'::regclass AND d.objid = p.oid
                          AND d.refclassid = 'pg_extension'::regclass AND d.deptype = 'e'
                          AND e.extname = medidas.ext AND p.oid::regprocedure::text = medidas.firma);
    IF lista IS NOT NULL THEN
        RAISE EXCEPTION '044 FALLA: hay funciones SECURITY DEFINER alcanzables por un rol externo con autoridad '
                        'sobre las tablas -> %', lista;
    END IF;
    SELECT string_agg(DISTINCT format('%s∈%s', m.rolname, r.rolname), ', ') INTO lista
      FROM pg_roles m, pg_roles r
     WHERE m.rolname IN ('anon', 'authenticated', 'service_role', 'authenticator')
       AND r.oid <> m.oid
       AND (r.oid = dueno OR r.rolsuper
            OR r.rolname IN ('pg_read_all_data', 'pg_write_all_data', 'pg_maintain',
                             'pg_execute_server_program', 'pg_read_server_files', 'pg_write_server_files'))
       AND pg_has_role(m.oid, r.oid, 'MEMBER');
    IF lista IS NOT NULL THEN
        RAISE EXCEPTION '044 FALLA: un rol externo es miembro de un rol con autoridad -> %', lista;
    END IF;

    -- Dueños, privilegios del dueño, restricciones (la FK saliente incluida), columnas y DEFAULT:
    -- idénticos a antes del efecto.
    SELECT string_agg(h.x, ' | ' ORDER BY h.x) INTO huella FROM (
        SELECT format('rel %s %s %s', c.oid::regclass, c.relkind, pg_get_userbyid(c.relowner)) AS x
          FROM pg_class c WHERE c.oid = ANY (tablas || secs)
        UNION ALL
        SELECT format('own %s %s', c.oid::regclass, string_agg(a.privilege_type, ',' ORDER BY a.privilege_type))
          FROM pg_class c,
               aclexplode(coalesce(c.relacl, acldefault(CASE WHEN c.relkind = 'S' THEN 's' ELSE 'r' END::"char",
                                                        c.relowner))) a
         WHERE c.oid = ANY (tablas || secs) AND a.grantee = c.relowner
         GROUP BY c.oid
        UNION ALL
        SELECT format('con %s %s %s', co.conrelid::regclass, co.conname, pg_get_constraintdef(co.oid))
          FROM pg_constraint co WHERE co.conrelid = ANY (tablas) OR co.confrelid = ANY (tablas)
        UNION ALL
        SELECT format('col %s %s %s %s', a.attrelid::regclass, a.attnum, a.attname,
                      format_type(a.atttypid, a.atttypmod))
          FROM pg_attribute a WHERE a.attrelid = ANY (tablas) AND a.attnum > 0 AND NOT a.attisdropped
        UNION ALL
        SELECT format('def %s %s %s', ad.adrelid::regclass, ad.adnum, pg_get_expr(ad.adbin, ad.adrelid))
          FROM pg_attrdef ad WHERE ad.adrelid = ANY (tablas)
    ) h;
    IF huella IS DISTINCT FROM current_setting('contexto_044.huella') THEN
        RAISE EXCEPTION '044 FALLA: cambió la estructura (dueño, privilegios del dueño, restricciones, columnas o '
                        'DEFAULT) -> antes: % / después: %', current_setting('contexto_044.huella'), huella;
    END IF;

    RAISE NOTICE '044 OK: RLS activado en 2 tablas, sin FORCE, 0 políticas, 0 privilegios externos (tablas, '
                 'columnas y % secuencia), PUBLIC/anon/authenticated/service_role sin nada efectivo, ningún camino '
                 'con autoridad ajena, dueño intacto, estructura idéntica', array_length(secs, 1);
END $$;

-- Verificación legible (debe devolver, por relación: RLS true en las tablas, FORCE false, 0
-- políticas, y un ACL con el dueño como único destinatario).
SELECT c.relname AS relacion,
       c.relrowsecurity AS con_rls,
       c.relforcerowsecurity AS con_force,
       (SELECT count(*) FROM pg_policy p WHERE p.polrelid = c.oid) AS politicas,
       coalesce(c.relacl::text, '') AS acl
  FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
 WHERE n.nspname = 'public' AND c.relname IN ('intencion_sesion', 'intencion_evento', 'intencion_evento_id_seq')
 ORDER BY c.relname;

COMMIT;

-- ── ROLLBACK ────────────────────────────────────────────────────────────────────────
--
-- EMERGENCY REVERSAL TO PRIOR KNOWN-INSECURE STATE. NO es un estado deseable: devuelve a `anon`,
-- `authenticated` y `service_role` todos los privilegios que tenían el 2026-10-07 (`arwdDxtm` en
-- PostgreSQL 17, `arwdDxt` en 15, sobre las dos tablas; USAGE, SELECT y UPDATE sobre la secuencia)
-- y apaga RLS: reabre lectura, escritura, TRUNCATE y `setval` desde fuera, y el oráculo de
-- existencia de la FK. Ningún consumidor legítimo lo necesita (el backend es el dueño). Sólo con
-- autorización explícita y separada. `PUBLIC` no tenía nada y no recibe nada.
--
--   BEGIN;
--   ALTER TABLE public.intencion_sesion DISABLE ROW LEVEL SECURITY;
--   ALTER TABLE public.intencion_evento DISABLE ROW LEVEL SECURITY;
--   GRANT ALL PRIVILEGES ON TABLE public.intencion_sesion, public.intencion_evento TO anon, authenticated, service_role;
--   GRANT ALL PRIVILEGES ON SEQUENCE public.intencion_evento_id_seq TO anon, authenticated, service_role;
--   COMMIT;
