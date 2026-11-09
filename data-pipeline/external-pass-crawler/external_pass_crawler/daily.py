"""Daily Linkareer scan -> public essays -> RDS prose, independently of Backend requests."""
import argparse
import datetime as dt
import hashlib
import json
import os
import time
from zoneinfo import ZoneInfo
from .errors import AccessRestricted, ContractError
from .platforms.linkareer import LinkareerAdapter, PublicHttp
from .policy import MINIMUM_SAMPLE_SIZE
from .repository import Repository
from .runner import collect

KST = ZoneInfo('Asia/Seoul')


class DailyRepository(Repository):
    def __init__(self, conn):
        super().__init__(conn)

    def check_daily(self):
        self.check_contract()
        row=self.conn.execute("SELECT checksum FROM public.external_pass_schema_migration WHERE version='public-08'").fetchone()
        if not row:
            raise ContractError('Run the explicit daily migration first')

    def targets(self, limit, company_id=None):
        # Scan every current IT posting, not just today's newly collected postings.
        # Company-scoped work shares essays across postings and revisits empty/partial results next day.
        return self.conn.execute("""
            WITH uncovered AS (
                SELECT p.id,p.company_id,
                    EXISTS(SELECT 1 FROM public.external_pass_material m
                        LEFT JOIN public.external_pass_material_body b ON b.material_id=m.id
                        WHERE m.company_id=p.company_id AND m.source_platform='linkareer' AND b.material_id IS NULL) AS needs_body
                FROM public.posting p
                WHERE p.status='진행' AND EXISTS (
                    SELECT 1 FROM public.extraction_run r JOIN public.recruit_unit u ON u.run_id=r.id
                    WHERE r.posting_id=p.id AND r.is_current AND u.is_it)
                  AND (%s::bigint IS NULL OR p.company_id=%s)
                  AND (NOT EXISTS (
                    SELECT 1 FROM public.external_pass_posting_material l
                    JOIN public.external_pass_material m ON m.id=l.material_id AND m.company_id=p.company_id
                    JOIN public.external_pass_material_body b ON b.material_id=m.id
                    WHERE l.posting_id=p.id AND l.relation_type<>'EXCLUDED' AND m.source_platform='linkareer')
                    OR (SELECT count(*) FROM public.external_pass_material m
                        WHERE m.company_id=p.company_id AND m.source_platform='linkareer' AND m.job_family='IT_SW')<%s
                    OR EXISTS(SELECT 1 FROM public.external_pass_material m
                        LEFT JOIN public.external_pass_material_body b ON b.material_id=m.id
                        WHERE m.company_id=p.company_id AND m.source_platform='linkareer' AND b.material_id IS NULL))
            )
            SELECT c.id,c.name,count(*) AS missing_postings,bool_or(u.needs_body) AS needs_body
            FROM uncovered u JOIN public.company c ON c.id=u.company_id
            LEFT JOIN public.external_pass_company_collection task ON task.company_id=c.id
            LEFT JOIN public.external_pass_daily_company a ON a.company_id=c.id AND a.source_platform='linkareer'
            WHERE btrim(c.name)<>'' AND coalesce(task.status,'')<>'RUNNING'
              AND (a.last_attempt_at IS NULL OR a.last_attempt_at <
                  (date_trunc('day',now() AT TIME ZONE 'Asia/Seoul') AT TIME ZONE 'Asia/Seoul'))
            GROUP BY c.id,c.name,a.last_attempt_at
            ORDER BY bool_or(u.needs_body) DESC,a.last_attempt_at NULLS FIRST,c.id LIMIT %s
            """,(company_id,company_id,MINIMUM_SAMPLE_SIZE,limit)).fetchall()

    def daily_claim(self, company_id):
        with self.conn.transaction():
            self.enqueue(company_id)
            current=self.conn.execute("SELECT status,error_code FROM public.external_pass_company_collection WHERE company_id=%s FOR UPDATE",(company_id,)).fetchone()
            if current['status']=='RUNNING':
                return None
            if current['error_code']=='ACCESS_RESTRICTED':
                raise AccessRestricted()
            self.conn.execute("""UPDATE public.external_pass_company_collection
                SET status='PENDING',minimum_sample_size=%s,completed_at=NULL,error_code=NULL,error_message=NULL,updated_at=now()
                WHERE company_id=%s""",(MINIMUM_SAMPLE_SIZE,company_id))
            task=self.claim(company_id)
            self.conn.execute("""INSERT INTO public.external_pass_daily_company(source_platform,company_id)
                VALUES('linkareer',%s) ON CONFLICT(source_platform,company_id) DO UPDATE SET last_attempt_at=now()""",(company_id,))
            return task

    def recover_stale(self):
        # Only recover a RUNNING attempt that this daily worker recorded in the same transaction.
        # Manually started/company-CLI jobs have a different started_at and remain untouched.
        return self.conn.execute("""UPDATE public.external_pass_company_collection task
            SET status='FAILED',error_code='STALE_TASK',error_message='Daily worker interrupted',
                completed_at=now(),updated_at=now()
            FROM public.external_pass_daily_company a
            WHERE a.source_platform='linkareer' AND a.company_id=task.company_id
              AND task.status='RUNNING' AND task.started_at=a.last_attempt_at
              AND a.last_attempt_at<now()-interval '6 hours'""").rowcount

    def finish(self, task, materials):
        # Prose, derived summary, links and terminal state commit together.
        with self.conn.transaction():
            result=super().finish(task,materials)
            for material in materials:
                if not material.body_text:
                    raise ContractError('Daily collection requires essay paragraphs')
                digest=hashlib.sha256(material.body_text.encode()).hexdigest()
                self.conn.execute("""INSERT INTO public.external_pass_material_body AS existing
                    (material_id,plain_text,content_sha256)
                    SELECT id,%s,%s FROM public.external_pass_material
                    WHERE source_platform='linkareer' AND external_record_id=%s AND company_id=%s
                    ON CONFLICT(material_id) DO UPDATE SET plain_text=excluded.plain_text,
                        content_sha256=excluded.content_sha256,extraction_status='PENDING',updated_at=now()
                    WHERE existing.content_sha256<>excluded.content_sha256""",
                    (material.body_text,digest,material.external_id,task['company_id']))
            return result


