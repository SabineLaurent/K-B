-- K-B: the role of the identity of the daily routine (caj-kb-daily-routine, #330) on the server, run
-- once by the Microsoft Entra administrator of the server on the base postgres, with psql
-- (infra/README.md, "La routine quotidienne (#330)"):
--   psql ... -v daily_routine_principal_id=<id> -f create-daily-routine-principal.sql
-- Apart from create-principals.sql, which cannot run again (its CREATE DATABASE kb fails once the
-- base exists). The role is tied to its identity by the object id of its service principal
-- (principalId of az identity show), not by its name, as in create-principals.sql.
-- grant-roles.sql comes next, on the base kb: it makes the role a member of kb_writer.
\set ON_ERROR_STOP on

SELECT * FROM pg_catalog.pgaadauth_create_principal_with_oid(
    'id-kb-daily-routine', :'daily_routine_principal_id', 'service', false, false
);
