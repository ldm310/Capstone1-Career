import datetime as dt
import json
import os
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch
from external_pass_crawler.daily import next_run, KST, process
from external_pass_crawler.models import Candidate, PublicMaterial, SearchPage, StoredMaterial
from external_pass_crawler.privacy import prose_text
from external_pass_crawler.errors import AccessRestricted


class DailyTests(unittest.TestCase):
    def test_search_name_requires_single_company_and_cannot_change_service(self):
        from external_pass_crawler.daily import main
        for args in (['--company-search-name', 'NHN'],
                     ['--company-id', '27', '--company-search-name', '  '],
                     ['--serve', '--company-id', '27', '--company-search-name', 'NHN']):
            with self.assertRaises(SystemExit) as exc:
                main(args)
            self.assertEqual(exc.exception.code, 2)

    def test_daily_reports_search_rejections_and_passes_explicit_alias(self):
        repo=Mock(); repo.daily_claim.return_value={'company_id':27,'name':'엔에이치엔(주)'}
        repo.postings.return_value=[{'title':'백엔드','site_job_category':'백엔드'}]
        repo.finish.return_value=('INSUFFICIENT',1)
        adapter=Mock()
        adapter.search.return_value=SearchPage((Candidate('1','NHN','백엔드'),
                                               Candidate('2','NHN AD','백엔드'),
                                               Candidate('3','NHN','영업')),3)
        adapter.detail.return_value=PublicMaterial('1','NHN','백엔드','Python 구현')
        outcomes,blocked=process(repo,adapter,[{'id':27}],10,2,'NHN')
        self.assertFalse(blocked)
        self.assertEqual(outcomes[0]['examined'],3)
        self.assertEqual(outcomes[0]['foreign_company'],1)
        self.assertEqual(outcomes[0]['excluded'],1)
        self.assertEqual(outcomes[0]['accepted'],1)
        adapter.search.assert_called_once_with('NHN',1)

    def test_service_started_before_nine_waits_before_collecting(self):
        from external_pass_crawler.daily import main
        fixed=dt.datetime.fromisoformat('2026-11-09T08:00:00+09:00')
        with patch('external_pass_crawler.daily.dt.datetime') as clock, patch('external_pass_crawler.daily.wait_until',side_effect=KeyboardInterrupt) as wait:
            clock.now.return_value=fixed
            with self.assertRaises(KeyboardInterrupt):main(['--serve'])
            self.assertEqual(wait.call_args.args[0].hour,9)

    def test_schedule_uses_kst_including_utc_boundary_and_exact_hour(self):
        now=dt.datetime(2026,11,9,0,tzinfo=dt.timezone.utc)
        self.assertEqual(next_run(now).isoformat(),'2026-11-10T09:00:00+09:00')
        self.assertEqual(next_run(now-dt.timedelta(seconds=1)).isoformat(),'2026-11-09T09:00:00+09:00')

    def test_prose_retains_paragraphs_removes_html_and_direct_contacts(self):
        value=prose_text('<p>Spring으로 API를 개발했습니다.</p><script>SECRET</script><p>연락 a@example.com 010-1234-5678</p>')
        self.assertIn('Spring으로 API를 개발했습니다.\n',value)
        self.assertNotIn('SECRET',value);self.assertNotIn('a@example.com',value)
        self.assertNotIn('010-1234-5678',value)

    def test_daily_collection_preserves_prose_and_stops_on_access_restriction(self):
        repo=Mock();repo.daily_claim.side_effect=[{'company_id':1,'name':'예시'}, {'company_id':2,'name':'다음'}]
        repo.postings.return_value=[{'title':'백엔드','site_job_category':'백엔드'}]
        repo.finish.return_value=('INSUFFICIENT',1)
        adapter=Mock()
        adapter.search.side_effect=[SearchPage((Candidate('1','예시','백엔드'),),1),AccessRestricted()]
        adapter.detail.return_value=PublicMaterial('1','예시','백엔드','Spring으로 API를 개발했습니다.')
        outcomes,blocked=process(repo,adapter,[{'id':1},{'id':2},{'id':3}],10,1)
        self.assertTrue(blocked);self.assertEqual(len(outcomes),2)
        saved=repo.finish.call_args.args[1][0]
        self.assertEqual(saved.body_text,'Spring으로 API를 개발했습니다.')
        self.assertNotIn('개발했습니다',saved.content)
        self.assertEqual(repo.daily_claim.call_count,2)


DSN=os.getenv('EXTERNAL_TEST_DATABASE_URL')


