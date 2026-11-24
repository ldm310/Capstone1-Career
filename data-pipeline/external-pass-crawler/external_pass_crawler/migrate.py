"""Atomic, repeatable installation using the single canonical external-material schema."""
import hashlib
import json
import os
from pathlib import Path
from psycopg import sql
from .errors import ContractError
from .repository import Repository
from .storage import OwnedConnection,owned,TABLES,OBJECTS,public_ddl

ROOT = Path(__file__).resolve().parents[3]
BASE_TABLES = {"company_collection", "pass_material", "posting_pass_material"}
REQUEST_COLUMNS = {
    "collection_request": {"id", "target_posting_id", "target_recruit_unit_id", "standard_role_code",
                           "policy_version", "selection_status", "request_source", "used_direct",
                           "requested_at", "updated_at"},
    "collection_candidate": {"id", "request_id", "candidate_posting_id", "candidate_recruit_unit_id",
                             "candidate_company_id", "standard_role_code", "confidence", "feature_mode",
                             "evidence_count", "candidate_rank", "is_selected", "requested", "reused", "requested_at"},
}


def public_snapshot(conn):
    result = {}
    tables = conn.execute("SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename").fetchall()
    for row in tables:
        table = row["tablename"]
        value = conn.execute(sql.SQL(
            "SELECT count(*) AS n,md5(coalesce(string_agg(to_jsonb(t)::text,'' ORDER BY to_jsonb(t)::text),'')) AS h "
            "FROM public.{} t").format(sql.Identifier(table))).fetchone()
        result[table] = (value["n"], value["h"])
    return result


def check_requests(conn):
    schema="public" if owned(conn) else "external_data"
    physical=lambda table:TABLES[table] if owned(conn) else table
    for table, required in REQUEST_COLUMNS.items():
        columns = {r["column_name"] for r in conn.execute(
            "SELECT column_name FROM information_schema.columns WHERE table_schema=%s AND table_name=%s",
            (schema,physical(table))).fetchall()}
        if columns != required:
            raise ContractError("Collection request table shape conflicts with migration")
    expected = {("collection_request", "target_posting_id", "public", "posting"),
                ("collection_request", "target_recruit_unit_id", "public", "recruit_unit"),
                ("collection_candidate", "request_id", "external_data", "collection_request"),
                ("collection_candidate", "candidate_posting_id", "public", "posting"),
                ("collection_candidate", "candidate_recruit_unit_id", "public", "recruit_unit"),
                ("collection_candidate", "candidate_company_id", "public", "company")}
    if owned(conn):
        expected={(physical(src),col,"public" if dst_schema=="external_data" else dst_schema,
                   physical(dst) if dst_schema=="external_data" else dst) for src,col,dst_schema,dst in expected}
    actual = set()
    for r in conn.execute("""
        SELECT s.relname AS src,a.attname AS col,n.nspname AS dst_schema,t.relname AS dst
        FROM pg_constraint c JOIN pg_class s ON s.oid=c.conrelid
        JOIN pg_namespace sn ON sn.oid=s.relnamespace JOIN pg_class t ON t.oid=c.confrelid
        JOIN pg_namespace n ON n.oid=t.relnamespace JOIN pg_attribute a ON a.attrelid=s.oid AND a.attnum=c.conkey[1]
        WHERE c.contype='f' AND sn.nspname=%s AND s.relname=ANY(%s)
        """,(schema,[physical('collection_request'),physical('collection_candidate')])).fetchall():
        actual.add((r["src"], r["col"], r["dst_schema"], r["dst"]))
    if actual != expected:
        raise ContractError("Collection request foreign keys conflict with public contract")
    guards = {(r["table_name"], r["trigger_name"], r["function_name"]) for r in conn.execute("""
        SELECT t.relname AS table_name,g.tgname AS trigger_name,p.proname AS function_name
        FROM pg_trigger g JOIN pg_class t ON t.oid=g.tgrelid JOIN pg_namespace n ON n.oid=t.relnamespace
        JOIN pg_proc p ON p.oid=g.tgfoid JOIN pg_namespace pn ON pn.oid=p.pronamespace
        WHERE n.nspname=%s AND pn.nspname=%s AND g.tgenabled<>'D'
          AND NOT g.tgisinternal
        """,(schema,schema)).fetchall()}
    required_guards={('posting_pass_material','posting_pass_material_company_guard','check_material_company'),
                     ('pass_material','pass_material_company_immutable','keep_material_company'),
                     ('collection_request','collection_request_provenance_guard','check_collection_provenance'),
                     ('collection_candidate','collection_candidate_provenance_guard','check_collection_provenance')}
    if owned(conn):required_guards={tuple(OBJECTS[name] for name in item) for item in required_guards}
    if not required_guards <= guards:
        raise ContractError("External company/provenance guards are missing or conflicting")


