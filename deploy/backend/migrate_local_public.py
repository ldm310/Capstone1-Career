"""Back up and rehearse the legacy local job -> public migration; never connects to RDS."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import uuid

ROOT = Path(__file__).resolve().parents[2]
SQL = ROOT / 'db/migrations/06-local-job-tables-to-public.sql'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true', help='Also migrate the actual local career database')
    args = parser.parse_args()
    container = 'career-db'
    info = json.loads(subprocess.check_output(['docker', 'inspect', container], text=True))[0]
    if not info['Config']['Image'].startswith('postgres:'):
        raise RuntimeError('Expected the local PostgreSQL container')
    env = dict(value.split('=', 1) for value in info['Config']['Env'] if '=' in value)
    user = env.get('POSTGRES_USER', 'postgres')
    database = env.get('POSTGRES_DB', 'career')
    if database != 'career':
        raise RuntimeError('Expected the local career database')

    def psql(db, sql, check=True):
        result = subprocess.run(['docker', 'exec', '-i', '-e', 'PGCLIENTENCODING=UTF8', container,
                                 'psql', '-h', '/var/run/postgresql', '-X', '-qAt', '-U', user, '-d', db, '-v', 'ON_ERROR_STOP=1'],
                                input=sql, capture_output=True, text=True, encoding='utf-8')
        if check and result.returncode:
            raise RuntimeError(result.stderr)
        return result

    def query(db, sql):
        return json.loads(psql(db, sql).stdout)

    def snapshot(db):
        tables = query(db, "SELECT coalesce(json_agg(json_build_array(schemaname,tablename) ORDER BY schemaname,tablename),'[]') FROM pg_tables WHERE schemaname IN ('job','public','profile','external_data')")
        result = {'tables': {}, 'sequences': {}}
        for schema, name in tables:
            ident = '"' + schema.replace('"', '""') + '"."' + name.replace('"', '""') + '"'
            key = ('public' if schema == 'job' else schema) + '.' + name
            result['tables'][key] = query(db, f"SELECT json_build_object('count',count(*),'hash',md5(coalesce(string_agg(to_jsonb(t)::text,'' ORDER BY to_jsonb(t)::text),''))) FROM {ident} t")
        seqs = query(db, "SELECT coalesce(json_agg(json_build_array(schemaname,sequencename) ORDER BY schemaname,sequencename),'[]') FROM pg_sequences WHERE schemaname IN ('job','public','profile','external_data')")
        for schema, name in seqs:
            ident = '"' + schema.replace('"', '""') + '"."' + name.replace('"', '""') + '"'
            key = ('public' if schema == 'job' else schema) + '.' + name
            result['sequences'][key] = query(db, f'SELECT json_build_array(last_value,is_called) FROM {ident}')
        return result

    out = ROOT / 'work' / ('local-public-migration-' + uuid.uuid4().hex)
    out.mkdir(parents=True)
    backup = out / 'career-before.dump'
    with backup.open('wb') as stream:
        subprocess.run(['docker', 'exec', container, 'pg_dump', '-h', '/var/run/postgresql', '-U', user, '-d', database, '-Fc'], stdout=stream, check=True)
    before = snapshot(database)
    (out / 'before.json').write_text(json.dumps(before, indent=2), encoding='utf-8')
    if query(database, "SELECT count(*) FROM pg_tables WHERE schemaname='job'") == 0:
        assert query(database, "SELECT to_json(to_regclass('public.posting') IS NOT NULL)"), 'No public posting table'
        assert query(database, "SELECT count(*) FROM pg_constraint c JOIN pg_class t ON t.oid=c.confrelid JOIN pg_namespace n ON n.oid=t.relnamespace WHERE c.contype='f' AND n.nspname='job'") == 0
        report = {'status': 'already_public', 'applied': False, 'backup': str(backup), 'rds_modified': False}
        (out / 'verification.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
        print(json.dumps(report, indent=2))
        return
    clone = 'extcrawler_test_move_' + uuid.uuid4().hex
    psql('postgres', f'CREATE DATABASE {clone}')
    checks = {}
    try:
        with backup.open('rb') as stream:
            subprocess.run(['docker', 'exec', '-i', container, 'pg_restore', '-h', '/var/run/postgresql', '-U', user, '-d', clone, '--exit-on-error'], stdin=stream, check=True)
        migration = SQL.read_text(encoding='utf-8')
        # Seed only the disposable clone; exercise nonempty rows and external FKs.
        psql(clone, r"""
            INSERT INTO job.company(name) VALUES ('migration-fixture') RETURNING id AS cid \gset
            INSERT INTO job.posting(company_id,site,site_posting_no,title,kind,status,raw_path,raw_hash,collected_at,last_checked_at)
              VALUES (:cid,'saramin','migration-fixture','Migration fixture','글','진행','fixture',repeat('0',64),now(),now()) RETURNING id AS pid \gset
            INSERT INTO external_data.pass_material(company_id,source_platform,external_record_id,role_name,title,content,source_url)
              VALUES (:cid,'test','migration-fixture','backend','fixture','Java','https://example.invalid/fixture') RETURNING id AS mid \gset
            INSERT INTO external_data.company_collection(company_id) VALUES (:cid);
            INSERT INTO external_data.posting_pass_material(posting_id,material_id,relation_type) VALUES (:pid,:mid,'EXACT_ROLE');
        """)
        clone_before = snapshot(clone)
        psql(clone, migration)
        assert snapshot(clone) == clone_before, 'Clone rows or sequences changed'
        checks['nonempty_clone_preserved'] = True
        psql(clone, 'BEGIN; UPDATE external_data.posting_pass_material SET relation_type=relation_type; ROLLBACK;')
        checks['company_guard_uses_public'] = True
        psql(clone, migration)
        assert snapshot(clone) == clone_before
        checks['repeat_safe'] = True
        psql(clone, 'CREATE TABLE job.company(id bigint PRIMARY KEY);')
        failed = psql(clone, migration, check=False)
        assert failed.returncode != 0 and 'Conflicting public objects' in failed.stderr
        assert query(clone, "SELECT to_json(to_regclass('job.company') IS NOT NULL AND to_regclass('public.company') IS NOT NULL)")
        checks['destination_conflict_rolls_back'] = True
    finally:
        # Only this script's newly created disposable database can be dropped.
        assert clone.startswith('extcrawler_test_move_') and len(clone) == 53
        psql('postgres', f'DROP DATABASE {clone} WITH (FORCE)')
    if args.apply:
        assert snapshot(database) == before, 'Local database changed during rehearsal; take a new backup'
        psql(database, migration)
        after = snapshot(database)
        assert after == before, 'Local rows or sequences changed'
        checks['local_rows_and_sequences_preserved'] = True
        checks['legacy_fk_count'] = query(database, "SELECT count(*) FROM pg_constraint c JOIN pg_class t ON t.oid=c.confrelid JOIN pg_namespace n ON n.oid=t.relnamespace WHERE c.contype='f' AND n.nspname='job'")
        assert checks['legacy_fk_count'] == 0
        (out / 'after.json').write_text(json.dumps(after, indent=2), encoding='utf-8')
    report = {'verifiedAt': datetime.now(timezone.utc).isoformat(), 'applied': args.apply,
              'backup': str(backup), 'checks': checks, 'rds_modified': False}
    (out / 'verification.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
