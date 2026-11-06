-- K-B: the rights on the tables of the base online, granted by their owner, the role of
-- kb migrate-database, in the transaction that creates them (database/creation.py). The roles are
-- created before by the administration of the base (infra/postgresql/grant-roles.sql): kb_reader
-- for the data API, which reads; kb_writer for the daily routine, which writes the data and purges
-- it, but changes no table. Neither TRUNCATE nor REFERENCES nor TRIGGER: K-B uses none.
GRANT SELECT ON ALL TABLES IN SCHEMA public TO kb_reader;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO kb_writer;
