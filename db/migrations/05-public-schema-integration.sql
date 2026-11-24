-- Manual, opt-in migration for OLD LOCAL databases only. Never auto-run at startup.
-- Keep public/job rows and sequences untouched. Do not copy/rename/drop any tables.
-- Existing public tables must already contain the correct identities.
BEGIN;
SET LOCAL search_path = pg_catalog;
SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '60s';

DO $$
DECLARE
    r record;
    fk record;
    source_oid oid;
    target_oid oid;
    old_oid oid;
    source_att smallint;
    target_att smallint;
    differs text;
    invalid boolean;
    has_fk boolean;
    definition text;
BEGIN
    -- Include known optional tables and any additional capability/tech FKs in
    -- profile/external_data. A missing source table is an intentional no-op.
    IF EXISTS (
        SELECT 1 FROM pg_constraint c
        JOIN pg_class t ON t.oid=c.conrelid
        JOIN pg_namespace n ON n.oid=t.relnamespace
        JOIN pg_class p ON p.oid=c.confrelid
        JOIN pg_namespace pn ON pn.oid=p.relnamespace
        WHERE c.contype='f' AND n.nspname IN ('profile','external_data')
          AND pn.nspname='job'
          AND (cardinality(c.conkey)<>1 OR cardinality(c.confkey)<>1
               OR p.relname NOT IN ('company','posting','capability','tech','recruit_unit'))
    ) THEN
        RAISE EXCEPTION 'Unsupported legacy FK; manual identity review required';
    END IF;

    FOR r IN
        SELECT * FROM (VALUES
            ('external_data','pass_material','company_id','company','RESTRICT'),
            ('external_data','company_collection','company_id','company','RESTRICT'),
            ('external_data','posting_pass_material','posting_id','posting','CASCADE'),
            ('profile','user_skill_evaluation','capability_id','capability','RESTRICT'),
            ('profile','comparison_target','unit_id','recruit_unit','CASCADE'),
            ('profile','successful_application','company_id','company','NO ACTION'),
            ('profile','successful_application','posting_id','posting','NO ACTION')
        ) AS known(schema_name,table_name,column_name,parent_name,delete_action)
        UNION
        SELECT n.nspname::text,t.relname::text,a.attname::text,p.relname::text,
               CASE c.confdeltype WHEN 'c' THEN 'CASCADE' WHEN 'r' THEN 'RESTRICT'
                    WHEN 'n' THEN 'SET NULL' WHEN 'd' THEN 'SET DEFAULT' ELSE 'NO ACTION' END
        FROM pg_constraint c
        JOIN pg_class t ON t.oid=c.conrelid JOIN pg_namespace n ON n.oid=t.relnamespace
        JOIN pg_class p ON p.oid=c.confrelid JOIN pg_namespace pn ON pn.oid=p.relnamespace
        JOIN pg_attribute a ON a.attrelid=t.oid AND a.attnum=c.conkey[1]
        WHERE c.contype='f' AND n.nspname IN ('profile','external_data')
          AND pn.nspname='job' AND cardinality(c.conkey)=1
    LOOP
        source_oid := to_regclass(format('%I.%I',r.schema_name,r.table_name));
        IF source_oid IS NULL THEN CONTINUE; END IF;
        EXECUTE format('LOCK TABLE %I.%I IN ACCESS EXCLUSIVE MODE',r.schema_name,r.table_name);
        target_oid := to_regclass(format('public.%I',r.parent_name));
        IF target_oid IS NULL THEN
            RAISE EXCEPTION 'Required public target missing for %.%',r.schema_name,r.table_name;
        END IF;
        EXECUTE format('LOCK TABLE public.%I IN SHARE MODE',r.parent_name);
        SELECT attnum INTO source_att FROM pg_attribute
          WHERE attrelid=source_oid AND attname=r.column_name AND NOT attisdropped;
        SELECT attnum INTO target_att FROM pg_attribute
          WHERE attrelid=target_oid AND attname='id' AND NOT attisdropped;
        IF source_att IS NULL OR target_att IS NULL THEN
            RAISE EXCEPTION 'Required FK column missing for %.%',r.schema_name,r.table_name;
        END IF;

        -- Refuse orphaned IDs, even if an old NOT VALID FK allowed them.
        EXECUTE format('SELECT EXISTS(SELECT 1 FROM %I.%I s LEFT JOIN public.%I p ON p.id=s.%I '
            'WHERE s.%I IS NOT NULL AND p.id IS NULL)',r.schema_name,r.table_name,
            r.parent_name,r.column_name,r.column_name) INTO invalid;
        IF invalid THEN RAISE EXCEPTION 'Missing public identities for %.%; no data copied',r.schema_name,r.table_name; END IF;

        has_fk := false;
        FOR fk IN SELECT c.* FROM pg_constraint c WHERE c.contype='f'
                  AND c.conrelid=source_oid AND source_att=ANY(c.conkey)
        LOOP
            IF cardinality(fk.conkey)<>1 OR cardinality(fk.confkey)<>1 THEN
                RAISE EXCEPTION 'Composite FK requires manual review';
            END IF;
            IF fk.confrelid=target_oid AND fk.confkey[1]=target_att THEN
                EXECUTE format('ALTER TABLE %I.%I VALIDATE CONSTRAINT %I',r.schema_name,r.table_name,fk.conname);
                has_fk := true;
                CONTINUE;
            END IF;
            old_oid := to_regclass(format('job.%I',r.parent_name));
            IF old_oid IS NULL OR fk.confrelid<>old_oid THEN
                RAISE EXCEPTION 'Unexpected FK target for %.%',r.schema_name,r.table_name;
            END IF;
            IF NOT EXISTS(SELECT 1 FROM pg_attribute WHERE attrelid=old_oid
                          AND attnum=fk.confkey[1] AND attname='id') THEN
                RAISE EXCEPTION 'Legacy FK must reference id';
            END IF;
            EXECUTE format('LOCK TABLE job.%I IN SHARE MODE',r.parent_name);
            EXECUTE format('SELECT EXISTS(SELECT 1 FROM %I.%I s LEFT JOIN job.%I o ON o.id=s.%I '
                'WHERE s.%I IS NOT NULL AND o.id IS NULL)',r.schema_name,r.table_name,
                r.parent_name,r.column_name,r.column_name) INTO invalid;
            IF invalid THEN RAISE EXCEPTION 'Legacy FK contains orphaned identities'; END IF;
            -- Matching numeric IDs alone are insufficient: compare every common
            -- column of referenced legacy/public rows. Any difference aborts all DDL.
            SELECT string_agg(format('o.%I IS DISTINCT FROM p.%I',a.attname,a.attname),' OR ')
              INTO differs FROM pg_attribute a JOIN pg_attribute b
                ON b.attrelid=target_oid AND b.attname=a.attname AND NOT b.attisdropped
              WHERE a.attrelid=old_oid AND a.attnum>0 AND NOT a.attisdropped AND b.attnum>0;
            EXECUTE format('SELECT EXISTS(SELECT 1 FROM job.%I o JOIN public.%I p USING(id) '
                'WHERE EXISTS(SELECT 1 FROM %I.%I s WHERE s.%I=o.id) AND (%s))',
                r.parent_name,r.parent_name,r.schema_name,r.table_name,r.column_name,differs) INTO invalid;
            IF invalid THEN RAISE EXCEPTION 'Legacy/public identities differ for %.%; manual reconciliation required',r.schema_name,r.table_name; END IF;
            definition := replace(pg_get_constraintdef(fk.oid),'REFERENCES job.','REFERENCES public.');
            IF definition=pg_get_constraintdef(fk.oid) THEN RAISE EXCEPTION 'Unexpected FK definition'; END IF;
            EXECUTE format('ALTER TABLE %I.%I DROP CONSTRAINT %I',r.schema_name,r.table_name,fk.conname);
            EXECUTE format('ALTER TABLE %I.%I ADD CONSTRAINT %I %s',r.schema_name,r.table_name,fk.conname,definition);
            EXECUTE format('ALTER TABLE %I.%I VALIDATE CONSTRAINT %I',r.schema_name,r.table_name,fk.conname);
            has_fk := true;
        END LOOP;
        IF NOT has_fk THEN
            EXECUTE format('ALTER TABLE %I.%I ADD CONSTRAINT %I FOREIGN KEY (%I) REFERENCES public.%I(id) ON DELETE %s',
                r.schema_name,r.table_name,r.table_name||'_'||r.column_name||'_fkey',r.column_name,r.parent_name,r.delete_action);
        END IF;
    END LOOP;

    -- The existing company guard also reads the posting table. Updating FKs
    -- alone would leave the trigger querying job.posting.
    IF to_regclass('external_data.posting_pass_material') IS NOT NULL
       AND to_regprocedure('external_data.check_material_company()') IS NOT NULL THEN
        EXECUTE $ddl$
            CREATE OR REPLACE FUNCTION external_data.check_material_company() RETURNS trigger
            LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog AS $fn$
            DECLARE posting_company bigint; material_company bigint;
            BEGIN
                SELECT company_id INTO posting_company FROM public.posting WHERE id=NEW.posting_id FOR SHARE;
                SELECT company_id INTO material_company FROM external_data.pass_material WHERE id=NEW.material_id FOR SHARE;
                IF posting_company IS NULL OR material_company IS NULL OR posting_company<>material_company THEN
                    RAISE EXCEPTION 'External material must belong to the posting company' USING ERRCODE='23514';
                END IF;
                RETURN NEW;
            END;
            $fn$;
        $ddl$;
    END IF;
END;
$$;
COMMIT;
