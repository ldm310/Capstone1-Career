from psycopg import sql
from .errors import ContractError, IdentityConflict, StaleTask
from .classification import relation
from .storage import detect,owned,public_sql,TABLES

REQUIRED = {
    "company": {"id", "name"},
    "posting": {"id", "company_id", "title", "site_job_category"},
    "company_collection": {"company_id", "status", "minimum_sample_size", "attempt_count",
                           "requested_at", "started_at", "completed_at", "updated_at", "error_code", "error_message"},
    "pass_material": {"id", "company_id", "source_platform", "external_record_id", "job_family",
                      "role_name", "title", "content", "source_url", "published_at", "collected_at", "updated_at"},
    "posting_pass_material": {"posting_id", "material_id", "relation_type", "linked_at"},
}


class Repository:
    def __init__(self, connection, posting_schema="public"):
        if posting_schema not in ("job", "public"):
            raise ContractError("Posting schema must be job or public")
        self.conn, self.schema = detect(connection), posting_schema

    def _query(self, statement):
        return sql.SQL(public_sql(statement) if owned(self.conn) else statement).format(schema=sql.Identifier(self.schema))

    def check_contract(self):
        for table, columns in REQUIRED.items():
            pipeline=table in ("company","posting")
            schema = self.schema if pipeline else ("public" if owned(self.conn) else "external_data")
            physical=TABLES[table] if not pipeline and owned(self.conn) else table
            rows = self.conn.execute(
                "SELECT column_name FROM information_schema.columns WHERE table_schema=%s AND table_name=%s",
                (schema, physical)).fetchall()
            if not columns <= {r["column_name"] for r in rows}:
                raise ContractError("Required BE tables/columns are missing")
        # Require the source IDs to be from the exact company/posting tables used by the BE FKs.
        for source, target in (("pass_material", "company"), ("company_collection", "company"),
                               ("posting_pass_material", "posting")):
            rows = self.conn.execute("""
                SELECT n.nspname AS schema_name, t.relname AS table_name
                FROM pg_constraint c
                JOIN pg_class s ON s.oid=c.conrelid JOIN pg_namespace sn ON sn.oid=s.relnamespace
                JOIN pg_class t ON t.oid=c.confrelid JOIN pg_namespace n ON n.oid=t.relnamespace
                WHERE c.contype='f' AND sn.nspname=%s AND s.relname=%s AND t.relname=%s
                """, ("public" if owned(self.conn) else "external_data",TABLES[source] if owned(self.conn) else source,target)).fetchall()
            if not rows or any(r["schema_name"] != self.schema for r in rows):
                raise ContractError("BE foreign keys do not match the selected posting schema")

    def companies(self, company_id=None):
        return self.conn.execute(self._query("""
            SELECT c.id, c.name, task.status, task.minimum_sample_size
            FROM {schema}.company c
            LEFT JOIN external_data.company_collection task ON task.company_id=c.id
            WHERE EXISTS(SELECT 1 FROM {schema}.posting p WHERE p.company_id=c.id)
              AND (%s::bigint IS NULL OR c.id=%s)
            ORDER BY c.id
            """), (company_id, company_id)).fetchall()

    def enqueue(self, company_id=None):
        return self.conn.execute(self._query("""
            INSERT INTO external_data.company_collection(company_id,status,completed_at)
            SELECT p.company_id,
                CASE WHEN count(m.id)>=5 THEN 'READY' WHEN count(m.id)>0 THEN 'INSUFFICIENT' ELSE 'PENDING' END,
                CASE WHEN count(m.id)>0 THEN now() ELSE NULL END
            FROM (SELECT DISTINCT company_id FROM {schema}.posting) p
            LEFT JOIN external_data.pass_material m ON m.company_id=p.company_id AND m.job_family='IT_SW'
            WHERE (%s::bigint IS NULL OR p.company_id=%s)
            GROUP BY p.company_id
            ON CONFLICT(company_id) DO NOTHING
            """), (company_id, company_id)).rowcount

    def claim(self, company_id=None):
        # Autocommit connection: this one statement commits RUNNING before any network access.
        return self.conn.execute(self._query("""
            WITH next_job AS (
                SELECT company_id FROM external_data.company_collection
                WHERE status='PENDING' AND (%s::bigint IS NULL OR company_id=%s)
                ORDER BY requested_at, company_id FOR UPDATE SKIP LOCKED LIMIT 1
            ), claimed AS (
                UPDATE external_data.company_collection c
                SET status='RUNNING', started_at=now(), completed_at=NULL, attempt_count=attempt_count+1,
                    updated_at=now(), error_code=NULL, error_message=NULL
                FROM next_job WHERE c.company_id=next_job.company_id RETURNING c.*
            )
            SELECT claimed.*, company.name FROM claimed
            JOIN {schema}.company company ON company.id=claimed.company_id
            """), (company_id, company_id)).fetchone()

    def platform_restricted(self):
        return self.conn.execute("""SELECT EXISTS(SELECT 1 FROM external_data.company_collection
            WHERE status='FAILED' AND error_code='ACCESS_RESTRICTED') AS blocked""").fetchone()["blocked"]

    def postings(self, company_id):
        return self.conn.execute(self._query("""
            SELECT id, title, site_job_category FROM {schema}.posting WHERE company_id=%s ORDER BY id
            """), (company_id,)).fetchall()

    def _link(self, company_id):
        postings = self.postings(company_id)
        materials = self.conn.execute("""
            SELECT id, role_name FROM external_data.pass_material
            WHERE company_id=%s AND job_family='IT_SW' ORDER BY id
            """, (company_id,)).fetchall()
        for posting in postings:
            target = (posting["site_job_category"] or "") + " " + posting["title"]
            for material in materials:
                self.conn.execute("""
                    INSERT INTO external_data.posting_pass_material(posting_id,material_id,relation_type)
                    VALUES(%s,%s,%s)
                    ON CONFLICT(posting_id,material_id) DO UPDATE
                    SET relation_type=excluded.relation_type, linked_at=now()
                    """, (posting["id"], material["id"], relation(target, material["role_name"])))

    def relink_existing(self, company_id=None):
        # New postings reuse collected data; no request to Linkareer and no requeue.
        for company in self.companies(company_id):
            if company["status"] not in ("READY", "INSUFFICIENT", "FAILED"):
                continue
            with self.conn.transaction():
                task = self.conn.execute("""
                    SELECT status FROM external_data.company_collection WHERE company_id=%s FOR UPDATE
                    """, (company["id"],)).fetchone()
                if task and task["status"] in ("READY", "INSUFFICIENT", "FAILED"):
                    self._link(company["id"])

    def finish(self, task, materials):
        with self.conn.transaction():
            current = self.conn.execute("""
                SELECT * FROM external_data.company_collection WHERE company_id=%s FOR UPDATE
                """, (task["company_id"],)).fetchone()
            if not current or current["status"] != "RUNNING" or current["attempt_count"] != task["attempt_count"]:
                raise StaleTask()
            for material in materials:
                saved = self.conn.execute("""
                    INSERT INTO external_data.pass_material AS existing
                        (company_id,source_platform,external_record_id,job_family,role_name,title,content,source_url)
                    VALUES(%s,'linkareer',%s,'IT_SW',%s,%s,%s,%s)
                    ON CONFLICT(source_platform,external_record_id) DO UPDATE
                    SET role_name=excluded.role_name,title=excluded.title,content=excluded.content,
                        source_url=excluded.source_url,updated_at=now()
                    WHERE existing.company_id=excluded.company_id RETURNING id
                    """, (task["company_id"], material.external_id, material.role,
                          material.role + " IT·SW 공개 합격자료", material.content,
                          "https://linkareer.com/cover-letter/" + material.external_id)).fetchone()
                if saved is None:
                    raise IdentityConflict()
            self._link(task["company_id"])
            count = self.conn.execute("""
                SELECT count(*) AS n FROM external_data.pass_material WHERE company_id=%s AND job_family='IT_SW'
                """, (task["company_id"],)).fetchone()["n"]
            status = "READY" if count >= current["minimum_sample_size"] else "INSUFFICIENT"
            self.conn.execute("""
                UPDATE external_data.company_collection SET status=%s,completed_at=now(),updated_at=now(),
                    error_code=NULL,error_message=NULL WHERE company_id=%s
                """, (status, task["company_id"]))
            return status, count

    def fail(self, task, error_code):
        # Never persist exception messages, HTML, DB DSNs or source text.
        self.conn.execute("""
            UPDATE external_data.company_collection SET status='FAILED',completed_at=now(),updated_at=now(),
                error_code=%s,error_message='External collection failed; inspect the error code.'
            WHERE company_id=%s AND status='RUNNING' AND attempt_count=%s
            """, (error_code, task["company_id"], task["attempt_count"]))
