-- K-B: the roles of the managed identities on the server, then the base kb, run once by the
-- Microsoft Entra administrator of the server on the base postgres, with psql (infra/README.md):
--   psql ... -v migrate_database_principal_id=<id> -v data_api_principal_id=<id> -f create-principals.sql
-- Each role is tied to its identity by the object id of its service principal (principalId of
-- az identity show), not by its name: an identity of another resource group of the directory may
-- bear the same name (Microsoft Learn, "Manage Microsoft Entra roles", read on 2026-11-06).
-- create-daily-routine-principal.sql (#330) comes next, then grant-roles.sql on the base kb.
\set ON_ERROR_STOP on

SELECT * FROM pg_catalog.pgaadauth_create_principal_with_oid(
    'id-kb-migrate-database', :'migrate_database_principal_id', 'service', false, false
);
SELECT * FROM pg_catalog.pgaadauth_create_principal_with_oid(
    'id-kb-data-api', :'data_api_principal_id', 'service', false, false
);

-- UTF8 and the collation C, which kb migrate-database checks: text sorts byte by byte, as in SQLite
-- (src/k_b/database/creation.py). From template0, the only template whose locale may change.
CREATE DATABASE kb TEMPLATE template0 ENCODING 'UTF8' LC_COLLATE 'C' LC_CTYPE 'C';