def migrate(conn):
    """Legacy-layout fixture/upgrade compatibility. New deployments use migrate_public()."""
    from psycopg.pq import TransactionStatus
    if not conn.autocommit or conn.info.transaction_status != TransactionStatus.IDLE:
        raise ContractError("Migration requires an idle autocommit connection")
    migration = (ROOT / "db/migrations/07-external-pass-collection-requests.sql").read_text(encoding="utf-8")
    checksum = hashlib.sha256(migration.encode()).hexdigest()
    with conn.transaction():
        conn.execute("SELECT pg_advisory_xact_lock(703114,1)")
        before = public_snapshot(conn)
        existing = {r["tablename"] for r in conn.execute(
            "SELECT tablename FROM pg_tables WHERE schemaname='external_data'").fetchall()}
        if existing & BASE_TABLES and not BASE_TABLES <= existing:
            raise ContractError("Partially installed external schema requires manual review")
        if not BASE_TABLES <= existing:
            if existing:
                raise ContractError("Unknown external schema objects require manual review")
            base = (ROOT / "db/init/04-external-pass-material.sql").read_text(encoding="utf-8")
            # The outer transaction owns commit/rollback, including both installation steps.
            base = base.replace("BEGIN;", "", 1).rsplit("COMMIT;", 1)[0]
            conn.execute(base)
        Repository(conn).check_contract()
        conn.execute("""CREATE TABLE IF NOT EXISTS external_data.schema_migration (
            version TEXT PRIMARY KEY, checksum TEXT NOT NULL, applied_at TIMESTAMPTZ NOT NULL DEFAULT now())""")
        old = conn.execute("SELECT checksum FROM external_data.schema_migration WHERE version='07'").fetchone()
        if not old and existing.intersection(REQUEST_COLUMNS):
            raise ContractError("Unversioned request tables require manual review")
        if not old:
            conflicts=conn.execute("""SELECT
                EXISTS(SELECT 1 FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace
                       WHERE n.nspname='external_data' AND p.proname='check_collection_provenance')
                OR EXISTS(SELECT 1 FROM pg_class t JOIN pg_namespace n ON n.oid=t.relnamespace
                          WHERE n.nspname='external_data' AND t.relname='collection_candidate_company_idx') AS found
                """).fetchone()["found"]
            if conflicts:
                raise ContractError("Unversioned migration object name collision")
        if old and old["checksum"] != checksum:
            raise ContractError("Applied migration checksum differs")
        if not old:
            conn.execute(migration)
        check_requests(conn)
        conn.execute("INSERT INTO external_data.schema_migration(version,checksum) VALUES('07',%s) ON CONFLICT DO NOTHING",
                     (checksum,))
        if public_snapshot(conn) != before:
            raise ContractError("Public snapshot changed; migration rolled back")
    return {"migration": "07", "already_applied": bool(old), "public_unchanged": True}


