"""Install only caller-owned objects; never install an extension or alter pipeline objects."""
import hashlib
import json
import os
from pathlib import Path
from psycopg import sql

ROOT=Path(__file__).resolve().parents[3]
TABLES=('be_embedding_schema_migration','be_embedding_request','be_embedding_cache','be_requirement_embedding')
OBJECTS=(*TABLES,'be_embedding_source','be_requirement_embedding_view','be_requirement_embedding_unit_idx')


def capabilities(conn):
    return conn.execute("""SELECT n.nspname AS schema,e.extversion,
        has_schema_privilege(n.oid,'USAGE') AND has_type_privilege(t.oid,'USAGE') AS usable
        FROM pg_extension e JOIN pg_namespace n ON n.oid=e.extnamespace
        JOIN pg_type t ON t.typnamespace=n.oid AND t.typname='vector' WHERE e.extname='vector'""").fetchone()


def pipeline_snapshot(conn):
    result={}
    for row in conn.execute("SELECT tablename FROM pg_tables WHERE schemaname='public' AND tablename NOT LIKE 'be\\_%' ESCAPE '\\' ORDER BY tablename"):
        value=conn.execute(sql.SQL("SELECT count(*) AS n,md5(coalesce(string_agg(to_jsonb(t)::text,'' ORDER BY to_jsonb(t)::text),'')) AS h FROM public.{} t").format(sql.Identifier(row['tablename']))).fetchone()
        result[row['tablename']]=(value['n'],value['h'])
    return result


def migrate(conn):
    template=(ROOT/'db/migrations/09-requirement-embedding-shadow.sql').read_text(encoding='utf-8')
    checksum=hashlib.sha256(template.encode()).hexdigest()
    with conn.transaction():
        conn.execute('SELECT pg_advisory_xact_lock(703114,4)')
        if not conn.execute('SELECT pg_try_advisory_xact_lock(703114,3) AS yes').fetchone()['yes']:
            raise ValueError('EMBEDDING_BATCH_RUNNING')
        existing=conn.execute("SELECT relname,relowner=current_user::regrole AS owned FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='public' AND relname=ANY(%s)",(list(OBJECTS),)).fetchall()
        if existing:
            if {r['relname'] for r in existing}!=set(OBJECTS) or not all(r['owned'] for r in existing):raise ValueError('EMBEDDING_OBJECT_CONFLICT')
            old=conn.execute("SELECT checksum,storage_backend FROM public.be_embedding_schema_migration WHERE version='09'").fetchone()
            if not old or old['checksum']!=checksum:raise ValueError('EMBEDDING_MIGRATION_CONFLICT')
            return {'already_applied':True,'storage':old['storage_backend']}
        # READ ONLY capability check is available separately; this only inspects catalogs, not CREATE EXTENSION.
        vector=capabilities(conn)
        storage='vector' if vector and vector['usable'] else 'real[]'
        dimension='cardinality(embedding)=embedding_dimension AND array_ndims(embedding)=1 AND array_position(embedding,NULL) IS NULL'
        typ='real[]'
        if storage=='vector':
            schema=vector['schema']
            usable=conn.execute("SELECT count(*) AS n FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname=%s AND p.proname='vector_dims' AND has_function_privilege(p.oid,'EXECUTE')",(schema,)).fetchone()['n']
            if not usable:storage='real[]'
            else:
                typ=sql.Identifier(schema,'vector').as_string(conn)
                dimension=sql.Identifier(schema,'vector_dims').as_string(conn)+'(embedding)=embedding_dimension'
        before=pipeline_snapshot(conn)
        conn.execute(template.replace('__EMBEDDING_TYPE__',typ).replace('__DIMENSION_CHECK__',dimension))
        conn.execute("INSERT INTO public.be_embedding_schema_migration(version,checksum,storage_backend) VALUES('09',%s,%s)",(checksum,storage))
        if pipeline_snapshot(conn)!=before:raise ValueError('PIPELINE_CHANGED')
    return {'already_applied':False,'storage':storage,'pipeline_unchanged':True}


def main():
    import argparse
    import psycopg
    from psycopg.rows import dict_row
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--inspect',action='store_true',help='READ ONLY catalogs; no installation or writes')
    args=parser.parse_args()
    try:
        with psycopg.connect(os.environ['DATABASE_URL'],autocommit=True,row_factory=dict_row,connect_timeout=10,
                options='-c default_transaction_read_only=on' if args.inspect else '') as conn:
            if args.inspect:
                with conn.transaction():
                    conn.execute('SET TRANSACTION READ ONLY')
                    print(json.dumps({'read_only':conn.execute('SHOW transaction_read_only').fetchone()['transaction_read_only'],
                        'installed_vector':capabilities(conn),'extension_install_attempted':False}))
            else:print(json.dumps(migrate(conn)))
        return 0
    except Exception:
        print(json.dumps({'error_code':'EMBEDDING_MIGRATION_FAILED'}));return 1


if __name__=='__main__':raise SystemExit(main())