@unittest.skipUnless(DSN,'An isolated external crawler PostgreSQL database is required')
class DailyDatabaseTests(unittest.TestCase):
    def setUp(self):
        # Reuse the isolated database safety checks and fixture helpers.
        from test_collection_migration import CollectionMigrationTests
        self.fixture=CollectionMigrationTests()
        self.conn=self.fixture.fresh()
        self.addCleanup(self.fixture.doCleanups)
        from external_pass_crawler.daily_migrate import migrate_daily
        from external_pass_crawler.daily import DailyRepository
        self.migrate=migrate_daily
        self.assertFalse(migrate_daily(self.conn)['already_applied'])
        self.repo=DailyRepository(self.conn);self.repo.check_daily()

    def test_upgrade_is_repeatable_reclassifies_two_samples_and_preserves_pipeline(self):
        from external_pass_crawler.migrate import public_snapshot
        before=public_snapshot(self.conn)
        task=self.repo.daily_claim(2)
        materials=[StoredMaterial(str(i),'backend','{"technologies":["Spring"]}',f'Spring으로 기능 {i}을 개발했습니다.') for i in (1,2)]
        self.assertEqual(self.repo.finish(task,materials),('READY',2))
        self.assertTrue(self.migrate(self.conn)['already_applied'])
        after=public_snapshot(self.conn)
        pipeline={k:v for k,v in before.items() if not k.startswith('external_pass_')}
        self.assertEqual(pipeline,{k:after[k] for k in pipeline})
        self.assertEqual(self.conn.execute('SELECT minimum_sample_size FROM public.external_pass_company_collection WHERE company_id=2').fetchone()['minimum_sample_size'],2)
        self.assertEqual(self.conn.execute('SELECT count(*) AS n FROM public.external_pass_material_body').fetchone()['n'],2)

    def test_scan_includes_old_missing_it_postings_and_has_daily_cooldown(self):
        targets=self.repo.targets(100)
        self.assertTrue(any(c['id']==2 for c in targets))
        task=self.repo.daily_claim(2);self.repo.finish(task,[])
        self.assertFalse(any(c['id']==2 for c in self.repo.targets(100)))
        self.conn.execute("UPDATE public.external_pass_daily_company SET last_attempt_at=now()-interval '2 days' WHERE company_id=2")
        self.assertTrue(any(c['id']==2 for c in self.repo.targets(100)))

    def test_prose_transaction_rolls_back_and_unchanged_text_keeps_extraction_status(self):
        from external_pass_crawler.errors import ContractError
        task=self.repo.daily_claim(2)
        with self.assertRaises(ContractError):
            self.repo.finish(task,[StoredMaterial('1','backend','{}')])
        self.assertEqual(self.conn.execute('SELECT count(*) AS n FROM public.external_pass_material').fetchone()['n'],0)
        material=StoredMaterial('1','backend','{}','Spring으로 개발했습니다.')
        self.repo.finish(task,[material])
        self.conn.execute("UPDATE public.external_pass_material_body SET extraction_status='EXTRACTED'")
        task=self.repo.daily_claim(2);self.repo.finish(task,[material])
        self.assertEqual(self.conn.execute('SELECT extraction_status FROM public.external_pass_material_body').fetchone()['extraction_status'],'EXTRACTED')
        changed=StoredMaterial('1','backend','{}','Spring과 Redis로 개발했습니다.')
        task=self.repo.daily_claim(2);self.repo.finish(task,[changed])
        self.assertEqual(self.conn.execute('SELECT extraction_status FROM public.external_pass_material_body').fetchone()['extraction_status'],'PENDING')

    def test_daily_run_is_idempotent_and_dry_run_does_not_crawl_or_write(self):
        from external_pass_crawler.daily import run_once
        args=SimpleNamespace(dry_run=True,max_companies=2,company_id=None,max_records=10,max_pages=1)
        adapter=Mock()
        report=run_once(self.conn,args,adapter)
        self.assertTrue(report['dry_run']);adapter.search.assert_not_called()
        self.assertEqual(self.conn.execute('SELECT count(*) AS n FROM public.external_pass_daily_run').fetchone()['n'],0)
        args.dry_run=False
        adapter.search.return_value=SearchPage((),0)
        self.assertEqual(run_once(self.conn,args,adapter)['status'],'SUCCEEDED')
        adapter.reset_mock()
        self.assertEqual(run_once(self.conn,args,adapter)['reason'],'ALREADY_RUN_TODAY')
        adapter.search.assert_not_called()

    def test_only_interrupted_daily_attempts_are_recovered(self):
        self.repo.daily_claim(2)
        self.conn.execute("UPDATE public.external_pass_daily_company SET last_attempt_at=now()-interval '2 days' WHERE company_id=2")
        self.assertEqual(self.repo.recover_stale(),0)
        self.conn.execute("UPDATE public.external_pass_company_collection SET started_at=(SELECT last_attempt_at FROM public.external_pass_daily_company WHERE company_id=2) WHERE company_id=2")
        self.assertEqual(self.repo.recover_stale(),1)
        self.assertEqual(self.conn.execute('SELECT error_code FROM public.external_pass_company_collection WHERE company_id=2').fetchone()['error_code'],'STALE_TASK')

    def test_upgrade_changes_existing_five_sample_policy_to_two(self):
        from external_pass_crawler.migrate import migrate_public
        from external_pass_crawler.daily_migrate import migrate_daily
        conn=self.fixture.fresh();migrate_public(conn)
        conn.execute("INSERT INTO public.external_pass_company_collection(company_id,status,minimum_sample_size,completed_at) VALUES(2,'INSUFFICIENT',5,now())")
        for rid in ('201','202'):
            conn.execute("""INSERT INTO public.external_pass_material(company_id,source_platform,external_record_id,
                role_name,title,content,source_url) VALUES(2,'linkareer',%s,'backend','fixture','{}','https://example.invalid')""",(rid,))
        migrate_daily(conn)
        result=conn.execute('SELECT status,minimum_sample_size FROM public.external_pass_company_collection WHERE company_id=2').fetchone()
        self.assertEqual(result,{'status':'READY','minimum_sample_size':2})