def migrate_public(conn):
    """Install only new, caller-owned public tables with SELECT/REFERENCES on pipeline tables."""
    from psycopg.pq import TransactionStatus
    if not conn.autocommit or conn.info.transaction_status != TransactionStatus.IDLE:
        raise ContractError("An idle autocommit connection is required")
    base=public_ddl((ROOT/'db/init/04-external-pass-material.sql').read_text(encoding='utf-8'))
    extension=public_ddl((ROOT/'db/migrations/07-external-pass-collection-requests.sql').read_text(encoding='utf-8'))
    checksum=hashlib.sha256((base+'\n'+extension).encode()).hexdigest()
    names=set(TABLES.values())
    with conn.transaction():
        conn.execute('SELECT pg_advisory_xact_lock(703114,1)')
        if not conn.execute("SELECT has_schema_privilege(current_user,'public','CREATE') AS yes").fetchone()['yes']:
            raise ContractError("CREATE on public is required")
        for table in ('company','posting','extraction_run','recruit_unit'):
            if not conn.execute("SELECT has_table_privilege(current_user,%s,'SELECT') AND has_table_privilege(current_user,%s,'REFERENCES') AS yes",
                                ('public.'+table,'public.'+table)).fetchone()['yes']:
                raise ContractError("Pipeline SELECT/REFERENCES permission is required")
        before={k:v for k,v in public_snapshot(conn).items() if k not in names}
        existing={r['tablename'] for r in conn.execute("SELECT tablename FROM pg_tables WHERE schemaname='public' AND tablename=ANY(%s)",(list(names),)).fetchall()}
        if existing and existing!=names:
            raise ContractError("Partially installed owned public store requires review")
        old=None
        if existing:
            not_owned=conn.execute("""SELECT count(*) AS n FROM pg_class t JOIN pg_namespace n ON n.oid=t.relnamespace
                WHERE n.nspname='public' AND t.relname=ANY(%s) AND t.relowner<>current_user::regrole""",(list(names),)).fetchone()['n']
            if not_owned:raise ContractError("Feature tables must be owned by the migration role")
            old=conn.execute("SELECT checksum FROM public.external_pass_schema_migration WHERE version='public-07'").fetchone()
            if not old or old['checksum']!=checksum:
                raise ContractError("Owned store version/checksum conflicts")
        else:
            # Do not hide populated legacy storage behind an empty new layout.
            for table in BASE_TABLES:
                row=conn.execute('SELECT to_regclass(%s) AS name',('external_data.'+table,)).fetchone()
                if row['name'] and conn.execute(sql.SQL('SELECT EXISTS(SELECT 1 FROM external_data.{}) AS yes').format(sql.Identifier(table))).fetchone()['yes']:
                    raise ContractError("Populated legacy external storage requires an explicit data migration")
            collisions=conn.execute("""SELECT
                EXISTS(SELECT 1 FROM pg_class t JOIN pg_namespace n ON n.oid=t.relnamespace
                       WHERE n.nspname='public' AND t.relname=ANY(%s))
                OR EXISTS(SELECT 1 FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace
                          WHERE n.nspname='public' AND p.proname=ANY(%s)) AS yes""",
                (list(OBJECTS.values()),list(OBJECTS.values()))).fetchone()['yes']
            if collisions:raise ContractError("Owned feature object name collision")
            conn.execute(base);conn.execute(extension)
            conn.execute("""CREATE TABLE public.external_pass_schema_migration(
                version TEXT PRIMARY KEY,checksum TEXT NOT NULL,applied_at TIMESTAMPTZ NOT NULL DEFAULT now())""")
            conn.execute("INSERT INTO public.external_pass_schema_migration(version,checksum) VALUES('public-07',%s)",(checksum,))
        mapped=OwnedConnection(conn)
        Repository(mapped).check_contract();check_requests(mapped)
        after={k:v for k,v in public_snapshot(conn).items() if k not in names}
        if before!=after:raise ContractError("Existing pipeline rows changed; rollback")
    return {'migration':'public-07','already_applied':bool(old),'existing_public_unchanged':True,'owned_tables':sorted(names)}


def main():
    import psycopg
    from psycopg.rows import dict_row
    try:
        if not os.environ.get("DATABASE_URL"):
            raise ContractError("DATABASE_URL is required")
        with psycopg.connect(os.environ["DATABASE_URL"], autocommit=True, row_factory=dict_row,
                             connect_timeout=10) as conn:
            print(json.dumps(migrate_public(conn)))
        return 0
    except Exception as exc:
        print(json.dumps({"error_code": getattr(exc, "code", "MIGRATION_FAILED"), "rolled_back": True}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
