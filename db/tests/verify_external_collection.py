"""Full local verification in a new disposable PostgreSQL container; never loads team credentials."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import re
import secrets
import socket
import subprocess
import sys
import time
import xml.etree.ElementTree as ET

sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[2]
CRAWLER=ROOT/'data-pipeline/external-pass-crawler'
sys.path.insert(0,str(CRAWLER))


def module(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value);return value


def main():
    import psycopg
    from psycopg.conninfo import make_conninfo
    from psycopg.rows import dict_row
    from psycopg import sql
    from external_pass_crawler.migrate import migrate,migrate_public
    from external_pass_crawler.storage import OwnedConnection
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--java-home',default=os.getenv('JAVA_HOME'))
    parser.add_argument('--crawler-only',action='store_true')
    parser.add_argument('--http-smoke-only',action='store_true')
    parser.add_argument('--with-http-smoke',action='store_true')
    parser.add_argument('--owned-public',action='store_true')
    args=parser.parse_args()
    suffix=secrets.token_hex(5);name='career-external-verify-'+suffix
    password=secrets.token_urlsafe(32);created=False;report={}
    def run(command,**kwargs):
        p=subprocess.run(command,capture_output=True,**kwargs)
        if p.returncode:raise RuntimeError('Local subprocess failed: '+Path(command[0]).name)
        return p.stdout.decode('utf-8',errors='replace')
    def docker(*command,**kwargs):return run(['docker',*command],**kwargs)
    def service_state():
        names=docker('ps','--format','{{.Names}}').splitlines()
        result={}
        for current in names:
            if current==name:continue
            info=json.loads(docker('inspect',current))[0]
            result[current]=(info['Id'],info['State']['StartedAt'],[m.get('Name') for m in info['Mounts']])
        return result
    def sanitized(data):
        value=data.decode('utf-8',errors='replace')
        return value.replace(password,'[REDACTED]')
    try:
        existing=service_state()
        for port in range(5450,5500):
            try:
                with socket.socket() as sock:sock.bind(('127.0.0.1',port))
                break
            except OSError:continue
        else:raise RuntimeError('No free isolated test port')
        similarity='extcrawler_test_similarity_'+suffix
        legacy='extcrawler_test_public_'+suffix
        external='extcrawler_test_external_'+suffix
        docker('run','-d','--name',name,'--mount','type=tmpfs,destination=/var/lib/postgresql',
               '-p',f'127.0.0.1:{port}:5432','-e','POSTGRES_PASSWORD','-e','POSTGRES_DB='+similarity,
               'postgres:18',env={**os.environ,'POSTGRES_PASSWORD':password})
        created=True
        for _ in range(60):
            p=subprocess.run(['docker','exec',name,'pg_isready','-U','postgres','-d',similarity],capture_output=True)
            if p.returncode==0:break
            time.sleep(1)
        else:raise RuntimeError('Disposable DB readiness timeout')
        config={'host':'127.0.0.1','port':port,'dbname':similarity,'user':'postgres','password':password}
        with psycopg.connect(**config,autocommit=True,row_factory=dict_row) as conn:
            for db in (legacy,external):conn.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(db)))
            conn.execute((ROOT/'db/init/01-job-schema.sql').read_text(encoding='utf-8'))
            conn.execute((ROOT/'backend/src/test/resources/posting-similarity-fixtures.sql').read_text(encoding='utf-8'))
            install=migrate_public if args.owned_public else migrate
            report['migration']=install(conn)
            report['migration_repeat']=install(conn)
            if args.owned_public:conn=OwnedConnection(conn)
            request=conn.execute("""INSERT INTO external_data.collection_request(target_posting_id,target_recruit_unit_id,
                standard_role_code,policy_version,selection_status,request_source)
                VALUES(1,11,'backend','keyword-mvp-2','SELECTED','MANUAL_BATCH') RETURNING id""").fetchone()['id']
            conn.execute("""INSERT INTO external_data.collection_candidate(request_id,candidate_posting_id,
                candidate_recruit_unit_id,candidate_company_id,standard_role_code,confidence,feature_mode,evidence_count,
                candidate_rank,requested,reused,requested_at)
                VALUES(%s,3,31,2,'backend','HIGH','REQUIRED',2,1,true,true,now())""",(request,))
            conn.execute("INSERT INTO external_data.company_collection(company_id,status,completed_at) VALUES(2,'READY',now())")
            for company,posting in ((2,3),(1,2)):
                for number in range(5):
                    material=conn.execute("""INSERT INTO external_data.pass_material(company_id,source_platform,
                        external_record_id,role_name,title,content,source_url)
                        VALUES(%s,'fixture',%s,'backend','fixture','{"technologies":["Python"]}',
                        'https://example.invalid/fixture') RETURNING id""",(company,f'{company}-{number}')).fetchone()['id']
                    conn.execute("INSERT INTO external_data.posting_pass_material(posting_id,material_id,relation_type) VALUES(%s,%s,'EXACT_ROLE')",(posting,material))
        env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1','PYTHONIOENCODING':'utf-8'}
        os.environ['PUBLIC_SCHEMA_TEST_DSN']=make_conninfo(**{**config,'dbname':legacy})
        helper=module('external_verify_public_fixtures',ROOT/'db/tests/test_public_schema_integration.py')
        with psycopg.connect(**{**config,'dbname':legacy},autocommit=True) as conn:
            helper.core(conn);helper.extensions(conn);helper.dependent_rows(conn)
        with psycopg.connect(**{**config,'dbname':external},autocommit=True,row_factory=dict_row) as conn:
            conn.execute((ROOT/'db/init/01-job-schema.sql').read_text(encoding='utf-8'));migrate(conn)
        env.update({'EXTERNAL_TEST_DATABASE_URL':make_conninfo(**{**config,'dbname':external}),
                    'POSTING_SIMILARITY_TEST_URL':f'jdbc:postgresql://127.0.0.1:{port}/{similarity}',
                    'POSTING_SIMILARITY_TEST_USER':'postgres','POSTING_SIMILARITY_TEST_PASSWORD':password,
                    'PUBLIC_SCHEMA_TEST_URL':f'jdbc:postgresql://127.0.0.1:{port}/{legacy}',
                    'PUBLIC_SCHEMA_TEST_USER':'postgres','PUBLIC_SCHEMA_TEST_PASSWORD':password})
        print('Fresh PostgreSQL fixtures and repeatable public migration prepared.',flush=True)
        if not args.http_smoke_only:
            p=subprocess.run([sys.executable,'-m','unittest','discover','-s','tests','-v'],cwd=CRAWLER,env=env,capture_output=True)
            output=sanitized(p.stdout+p.stderr)
            report['crawler_exit']=p.returncode
            count=re.search(r'Ran (\d+) tests',output)
            report['crawler_tests']=int(count.group(1)) if count else 0
            report['crawler_skips']=len(re.findall(r'\.\.\. skipped ',output))
            if p.returncode:print(output[-16000:],flush=True)
            assert p.returncode==0 and report['crawler_tests']>0 and report['crawler_skips']==0
        if not args.crawler_only and not args.http_smoke_only:
            java=str(Path(args.java_home)/'bin'/('java.exe' if os.name=='nt' else 'java')) if args.java_home else 'java'
            if args.java_home:env['JAVA_HOME']=args.java_home
            p=subprocess.run([java,'-jar','gradle/wrapper/gradle-wrapper.jar','test','--no-daemon',
                              '--rerun-tasks','--no-build-cache','--no-configuration-cache'],cwd=ROOT/'backend',env=env,capture_output=True)
            output=sanitized(p.stdout+p.stderr)
            print('\n'.join(line for line in output.splitlines() if line.startswith(('> Task','BUILD '))),flush=True)
            suites=[];bad_log='Unsuccessful: drop schema public' in output
            for file in sorted((ROOT/'backend/build/test-results/test').glob('TEST-*.xml')):
                text=file.read_text(encoding='utf-8');tree=ET.fromstring(text)
                suites.append({key:tree.get(key) for key in ('name','tests','failures','errors','skipped')})
                bad_log|='Schema "public" cannot be dropped' in text
            report['backend_exit']=p.returncode
            report['backend_totals']={key:sum(int(s[key]) for s in suites) for key in ('tests','failures','errors','skipped')}
            report['backend_suites']=suites;report['h2_public_drop_log']=bad_log
            if p.returncode:print(output[-14000:],flush=True)
            assert p.returncode==0 and not bad_log
            assert all(report['backend_totals'][key]==0 for key in ('failures','errors','skipped'))
            assert report['backend_totals']['tests']>=160
        if args.http_smoke_only or args.with_http_smoke:
            smoke=module('external_collection_http_smoke',ROOT/'db/tests/smoke_external_collection_http.py')
            report['http_smoke']=smoke.verify(ROOT,config,args.java_home)
        report['existing_services_unchanged']=service_state()==existing
        assert report['existing_services_unchanged']
    except Exception as exc:
        report['verification_error_type']=type(exc).__name__
    finally:
        if created:
            docker('rm','-f','--volumes',name);report['temporary_database_removed']=True
        print(json.dumps(report,ensure_ascii=True),flush=True)
    return 1 if report.get('verification_error_type') else 0


if __name__=='__main__':raise SystemExit(main())
