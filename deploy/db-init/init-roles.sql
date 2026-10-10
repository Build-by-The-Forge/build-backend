-- Least-privilege PostgreSQL roles for the combined topology (design B.6).
--
-- Run by the db-init service as the superuser, with psql variables:
--   db, backend_owner_password, backend_app_password,
--   ai_owner_password, ai_app_password
-- Idempotent: safe to run on every start, before or after migrations.
--
--   build_backend_owner  owns backend tables and alembic_version (migrations)
--   build_backend_app    backend runtime: DML on backend tables only
--   build_ai_owner       owns learning_memory, session_memory and
--                        ai_service_alembic_version (migrations)
--   build_ai_app         AI-service runtime: DML on AI-owned tables only;
--                        nothing on any backend table

\set ON_ERROR_STOP on

-- Roles (created once; passwords re-applied each run).
SELECT format('CREATE ROLE %I LOGIN', r)
FROM unnest(ARRAY['build_backend_owner', 'build_backend_app', 'build_ai_owner', 'build_ai_app']) AS r
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = r)
\gexec

ALTER ROLE build_backend_owner LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE PASSWORD :'backend_owner_password';
ALTER ROLE build_backend_app LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE PASSWORD :'backend_app_password';
ALTER ROLE build_ai_owner LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE PASSWORD :'ai_owner_password';
ALTER ROLE build_ai_app LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE PASSWORD :'ai_app_password';

-- Database: only the four roles may connect.
REVOKE ALL ON DATABASE :"db" FROM PUBLIC;
GRANT CONNECT ON DATABASE :"db" TO build_backend_owner, build_backend_app, build_ai_owner, build_ai_app;

-- Schema: PUBLIC loses its default CREATE; only the owners may create objects.
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
GRANT USAGE, CREATE ON SCHEMA public TO build_backend_owner, build_ai_owner;
GRANT USAGE ON SCHEMA public TO build_backend_app, build_ai_app;

-- Future objects each owner creates are usable by its own runtime role only.
ALTER DEFAULT PRIVILEGES FOR ROLE build_backend_owner IN SCHEMA public
    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO build_backend_app;
ALTER DEFAULT PRIVILEGES FOR ROLE build_backend_owner IN SCHEMA public
    GRANT USAGE, SELECT ON SEQUENCES TO build_backend_app;
ALTER DEFAULT PRIVILEGES FOR ROLE build_ai_owner IN SCHEMA public
    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO build_ai_app;
ALTER DEFAULT PRIVILEGES FOR ROLE build_ai_owner IN SCHEMA public
    GRANT USAGE, SELECT ON SEQUENCES TO build_ai_app;

-- Objects that already exist (a re-run after migrations): grant by owner.
DO $$
DECLARE
    pair record;
    t record;
BEGIN
    FOR pair IN
        SELECT * FROM (VALUES ('build_backend_owner', 'build_backend_app'),
                              ('build_ai_owner', 'build_ai_app')) AS p(owner, app)
    LOOP
        FOR t IN
            SELECT c.relname, c.relkind
            FROM pg_class c
            JOIN pg_namespace n ON n.oid = c.relnamespace
            JOIN pg_roles r ON r.oid = c.relowner
            WHERE n.nspname = 'public' AND r.rolname = pair.owner AND c.relkind IN ('r', 'p', 'S')
        LOOP
            IF t.relkind = 'S' THEN
                EXECUTE format('GRANT USAGE, SELECT ON SEQUENCE public.%I TO %I', t.relname, pair.app);
            ELSE
                EXECUTE format('GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.%I TO %I', t.relname, pair.app);
            END IF;
        END LOOP;
    END LOOP;
END
$$;
