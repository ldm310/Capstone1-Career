from collections import Counter
from dataclasses import replace
from .client import SafeFailure,validate_response
from .preprocessing import Taxonomy,prepare,CompanyFilter
from .repository import Repository
from .source import rows


def token_counter(model):
    import tiktoken
    encoding=tiktoken.encoding_for_model(model)
    return lambda text:len(encoding.encode(text,disallowed_special=()))


def pack(prepared,config,count):
    batch=[];tokens=0
    for item in prepared:
        n=count(item.text)
        if n>config.input_tokens:raise ValueError('INPUT_TOO_LONG_WAS_NOT_FILTERED')
        if batch and (len(batch)>=config.batch_items or tokens+n>config.batch_tokens):
            yield batch;batch=[];tokens=0
        batch.append(item);tokens+=n
    if batch:yield batch


def run(conn,config,client=None,*,apply=False,limit=1000,count_tokens=None,price=None):
    if not conn.execute('SELECT pg_try_advisory_lock(703114,3) AS yes').fetchone()['yes']:
        return {'status':'SKIPPED','error_code':'EMBEDDING_BATCH_RUNNING'}
    try:
        taxonomy=Taxonomy()
        # A consistent source snapshot is released before network access.
        with conn.transaction():
            conn.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
            source=rows(conn,limit+1)
            companies=[r['name'] for r in conn.execute("SELECT name FROM public.company WHERE btrim(name)<>''")]
        limited=len(source)>limit;source=source[:limit]
        count=count_tokens or token_counter(config.model)
        company_filter=CompanyFilter(companies)
        prepared=[prepare(row,taxonomy,company_filter) for row in source]
        prepared=[replace(p,text=None,input_hash=None,error='INPUT_TOO_LONG') if p.text and count(p.text)>config.input_tokens else p for p in prepared]
        groups={}
        for p in prepared:
            if not p.error:groups.setdefault(p.input_hash,[]).append(p)
        report={'mode':'APPLY' if apply else 'DRY_RUN','source_rows':len(source),'limited':limited,
                'unique_inputs':len(groups),'excluded':dict(Counter(p.error for p in prepared if p.error)),
                'api_calls':0,'prompt_tokens':0,'reused_inputs':0,'failed_inputs':0,'unknown_inputs':0}
        exists=conn.execute("SELECT to_regclass('public.be_embedding_schema_migration') IS NOT NULL AS yes").fetchone()['yes']
        repo=Repository(conn,config) if exists else None
        cached=repo.cached(groups) if repo else {}
        report['reused_inputs']=sum(r['status']=='READY' for r in cached.values())
        report['failed_inputs']=sum(r['status']=='FAILED' for r in cached.values())
        report['unknown_inputs']=sum(r['status'] in ('UNKNOWN','IN_FLIGHT') for r in cached.values())
        report['pending_inputs']=len(set(groups)-set(cached))
        missing=[groups[h][0] for h in sorted(set(groups)-set(cached))]
        report['planned_api_calls']=sum(1 for _ in pack(missing,config,count))
        def coverage(current):
            return {category:{'source_rows':sum(p.source['category']==category for p in prepared),
                'eligible_rows':sum(p.source['category']==category and not p.error for p in prepared),
                'ready_vector_rows':sum(p.source['category']==category and current.get(p.input_hash,{}).get('status')=='READY' for p in prepared)}
                for category in ('REQUIRED','PREFERRED','DUTIES')}
        report['categories']=coverage(cached)
        if not apply:return report
        if repo is None:raise ValueError('EMBEDDING_SCHEMA_NOT_INSTALLED')
        if client is None:raise SafeFailure('AUTH_FAILED')
        repo.recover_uncertain()
        for p in prepared:
            if p.error:repo.bind(p)
            elif p.input_hash in cached:repo.bind(p,cached[p.input_hash])
        for batch in pack(missing,config,count):
            request,claimed=repo.claim(batch)
            stop=False
            try:
                report['api_calls']+=1
                result,tokens=validate_response(client.create([p.text for p in batch]),len(batch),config)
                repo.finish(request,batch,result,tokens,price)
                report['prompt_tokens']+=tokens
                report['failed_inputs']+=sum(error is not None for _,error in result.values())
            except SafeFailure as exc:
                repo.fail(request,exc.code,exc.uncertain)
                report['unknown_inputs' if exc.uncertain else 'failed_inputs']+=len(batch)
                if exc.code in ('AUTH_FAILED','RATE_LIMITED'):
                    report['safe_error_code']=exc.code
                    stop=True
            except Exception:
                # Provider response might have completed. Never automatically replay it after a DB failure.
                repo.fail(request,'DB_SAVE_FAILED',True);report['unknown_inputs']+=len(batch)
            for p in batch:
                for linked in groups[p.input_hash]:repo.bind(linked,claimed[p.input_hash])
            if stop:break
        final_cache=repo.cached(groups)
        report['pending_inputs']=len(groups)-len(final_cache)
        report['categories']=coverage(final_cache)
        report['estimated_cost_usd']=None if price is None else report['prompt_tokens']*price/1_000_000
        report['status']='PARTIAL' if report['failed_inputs'] or report['unknown_inputs'] or report.get('safe_error_code') else 'READY'
        return report
    finally:
        conn.execute('SELECT pg_advisory_unlock(703114,3)')
