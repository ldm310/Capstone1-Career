"""Explicit versioned upgrade for daily Linkareer collection and two-sample readiness."""
import hashlib
import json
import os
from .migrate import ROOT, migrate_public, public_snapshot
from .storage import TABLES
from .errors import ContractError

DAILY_TABLES = {'external_pass_material_body','external_pass_daily_company','external_pass_daily_run'}


def migrate_daily(conn):
    migrate_public(conn)
    ddl = (ROOT/'db/migrations/08-external-pass-daily.sql').read_text(encoding='utf-8')
    checksum = hashlib.sha256(ddl.encode()).hexdigest()
    excluded = set(TABLES.values()) | DAILY_TABLES
    with conn.transaction():
        conn.execute('SELECT pg_advisory_xact_lock(703114,1)')
        if not conn.execute('SELECT pg_try_advisory_xact_lock(703114,2) AS yes').fetchone()['yes']:
            raise ContractError('A crawler is running; retry migration later')
        old = conn.execute("SELECT checksum FROM public.external_pass_schema_migration WHERE version='public-08'").fetchone()
        existing = conn.execute("SELECT tablename,tableowner=current_user AS owned FROM pg_tables WHERE schemaname='public' AND tablename=ANY(%s)",(list(DAILY_TABLES),)).fetchall()
        if old:
            if old['checksum'] != checksum or {r['tablename'] for r in existing} != DAILY_TABLES or not all(r['owned'] for r in existing):
                raise ContractError('Daily store version or ownership conflicts')
            return {'migration':'public-08','already_applied':True}
        if existing:
            raise ContractError('Unversioned daily table collision')
        before={k:v for k,v in public_snapshot(conn).items() if k not in excluded}
        conn.execute(ddl)
        after={k:v for k,v in public_snapshot(conn).items() if k not in excluded}
        if before!=after:
            raise ContractError('Pipeline data changed; rollback')
        conn.execute("INSERT INTO public.external_pass_schema_migration(version,checksum) VALUES('public-08',%s)",(checksum,))
    return {'migration':'public-08','already_applied':False,'pipeline_unchanged':True}


def main():
    import psycopg
    from psycopg.rows import dict_row
    try:
        with psycopg.connect(os.environ['DATABASE_URL'],autocommit=True,row_factory=dict_row,connect_timeout=10) as conn:
            print(json.dumps(migrate_daily(conn)))
        return 0
    except Exception as exc:
        print(json.dumps({'error_code':getattr(exc,'code','MIGRATION_FAILED'),'rolled_back':True}))
        return 1


if __name__=='__main__':
    raise SystemExit(main())
