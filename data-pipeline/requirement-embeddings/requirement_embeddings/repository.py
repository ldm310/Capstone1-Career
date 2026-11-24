import uuid
from psycopg import sql


class Repository:
    def __init__(self,conn,config):
        self.conn,self.config=conn,config
        row=conn.execute("SELECT storage_backend FROM public.be_embedding_schema_migration WHERE version='09'").fetchone()
        if not row:raise ValueError('EMBEDDING_SCHEMA_NOT_INSTALLED')
        self.storage=row['storage_backend']
        self.cast=sql.SQL('real[]')
        if self.storage=='vector':
            schema=conn.execute("SELECT n.nspname FROM pg_extension e JOIN pg_namespace n ON n.oid=e.extnamespace WHERE e.extname='vector'").fetchone()['nspname']
            self.cast=sql.Identifier(schema,'vector')

    def recover_uncertain(self):
        with self.conn.transaction():
            self.conn.execute("UPDATE public.be_embedding_cache SET status='UNKNOWN',error_code='DELIVERY_UNCERTAIN',updated_at=now() WHERE status='IN_FLIGHT'")
            self.conn.execute("UPDATE public.be_embedding_request SET status='UNKNOWN',error_code='DELIVERY_UNCERTAIN',updated_at=now() WHERE status='IN_FLIGHT'")

    def cached(self,hashes):
        if not hashes:return {}
        return {r['input_hash']:r for r in self.conn.execute("""SELECT id,input_hash,status FROM public.be_embedding_cache
            WHERE model_name=%s AND model_revision=%s AND embedding_dimension=%s AND preprocessing_version=%s
            AND input_hash=ANY(%s)""",(*self.config.key,list(hashes))).fetchall()}

    def claim(self,prepared):
        request=uuid.uuid4()
        with self.conn.transaction():
            self.conn.execute("""INSERT INTO public.be_embedding_request
                (id,model_name,model_revision,embedding_dimension,preprocessing_version,input_hashes,status)
                VALUES(%s,%s,%s,%s,%s,%s,'IN_FLIGHT')""",(request,*self.config.key,[p.input_hash for p in prepared]))
            claimed={}
            for p in prepared:
                row=self.conn.execute("""INSERT INTO public.be_embedding_cache
                    (model_name,model_revision,embedding_dimension,preprocessing_version,input_hash,input_text,status,request_id)
                    VALUES(%s,%s,%s,%s,%s,%s,'IN_FLIGHT',%s) ON CONFLICT DO NOTHING RETURNING id,input_hash,status""",
                    (*self.config.key,p.input_hash,p.text,request)).fetchone()
                if row is None:raise ValueError('EMBEDDING_CLAIM_CONFLICT')
                claimed[p.input_hash]=row
        return request,claimed

    def bind(self,p,cache=None):
        s=p.source
        # A slow API must not attach a vector to a requirement whose source has since changed.
        fresh=self.conn.execute("SELECT source_fingerprint,source_run_id FROM public.be_embedding_source WHERE requirement_id=%s",(s['requirement_id'],)).fetchone()
        if not fresh or fresh['source_fingerprint']!=s['source_fingerprint'] or fresh['source_run_id']!=s['source_run_id']:return False
        self.conn.execute("""INSERT INTO public.be_requirement_embedding
            (requirement_id,recruit_unit_id,source_run_id,category,role_code,source_fingerprint,taxonomy_hash,
             model_name,model_revision,embedding_dimension,preprocessing_version,input_hash,cache_id,eligibility,exclusion_code)
            VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT(requirement_id,model_name,model_revision,embedding_dimension,preprocessing_version)
            DO UPDATE SET recruit_unit_id=excluded.recruit_unit_id,source_run_id=excluded.source_run_id,
                category=excluded.category,role_code=excluded.role_code,source_fingerprint=excluded.source_fingerprint,
                taxonomy_hash=excluded.taxonomy_hash,input_hash=excluded.input_hash,cache_id=excluded.cache_id,
                eligibility=excluded.eligibility,exclusion_code=excluded.exclusion_code,updated_at=now()""",
            (s['requirement_id'],s['recruit_unit_id'],s['source_run_id'],s['category'],p.role,s['source_fingerprint'],p.taxonomy_hash,
             *self.config.key,p.input_hash if cache else None,cache['id'] if cache else None,'ELIGIBLE' if cache else 'EXCLUDED',p.error if not cache else None))
        return True

    def finish(self,request,prepared,result,tokens,price=None):
        with self.conn.transaction():
            for index,p in enumerate(prepared):
                vector,error=result[index]
                value=('['+','.join(map(str,vector))+']') if vector is not None and self.storage=='vector' else vector
                self.conn.execute(sql.SQL("""UPDATE public.be_embedding_cache SET embedding=%s::{},status=%s,
                    error_code=%s,updated_at=now() WHERE request_id=%s AND input_hash=%s AND status='IN_FLIGHT'""").format(self.cast),
                    (value,'FAILED' if error else 'READY',error,request,p.input_hash))
            any_error=next((error for _,error in result.values() if error),None)
            self.conn.execute("""UPDATE public.be_embedding_request SET status=%s,error_code=%s,prompt_tokens=%s,
                price_per_million_tokens=%s,estimated_cost_usd=%s,pricing_version=%s,updated_at=now() WHERE id=%s""",
                ('FAILED' if any_error else 'READY',any_error,tokens,price,None if price is None else tokens*price/1_000_000,
                 None if price is None else 'configured-estimate-v1',request))

    def fail(self,request,code,uncertain):
        status='UNKNOWN' if uncertain else 'FAILED'
        with self.conn.transaction():
            self.conn.execute("UPDATE public.be_embedding_cache SET status=%s,error_code=%s,updated_at=now() WHERE request_id=%s AND status='IN_FLIGHT'",(status,code,request))
            self.conn.execute("UPDATE public.be_embedding_request SET status=%s,error_code=%s,updated_at=now() WHERE id=%s",(status,code,request))
