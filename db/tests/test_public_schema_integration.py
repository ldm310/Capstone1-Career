"""Opt-in PostgreSQL tests. Only loopback extcrawler_test* databases are accepted.

Creates disposable databases for each test and drops only those databases.
--prepare-backend seeds the supplied isolated database for the Java opt-in test.
Never loads an env file or a production connection configuration.
"""
import os
from pathlib import Path
import sys
import unittest
import uuid

import psycopg
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict, make_conninfo

ROOT = Path(__file__).resolve().parents[2]
DSN = os.environ.get("PUBLIC_SCHEMA_TEST_DSN")


def safe_dsn():
    if not DSN:
        raise RuntimeError("PUBLIC_SCHEMA_TEST_DSN is required")
    cfg = conninfo_to_dict(DSN)
    if (cfg.get("host") not in ("127.0.0.1", "localhost")
            or cfg.get("hostaddr", "127.0.0.1") != "127.0.0.1"
            or not cfg.get("dbname", "").startswith("extcrawler_test")
            or "service" in cfg):
        raise RuntimeError("Only isolated local extcrawler_test databases are allowed")
    return DSN


def execute_file(conn, name):
    conn.execute((ROOT / name).read_text(encoding="utf-8"))


def core(conn):
    execute_file(conn, "db/init/01-job-schema.sql")
    conn.execute("""
        INSERT INTO public.company(id,name) OVERRIDING SYSTEM VALUE VALUES (1,'fixture-company'),(2,'other-company');
        INSERT INTO public.capability(id,name,group_name) OVERRIDING SYSTEM VALUE VALUES(1,'fixture-capability','fixture');
        INSERT INTO public.tech(id,name,aliases) OVERRIDING SYSTEM VALUE VALUES(1,'Java',ARRAY['java']);
        INSERT INTO public.tech_capability(tech_id,capability_id,is_primary) VALUES(1,1,true);
        INSERT INTO public.posting(id,company_id,site_posting_no,title,kind,raw_hash,collected_at,last_checked_at)
            OVERRIDING SYSTEM VALUE VALUES(1,1,'fixture-1','Backend fixture','글',repeat('0',64),'2026-11-01Z','2026-11-01Z');
        INSERT INTO public.extraction_run(id,posting_id,model,prompt_version,dict_version,input_hash,
            input_tokens,output_tokens,cost_usd,is_current,run_at,llm_output_raw)
            OVERRIDING SYSTEM VALUE VALUES(1,1,'fixture','fixture','fixture',repeat('0',64),0,0,0,true,'2026-11-01Z','{}');
        INSERT INTO public.recruit_unit(id,run_id,seq,name,is_it,career)
            OVERRIDING SYSTEM VALUE VALUES(1,1,1,'backend',true,'신입');
        INSERT INTO public.unit_item(id,unit_id,category,seq,text,quote)
            OVERRIDING SYSTEM VALUE VALUES(1,1,'필수',1,'Java','Java');
        INSERT INTO public.requirement(id,item_id,capability_id,relation)
            OVERRIDING SYSTEM VALUE VALUES(1,1,1,'모두');
        INSERT INTO public.requirement_tech(id,requirement_id,tech_id,written_name)
            OVERRIDING SYSTEM VALUE VALUES(1,1,1,'Java');
    """)


def extensions(conn, legacy=False):
    for name in ("02-user-skill-schema.sql", "03-capability-comparison.sql", "04-external-pass-material.sql"):
        ddl = (ROOT / "db/init" / name).read_text(encoding="utf-8")
        if legacy:
            ddl = ddl.replace("REFERENCES public.", "REFERENCES job.").replace("FROM public.posting", "FROM job.posting")
        conn.execute(ddl)