def process(repo, adapter, targets, max_records, max_pages, company_search_name=None):
    outcomes=[]
    for company in targets:
        task=repo.daily_claim(company['id'])
        if task is None:
            continue
        try:
            materials,counters=collect(adapter,task['name'],repo.postings(company['id']),
                                       max_records,max_pages,
                                       (company_search_name,) if company_search_name else (),
                                       preserve_text=True,search_company=company_search_name)
            status,total=repo.finish(task,materials)
            outcomes.append({'company_id':company['id'],'status':status,'accepted':counters.accepted,
                             'total_materials':total,'truncated':counters.truncated,
                             'examined':counters.examined,'foreign_company':counters.foreign_company,
                             'excluded':counters.excluded})
        except Exception as exc:
            code=getattr(exc,'code','COLLECTION_FAILED')
            repo.fail(task,code)
            outcomes.append({'company_id':company['id'],'status':'FAILED','error_code':code})
            if isinstance(exc,AccessRestricted):
                return outcomes,True
    return outcomes,False


def run_once(conn, args, adapter=None):
    repo=DailyRepository(conn);repo.check_daily()
    if not conn.execute('SELECT pg_try_advisory_lock(703114,2) AS yes').fetchone()['yes']:
        return {'status':'SKIPPED','reason':'CRAWLER_RUNNING'}
    try:
        day=dt.datetime.now(KST).date()
        tracked = args.company_id is None
        if not args.dry_run and tracked:
            previous=conn.execute("SELECT status FROM public.external_pass_daily_run WHERE source_platform='linkareer' AND run_date=%s",(day,)).fetchone()
            if previous and previous['status']!='RUNNING':
                return {'status':'SKIPPED','reason':'ALREADY_RUN_TODAY'}
        if not args.dry_run:
            repo.recover_stale()
        targets=repo.targets(args.max_companies+1,args.company_id)
        limited=len(targets)>args.max_companies
        targets=targets[:args.max_companies]
        report={'date_kst':day.isoformat(),'source':'linkareer','target_companies':len(targets),
                'missing_postings':sum(c['missing_postings'] for c in targets),'remaining_backlog':limited}
        if args.dry_run:
            return {**report,'dry_run':True,'company_ids':[c['id'] for c in targets]}
        if tracked:
            conn.execute("""INSERT INTO public.external_pass_daily_run(source_platform,run_date,status)
                VALUES('linkareer',%s,'RUNNING') ON CONFLICT(source_platform,run_date) DO UPDATE
                SET status='RUNNING',completed_at=NULL""",(day,))
        if repo.platform_restricted():
            report.update(status='BLOCKED',error_code='ACCESS_RESTRICTED',outcomes=[])
        else:
            outcomes,blocked=process(repo,adapter or LinkareerAdapter(PublicHttp()),targets,args.max_records,args.max_pages,
                                     getattr(args,'company_search_name',None))
            report.update(status='BLOCKED' if blocked else 'FAILED' if any(r['status']=='FAILED' for r in outcomes) else 'SUCCEEDED',outcomes=outcomes)
        if tracked:
            conn.execute("""UPDATE public.external_pass_daily_run SET status=%s,completed_at=now(),report=%s::jsonb
                WHERE source_platform='linkareer' AND run_date=%s""",(report['status'],json.dumps(report),day))
        return report
    finally:
        conn.execute('SELECT pg_advisory_unlock(703114,2)')


