import json
import os
from pathlib import Path
import unittest
import uuid
from external_pass_crawler.errors import ContractError

DSN=os.getenv("EXTERNAL_TEST_DATABASE_URL")
ROOT=Path(__file__).resolve().parents[3]


def selected():
    return {"postingId":1,"recruitUnitId":11,"selectionStatus":"SELECTED","roleCode":"backend",
            "policyVersion":"keyword-mvp-2","appliedCriteria":{"jobFamilyExpansionEnabled":False},
            "candidates":[{"postingId":3,"recruitUnitId":31,"companyId":2,"rank":1,
                           "confidence":"HIGH","featureMode":"REQUIRED","evidenceCount":2}]}


@unittest.skipUnless(DSN,"An isolated external crawler PostgreSQL database is required")
class CollectionMigrationTests(unittest.TestCase):
    def fresh(self):
        import psycopg
        from psycopg import sql
        from psycopg.conninfo import conninfo_to_dict
        from psycopg.rows import dict_row
        cfg=conninfo_to_dict(DSN)
        self.assertIn(cfg['host'],('127.0.0.1','localhost'))
        self.assertTrue(cfg['dbname'].startswith('extcrawler_test'))
        with psycopg.connect(DSN,autocommit=True) as admin:
            cfg['dbname']='extcrawler_test_migration_'+uuid.uuid4().hex[:10]
            admin.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(cfg['dbname'])))
        conn=psycopg.connect(**cfg,autocommit=True,row_factory=dict_row)
        self.cfg=cfg
        self.addCleanup(conn.close)
        conn.execute((ROOT/'db/init/01-job-schema.sql').read_text(encoding='utf-8'))
        conn.execute((ROOT/'backend/src/test/resources/posting-similarity-fixtures.sql').read_text(encoding='utf-8'))
        return conn

    def test_new_install_and_repeat_preserve_public_and_existing_external_rows(self):
        from external_pass_crawler.migrate import migrate,public_snapshot
        conn=self.fresh();before=public_snapshot(conn)
        self.assertFalse(migrate(conn)['already_applied'])
        conn.execute("INSERT INTO external_data.company_collection(company_id) VALUES(2)")
        row=conn.execute("SELECT * FROM external_data.company_collection WHERE company_id=2").fetchone()
        self.assertTrue(migrate(conn)['already_applied'])
        self.assertEqual(public_snapshot(conn),before)
        self.assertEqual(row,conn.execute("SELECT * FROM external_data.company_collection WHERE company_id=2").fetchone())

    def test_existing_canonical_base_is_upgraded_without_reset(self):
        from external_pass_crawler.migrate import migrate,public_snapshot
        conn=self.fresh()
        conn.execute((ROOT/'db/init/04-external-pass-material.sql').read_text(encoding='utf-8'))
        conn.execute("INSERT INTO external_data.company_collection(company_id) VALUES(2)")
        before=public_snapshot(conn)
        migrate(conn)
        self.assertEqual(conn.execute('SELECT count(*) AS n FROM external_data.company_collection').fetchone()['n'],1)
        self.assertEqual(public_snapshot(conn),before)

    def test_job_foreign_key_contract_is_rejected_without_partial_migration(self):
        from external_pass_crawler.migrate import migrate,public_snapshot
        conn=self.fresh();before=public_snapshot(conn)
        conn.execute('CREATE SCHEMA job; CREATE TABLE job.company(id BIGINT PRIMARY KEY); CREATE TABLE job.posting(id BIGINT PRIMARY KEY,company_id BIGINT)')
        text=(ROOT/'db/init/04-external-pass-material.sql').read_text(encoding='utf-8')
        conn.execute(text.replace('REFERENCES public.','REFERENCES job.').replace('FROM public.posting','FROM job.posting'))
        with self.assertRaises(ContractError):migrate(conn)
        self.assertIsNone(conn.execute("SELECT to_regclass('external_data.collection_request') AS name").fetchone()['name'])
        self.assertEqual(public_snapshot(conn),before)

    def test_partially_installed_base_is_rejected_without_touching_existing_table(self):
        from external_pass_crawler.migrate import migrate
        conn=self.fresh()
        conn.execute('CREATE SCHEMA external_data; CREATE TABLE external_data.company_collection(company_id BIGINT)')
        with self.assertRaises(ContractError):migrate(conn)
        self.assertIsNone(conn.execute("SELECT to_regclass('external_data.pass_material') AS name").fetchone()['name'])

    def test_candidate_ownership_role_and_same_company_provenance_are_enforced(self):
        import psycopg
        from external_pass_crawler.migrate import migrate
        from external_pass_crawler.comparison_requests import RequestRepository
        conn=self.fresh();migrate(conn);repo=RequestRepository(conn)
        first=repo.register(selected());self.assertEqual(first,repo.register(selected()))
        row=conn.execute('SELECT * FROM external_data.collection_candidate WHERE request_id=%s',(first,)).fetchone()
        self.assertEqual(row['candidate_company_id'],2)
        for candidate in [dict(postingId=2,recruitUnitId=21,companyId=1),dict(postingId=5,recruitUnitId=31,companyId=3)]:
            data=selected();data['candidates'][0].update(candidate)
            with self.assertRaises(psycopg.errors.CheckViolation):repo.register(data)
        with self.assertRaises(psycopg.errors.CheckViolation):
            conn.execute("UPDATE external_data.collection_candidate SET standard_role_code='frontend' WHERE request_id=%s",(first,))

    def test_direct_link_prevents_company_work_and_readonly_dry_run_cannot_persist(self):
        import psycopg
        from external_pass_crawler.migrate import migrate
        from external_pass_crawler.comparison_requests import RequestRepository
        conn=self.fresh();migrate(conn);repo=RequestRepository(conn)
        mid=conn.execute("""INSERT INTO external_data.pass_material(company_id,source_platform,external_record_id,
            role_name,title,content,source_url) VALUES(1,'fixture','direct','backend','fixture',
            '{"technologies":["Python"]}','https://example.invalid/1') RETURNING id""").fetchone()['id']
        conn.execute("INSERT INTO external_data.posting_pass_material(posting_id,material_id,relation_type) VALUES(1,%s,'EXACT_ROLE')",(mid,))
        req=repo.register(selected())
        self.assertEqual(repo.candidates([req]),[])
        self.assertTrue(conn.execute('SELECT used_direct FROM external_data.collection_request WHERE id=%s',(req,)).fetchone()['used_direct'])
        with self.assertRaises(psycopg.errors.CheckViolation):
            conn.execute("INSERT INTO external_data.posting_pass_material(posting_id,material_id,relation_type) VALUES(3,%s,'EXACT_ROLE')",(mid,))
        with psycopg.connect(**self.cfg,autocommit=True,row_factory=psycopg.rows.dict_row,options='-c default_transaction_read_only=on') as readonly:
            with self.assertRaises(psycopg.errors.ReadOnlySqlTransaction):RequestRepository(readonly).register(selected())

    def test_single_crawler_session_lock_is_shared_across_entrypoints(self):
        import psycopg
        conn=self.fresh()
        self.assertTrue(conn.execute('SELECT pg_try_advisory_lock(703114,2) AS yes').fetchone()['yes'])
        with psycopg.connect(**self.cfg,autocommit=True,row_factory=psycopg.rows.dict_row) as other:
            self.assertFalse(other.execute('SELECT pg_try_advisory_lock(703114,2) AS yes').fetchone()['yes'])

    def test_saved_target_discovery_uses_only_committed_current_it_units(self):
        from external_pass_crawler.migrate import migrate
        from external_pass_crawler.comparison_requests import RequestRepository
        conn=self.fresh();migrate(conn)
        rows=RequestRepository(conn).saved_targets('2000-01-01T00:00:00+00:00',100)
        ids={row['unit_id'] for row in rows}
        self.assertIn(11,ids);self.assertIn(52,ids)
        self.assertNotIn(51,ids);self.assertNotIn(13,ids)

    def test_stored_materials_reuse_the_backend_unit_role_on_a_multi_role_posting(self):
        from external_pass_crawler.migrate import migrate,public_snapshot
        from external_pass_crawler.comparison_requests import RequestRepository
        conn=self.fresh();migrate(conn);repo=RequestRepository(conn);before=public_snapshot(conn)
        request=repo.register(selected())
        for i in range(5):
            conn.execute("""INSERT INTO external_data.pass_material(company_id,source_platform,external_record_id,
                role_name,title,content,source_url) VALUES(2,'fixture',%s,'backend','fixture',
                '{"technologies":["Python"]}','https://example.invalid/1')""",(str(i),))
        repo.enqueue(2)
        self.assertIsNone(repo.claim(2))
        candidate=repo.candidates([request])[0]
        self.assertEqual(candidate['status'],'READY')
        repo.link_candidate(candidate)
        self.assertEqual(len(repo.material_ids(candidate)),5)
        self.assertEqual(public_snapshot(conn),before)

    def test_public_owned_install_works_with_only_create_select_and_references(self):
        import psycopg
        from psycopg import sql
        from psycopg.rows import dict_row
        from external_pass_crawler.migrate import migrate_public,public_snapshot
        from external_pass_crawler.comparison_requests import RequestRepository
        from external_pass_crawler.models import StoredMaterial
        admin=self.fresh();before=public_snapshot(admin)
        role='owned_external_'+uuid.uuid4().hex[:10]
        admin.execute(sql.SQL('CREATE ROLE {} LOGIN PASSWORD {}').format(sql.Identifier(role),sql.Literal(self.cfg['password'])))
        admin.execute(sql.SQL('GRANT USAGE,CREATE ON SCHEMA public TO {}').format(sql.Identifier(role)))
        admin.execute(sql.SQL('GRANT SELECT ON ALL TABLES IN SCHEMA public TO {}').format(sql.Identifier(role)))
        for table in before:
            if table!='tech_capability':
                admin.execute(sql.SQL('GRANT REFERENCES ON public.{} TO {}').format(sql.Identifier(table),sql.Identifier(role)))
        with psycopg.connect(**{**self.cfg,'user':role},autocommit=True,row_factory=dict_row) as conn:
            self.assertFalse(conn.execute("SELECT has_table_privilege(current_user,'public.posting','INSERT') AS yes").fetchone()['yes'])
            self.assertFalse(conn.execute("SELECT has_table_privilege(current_user,'public.tech_capability','REFERENCES') AS yes").fetchone()['yes'])
            self.assertTrue(migrate_public(conn)['existing_public_unchanged'])
            self.assertTrue(migrate_public(conn)['already_applied'])
            repo=RequestRepository(conn);repo.check_contract();request=repo.register(selected())
            repo.enqueue(2);task=repo.claim(2)
            repo.finish(task,[StoredMaterial('restricted-fixture','backend','{"technologies":["Python"]}')])
            candidate=repo.candidates([request])[0];repo.link_candidate(candidate)
            self.assertEqual(len(repo.material_ids(candidate)),1)
            refs=conn.execute("""SELECT count(*) AS n FROM pg_constraint c JOIN pg_class t ON t.oid=c.conrelid
                JOIN pg_class target ON target.oid=c.confrelid WHERE c.contype='f'
                AND t.relname LIKE 'external_pass_%' AND target.relname='tech_capability'""").fetchone()['n']
            self.assertEqual(refs,0)
        after=public_snapshot(admin)
        self.assertEqual(before,{k:after[k] for k in before})