def dependent_rows(conn):
    conn.execute("""
        INSERT INTO external_data.pass_material(company_id,source_platform,external_record_id,role_name,title,content,source_url)
            VALUES(1,'linkareer','fixture-1','backend','fixture','{"technologies":["Java"]}','https://example.invalid/1');
        INSERT INTO external_data.company_collection(company_id,status,minimum_sample_size,completed_at)
            VALUES(1,'READY',1,now());
        INSERT INTO external_data.posting_pass_material(posting_id,material_id,relation_type)
            SELECT 1,id,'EXACT_ROLE' FROM external_data.pass_material;
        INSERT INTO profile.app_user(email,name) VALUES('fixture@example.invalid','fixture');
        INSERT INTO profile.project(user_id,project_name) SELECT user_id,'fixture' FROM profile.app_user;
        INSERT INTO profile.user_skill_evaluation(project_id,capability_id,confirmed_score)
            SELECT project_id,1,80 FROM profile.project;
        INSERT INTO profile.comparison_target(unit_id,role_group,career_band) VALUES(1,'backend','entry');
        INSERT INTO profile.successful_application(user_id,company_id,posting_id,role_group,career_band,stage,accepted_at)
            SELECT user_id,1,1,'backend','entry','FINAL_PASSED','2026-11-01' FROM profile.app_user;
    """)


def snapshot(conn, schemas=("public", "job", "profile", "external_data")):
    result = {}
    for schema, table in conn.execute("SELECT schemaname,tablename FROM pg_tables WHERE schemaname=ANY(%s) ORDER BY 1,2", (list(schemas),)):
        result[schema, table] = conn.execute(sql.SQL(
            "SELECT count(*),md5(coalesce(string_agg(to_jsonb(t)::text,'' ORDER BY to_jsonb(t)::text),'')) FROM {}.{} t"
        ).format(sql.Identifier(schema), sql.Identifier(table))).fetchone()
    # Sequences must remain untouched by the migration as well.
    result["sequences"] = conn.execute("SELECT schemaname,sequencename,last_value FROM pg_sequences WHERE schemaname=ANY(%s) ORDER BY 1,2", (list(schemas),)).fetchall()
    return result