def next_run(now, hour=9):
    local=now.astimezone(KST)
    result=local.replace(hour=hour,minute=0,second=0,microsecond=0)
    return result if result>local else result+dt.timedelta(days=1)


def wait_until(due):
    print(json.dumps({'next_run_kst':due.isoformat()}),flush=True)
    while True:
        remaining=(due-dt.datetime.now(KST)).total_seconds()
        if remaining<=0:
            return
        time.sleep(min(60,remaining))


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--dry-run',action='store_true',help='Scan database only; no crawling or writes')
    p.add_argument('--serve',action='store_true',help='Catch up once on startup, then run daily in KST')
    p.add_argument('--hour',type=int,default=9,help='KST hour for the daily schedule')
    p.add_argument('--max-companies',type=int,default=30)
    p.add_argument('--max-records',type=int,default=40)
    p.add_argument('--max-pages',type=int,default=2)
    p.add_argument('--company-id',type=int,help='Limit a one-time initial backfill to a company')
    p.add_argument('--company-search-name',help='Verified alternate name for this company only; also accepted as an exact company alias')
    args=p.parse_args(argv)
    if args.company_search_name is not None:
        args.company_search_name=args.company_search_name.strip()
        if not args.company_id or not args.company_search_name or args.serve:
            p.error('--company-search-name requires --company-id and a nonempty verified name')
    if not 0<=args.hour<=23 or not 1<=args.max_companies<=100 or not 1<=args.max_records<=100 or not 1<=args.max_pages<=5 or (args.company_id is not None and args.company_id<1) or (args.serve and (args.dry_run or args.company_id)):
        p.error('Invalid daily limits or incompatible serve options')
    if args.serve:
        now=dt.datetime.now(KST)
        today=now.replace(hour=args.hour,minute=0,second=0,microsecond=0)
        if now<today:
            wait_until(today)
    while True:
        try:
            import psycopg
            from psycopg.rows import dict_row
            options='-c default_transaction_read_only=on' if args.dry_run else ''
            with psycopg.connect(os.environ['DATABASE_URL'],autocommit=True,row_factory=dict_row,
                                 connect_timeout=10,options=options) as conn:
                report=run_once(conn,args)
            print(json.dumps(report),flush=True)
            failed=report.get('status') in ('FAILED','BLOCKED')
        except Exception as exc:
            print(json.dumps({'status':'FAILED','error_code':getattr(exc,'code','DAILY_FAILED')}),flush=True)
            failed=True
        if not args.serve:
            return 1 if failed else 0
        wait_until(next_run(dt.datetime.now(KST),args.hour))


if __name__=='__main__':
    raise SystemExit(main())
