from pathlib import Path

ROOT=Path(__file__).resolve().parents[3]


def source_sql():
    ddl=(ROOT/'db/migrations/09-requirement-embedding-shadow.sql').read_text(encoding='utf-8')
    return ddl.split('CREATE VIEW public.be_embedding_source AS\n',1)[1].split(';\n\nCREATE VIEW',1)[0]


def rows(conn,limit=1000):
    if conn.execute("SELECT EXISTS(SELECT 1 FROM public.extraction_run WHERE is_current GROUP BY posting_id HAVING count(*)>1) AS yes").fetchone()['yes']:
        raise ValueError('DUPLICATE_CURRENT_EXTRACTION')
    return conn.execute('SELECT * FROM ('+source_sql()+') source ORDER BY requirement_id LIMIT %s',(limit,)).fetchall()
