"""One logical external-material contract, with an owned public-table deployment layout."""
import re

TABLES={"pass_material":"external_pass_material","company_collection":"external_pass_company_collection",
        "posting_pass_material":"external_pass_posting_material","collection_request":"external_pass_collection_request",
        "collection_candidate":"external_pass_collection_candidate","schema_migration":"external_pass_schema_migration"}
OBJECTS={**TABLES,
    "check_material_company":"external_pass_check_material_company",
    "keep_material_company":"external_pass_keep_material_company",
    "check_collection_provenance":"external_pass_check_collection_provenance",
    "pass_material_company_idx":"external_pass_material_company_idx",
    "company_collection_queue_idx":"external_pass_company_collection_queue_idx",
    "posting_pass_material_material_idx":"external_pass_posting_material_idx",
    "collection_candidate_company_idx":"external_pass_candidate_company_idx",
    "posting_pass_material_company_guard":"external_pass_posting_material_company_guard",
    "pass_material_company_immutable":"external_pass_material_company_immutable",
    "collection_request_provenance_guard":"external_pass_request_provenance_guard",
    "collection_candidate_provenance_guard":"external_pass_candidate_provenance_guard"}


def public_sql(statement):
    for logical,physical in sorted(OBJECTS.items(),key=lambda item:-len(item[0])):
        statement=re.sub(r'\bexternal_data\.'+re.escape(logical)+r'\b','public.'+physical,statement)
    return statement


def public_ddl(statement):
    statement=re.sub(r'CREATE SCHEMA IF NOT EXISTS external_data\s*;','',statement)
    statement=re.sub(r"COMMENT ON SCHEMA external_data IS '[^']*';",'',statement)
    statement=statement.replace('BEGIN;','',1).rsplit('COMMIT;',1)[0]
    # SELECT/REFERENCES on pipeline tables do not permit explicit row-locking clauses.
    statement=re.sub(r' FOR SHARE(?: OF [a-z,]+)?','',statement)
    for logical,physical in sorted(OBJECTS.items(),key=lambda item:-len(item[0])):
        statement=re.sub(r'\b'+re.escape(logical)+r'\b',physical,statement)
    return statement.replace('external_data.','public.')


class OwnedConnection:
    """Rewrite only fixed, allowlisted feature identifiers; never pipeline identifiers or parameters."""
    def __init__(self,connection):self.raw=connection
    def execute(self,statement,params=None,**kwargs):
        return self.raw.execute(public_sql(statement) if isinstance(statement,str) else statement,params,**kwargs)
    def __getattr__(self,name):return getattr(self.raw,name)


def owned(connection):
    return isinstance(connection,OwnedConnection)


def detect(connection):
    if owned(connection):return connection
    row=connection.execute("SELECT to_regclass('public.external_pass_material') IS NOT NULL AS yes").fetchone()
    exists=row['yes'] if isinstance(row,dict) else row[0]
    return OwnedConnection(connection) if exists else connection
