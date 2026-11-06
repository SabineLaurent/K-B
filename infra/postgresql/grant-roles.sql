-- K-B: the roles and the rights of the base kb online, run by the Microsoft Entra administrator of
-- the server on the base kb, after create-principals.sql and before the first kb migrate-database
-- (infra/README.md). It can be run again: each statement leaves what is already there as it is.
-- The tests run it as it is on their server (tests/database/test_grants.py).
--
-- id-kb-migrate-database creates the tables, and owns them: kb migrate-database grants them to
-- kb_reader and kb_writer (src/k_b/database/grants_postgresql.sql). kb_reader is the data API, which
-- reads; kb_writer the daily routine, which writes the data (its identity joins it with #330).
-- No other role connects to the base, nor creates anything in it: on Azure, every role may create
-- objects in public until this script revokes it (Microsoft Learn, "Access management", read on
-- 2026-11-06).

-- citext, which the role of kb migrate-database does not create on Azure
-- (src/k_b/database/schema_postgresql.sql).
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_extension WHERE extname = 'citext') THEN
        CREATE EXTENSION citext;
    END IF;
END
$$;

-- The two groups, without login: a role of an identity gets its rights by joining one.
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'kb_reader') THEN
        CREATE ROLE kb_reader NOLOGIN;
    END IF;
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'kb_writer') THEN
        CREATE ROLE kb_writer NOLOGIN;
    END IF;
END
$$;

-- CONNECT and TEMPORARY are given to PUBLIC by default: only the three roles connect, and none
-- creates a temporary table. The name of the base is read, so that the tests run the same text.
DO $$
BEGIN
    EXECUTE format('REVOKE ALL ON DATABASE %I FROM PUBLIC', current_database());
    EXECUTE format(
        'GRANT CONNECT ON DATABASE %I TO kb_reader, kb_writer, "id-kb-migrate-database"',
        current_database()
    );
END
$$;

REVOKE CREATE ON SCHEMA public FROM PUBLIC;
GRANT USAGE ON SCHEMA public TO kb_reader, kb_writer;
GRANT USAGE, CREATE ON SCHEMA public TO "id-kb-migrate-database";

GRANT kb_reader TO "id-kb-data-api";