@unittest.skipUnless(DSN, "Set PUBLIC_SCHEMA_TEST_DSN to an isolated loopback database")
class PublicSchemaIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.admin = psycopg.connect(safe_dsn(), autocommit=True)
        self.name = "extcrawler_test_" + uuid.uuid4().hex
        self.admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(self.name)))
        self.conn = psycopg.connect(make_conninfo(safe_dsn(), dbname=self.name), autocommit=True)
        self.addCleanup(self.cleanup)

    def cleanup(self):
        self.conn.close()
        self.admin.execute(sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(self.name)))
        self.admin.close()

    def migrate(self):
        execute_file(self.conn, "db/migrations/05-public-schema-integration.sql")

    def legacy(self):
        # Synthetic legacy parents in a disposable test DB only. No real data copied.
        self.conn.execute("""
            CREATE SCHEMA job;
            CREATE TABLE job.company(id bigint PRIMARY KEY,name text);
            CREATE TABLE job.posting(id bigint PRIMARY KEY,company_id bigint,site_posting_no text,title text);
            CREATE TABLE job.capability(id bigint PRIMARY KEY,name text);
            CREATE TABLE job.tech(id bigint PRIMARY KEY,name text);
            CREATE TABLE job.recruit_unit(id bigint PRIMARY KEY,run_id bigint,seq smallint,name text);
            INSERT INTO job.company VALUES(1,'fixture-company'),(2,'other-company');
            INSERT INTO job.posting VALUES(1,1,'fixture-1','Backend fixture');
            INSERT INTO job.capability VALUES(1,'fixture-capability');
            INSERT INTO job.tech VALUES(1,'Java');
            INSERT INTO job.recruit_unit VALUES(1,1,1,'backend');
        """)
        extensions(self.conn, legacy=True)
        self.conn.execute("CREATE TABLE profile.legacy_tech(tech_id bigint REFERENCES job.tech(id)); INSERT INTO profile.legacy_tech VALUES(1)")
        dependent_rows(self.conn)

    def test_fresh_install_and_extensions_preserve_public(self):
        core(self.conn)
        before = snapshot(self.conn, ("public",))
        self.migrate()  # No extension tables yet: no-op.
        extensions(self.conn)
        self.migrate()
        self.migrate()  # Idempotence.
        self.assertEqual(before, snapshot(self.conn, ("public",)))
        self.assertIsNone(self.conn.execute("SELECT to_regnamespace('job')").fetchone()[0])
        refs = self.conn.execute("""SELECT pn.nspname,p.relname FROM pg_constraint c
            JOIN pg_class t ON t.oid=c.conrelid JOIN pg_namespace n ON n.oid=t.relnamespace
            JOIN pg_class p ON p.oid=c.confrelid JOIN pg_namespace pn ON pn.oid=p.relnamespace
            WHERE c.contype='f' AND n.nspname='external_data' AND p.relname IN ('company','posting')""").fetchall()
        self.assertCountEqual(refs, [('public','company'),('public','company'),('public','posting')])

    def test_legacy_fks_retarget_without_row_or_sequence_changes(self):
        core(self.conn)
        self.legacy()
        before = snapshot(self.conn)
        self.migrate()
        self.migrate()
        self.assertEqual(before, snapshot(self.conn))
        legacy_refs = self.conn.execute("""SELECT count(*) FROM pg_constraint c
            JOIN pg_class t ON t.oid=c.conrelid JOIN pg_namespace n ON n.oid=t.relnamespace
            JOIN pg_class p ON p.oid=c.confrelid JOIN pg_namespace pn ON pn.oid=p.relnamespace
            WHERE c.contype='f' AND n.nspname IN ('profile','external_data') AND pn.nspname='job'""").fetchone()[0]
        self.assertEqual(legacy_refs, 0)
        self.assertNotIn('job.posting', self.conn.execute("SELECT pg_get_functiondef('external_data.check_material_company()'::regprocedure)").fetchone()[0])
        # Give the legacy posting another company: successful re-link now proves
        # the guard reads public.posting. This changes test-only legacy fixtures.
        self.conn.execute("UPDATE job.posting SET company_id=2 WHERE id=1")
        self.conn.execute("UPDATE external_data.posting_pass_material SET relation_type='SAME_JOB_FAMILY'")
        with self.assertRaises(psycopg.errors.CheckViolation):
            self.conn.execute("UPDATE external_data.posting_pass_material SET posting_id=2")

    def test_conflicting_ids_abort_atomically(self):
        core(self.conn)
        self.legacy()
        self.conn.execute("UPDATE job.company SET name='different-identity' WHERE id=1")
        before = snapshot(self.conn)
        with self.assertRaises(psycopg.errors.RaiseException):
            self.migrate()
        self.conn.execute("ROLLBACK")
        self.assertEqual(before, snapshot(self.conn))
        self.assertIn('job.posting', self.conn.execute("SELECT pg_get_functiondef('external_data.check_material_company()'::regprocedure)").fetchone()[0])

    def test_missing_public_parent_aborts_without_copying(self):
        core(self.conn)
        self.legacy()
        # Simulate an ID present only in the old source. No public rows altered.
        self.conn.execute("INSERT INTO job.tech VALUES(99,'legacy-only'); INSERT INTO profile.legacy_tech VALUES(99)")
        before = snapshot(self.conn)
        with self.assertRaises(psycopg.errors.RaiseException):
            self.migrate()
        self.conn.execute("ROLLBACK")
        self.assertEqual(before, snapshot(self.conn))


if __name__ == "__main__":
    if sys.argv[1:] == ["--prepare-backend"]:
        with psycopg.connect(safe_dsn(), autocommit=True) as conn:
            core(conn)
            extensions(conn)
            dependent_rows(conn)
        print("Isolated Backend PostgreSQL fixtures prepared")
    else:
        unittest.main()
