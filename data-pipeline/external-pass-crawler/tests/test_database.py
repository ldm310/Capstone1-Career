import contextlib
import io
import json
import os
import unittest
import uuid
from unittest.mock import Mock, patch

DSN = os.getenv("EXTERNAL_TEST_DATABASE_URL")


@unittest.skipUnless(DSN, "Set EXTERNAL_TEST_DATABASE_URL to an isolated local extcrawler_test* DB")
class DatabaseTests(unittest.TestCase):
    def setUp(self):
        import psycopg
        from psycopg.rows import dict_row
        from external_pass_crawler.repository import Repository
        self.conn = psycopg.connect(DSN, autocommit=True, row_factory=dict_row)
        if not self.conn.info.dbname.startswith("extcrawler_test") or self.conn.info.host not in ("127.0.0.1", "localhost"):
            self.conn.close()
            self.fail("Integration tests require an isolated local extcrawler_test* database")
        self.addCleanup(self.conn.close)
        self.repo = Repository(self.conn)
        self.repo.check_contract()
        name = "테스트테크" + uuid.uuid4().hex[:10]
        self.c1 = self.conn.execute("INSERT INTO job.company(name) VALUES(%s) RETURNING id", (name,)).fetchone()["id"]
        self.c2 = self.conn.execute("INSERT INTO job.company(name) VALUES(%s) RETURNING id", (name + "타사",)).fetchone()["id"]
        self.p1 = self.posting(self.c1, "백엔드")
        self.p2 = self.posting(self.c1, "데이터 엔지니어")
        self.posting(self.c2, "백엔드")
        self.rid = str(self.c1) + "0001"

    def posting(self, company, role):
        return self.conn.execute("""
            INSERT INTO job.posting(company_id,site_posting_no,title,site_job_category,kind,raw_path,raw_hash)
            VALUES(%s,%s,%s,%s,'글','test',%s) RETURNING id
            """, (company, uuid.uuid4().hex, role + " 개발자", role, "0" * 64)).fetchone()["id"]

    def material(self):
        from external_pass_crawler.models import StoredMaterial
        from external_pass_crawler.privacy import technical_summary
        return StoredMaterial(self.rid, "backend", technical_summary("Python과 Spring으로 API 기능을 구현했습니다."))

    def task(self, minimum=1):
        self.repo.enqueue(self.c1)
        self.conn.execute("UPDATE external_data.company_collection SET minimum_sample_size=%s WHERE company_id=%s", (minimum, self.c1))
        return self.repo.claim(self.c1)

    def test_one_company_task_atomic_claim_and_shared_links(self):
        self.assertEqual(self.repo.enqueue(self.c1), 1)
        self.assertEqual(self.repo.enqueue(self.c1), 0)
        task = self.task()
        self.assertIsNone(self.repo.claim(self.c1))
        self.assertEqual(self.repo.finish(task, [self.material()]), ("READY", 1))
        stored = self.conn.execute("SELECT content, pg_typeof(content)::text AS content_type FROM external_data.pass_material WHERE company_id=%s", (self.c1,)).fetchone()
        self.assertEqual(stored["content_type"], "text")
        self.assertEqual(json.loads(stored["content"]), {
            "technologies": ["Python", "Spring"], "projectSignals": ["FEATURE_IMPLEMENTATION"]})
        self.repo.enqueue(self.c1)
        self.assertIsNone(self.repo.claim(self.c1))
        links = self.conn.execute("""
            SELECT p.company_id,l.relation_type FROM external_data.posting_pass_material l
            JOIN job.posting p ON p.id=l.posting_id WHERE l.material_id IN
              (SELECT id FROM external_data.pass_material WHERE company_id=%s) ORDER BY p.id
            """, (self.c1,)).fetchall()
        self.assertEqual([x["relation_type"] for x in links], ["EXACT_ROLE", "SAME_IT_DOMAIN"])
        self.assertTrue(all(x["company_id"] == self.c1 for x in links))

    def test_worker_skips_locked_company_without_network_or_double_claim(self):
        import psycopg
        from psycopg.rows import dict_row
        from external_pass_crawler.repository import Repository
        self.repo.enqueue(self.c1)
        with psycopg.connect(DSN, autocommit=True, row_factory=dict_row) as other:
            with self.conn.transaction():
                self.conn.execute("SELECT * FROM external_data.company_collection WHERE company_id=%s FOR UPDATE", (self.c1,))
                self.assertIsNone(Repository(other).claim(self.c1))
            self.assertIsNotNone(Repository(other).claim(self.c1))
            self.assertIsNone(self.repo.claim(self.c1))

    def test_empty_or_below_minimum_is_insufficient(self):
        task = self.task(minimum=5)
        self.assertEqual(self.repo.finish(task, []), ("INSUFFICIENT", 0))
        self.conn.execute("UPDATE external_data.company_collection SET status='PENDING',started_at=NULL,completed_at=NULL WHERE company_id=%s", (self.c1,))
        self.assertEqual(self.repo.finish(self.repo.claim(self.c1), [self.material()]), ("INSUFFICIENT", 1))

    def test_new_posting_reuses_material_and_no_new_attempt(self):
        task = self.task()
        self.repo.finish(task, [self.material()])
        p3 = self.posting(self.c1, "프론트엔드")
        self.repo.enqueue(self.c1)
        self.repo.relink_existing(self.c1)
        result = self.conn.execute("SELECT relation_type FROM external_data.posting_pass_material WHERE posting_id=%s", (p3,)).fetchone()
        self.assertEqual(result["relation_type"], "SAME_JOB_FAMILY")
        self.assertEqual(self.conn.execute("SELECT attempt_count FROM external_data.company_collection WHERE company_id=%s", (self.c1,)).fetchone()["attempt_count"], 1)

    def test_upsert_is_idempotent_and_source_company_collision_rolls_back_then_failed(self):
        from external_pass_crawler.errors import IdentityConflict
        task = self.task()
        self.repo.finish(task, [self.material(), self.material()])
        self.assertEqual(self.conn.execute("SELECT count(*) n FROM external_data.pass_material WHERE company_id=%s", (self.c1,)).fetchone()["n"], 1)
        self.repo.enqueue(self.c2)
        other = self.repo.claim(self.c2)
        with self.assertRaises(IdentityConflict):
            self.repo.finish(other, [self.material()])
        self.repo.fail(other, "SOURCE_COMPANY_CONFLICT")
        self.assertEqual(self.conn.execute("SELECT status FROM external_data.company_collection WHERE company_id=%s", (self.c2,)).fetchone()["status"], "FAILED")
        self.assertEqual(self.conn.execute("SELECT count(*) n FROM external_data.pass_material WHERE company_id=%s", (self.c2,)).fetchone()["n"], 0)

    def test_dry_run_has_no_enqueue_status_or_material_writes(self):
        from external_pass_crawler.__main__ import main
        from external_pass_crawler.models import Candidate, PublicMaterial, SearchPage
        company = self.repo.companies(self.c1)[0]
        adapter = Mock()
        adapter.search.return_value = SearchPage((Candidate("101", company["name"], "백엔드"),), 1)
        adapter.detail.return_value = PublicMaterial("101", company["name"], "백엔드", "임의 개인정보 Python")
        output = io.StringIO()
        with patch.dict(os.environ, {"DATABASE_URL": DSN}), patch("external_pass_crawler.__main__.LinkareerAdapter", return_value=adapter), contextlib.redirect_stdout(output):
            self.assertEqual(main(["--company-id", str(self.c1), "--dry-run"]), 0)
        self.assertEqual(json.loads(output.getvalue())["accepted"], 1)
        self.assertNotIn("개인정보", output.getvalue())
        self.assertIsNone(self.conn.execute("SELECT * FROM external_data.company_collection WHERE company_id=%s", (self.c1,)).fetchone())
        self.assertEqual(self.conn.execute("SELECT count(*) n FROM external_data.pass_material WHERE company_id=%s", (self.c1,)).fetchone()["n"], 0)

    def test_read_only_session_enforces_no_writes_and_schema_mismatch_fails(self):
        import psycopg
        from psycopg.rows import dict_row
        from external_pass_crawler.repository import Repository
        from external_pass_crawler.errors import ContractError
        with self.assertRaises(ContractError):
            Repository(self.conn, "public").check_contract()
        with psycopg.connect(DSN, autocommit=True, row_factory=dict_row, options="-c default_transaction_read_only=on") as readonly:
            with self.assertRaises(psycopg.errors.ReadOnlySqlTransaction):
                Repository(readonly).enqueue(self.c1)

    def test_stale_attempt_cannot_overwrite_new_attempt(self):
        from external_pass_crawler.errors import StaleTask
        task = self.task()
        self.conn.execute("UPDATE external_data.company_collection SET attempt_count=attempt_count+1 WHERE company_id=%s", (self.c1,))
        with self.assertRaises(StaleTask):
            self.repo.finish(task, [self.material()])
        self.repo.fail(task, "STALE_TASK")
        current = self.conn.execute("SELECT status,error_code FROM external_data.company_collection WHERE company_id=%s", (self.c1,)).fetchone()
        self.assertEqual(current["status"], "RUNNING")
        self.assertIsNone(current["error_code"])
