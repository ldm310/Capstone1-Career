-- Manual LOCAL-only migration when legacy job tables exist and public has no
-- conflicting objects. Unlike 05, this moves the original tables and IDs.
-- Never run against RDS. The runner backs up and rehearses on a local clone.
BEGIN;
SET LOCAL search_path = pg_catalog;
SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '60s';

DO $$
DECLARE
    r record;
    definition text;
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_namespace WHERE nspname='public') THEN
        RAISE EXCEPTION 'public schema missing';
    END IF;
    -- Check every destination before moving anything, including indexes and
    -- owned sequences, which ALTER TABLE SET SCHEMA moves automatically.
    IF EXISTS (
        SELECT 1 FROM pg_class source
        JOIN pg_namespace sn ON sn.oid=source.relnamespace AND sn.nspname='job'
        JOIN pg_class target ON target.relname=source.relname
        JOIN pg_namespace tn ON tn.oid=target.relnamespace AND tn.nspname='public'
    ) THEN
        RAISE EXCEPTION 'Conflicting public objects: reconciliation required';
    END IF;
    IF EXISTS (
        SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
        WHERE n.nspname='job' AND c.relkind NOT IN ('r','i','S')
    ) OR EXISTS (
        SELECT 1 FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname='job'
    ) THEN
        RAISE EXCEPTION 'Unexpected legacy objects: manual review required';
    END IF;
    FOR r IN
        SELECT c.relname FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
        WHERE n.nspname='job' AND c.relkind='r' ORDER BY c.relname
    LOOP
        EXECUTE format('LOCK TABLE job.%I IN ACCESS EXCLUSIVE MODE',r.relname);
    END LOOP;
    FOR r IN
        SELECT c.relname FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
        WHERE n.nspname='job' AND c.relkind='r' ORDER BY c.relname
    LOOP
        EXECUTE format('ALTER TABLE job.%I SET SCHEMA public',r.relname);
    END LOOP;
    -- Foreign keys track table OIDs and follow the move. PL/pgSQL source text
    -- does not, so rewrite the known company guard without changing ownership.
    IF to_regprocedure('external_data.check_material_company()') IS NOT NULL THEN
        SELECT pg_get_functiondef(to_regprocedure('external_data.check_material_company()')) INTO definition;
        IF position('job.posting' IN definition)>0 THEN
            EXECUTE replace(definition,'job.posting','public.posting');
        END IF;
    END IF;
    IF EXISTS (
        SELECT 1 FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace
        WHERE n.nspname IN ('public','profile','external_data') AND p.prokind='f'
          AND pg_get_functiondef(p.oid) ~ 'job\.'
    ) OR EXISTS (
        SELECT 1 FROM pg_constraint c JOIN pg_class t ON t.oid=c.confrelid
        JOIN pg_namespace n ON n.oid=t.relnamespace WHERE c.contype='f' AND n.nspname='job'
    ) OR EXISTS (
        SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='job'
    ) THEN
        RAISE EXCEPTION 'Legacy job objects or references remain; rolled back';
    END IF;
END;
$$;
COMMIT;
