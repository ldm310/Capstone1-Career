"""Integration checks use only an explicitly named disposable loopback database."""
import os
import unittest
from unittest.mock import patch
import psycopg
from psycopg.rows import dict_row
from psycopg.conninfo import conninfo_to_dict
from requirement_embeddings.config import Config
from requirement_embeddings.preprocessing import ROOT
from requirement_embeddings.migrate import migrate,pipeline_snapshot
from requirement_embeddings.batch import run
from requirement_embeddings.client import SafeFailure


class FakeClient:
    def __init__(self):self.calls=[];self.failure=None;self.invalid=False;self.mutate=None
    def create(self,texts):
        self.calls.append(list(texts))
        if self.mutate:self.mutate()
        if self.failure:raise self.failure
        return {'model':'text-embedding-3-small','data':list(reversed([
            {'index':i,'embedding':None if self.invalid and i==0 else [1.,float(i+1),0.]}
            for i in range(len(texts))])),'usage':{'prompt_tokens':len(texts)*2}}


@unittest.skipUnless(os.getenv('EMBEDDING_TEST_DSN'),'Disposable embedding DB required')
class DatabaseTests(unittest.TestCase):
    def setUp(self):
        dsn=os.environ['EMBEDDING_TEST_DSN'];info=conninfo_to_dict(dsn)
        assert info.get('host') in ('127.0.0.1','localhost') and info.get('dbname','').startswith('extcrawler_test_embedding_')
        self.conn=psycopg.connect(dsn,autocommit=True,row_factory=dict_row)
        self.conn.execute('DROP SCHEMA public CASCADE; CREATE SCHEMA public')
        self.conn.execute((ROOT/'db/init/01-job-schema.sql').read_text(encoding='utf-8'))
        self.conn.execute((ROOT/'backend/src/test/resources/posting-similarity-fixtures.sql').read_text(encoding='utf-8'))
        self.before=pipeline_snapshot(self.conn)
        self.sequences=self.conn.execute("SELECT sequencename,last_value FROM pg_sequences WHERE schemaname='public' ORDER BY sequencename").fetchall()
        self.assertEqual(migrate(self.conn)['storage'],'real[]')
        self.config=Config(dimensions=3);self.client=FakeClient()
    def tearDown(self):self.conn.close()
    def batch(self,**kw):return run(self.conn,self.config,self.client,apply=True,limit=100000,count_tokens=lambda text:2,**kw)
    def scalar(self,sql):return next(iter(self.conn.execute(sql).fetchone().values()))

    def test_migration_repeated_dry_run_and_batch_never_change_pipeline(self):
        self.assertTrue(migrate(self.conn)['already_applied'])
        before=self.scalar('SELECT count(*) FROM public.be_embedding_cache')
        report=run(self.conn,self.config,apply=False,count_tokens=lambda text:2)
        self.assertEqual(report['api_calls'],0);self.assertGreater(report['unique_inputs'],0)
        self.assertEqual(before,self.scalar('SELECT count(*) FROM public.be_embedding_cache'))
        self.batch();self.assertEqual(pipeline_snapshot(self.conn),self.before)
        self.assertEqual(self.sequences,self.conn.execute("SELECT sequencename,last_value FROM pg_sequences WHERE schemaname='public' AND sequencename NOT LIKE 'be_%' ORDER BY sequencename").fetchall())
        self.assertIsNone(self.conn.execute("SELECT extname FROM pg_extension WHERE extname='vector'").fetchone())

    def test_same_hash_reuses_vectors_and_only_changed_sentence_regenerates(self):
        first=self.batch();calls=len(self.client.calls)
        second=self.batch();self.assertEqual(len(self.client.calls),calls)
        self.assertGreater(self.scalar("SELECT count(*) FROM public.be_requirement_embedding WHERE eligibility='ELIGIBLE'"),first['unique_inputs'])
        self.assertEqual(second['pending_inputs'],0);self.assertEqual(second['reused_inputs'],first['unique_inputs'])
        self.conn.execute("UPDATE public.unit_item SET text='REST endpoint implemented' WHERE id=521")
        third=self.batch();self.assertEqual(len(self.client.calls),calls+1)
        self.assertEqual(len(self.client.calls[-1]),1)
        self.assertEqual(third['pending_inputs'],0)
        self.assertEqual(self.scalar('SELECT count(*) FROM public.be_embedding_cache'),first['unique_inputs']+1)

    def test_response_index_maps_to_original_requirement(self):
        self.batch()
        rows=self.conn.execute('SELECT c.embedding,r.input_hashes,c.input_hash FROM public.be_embedding_cache c JOIN public.be_embedding_request r ON r.id=c.request_id').fetchall()
        for row in rows:self.assertEqual(row['embedding'][1],row['input_hashes'].index(row['input_hash'])+1)

    def test_partial_invalid_response_preserves_ready_data_and_never_automatically_replays(self):
        self.client.invalid=True;report=self.batch();self.assertEqual(report['status'],'PARTIAL')
        ready=self.scalar("SELECT count(*) FROM public.be_embedding_cache WHERE status='READY'")
        self.assertGreater(ready,0);self.assertEqual(report['failed_inputs'],1)
        calls=len(self.client.calls);self.client.invalid=False;again=self.batch()
        self.assertEqual(len(self.client.calls),calls);self.assertEqual(again['failed_inputs'],1)
        self.assertEqual(ready,self.scalar("SELECT count(*) FROM public.be_embedding_cache WHERE status='READY'"))

    def test_api_failure_and_unknown_delivery_are_safe_and_not_replayed(self):
        self.client.failure=SafeFailure('DELIVERY_UNCERTAIN',True)
        self.assertEqual(self.batch()['status'],'PARTIAL');calls=len(self.client.calls)
        again=self.batch();self.assertEqual(len(self.client.calls),calls)
        self.assertGreater(again['unknown_inputs'],0)
        self.assertEqual(pipeline_snapshot(self.conn),self.before)
        self.assertGreater(self.scalar("SELECT count(*) FROM public.be_requirement_embedding WHERE eligibility='ELIGIBLE'"),0)

    def test_interrupted_inflight_request_recovers_to_unknown(self):
        def interrupted(*args,**kw):raise KeyboardInterrupt()
        with patch.object(self.client,'create',side_effect=interrupted):
            with self.assertRaises(KeyboardInterrupt):self.batch()
        report=self.batch();self.assertGreater(report['unknown_inputs'],0)
        self.assertEqual(self.scalar("SELECT count(*) FROM public.be_embedding_cache WHERE status='IN_FLIGHT'"),0)
        self.assertEqual(len(self.client.calls),0)

    def test_changed_source_during_api_does_not_bind_stale_vector(self):
        self.client.mutate=lambda:self.conn.execute("UPDATE public.unit_item SET text='changed during request' WHERE id=521")
        self.batch()
        self.assertEqual(self.scalar('SELECT count(*) FROM public.be_requirement_embedding WHERE requirement_id=5211'),0)

    def test_concurrent_runner_skips_without_api_or_writes(self):
        with psycopg.connect(os.environ['EMBEDDING_TEST_DSN'],autocommit=True) as other:
            other.execute('SELECT pg_advisory_lock(703114,3)')
            report=self.batch();self.assertEqual(report['status'],'SKIPPED');self.assertEqual(self.client.calls,[])

    def test_dimension_constraint_rejects_invalid_storage(self):
        self.batch()
        with self.assertRaises(psycopg.errors.CheckViolation):
            self.conn.execute("UPDATE public.be_embedding_cache SET embedding=ARRAY[1,2]::real[] WHERE status='READY'")
