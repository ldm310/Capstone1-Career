"""Actual local Spring HTTP -> Python registration -> fixture worker -> status GET smoke check."""
import json
import os
from pathlib import Path
import socket
import subprocess
import threading
import time
import urllib.error
import urllib.request


def verify(root,config,java_home):
    import psycopg
    from psycopg import sql
    from psycopg.rows import dict_row
    from external_pass_crawler.comparison_batch import selection,consume
    from external_pass_crawler.comparison_requests import RequestRepository
    from external_pass_crawler.models import SearchPage
    java=str(Path(java_home)/'bin'/('java.exe' if os.name=='nt' else 'java')) if java_home else 'java'
    build=subprocess.run([java,'-jar','gradle/wrapper/gradle-wrapper.jar','bootJar','--no-daemon',
                          '--no-build-cache','--no-configuration-cache'],cwd=root/'backend',capture_output=True)
    if build.returncode:raise RuntimeError('Smoke Backend build failed')
    jars=[p for p in (root/'backend/build/libs').glob('*.jar') if not p.name.endswith('-plain.jar')]
    if len(jars)!=1:raise RuntimeError('One runnable Backend jar required')
    with socket.socket() as s:s.bind(('127.0.0.1',0));port=s.getsockname()[1]
    url=f"jdbc:postgresql://127.0.0.1:{config['port']}/{config['dbname']}"
    env={**os.environ,'SPRING_PROFILES_ACTIVE':'rds','SPRING_DATASOURCE_URL':url,
         'SPRING_DATASOURCE_USERNAME':config['user'],'SPRING_DATASOURCE_PASSWORD':config['password'],
         'SPRING_JPA_HIBERNATE_DDL_AUTO':'none','SPRING_SQL_INIT_MODE':'never',
         'SERVER_ADDRESS':'127.0.0.1','SERVER_PORT':str(port),'LOGGING_LEVEL_ROOT':'WARN','SPRING_MAIN_BANNER_MODE':'off'}
    env.pop('OPENAI_API_KEY',None)
    env['OPENAI_EMBEDDING_MODEL']='text-embedding-3-small'
    env['OPENAI_EMBEDDING_DIMENSIONS']='3'
    env['POSTING_EMBEDDING_MODE']='SHADOW_MODE'
    process=subprocess.Popen([java,'-jar',str(jars[0])],env=env,cwd=root/'backend',
                             stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
    logs=[]
    def drain():
        for line in process.stdout:logs.append(line)
    threading.Thread(target=drain,daemon=True).start()
    base=f'http://127.0.0.1:{port}'
    def get(path):
        try:
            with urllib.request.urlopen(base+path,timeout=30) as response:return response.status,json.load(response)
        except urllib.error.HTTPError as e:return e.code,{}
    def snapshot(conn):
        result={}
        for row in conn.execute("SELECT schemaname,tablename FROM pg_tables WHERE schemaname IN ('public','external_data') ORDER BY 1,2").fetchall():
            item=conn.execute(sql.SQL("SELECT count(*) AS n,md5(coalesce(string_agg(to_jsonb(t)::text,'' ORDER BY to_jsonb(t)::text),'')) AS h FROM {}.{} t").format(sql.Identifier(row['schemaname']),sql.Identifier(row['tablename']))).fetchone()
            result[row['schemaname']+'.'+row['tablename']]=(item['n'],item['h'])
        result['sequences']=[tuple(r.values()) for r in conn.execute("SELECT schemaname,sequencename,last_value FROM pg_sequences WHERE schemaname IN ('public','external_data') ORDER BY 1,2").fetchall()]
        return result
    try:
        for _ in range(120):
            if process.poll() is not None:
                # Print only sanitized local startup diagnostics on failure.
                text=b''.join(logs).decode('utf-8',errors='replace').replace(config['password'],'[REDACTED]').replace(url,'[REDACTED]')
                print(text[-4000:],flush=True)
                raise RuntimeError('Smoke server exited')
            try:
                code,document=get('/v3/api-docs')
                if code==200:break
            except OSError:pass
            time.sleep(1)
        else:raise RuntimeError('Smoke server readiness timeout')
        class EmptyPublicFixture:
            def search(self,company,page):return SearchPage((),0)
            def detail(self,external_id):raise AssertionError('No detail request expected')
        with psycopg.connect(**config,autocommit=True,row_factory=dict_row) as conn:
            data=selection(base,1,11)
            assert any(c['requiredSemanticSimilarity'] is not None for c in data['candidates'])
            assert all(c['embeddingModel']=='text-embedding-3-small' for c in data['candidates'])
            repo=RequestRepository(conn);repo.check_contract();request=repo.register(data)
            # No website is contacted; the fixture simulates an empty result for any new company.
            consume(repo,EmptyPublicFixture(),[request])
            before=snapshot(conn)
            path='/api/postings/1/recruit-units/11/external-pass-collection-status'
            status,result=get(path)
            assert status==200 and result['collectionStatus']=='READY' and result['materialCount']==5, 'Unexpected HTTP collection status or material count'
            assert snapshot(conn)==before
            assert get('/api/postings/1/recruit-units/31/external-pass-collection-status')[0]==400
            assert get('/api/postings/999999/recruit-units/11/external-pass-collection-status')[0]==404
            repo.conn.execute("UPDATE external_data.collection_candidate SET confidence='LOW' WHERE request_id=%s AND candidate_recruit_unit_id=31",(request,))
            before_conflict=snapshot(conn)
            assert get(path)[0]==409
            assert snapshot(conn)==before_conflict
            repo.conn.execute("UPDATE external_data.collection_candidate SET confidence='HIGH' WHERE request_id=%s AND candidate_recruit_unit_id=31",(request,))
            assert snapshot(conn)==before
            material_status,material_response=get('/api/postings/3/external-pass-materials')
            keyword_status,keyword_response=get('/api/postings/3/external-pass-keywords')
            assert material_status==200 and material_response['materials']['totalElements']==5
            assert keyword_status==200 and keyword_response['sourceMaterialCount']==5
            assert keyword_response['unmappedKeywords']==['Python']
            assert snapshot(conn)==before
            assert path.replace('/1/','/{postingId}/').replace('/11/','/{recruitUnitId}/') in document['paths']
            return {'http_statuses':[200,400,404,409],'backend_candidate_count':len(data['candidates']),
                    'material_count':result['materialCount'],'public_and_external_unchanged_by_get':True,
                    'network_fixture_only':True,'swagger_registered':True,
                    'shadow_fields_http':True,'shadow_model':'text-embedding-3-small',
                    'materials_http':material_status,'keywords_http':keyword_status}
    finally:
        process.terminate()
        try:process.wait(timeout=20)
        except subprocess.TimeoutExpired:process.kill();process.wait(timeout=10)
