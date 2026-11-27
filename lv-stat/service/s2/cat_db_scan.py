"""cat_db의 레포 스캔 부품(버림용 스파이크, 2026-11-26). 규칙만 쓴다. 받은 레포는 git으로 읽기만 한다.

파서(결과 parser 칸에 남긴다):
- Python: 표준 ast (SyntaxError면 그 파일은 '못 뽑힌 것'으로 S5 대상)
- 그 밖(Java·Kotlin·JS·TS·Vue·SQL·XML·YAML·properties·PHP·Go·C#·Dart·Ruby): 주석·문자열을 가린 줄에 정규식
  (스파이크 한정. tree-sitter가 이 환경에 없다. 최종 개발에서는 설계 9.8대로 바꾼다)
"""
import ast
import datetime
import hashlib
import json
import re
import warnings
from collections import defaultdict

import s2lib as L

PARSER_PY = 'python-ast'
PARSER_RX = 'regex-masked@spike'

# ---------------------------------------------------------------- DB 이름
REL = {'MySQL', 'MariaDB', 'PostgreSQL', 'SQLite', 'Oracle', 'SQL Server', 'H2', 'HSQLDB', 'Derby', 'DuckDB', 'ClickHouse', 'CockroachDB', 'SQL(미상)'}
DOCKV = {'MongoDB', 'DynamoDB', 'Firestore', 'Cassandra', 'Neo4j', 'Firebase RTDB', 'CouchDB'}
MAIN_KINDS = REL | DOCKV                      # 주 DB가 될 수 있는 것
NAMED_EXTRA = ('MongoDB', 'Elasticsearch', 'Redis')
EMBEDDED = {'H2', 'HSQLDB', 'Derby'}         # 개발·시험용 내장 DB: '더 쓴 DB'에서 뺀다(제안)
VECTOR = {'Chroma', 'Pinecone', 'Qdrant', 'Weaviate', 'Milvus', 'pgvector'}
DE_ONLY = {'Snowflake', 'BigQuery', 'Hive', 'Trino', 'Spark SQL', 'Redshift', 'Databricks'}   # 데이터 엔지니어에서만 센다(제안 B-33)

SCHEME = [  # (정규식, DB) 연결 문자열·드라이버 이름
    (r'jdbc:mysql:|\bmysql(\+\w+)?://|com\.mysql(\.cj)?\.jdbc|MySQL\d*Dialect|\bmysql2?\b(?=[\'"])', 'MySQL'),
    (r'jdbc:mariadb:|\bmariadb(\+\w+)?://|org\.mariadb\.jdbc|MariaDB\d*Dialect', 'MariaDB'),
    (r'jdbc:postgresql:|\bpostgres(ql)?(\+\w+)?://|org\.postgresql\.Driver|PostgreSQL\d*Dialect', 'PostgreSQL'),
    (r'jdbc:sqlite:|\bsqlite(\+\w+)?:///|org\.sqlite\.JDBC', 'SQLite'),
    (r'jdbc:h2:|org\.h2\.Driver|H2Dialect', 'H2'),
    (r'jdbc:hsqldb:', 'HSQLDB'),
    (r'jdbc:derby:', 'Derby'),
    (r'jdbc:oracle:|\boracle(\+\w+)?://|oracle\.jdbc|OracleDialect', 'Oracle'),
    (r'jdbc:sqlserver:|\bmssql(\+\w+)?://|SQLServer\w*Dialect', 'SQL Server'),
    (r'\bmongodb(\+srv)?://', 'MongoDB'),
    (r'\brediss?://', 'Redis'),
]
SCHEME = [(re.compile(a, re.I if 'Dialect' not in a else 0), b) for a, b in SCHEME]
DJANGO_ENGINE = {'mysql': 'MySQL', 'postgresql': 'PostgreSQL', 'postgresql_psycopg2': 'PostgreSQL', 'postgis': 'PostgreSQL', 'sqlite3': 'SQLite',
                 'oracle': 'Oracle', 'djongo': 'MongoDB', 'mssql': 'SQL Server', 'sql_server.pyodbc': 'SQL Server'}
ORMTYPE = {'mysql': 'MySQL', 'mysql2': 'MySQL', 'mariadb': 'MariaDB', 'postgres': 'PostgreSQL', 'postgresql': 'PostgreSQL', 'pg': 'PostgreSQL',
           'sqlite': 'SQLite', 'sqlite3': 'SQLite', 'better-sqlite3': 'SQLite', 'mongodb': 'MongoDB', 'mssql': 'SQL Server', 'sqlserver': 'SQL Server',
           'oracle': 'Oracle', 'oracledb': 'Oracle', 'cockroachdb': 'CockroachDB'}
PY_CONNECT = {'sqlite3': 'SQLite', 'pymysql': 'MySQL', 'MySQLdb': 'MySQL', 'mysql.connector': 'MySQL', 'psycopg2': 'PostgreSQL', 'psycopg': 'PostgreSQL',
              'asyncpg': 'PostgreSQL', 'aiomysql': 'MySQL', 'aiosqlite': 'SQLite', 'cx_Oracle': 'Oracle', 'oracledb': 'Oracle', 'pyodbc': 'SQL Server',
              'duckdb': 'DuckDB', 'clickhouse_driver': 'ClickHouse', 'snowflake.connector': 'Snowflake'}
IMAGE = [(r'^(mysql|bitnami/mysql|mysql/mysql-server)\b', 'MySQL'), (r'^(mariadb|bitnami/mariadb)\b', 'MariaDB'),
         (r'^(postgres|postgis/postgis|bitnami/postgresql|timescale/timescaledb|ankane/pgvector|pgvector/pgvector)\b', 'PostgreSQL'),
         (r'^(mongo|bitnami/mongodb|mongodb/mongodb)', 'MongoDB'), (r'^(redis|bitnami/redis|redis/redis-stack)', 'Redis'),
         (r'^(docker\.elastic\.co/elasticsearch|elasticsearch|bitnami/elasticsearch)', 'Elasticsearch'), (r'^opensearchproject/opensearch', 'OpenSearch'),
         (r'^(cassandra|bitnami/cassandra)', 'Cassandra'), (r'^neo4j', 'Neo4j'), (r'^(clickhouse|yandex/clickhouse)', 'ClickHouse'),
         (r'^amazon/dynamodb-local', 'DynamoDB'), (r'^chromadb/chroma', 'Chroma'), (r'^qdrant/qdrant', 'Qdrant'), (r'^milvusdb/milvus', 'Milvus'),
         (r'^(mcr\.microsoft\.com/mssql|mcr\.microsoft\.com/azure-sql-edge)', 'SQL Server'), (r'^(gvenzl/oracle|container-registry\.oracle\.com/database)', 'Oracle')]
IMAGE = [(re.compile(a, re.I), b) for a, b in IMAGE]
# 의존성 이름 → (DB 또는 None, 스택) : 흔적으로만 쓴다(문서 공통 규칙 8: 의존성만이면 X)
DEPS = {
    'mysql': ('MySQL', None), 'mysql2': ('MySQL', None), 'pymysql': ('MySQL', None), 'mysqlclient': ('MySQL', None), 'mysql-connector-python': ('MySQL', None),
    'mysql-connector-java': ('MySQL', None), 'mysql-connector-j': ('MySQL', None), 'aiomysql': ('MySQL', None), 'mariadb': ('MariaDB', None),
    'mariadb-java-client': ('MariaDB', None), 'pg': ('PostgreSQL', None), 'postgres': ('PostgreSQL', None), 'psycopg2': ('PostgreSQL', None),
    'psycopg2-binary': ('PostgreSQL', None), 'psycopg': ('PostgreSQL', None), 'asyncpg': ('PostgreSQL', None), 'postgresql': ('PostgreSQL', None),
    'sqlite3': ('SQLite', None), 'better-sqlite3': ('SQLite', None), 'sqlite-jdbc': ('SQLite', None), 'aiosqlite': ('SQLite', None),
    'h2': ('H2', None), 'mongoose': ('MongoDB', 'mongoose'), 'mongodb': ('MongoDB', None), 'pymongo': ('MongoDB', None), 'motor': ('MongoDB', None),
    'mongoengine': ('MongoDB', 'mongoengine'), 'spring-boot-starter-data-mongodb': ('MongoDB', 'spring-data-mongo'), 'djongo': ('MongoDB', None),
    'redis': ('Redis', None), 'ioredis': ('Redis', None), 'django-redis': ('Redis', None), 'spring-boot-starter-data-redis': ('Redis', None),
    'aioredis': ('Redis', None), 'redis-om': ('Redis', None), 'jedis': ('Redis', None), 'lettuce-core': ('Redis', None), 'redisson': ('Redis', None),
    'bull': ('Redis', None), 'bullmq': ('Redis', None), 'elasticsearch': ('Elasticsearch', None), '@elastic/elasticsearch': ('Elasticsearch', None),
    'elasticsearch-dsl': ('Elasticsearch', None), 'spring-boot-starter-data-elasticsearch': ('Elasticsearch', None), 'opensearch-py': ('OpenSearch', None),
    '@aws-sdk/client-dynamodb': ('DynamoDB', 'dynamodb'), '@aws-sdk/lib-dynamodb': ('DynamoDB', 'dynamodb'), 'pynamodb': ('DynamoDB', 'dynamodb'),
    'firebase': ('Firestore', 'firebase'), 'firebase-admin': ('Firestore', 'firebase'), '@supabase/supabase-js': ('PostgreSQL', 'supabase'), 'supabase': ('PostgreSQL', 'supabase'),
    'chromadb': ('Chroma', None), 'langchain-chroma': ('Chroma', None), 'pinecone-client': ('Pinecone', None), 'pinecone': ('Pinecone', None),
    '@pinecone-database/pinecone': ('Pinecone', None), 'qdrant-client': ('Qdrant', None), 'weaviate-client': ('Weaviate', None), 'pymilvus': ('Milvus', None),
    'pgvector': ('pgvector', None), 'cassandra-driver': ('Cassandra', None), 'neo4j': ('Neo4j', None), 'duckdb': ('DuckDB', None),
    'snowflake-connector-python': ('Snowflake', None), 'google-cloud-bigquery': ('BigQuery', None),
    'typeorm': (None, 'typeorm'), '@nestjs/typeorm': (None, 'typeorm'), 'sequelize': (None, 'sequelize'), 'sequelize-typescript': (None, 'sequelize'),
    'prisma': (None, 'prisma'), '@prisma/client': (None, 'prisma'), 'knex': (None, 'knex'), 'drizzle-orm': (None, 'drizzle'), '@mikro-orm/core': (None, 'mikro-orm'),
    'objection': (None, 'objection'), 'sqlalchemy': (None, 'sqlalchemy'), 'flask-sqlalchemy': (None, 'sqlalchemy'), 'sqlmodel': (None, 'sqlmodel'),
    'peewee': (None, 'peewee'), 'tortoise-orm': (None, 'tortoise'), 'spring-boot-starter-data-jpa': (None, 'jpa'), 'mybatis-spring-boot-starter': (None, 'mybatis'),
    'mybatis': (None, 'mybatis'), 'jooq': (None, 'jooq'), 'spring-boot-starter-jooq': (None, 'jooq'), 'querydsl-jpa': (None, 'jpa'), 'exposed-core': (None, 'exposed'),
    'spring-boot-starter-jdbc': (None, 'jdbc'), 'spring-boot-starter-data-r2dbc': (None, 'r2dbc'), 'alembic': (None, 'sqlalchemy'),
}
UNRULED_STACKS = {'mikro-orm', 'objection', 'peewee', 'tortoise', 'jooq', 'r2dbc', 'ef', 'gorm', 'eloquent', 'activerecord', 'dapper'}

SQLSHAPE = re.compile(r'^\s*\(?\s*(SELECT\s[\s\S]*?\bFROM\s+[\w."`\[\]$({]|INSERT\s+(OR\s+\w+\s+|IGNORE\s+)?INTO\b|UPDATE\s+[\w."`\[\]${}]+\s+SET\b|DELETE\s+FROM\b|'
                      r'CREATE\s+(OR\s+REPLACE\s+)?(TEMP\w*\s+|UNIQUE\s+|VIRTUAL\s+)?(TABLE|INDEX|VIEW|SCHEMA|DATABASE|SEQUENCE|TRIGGER|MATERIALIZED)\b|ALTER\s+TABLE\b|'
                      r'DROP\s+(TABLE|INDEX|VIEW|SCHEMA|DATABASE)\b|WITH\s+(RECURSIVE\s+)?\w+\s+AS\s*\(|REPLACE\s+INTO\b|MERGE\s+INTO\b|UPSERT\s+INTO\b|'
                      r'BEGIN(\s+TRANSACTION|\s+WORK)?\s*;?\s*$|START\s+TRANSACTION\b|COMMIT\s*;?\s*$|TRUNCATE\s+(TABLE\s+)?\w|EXPLAIN\s+(ANALYZE\s+)?(SELECT|UPDATE|DELETE|INSERT))', re.I)
SQL_DUMP = re.compile(r'--> statement-breakpoint|^-- (MySQL dump|PostgreSQL database dump|phpMyAdmin SQL Dump|Dumped (from|by))|^/\*!40\d{3} SET', re.M)
EXAMPLE_PATH = re.compile(r'(\.example|\.sample|\.template|\.dist|-example|_example)(\.|$)|(^|/)examples?/', re.I)
DEVCFG = re.compile(r'(^|/)(settings/)?(dev|development|local)(_settings)?\.py$|local_settings\.py$|application-(local|dev)[^/]*\.(ya?ml|properties)$', re.I)
TESTCFG = re.compile(r'(^|/)(src/test/|test/|tests/)|application-test|_test\.|\.test\.|-test\.ya?ml$|test_settings|settings_test|conftest', re.I)


def hkey(s):
    return hashlib.sha1(s.encode()).hexdigest()[:10]


def norm_table(name):
    n = (name or '').strip().strip('`"[]\'').split('.')[-1].strip('`"[]\'').lower()
    n = re.sub(r'[^a-z0-9]', '', n)
    if len(n) > 3 and n.endswith('ies'):
        n = n[:-3] + 'y'
    elif len(n) > 3 and n.endswith('s') and not n.endswith('ss'):
        n = n[:-1]
    return n


def date_of(iso):
    return datetime.datetime.fromisoformat(iso.replace('Z', '+00:00'))


# ---------------------------------------------------------------- 주석·문자열 가리기(옛 extract.mask_code를 옮겨 고침)
def mask(text, style):
    """-> (줄별 코드(주석 지움·문자열 내용 비움), [(시작 줄 i, 끝 줄 j, 내용)]) 줄 번호는 0부터.
    style: 'c'(// /* */ ' " `) · 'java' · 'kt' · 'sql' · 'php' · 'go' · 'rb' · 'yaml' · 'xml'"""
    if style == 'xml':
        out = re.sub(r'<!--[\s\S]*?-->', lambda m: '\n' * m.group(0).count('\n'), text)
        return out.split('\n'), []
    slash = style in ('c', 'java', 'kt', 'php', 'go', 'dart', 'cs')
    hashc = style in ('php', 'rb', 'yaml', 'py')
    dash = style == 'sql'
    tick = style in ('c', 'go', 'kt')
    triple = style in ('java', 'kt', 'dart', 'py')
    dq = style != 'sql'
    out, strs, buf, i, n, line = [], [], [], 0, len(text), 0
    while i < n:
        c, two = text[i], text[i:i + 2]
        if c == '\n':
            out.append(''.join(buf)); buf = []; line += 1; i += 1; continue
        if (slash and two == '//' and not (i and text[i - 1] == ':')) or (hashc and c == '#') or (dash and two == '--'):
            j = text.find('\n', i); i = n if j < 0 else j; continue
        if (slash or dash) and two == '/*':
            j = text.find('*/', i + 2); j = n if j < 0 else j + 2
            for _ in range(text.count('\n', i, j)):
                out.append(''.join(buf)); buf = []; line += 1
            i = j; continue
        if style == 'yaml':
            buf.append(c); i += 1; continue
        if c == "'" or (c == '"' and dq) or (tick and c == '`'):
            q = c * 3 if triple and text[i:i + 3] == c * 3 else c
            j, content, start = i + len(q), [], line
            while j < n and not text.startswith(q, j):
                if text[j] == '\\' and style != 'sql':
                    content.append(text[j:j + 2]); j += 2; continue
                if text[j] == '\n' and len(q) == 1 and q != '`' and style != 'sql':
                    break
                content.append(text[j]); j += 1
            s = ''.join(content)
            buf.append(q[0] * 2)
            nl = s.count('\n')
            for _ in range(nl):
                out.append(''.join(buf)); buf = []; line += 1
            strs.append((start, line, s))
            i = j + len(q) if text.startswith(q, j) else j
            continue
        buf.append(c); i += 1
    out.append(''.join(buf))
    return out, strs


def block_end(code, start, opener='{'):
    """start 줄부터 처음 여는 괄호의 짝이 닫히는 줄(0부터). 못 찾으면 마지막 줄."""
    close = {'{': '}', '(': ')'}[opener]
    depth, opened = 0, False
    for i in range(start, len(code)):
        for ch in code[i]:
            if ch == opener:
                depth += 1; opened = True
            elif ch == close and opened:
                depth -= 1
                if depth == 0:
                    return i
    return len(code) - 1


def group_end(code, start):
    """start 줄부터 ( 또는 { 묶음이 모두 닫히는 줄."""
    depth, opened = 0, False
    for i in range(start, len(code)):
        for ch in code[i]:
            if ch in '({[':
                depth += 1; opened = True
            elif ch in ')}]' and opened:
                depth -= 1
                if depth <= 0:
                    return i
    return len(code) - 1


# ---------------------------------------------------------------- SQL 문장 규칙('sql-rule')
CT = re.compile(r'\bCREATE\s+(?:OR\s+REPLACE\s+)?(?:GLOBAL\s+|LOCAL\s+)?(?:TEMP(?:ORARY)?\s+|VIRTUAL\s+|EXTERNAL\s+)?TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?([\w.`"\[\]]+)\s*(\(|AS\b|LIKE\b)?', re.I)
CI = re.compile(r'\bCREATE\s+(UNIQUE\s+)?(?:CLUSTERED\s+|NONCLUSTERED\s+|FULLTEXT\s+|SPATIAL\s+)?INDEX\s+(?:CONCURRENTLY\s+)?(?:IF\s+NOT\s+EXISTS\s+)?(?:[\w.`"\[\]]+\s+)?ON\s+(?:ONLY\s+)?([\w.`"\[\]]+)', re.I)
ALTER_IDX = re.compile(r'\bALTER\s+TABLE\s+(?:IF\s+EXISTS\s+)?(?:ONLY\s+)?([\w.`"\[\]]+)[\s\S]*?\bADD\s+(UNIQUE\s+)?(?:INDEX|KEY)\b', re.I)
INLINE_IDX = re.compile(r'(?:^|,)\s*(?:(UNIQUE)\s+)?(?:INDEX|KEY)\s+[`"\w]*\s*\(', re.I)
FK = re.compile(r'\bREFERENCES\b|\bFOREIGN\s+KEY\b', re.I)
TXSQL = re.compile(r'^\s*(BEGIN(\s+TRAN(SACTION)?|\s+WORK)?|START\s+TRANSACTION)\s*;?\s*$', re.I)
DML = re.compile(r'^\s*\(?\s*(SELECT|INSERT|UPDATE|DELETE|WITH|REPLACE|MERGE|UPSERT)\b', re.I)
VIEW = re.compile(r'\bCREATE\s+(OR\s+REPLACE\s+)?(MATERIALIZED\s+)?VIEW\b', re.I)
JPQL_FETCH = re.compile(r'\bjoin\s+fetch\b|\bleft\s+(outer\s+)?join\s+fetch\b', re.I)
DIALECT = [(re.compile(r'AUTO_INCREMENT|ENGINE\s*=\s*InnoDB|\bUNSIGNED\b|`\w+`', re.I), 'MySQL'),
           (re.compile(r'CLUSTERING\s+ORDER\s+BY|\bWITH\s+compaction\b|\bCREATE\s+KEYSPACE\b|PRIMARY\s+KEY\s*\(\s*\(', re.I), 'Cassandra'),
           (re.compile(r'\bSTORED\s+AS\b|\bROW\s+FORMAT\b|\bTBLPROPERTIES\b|\bLOCATION\s+\'(s3a?|hdfs|gs)://', re.I), 'Hive'),
           (re.compile(r'\bWITH\s*\(\s*(format|partitioned_by|external_location)\s*=', re.I), 'Trino'),
           (re.compile(r'\b(BIG)?SERIAL\b|\bTIMESTAMPTZ\b|\bJSONB\b|::\w+|\bBYTEA\b', re.I), 'PostgreSQL'),
           (re.compile(r'\bAUTOINCREMENT\b|\bWITHOUT\s+ROWID\b', re.I), 'SQLite'),
           (re.compile(r'\bVARCHAR2\b|\bNUMBER\s*\(|\bCLOB\b', re.I), 'Oracle'),
           (re.compile(r'IDENTITY\s*\(\s*\d+\s*,\s*\d+\s*\)|\bNVARCHAR\s*\(|\[dbo\]', re.I), 'SQL Server')]


def sql_statements(code_lines, base=0):
    """가린 SQL 줄 → [(시작 줄, 끝 줄, 문장)] (줄 번호 0부터, base를 더함)"""
    res, buf, start = [], [], None
    for i, c in enumerate(code_lines):
        if start is None and c.strip():
            start = i
        if start is not None:
            buf.append(c)
        if ';' in c and start is not None:
            parts = c.split(';')
            res.append((base + start, base + i, ' \n'.join(buf[:-1] + [parts[0]])))
            rest = ';'.join(parts[1:])
            buf, start = ([rest], i) if rest.strip() else ([], None)
    if buf and start is not None and ''.join(buf).strip():
        res.append((base + start, base + len(code_lines) - 1, '\n'.join(buf)))
    return res


def sql_facts(stmt_text):
    """문장 하나 → 사실 목록 [(종류, 문장 안 줄 오프셋, 값)]"""
    out = []
    t = stmt_text
    if VIEW.search(t):
        return [('view', 0, None)]
    m = CT.search(t)
    if m and (m.group(2) or '').upper() != 'AS' and re.search(r'\bAS\s*\(?\s*(SELECT|WITH)\b', t[m.end():], re.I) and not re.search(r'^\s*\(', t[m.end():]):
        return [('table', t[:m.start()].count('\n'), dict(name=m.group(1), rel=False, ctas=True, body_lines=1))]
    if m and (m.group(2) or '').upper() != 'LIKE':
        off = t[:m.start()].count('\n')
        body = t[m.end():]
        out.append(('table', off, dict(name=m.group(1), rel=bool(FK.search(body)), ctas=(m.group(2) or '').upper() == 'AS', body_lines=t.count('\n') - off + 1)))
        for mi in INLINE_IDX.finditer(body):
            pre = body[:mi.start()]
            if re.search(r'PRIMARY\s*$', pre[-20:], re.I):
                continue
            o2 = off + body[:mi.start()].count('\n') + (t[m.start():m.end()].count('\n'))
            if mi.group(1):
                out.append(('unique', o2, dict(table=m.group(1))))
            else:
                out.append(('index', o2, dict(table=m.group(1), unique=False)))
        if re.search(r'\bUNIQUE\b', body, re.I):
            out.append(('unique', off, dict(table=m.group(1))))
        for d_rx, d in DIALECT:
            if d_rx.search(t):
                out.append(('dialect', off, d))
                break
        return out
    m = CI.search(t)
    if m:
        out.append(('index', t[:m.start()].count('\n'), dict(table=m.group(2), unique=bool(m.group(1)))))
        return out
    m = ALTER_IDX.search(t)
    if m:
        out.append(('index', t[:m.start()].count('\n'), dict(table=m.group(1), unique=bool(m.group(2)))))
    if re.match(r'\s*ALTER\s+TABLE', t, re.I) and FK.search(t):
        out.append(('rel', 0, None))
    if re.match(r'\s*ALTER\s+TABLE', t, re.I) and re.search(r'\bADD\s+(CONSTRAINT\s+\w+\s+)?UNIQUE\b', t, re.I):
        out.append(('unique', 0, None))
    if TXSQL.match(t.strip().split('\n')[0] if t.strip() else ''):
        out.append(('tx', 0, None))
    if DML.match(t):
        out.append(('dml', 0, None))
    if JPQL_FETCH.search(t):
        out.append(('fetchjoin', t[:JPQL_FETCH.search(t).start()].count('\n'), None))
    if re.match(r'\s*EXPLAIN\b', t, re.I):
        out.append(('explain', 0, None))
    return out


# ---------------------------------------------------------------- 레포 스캔
READ_LANGS = {'Java', 'Kotlin', 'Python', 'JavaScript', 'TypeScript', 'Vue', 'Svelte', 'SQL', 'PLpgSQL', 'PLSQL', 'TSQL', 'SQLPL', 'Prisma', 'XML', 'YAML',
              'Java Properties', 'INI', 'TOML', 'PHP', 'Go', 'C#', 'Dart', 'Ruby', 'Jupyter Notebook', 'JSON', 'Groovy', 'Gradle', 'Kotlin Script'}
DEP_FILES = re.compile(r'(^|/)(package\.json|requirements[^/]*\.txt|pyproject\.toml|Pipfile|setup\.py|setup\.cfg|environment\.ya?ml|pom\.xml|build\.gradle(\.kts)?|'
                       r'go\.mod|composer\.json|Gemfile|[^/]+\.csproj|pubspec\.yaml)$')
COMPOSE = re.compile(r'(^|/)(docker-)?compose[^/]*\.ya?ml$', re.I)
# 경로 규칙(지운 파일에도 쓴다): 카테고리 파일 종류
P_SCHEMA = re.compile(r'\.(sql|prisma)$|(^|/)(migrations?|db/migrate|flyway|liquibase|alembic/versions|prisma/migrations|changelogs?)/|(^|/)V\d+(_\d+)*__[^/]+\.sql$', re.I)
P_MODEL = re.compile(r'(^|/)models?\.py$|(^|/)models/[^/]+\.py$|(^|/)(entity|entities)/[^/]+\.(java|kt|ts|js)$|[A-Za-z]Entity\.(java|kt)$|'
                     r'\.(entity|model|schema)\.(ts|js)$|(^|/)(models|schemas)/[^/]+\.(js|ts)$', re.I)
P_REPO = re.compile(r'(Repository|Repo|Dao|DAO|Mapper)\.(java|kt|ts|js|py)$|\.repository\.(ts|js)$|(^|/)(repositor(y|ies)|daos?|mappers?|mapper)/[^/]+\.(java|kt|ts|js|py|xml)$|'
                    r'Mapper\.xml$|(^|/)crud(/[^/]+)?\.py$|(^|/)(db|database)\.(py|js|ts)$|(^|/)(db|database)/[^/]+\.(py|ts|js)$', re.I)
P_CONN = re.compile(r'(^|/)(ormconfig\.(json|js|ts|ya?ml)|knexfile\.(js|ts)|data-?source\.(ts|js)|database\.(js|ts|json|ya?ml)|db\.config\.(js|ts)|prisma\.service\.ts)$', re.I)


class RepoScan:
    """레포 하나의 DB 사실을 모은다. 위치만 남기고 코드 내용은 남기지 않는다."""

    def __init__(self, repo):
        self.r = repo
        self.own = {c['sha'] for c in repo.commits if c['own']}
        self.touched = {f['path'] for c in repo.commits if c['own'] for f in c['files']}
        self.tables, self.indexes, self.access, self.conn, self.tx, self.tuning = [], [], [], [], [], []
        self.uniques, self.rels = [], []
        self.traces = []          # {path, line, var, tech, why}
        self.deps = defaultdict(list)   # tech/stack -> [(path, line)]
        self.stacks = set()
        self.file_cls = defaultdict(set)
        self.parse_errors = []
        self.amb_tx = []          # 애매한 트랜잭션 후보
        self.files_read = 0
        self.parsers = defaultdict(int)
        self.unreadable = []
        self._blame = {}
        self.model_names_js = set()   # mongoose·sequelize 모델 이름(레포 단위)
        self.py_model_bases = set()
        self.notes = []
        self.first_commit = self._first_commits()

    # -- 내 줄
    def mine_fn(self, f):
        """-> (함수(줄 번호 1부터)->bool, 방식)"""
        s = self.r.own_line_set(f['path'])
        if s is not None:
            return (lambda n, s=s: n in s), 'blame-index'
        if f['path'] not in self.touched:
            return (lambda n: False), 'not-touched'
        if (f.get('size') or 0) > 2_000_000:
            return None, 'too-big'
        sset = self.blame(f)
        if sset is None:
            return None, 'blame-failed'
        return (lambda n, s=sset: n in s), 'blame-local'

    def blame(self, f, per_line=False):
        key = (f['path'], per_line)
        if key in self._blame:
            return self._blame[key]
        rc, out = L.git(self.r.dir, 'blame', '--porcelain', f['ref'], '--', f['path'], timeout=300)
        if rc != 0:
            self._blame[key] = None
            return None
        mine, cur, shamap = set(), None, {}
        for line in out.decode('utf-8', errors='replace').splitlines():
            m = re.match(r'^([0-9a-f]{40}) \d+ (\d+)', line)
            if m:
                cur = (m.group(1), int(m.group(2)))
                continue
            if line.startswith('\t') and cur:
                shamap[cur[1]] = cur[0]
                if cur[0] in self.own:
                    mine.add(cur[1])
                cur = None
        self._blame[(f['path'], False)] = mine
        self._blame[(f['path'], True)] = shamap
        return self._blame[key]

    def _first_commits(self):
        """경로마다 처음 더한 커밋(날짜가 가장 이른 것): (sha, own, date)"""
        fc = {}
        for c in self.r.commits:
            try:
                d = date_of(c['date'])
            except Exception:
                continue
            for f in c['files']:
                if f.get('add', 0) <= 0:
                    continue
                p = f['path']
                if p not in fc or d < fc[p][2]:
                    fc[p] = (c['sha'], c['own'], d)
        return fc

    # -- 기록 도우미
    def _rec(self, lst, f, line, mine, **kw):
        d = dict(path=f['path'], line=line, mine=bool(mine), **kw)
        lst.append(d)
        return d

    # -- 파일 고르기
    def candidates(self):
        res = []
        for f in self.r.files:
            if f['kind'] in ('vendor', 'generated', 'doc'):
                continue
            p = f['path']
            if re.search(r'(^|/)\.env', p):
                continue
            if f['lang'] not in READ_LANGS and not COMPOSE.search(p) and not DEP_FILES.search(p):
                continue
            if f['lang'] == 'JSON' and not re.search(r'(^|/)(package|composer|ormconfig|firebase)\.json$', p):
                continue
            if (f.get('size') or 0) > 1_500_000:
                if f.get('my_lines') or p in self.touched:
                    self.unreadable.append(dict(path=p, why='큰 파일(1.5MB 넘음)'))
                continue
            dep_or_cfg = bool(DEP_FILES.search(p) or COMPOSE.search(p) or f['kind'] == 'config' or P_CONN.search(p))
            if not (f.get('my_lines') or p in self.touched or dep_or_cfg):
                continue
            res.append(f)
        return res

    def run(self):
        files = self.candidates()
        texts = {}
        for f in files:
            t = self.r.text(f['path'])
            if t is None:
                if f.get('my_lines') or f['path'] in self.touched:
                    self.unreadable.append(dict(path=f['path'], why='읽기 실패'))
                continue
            texts[f['path']] = t
        self.files_read = len(texts)
        # 1차: 레포 단위 이름(모델 클래스·mongoose 모델)과 의존성
        for f in files:
            t = texts.get(f['path'])
            if t is None:
                continue
            p = f['path']
            if DEP_FILES.search(p):
                self.scan_deps(f, t)
            if f['lang'] in ('JavaScript', 'TypeScript', 'Vue', 'Svelte'):
                for m in re.finditer(r"""\b(?:mongoose\.)?model\s*(?:<[^>]*>)?\(\s*['"`](\w+)['"`]|\bsequelize\.define\(\s*['"`](\w+)|\bclass\s+(\w+)\s+extends\s+(?:Sequelize\.)?Model\b""", t):
                    self.model_names_js.add(next(x for x in m.groups() if x))
                for m in re.finditer(r'\b(?:export\s+)?(?:const|let|var)\s+(\w+)\s*=\s*(?:mongoose\.)?model\s*(?:<[^>]*>)?\(', t):
                    self.model_names_js.add(m.group(1))
            if f['lang'] == 'Python':
                for m in re.finditer(r'^class\s+(\w+)\s*\(([^)]*)\)', t, re.M):
                    self.py_model_bases.add((m.group(1), m.group(2)))
        self.py_models = self._py_model_closure()
        # 2차: 파일마다(내 줄 판정은 처음 물을 때 한다)
        for f in files:
            t = texts.get(f['path'])
            if t is None:
                continue
            if f['lang'] == 'Jupyter Notebook':
                if f['kind'] != 'test' and not L.TEST.search(f['path']):
                    self.scan_notebook(f, t)
                continue
            if f['lang'] == 'XML' and not re.search(r'<mapper\s+namespace|<databaseChangeLog|<sqlMap\b', t) and not DEP_FILES.search(f['path']):
                continue
            try:
                self.scan_file(f, t, self.lazy_mine(f))
            except RecursionError:
                self.parse_errors.append(dict(path=f['path'], why='RecursionError'))
        return self

    def lazy_mine(self, f):
        box = {}

        def mine(n):
            if 'fn' not in box:
                fn, how = self.mine_fn(f)
                if fn is None:
                    self.unreadable.append(dict(path=f['path'], why=how))
                    fn = (lambda n: False)
                box['fn'] = fn
            return box['fn'](n)
        return mine

    def _py_model_closure(self):
        base_models = {'models.Model', 'Model', 'AbstractUser', 'AbstractBaseUser', 'PermissionsMixin', 'TimeStampedModel', 'db.Model'}
        names = {}
        for name, bases in self.py_model_bases:
            names.setdefault(name, set()).update(b.strip().split('[')[0] for b in bases.split(',') if b.strip())
        known = set()
        changed = True
        while changed:
            changed = False
            for n, bs in names.items():
                if n not in known and (bs & base_models or bs & known or any(b.endswith('.Model') and 'pydantic' not in b for b in bs)):
                    known.add(n); changed = True
        return known

    # -- 의존성 흔적
    def scan_deps(self, f, t):
        p = f['path']
        for i, ln in enumerate(t.split('\n'), 1):
            st = ln.strip()
            if not st or st.startswith(('#', '//', '<!--')):
                continue
            toks = set()
            toks.update(re.findall(r'"(@?[\w.-]+(?:/[\w.-]+)?)"\s*:', st))                       # package.json · composer.json
            toks.update(re.findall(r'<artifactId>\s*([\w.-]+)\s*</artifactId>', st))              # pom.xml
            toks.update(m.split(':')[1] for m in re.findall(r'[\'"]([\w.-]+:[\w.-]+)(?::[^\'"]*)?[\'"]', st) if ':' in m)   # gradle
            m = re.match(r'^([A-Za-z0-9_.\[\]-]+)\s*(?:[<>=~!;\[]|$)', st)                             # requirements·Pipfile·pyproject
            if m:
                toks.add(m.group(1).split('[')[0])
            toks.update(re.findall(r'^\s*"?([A-Za-z0-9_.-]+)\s*(?:[<>=~!]=?|\^)', st))
            toks.update(re.findall(r'["\']([A-Za-z0-9_.-]+)(?:\[[^\]]*\])?\s*(?:[<>=~!]=?[^"\']*)?["\']', st))   # pyproject dependencies 목록
            for tok in toks:
                low = tok.lower()
                for cand in (low, low.rsplit('/', 1)[-1]):
                    if cand in DEPS:
                        db, stack = DEPS[cand]
                        if db:
                            self.deps[db].append((p, i))
                        if stack:
                            self.deps['stack:' + stack].append((p, i))
                            self.stacks.add(stack)
                        break
        if p.endswith('.csproj') and re.search(r'EntityFrameworkCore', t):
            self.deps['stack:ef'].append((p, 1)); self.stacks.add('ef')
        if p.endswith('go.mod') and re.search(r'gorm\.io/gorm', t):
            self.deps['stack:gorm'].append((p, 1)); self.stacks.add('gorm')
        if p.endswith('composer.json') and re.search(r'laravel/framework', t):
            self.deps['stack:eloquent'].append((p, 1)); self.stacks.add('eloquent')
        if p.endswith('Gemfile') and re.search(r"""gem\s+['"]rails['"]|activerecord""", t):
            self.deps['stack:activerecord'].append((p, 1)); self.stacks.add('activerecord')

    # -- 파일 하나
    def scan_file(self, f, t, mine):
        p, lang = f['path'], f['lang']
        is_test = f['kind'] == 'test' or bool(L.TEST.search(p))
        if is_test:
            return
        if lang == 'Python':
            self.scan_python(f, t, mine)
        elif lang == 'Jupyter Notebook':
            self.scan_notebook(f, t)
        elif lang in ('SQL', 'PLpgSQL', 'PLSQL', 'TSQL', 'SQLPL'):
            self.scan_sql_file(f, t, mine)
        elif lang == 'Prisma':
            self.scan_prisma(f, t, mine)
        elif lang in ('Java', 'Kotlin'):
            self.scan_jvm(f, t, mine, 'java' if lang == 'Java' else 'kt')
        elif lang in ('JavaScript', 'TypeScript', 'Vue', 'Svelte'):
            self.scan_js(f, t, mine)
        elif lang == 'XML':
            self.scan_xml(f, t, mine)
        elif lang in ('PHP', 'Go', 'C#', 'Dart', 'Ruby'):
            self.scan_other_code(f, t, mine, lang)
        if lang in ('YAML', 'Java Properties', 'INI', 'TOML') or COMPOSE.search(p):
            self.scan_config(f, t, mine)

    # ---------------- SQL 파일
    def scan_sql_file(self, f, t, mine, base_line=0):
        p = f['path']
        self.parsers['sql-rule'] += 1
        if SQL_DUMP.search(t):
            self.notes.append(f'SQL 덤프로 보고 뺌: {p}')
            return
        gen = bool(re.search(r'(^|/)prisma/migrations/', p))
        routine = bool(re.search(r'CREATE\s+(OR\s+REPLACE\s+)?(FUNCTION|PROCEDURE|TRIGGER)\b|\$\$', t, re.I))
        code, _ = mask(t, 'sql')
        pdb = next((k for rx, k in ((r'cassandra|\.cql$', 'Cassandra'), (r'(^|/)hive(/|_)', 'Hive'), (r'trino|presto', 'Trino'), (r'snowflake', 'Snowflake'),
                                     (r'bigquery|(^|/)bq_', 'BigQuery'), (r'spark', 'Spark SQL')) if re.search(rx, p, re.I)), None)
        if p.endswith('.cql'):
            pdb = 'Cassandra'
        if pdb:
            self._rec(self.conn, f, 1, mine(1), db=pdb, how='dialect', stack='sql-file-path')
        for (a, b, st) in sql_statements(code):
            facts = sql_facts(st)
            dia = next((v for k, o, v in facts if k == 'dialect'), None)
            for kind, off, val in facts:
                if kind == 'dialect' and pdb:
                    continue
                if kind == 'tx' and routine:
                    continue          # 함수·프로시저 본문의 BEGIN은 트랜잭션이 아님
                ln = a + off + 1
                self._sql_fact(f, kind, ln, val, mine, stack='sql-file', gen=gen, end=b + 1, db=pdb or (dia if dia in ('Cassandra', 'Hive', 'Trino') else None))
        if gen:
            self.file_cls[p].add('schema')

    def _sql_fact(self, f, kind, ln, val, mine, stack, gen=False, end=None, db=None):
        p = f['path']
        m = mine(ln)
        if kind == 'table':
            if val.get('ctas'):
                # CREATE TABLE ... AS SELECT: 쿼리 결과로 만든 표(설계로 보지 않음, 제안) → 접근으로만
                self._rec(self.access, f, ln, m, stack=stack, what='CTAS', db=db)
                return
            self._rec(self.tables, f, ln, m, name=val['name'], norm=norm_table(val['name']), stack=stack, kind='ddl', rel=val['rel'],
                      gen=gen, end=end, db=db, body=(ln, end))
            self.file_cls[p].add('schema')
        elif kind == 'index':
            self._rec(self.indexes, f, ln, m, stack=stack, unique=val['unique'], table=norm_table(val['table']), gen=gen, sql=True)
            self.file_cls[p].add('schema')
        elif kind == 'unique':
            self._rec(self.uniques, f, ln, m, stack=stack)
        elif kind == 'rel':
            self._rec(self.rels, f, ln, m, stack=stack)
        elif kind == 'tx':
            self._rec(self.tx, f, ln, m, stack=stack, sure=True, what='SQL BEGIN/START TRANSACTION')
        elif kind == 'dml':
            self._rec(self.access, f, ln, m, stack=stack, what='SQL DML', db=db)
        elif kind == 'fetchjoin':
            self._rec(self.tuning, f, ln, m, stack=stack, what='JPQL join fetch', doc=True)
        elif kind == 'explain':
            self._rec(self.tuning, f, ln, m, stack=stack, what='EXPLAIN', doc=False)
        elif kind == 'dialect':
            self._rec(self.conn, f, ln, m, db=val, how='dialect', stack=stack)
        elif kind == 'view':
            pass

    def sql_in_string(self, f, start_line0, content, mine, stack, db=None):
        """코드 안 SQL 문자열(쿼리 API 인자) → 사실. start_line0: 문자열 시작 줄(0부터)."""
        code, _ = mask(content, 'sql')
        for (a, b, st) in sql_statements(code):
            for kind, off, val in sql_facts(st):
                ln = start_line0 + a + off + 1
                self._sql_fact(f, kind, ln, val, mine, stack=stack, end=start_line0 + b + 1, db=db)

    # ---------------- Prisma
    def scan_prisma(self, f, t, mine):
        p = f['path']
        self.parsers['prisma-rule'] += 1
        self.stacks.add('prisma')
        self.file_cls[p].update({'schema', 'model'})
        lines = t.split('\n')
        cur = None
        for i, raw in enumerate(lines, 1):
            ln = raw.split('//')[0]
            m = re.match(r'\s*(model|type)\s+(\w+)\s*\{', ln)
            if m and m.group(1) == 'model':
                end = i
                for j in range(i, len(lines)):
                    if lines[j].strip().startswith('}'):
                        end = j + 1; break
                mp = re.search(r'@@map\(\s*"([^"]+)"', '\n'.join(lines[i:end]))
                cur = self._rec(self.tables, f, i, mine(i), name=mp.group(1) if mp else m.group(2), norm=norm_table(mp.group(1) if mp else m.group(2)),
                                stack='prisma', kind='schema', rel=False, gen=False, end=end, db=None, body=(i, end))
                continue
            if cur and re.match(r'\s*\}', ln):
                cur = None
                continue
            if '@relation(' in ln and cur:
                cur['rel'] = True
                self._rec(self.rels, f, i, mine(i), stack='prisma')
            if re.search(r'@@index\(|@@fulltext\(', ln) and cur:
                self._rec(self.indexes, f, i, mine(i), stack='prisma', unique=False, table=cur['norm'], gen=False)
            if re.search(r'@@unique\(|\s@unique\b', ln) and cur:
                self._rec(self.uniques, f, i, mine(i), stack='prisma')
            m = re.search(r'provider\s*=\s*"(\w+)"', ln)
            if m and m.group(1).lower() in ORMTYPE:
                self._rec(self.conn, f, i, mine(i), db=ORMTYPE[m.group(1).lower()], how='config', stack='prisma')
                self.file_cls[p].add('conn')

    # ---------------- Java · Kotlin
    def scan_jvm(self, f, t, mine, style):
        p = f['path']
        self.parsers[PARSER_RX + ':' + style] += 1
        code, strs = mask(t, style)
        raw = t.split('\n')
        sby = defaultdict(list)
        for a, b, s in strs:
            sby[a].append(s)
        imports_room = 'androidx.room' in t
        pend, pend_table_name, cur = None, None, None
        cur_end = -1
        pend_idx = []
        is_mapper_iface = bool(re.search(r'@Mapper\b', '\n'.join(code)))
        file_has_jpa = bool(re.search(r'\b(javax|jakarta)\.persistence\b|org\.springframework\.data\b|org\.hibernate\b', t))
        for i, c in enumerate(code):
            n = i + 1
            if re.match(r'\s*(import|package)\s', c):
                continue
            # 엔티티(@Entity·Room @Entity·Spring Data Mongo @Document. ES @Document(indexName)는 테이블이 아니라 ES 사용)
            if re.search(r'@(Entity|Document)\b', c):
                if '@Document' in c and re.search(r'indexName\s*=', raw[i]):
                    self._rec(self.conn, f, n, mine(n), db='Elasticsearch', how='call', stack='spring-data-es')
                else:
                    stack = 'room' if imports_room else ('spring-data-mongo' if '@Document' in c else 'jpa')
                    nm = None
                    mm = re.search(r'tableName\s*=\s*"([^"]+)"', raw[i]) or re.search(r'@Document\s*\(\s*(?:collection\s*=\s*|value\s*=\s*)?"([^"]+)"', raw[i]) \
                        or re.search(r'@Entity\s*\(\s*name\s*=\s*"([^"]+)"', raw[i])
                    if mm:
                        nm = mm.group(1)
                    pend, pend_table_name, pend_idx = (stack, n), nm, []
            if pend and re.search(r'@Table\s*\(', c):
                seg = ' '.join(raw[i:i + 3])
                mm = re.search(r'@Table\s*\([^)]*?\bname\s*=\s*"([^"]+)"', seg)
                if mm:
                    pend_table_name = mm.group(1)
            is_idx = bool(re.search(r'@Index\s*\(|@CompoundIndex\b|@Indexed\b', c))
            uq_idx = bool(re.search(r'unique\s*=\s*true', raw[i], re.I))
            if is_idx and pend:
                pend_idx.append((n, uq_idx))
            if re.search(r'uniqueConstraints|@UniqueConstraint\b|unique\s*=\s*true', c + raw[i], re.I) and not is_idx:
                self._rec(self.uniques, f, n, mine(n), stack='jpa')
            m = re.search(r'\b(?:class|interface|object|record)\s+(\w+)', c)
            if m and pend:
                stack, pl = pend
                if style == 'kt' and '(' in c and '{' not in c:
                    end = group_end(code, i)
                else:
                    end = block_end(code, i, '{') if '{' in ''.join(code[i:i + 3]) else group_end(code, i)
                name = pend_table_name or m.group(1)
                cur = self._rec(self.tables, f, n, mine(n), name=name, norm=norm_table(name), stack=stack, kind='model', rel=False, gen=False,
                                end=end + 1, db='MongoDB' if stack == 'spring-data-mongo' else None, body=(pl, end + 1), anno_line=pl)
                cur_end = end
                for ln_i, uq in pend_idx:
                    self._rec(self.indexes, f, ln_i, mine(ln_i), stack=stack, unique=uq, table=cur['norm'], gen=False)
                pend_idx, pend, pend_table_name = [], None, None
                self.file_cls[p].add('model')
                continue
            if cur and i <= cur_end:
                if re.search(r'@(ManyToOne|OneToMany|OneToOne|ManyToMany|DBRef|DocumentReference)\b', c) or re.search(r'\bforeignKeys\s*=|ForeignKey\s*\(', c):
                    cur['rel'] = True
                    self._rec(self.rels, f, n, mine(n), stack=cur['stack'])
                if is_idx:
                    self._rec(self.indexes, f, n, mine(n), stack=cur['stack'], unique=uq_idx, table=cur['norm'], gen=False)
            elif cur and i > cur_end:
                cur = None
            # Exposed(Kotlin)
            mx = re.match(r'\s*(?:internal\s+|private\s+)?object\s+(\w+)\s*:\s*(Int|Long|UUID)?IdTable|\s*(?:internal\s+|private\s+)?object\s+(\w+)\s*:\s*Table\s*\(', c)
            if mx and style == 'kt':
                name = mx.group(1) or mx.group(3)
                end = block_end(code, i, '{')
                self._rec(self.tables, f, n, mine(n), name=(sby.get(i) or [name])[0], norm=norm_table((sby.get(i) or [name])[0]), stack='exposed', kind='model',
                          rel=False, gen=False, end=end + 1, db=None, body=(n, end + 1))
                self.file_cls[p].add('model')
            # 리포지토리 선언·호출
            if re.search(r'\binterface\s+\w+\s*(extends|:)\s*[\w.]*(Jpa|Crud|PagingAndSorting|ListCrud|ListPagingAndSorting|Mongo|ReactiveCrud|ReactiveMongo|R2dbc|Elasticsearch|Redis)?Repository\s*<', c):
                kind = 'MongoDB' if 'Mongo' in c else ('Elasticsearch' if 'Elasticsearch' in c else None)
                self._rec(self.access, f, n, mine(n), stack='spring-data', what='리포지토리 선언', db=kind)
                self.file_cls[p].add('repo')
                if 'Elasticsearch' in c:
                    self._rec(self.conn, f, n, mine(n), db='Elasticsearch', how='call', stack='spring-data')
                if 'Mongo' in c:
                    self._rec(self.conn, f, n, mine(n), db='MongoDB', how='call', stack='spring-data')
            if re.search(r'@Query\s*\(|@(Select|Insert|Update|Delete)\s*\(', c):
                self._rec(self.access, f, n, mine(n), stack='spring-data' if '@Query' in c else 'mybatis', what='쿼리 선언')
                self.file_cls[p].add('repo')
                for j in range(i, min(i + 8, len(code))):
                    for s in sby.get(j, []):
                        if JPQL_FETCH.search(s):
                            off = s[:JPQL_FETCH.search(s).start()].count('\n')
                            self._rec(self.tuning, f, j + off + 1, mine(j + off + 1), stack='jpa', what='fetch join(@Query)', doc=True)
                        if re.search(r'\bCREATE\s+TABLE\b|\bCREATE\s+(UNIQUE\s+)?INDEX\b', s, re.I):
                            self.sql_in_string(f, j, s, mine, stack='sql-in-code')
                    if ')' in code[j] and j > i and not code[j].strip().startswith('"'):
                        break
            if re.search(r'@EntityGraph\b', c):
                self._rec(self.tuning, f, n, mine(n), stack='jpa', what='@EntityGraph', doc=True)
            if re.search(r'@BatchSize\b', c):
                self._rec(self.tuning, f, n, mine(n), stack='jpa', what='@BatchSize', doc=True)
            if re.search(r'\.fetchJoin\(\)', c):
                self._rec(self.tuning, f, n, mine(n), stack='jpa', what='QueryDSL fetchJoin', doc=True)
            if re.search(r'@Transactional\b', c):
                ro = 'readOnly' in raw[i] and 'false' not in raw[i]
                nxt = ' '.join(code[i + 1:i + 3])
                priv = bool(re.search(r'^\s*private\s', nxt))
                self._rec(self.tx, f, n, mine(n), stack='spring', sure=True, what='@Transactional' + ('(readOnly)' if ro else '') + ('(private)' if priv else ''))
            if re.search(r'\bTransactionTemplate\b.*\.execute\w*\(|\btransactionTemplate\.execute\w*\(|\.setAutoCommit\(\s*false\s*\)|\.startTransaction\(|\.withTransaction\(', c):
                self._rec(self.tx, f, n, mine(n), stack='jdbc', sure=True, what='명시 트랜잭션')
            # 호출
            if re.search(r'\b\w*(Repository|Repo)\.(save\w*|find\w*|delete\w*|exists\w*|count\w*|get\w*|update\w*|insert\w*|search\w*|flush)\s*\(', c):
                self._rec(self.access, f, n, mine(n), stack='spring-data', what='리포지토리 호출')
            if re.search(r'\b(em|entityManager|entityManagerFactory)\.(persist|merge|find|createQuery|createNativeQuery|remove|flush|getReference)\s*\(', c):
                self._rec(self.access, f, n, mine(n), stack='jpa', what='EntityManager 호출')
            if re.search(r'\b(queryFactory|jpaQueryFactory)\.(select\w*|update|delete|insert)\s*\(', c):
                self._rec(self.access, f, n, mine(n), stack='jpa', what='QueryDSL 호출')
            if re.search(r'\b\w*[jJ]dbcTemplate\.(query\w*|update|execute|batchUpdate)\s*\(', c):
                self._rec(self.access, f, n, mine(n), stack='jdbc', what='JdbcTemplate 호출')
            if re.search(r'\.(executeQuery|executeUpdate|prepareStatement|createStatement|executeBatch)\s*\(', c):
                self._rec(self.access, f, n, mine(n), stack='jdbc', what='JDBC 호출')
            if re.search(r'\bDriverManager\.getConnection\s*\(', c):
                db = None
                for s in sby.get(i, []):
                    for rx, k in SCHEME:
                        if rx.search(s):
                            db = k
                self._rec(self.conn, f, n, mine(n), db=db or 'SQL(미상)', how='call', stack='jdbc')
                self.file_cls[p].add('conn')
            if re.search(r'\b\w*Mapper\.(select|insert|update|delete|find|get|count|save)\w*\s*\(', c) and ('mybatis' in self.stacks or is_mapper_iface):
                self._rec(self.access, f, n, mine(n), stack='mybatis', what='매퍼 호출')
            if re.search(r'\bsqlSession\w*\.(selectList|selectOne|insert|update|delete)\s*\(', c):
                self._rec(self.access, f, n, mine(n), stack='mybatis', what='SqlSession 호출')
            if re.search(r'\b(mongoTemplate|reactiveMongoTemplate)\.\w+\s*\(', c):
                self._rec(self.access, f, n, mine(n), stack='spring-data-mongo', what='MongoTemplate 호출', db='MongoDB')
                self._rec(self.conn, f, n, mine(n), db='MongoDB', how='call', stack='spring-data-mongo')
            if re.search(r'\b(redisTemplate|stringRedisTemplate|reactiveRedisTemplate|redissonClient|jedis)\w*\.\w+\s*\(|new\s+(LettuceConnectionFactory|JedisConnectionFactory)\s*\(|Redisson\.create\s*\(|@RedisHash\b', c, re.I):
                self._rec(self.conn, f, n, mine(n), db='Redis', how='call', stack='spring-data-redis')
            if re.search(r'\b(elasticsearchOperations|elasticsearchTemplate|elasticsearchClient|restHighLevelClient)\.\w+\s*\(|new\s+RestHighLevelClient\s*\(', c):
                self._rec(self.conn, f, n, mine(n), db='Elasticsearch', how='call', stack='spring-data-es')
            # SQL 문자열(쿼리 API 인자)
            for s in sby.get(i, []):
                if SQLSHAPE.search(s) and (re.search(r'\b(execute\w*|prepareStatement|executeQuery|executeUpdate|execSQL|rawQuery|query\w*|update|createQuery|createNativeQuery|batchUpdate|addBatch)\s*\(', ' '.join(code[max(0, i - 1):i + 1]))
                                           or re.search(r'@(Query|Select|Insert|Update|Delete)\b', ' '.join(code[max(0, i - 3):i + 1]))
                                           or self._assigned_then_executed(code, i, raw)):
                    self.sql_in_string(f, i, s, mine, stack='sql-in-code')
        # Android SQLiteOpenHelper 등 execSQL
        if re.search(r'extends\s+SQLiteOpenHelper|:\s*SQLiteOpenHelper\(', t):
            self.stacks.add('android-sqlite')

    def _assigned_then_executed(self, code, i, raw):
        m = re.search(r'\b(\w+)\s*=\s*""', code[i]) or re.search(r'\b(\w+)\s*=\s*$', code[i - 1] if i else '')
        if not m:
            return False
        name = m.group(1)
        if name in ('sql', 'query', 'SQL', 'QUERY') or name.upper().endswith(('_SQL', '_QUERY')) or name.endswith(('Sql', 'Query')):
            pat = re.compile(r'\(\s*' + re.escape(name) + r'\b|,\s*' + re.escape(name) + r'\s*[,)]')
            return any(pat.search(c) for c in code)
        return False

    # ---------------- JS · TS · Vue
    def scan_js(self, f, t, mine):
        p = f['path']
        self.parsers[PARSER_RX + ':js'] += 1
        code, strs = mask(t, 'c')
        raw = t.split('\n')
        joined = '\n'.join(code)
        sby = defaultdict(list)
        for a, b, s in strs:
            sby[a].append(s)
        imp = set(re.findall(r"""(?:from\s+|require\(\s*|import\s*\(\s*|import\s+)['"`]([@\w./-]+)['"`]""", t))
        uses = lambda *mods: any(any(x == m or x.startswith(m + '/') for x in imp) for m in mods)
        has_typeorm = uses('typeorm', '@nestjs/typeorm') or 'typeorm' in self.stacks
        has_seq = uses('sequelize', 'sequelize-typescript') or 'sequelize' in self.stacks
        has_mongoose = uses('mongoose', '@nestjs/mongoose') or 'mongoose' in self.stacks
        has_prisma = uses('@prisma/client') or 'prisma' in self.stacks
        if uses('typeorm', '@nestjs/typeorm'):
            self.stacks.add('typeorm')
        if uses('sequelize', 'sequelize-typescript'):
            self.stacks.add('sequelize')
        if uses('mongoose', '@nestjs/mongoose'):
            self.stacks.add('mongoose')
        if uses('@prisma/client'):
            self.stacks.add('prisma')
        if uses('knex'):
            self.stacks.add('knex')
        if uses('drizzle-orm'):
            self.stacks.add('drizzle')
        if uses('@mikro-orm/core'):
            self.stacks.add('mikro-orm'); self.traces.append(dict(path=p, line=1, var='depth', tech='MikroORM', why='규칙 밖 ORM(MikroORM)'))
        pend, cur, cur_end = None, None, -1
        for i, c in enumerate(code):
            n = i + 1
            if re.match(r'\s*(import\s|export\s+\*\s+from)', c) or re.search(r'\brequire\(\s*""\s*\)\s*;?\s*$', c) and re.match(r'\s*(const|let|var)\s', c):
                continue
            # TypeORM 엔티티
            if re.search(r'@Entity\s*\(', c) and (has_typeorm or 'typeorm' in t):
                pend = (n, sby.get(i, [None])[0])
            if re.search(r'@Index\s*\(', c) and (cur and i <= cur_end or pend):
                self._rec(self.indexes, f, n, mine(n), stack='typeorm', unique='unique' in raw[i].lower(), table=cur['norm'] if cur and i <= cur_end else '?', gen=False)
            m = re.search(r'\bclass\s+(\w+)', c)
            if m and pend:
                end = block_end(code, i, '{')
                name = pend[1] or m.group(1)
                cur = self._rec(self.tables, f, n, mine(n), name=name, norm=norm_table(name), stack='typeorm', kind='model', rel=False, gen=False,
                                end=end + 1, db=None, body=(pend[0], end + 1), anno_line=pend[0])
                cur_end, pend = end, None
                self.file_cls[p].add('model')
                continue
            if cur and i <= cur_end:
                if re.search(r'@(ManyToOne|OneToMany|OneToOne|ManyToMany|JoinColumn)\s*\(', c):
                    cur['rel'] = True; self._rec(self.rels, f, n, mine(n), stack='typeorm')
                if re.search(r'unique\s*:\s*true', c):
                    self._rec(self.uniques, f, n, mine(n), stack='typeorm')
            # sequelize-typescript @Table class X extends Model
            mt = re.search(r'\bclass\s+(\w+)\s+extends\s+(?:Sequelize\.)?Model\b', c)
            if mt and has_seq:
                end = block_end(code, i, '{')
                mi = re.search(r'\b' + re.escape(mt.group(1)) + r'\.init\s*\(', joined)
                tbl = None
                if mi:
                    ln_init = joined[:mi.start()].count('\n')
                    e2 = group_end(code, ln_init)
                    seg = '\n'.join(raw[ln_init:e2 + 1])
                    mm = re.search(r"""tableName\s*:\s*['"`](\w+)""", seg)
                    tbl = mm.group(1) if mm else None
                    if re.search(r'\bindexes\s*:\s*\[', seg):
                        k = next((j for j in range(ln_init, e2 + 1) if re.search(r'\bindexes\s*:', code[j])), ln_init)
                        self._rec(self.indexes, f, k + 1, mine(k + 1), stack='sequelize', unique=False, table=norm_table(tbl or mt.group(1)), gen=False)
                    end = max(end, e2)
                cur = self._rec(self.tables, f, n, mine(n), name=tbl or mt.group(1), norm=norm_table(tbl or mt.group(1)), stack='sequelize', kind='model', rel=False,
                                gen=False, end=end + 1, db=None, body=(n, end + 1))
                cur_end = end
                self.file_cls[p].add('model')
            # sequelize.define / mongoose Schema / knex createTable / drizzle
            md = re.search(r'\.define\s*\(', c)
            if md and (has_seq or 'sequelize' in c) and sby.get(i):
                end = group_end(code, i)
                seg = '\n'.join(raw[i:end + 1])
                name = sby[i][0]
                cur = self._rec(self.tables, f, n, mine(n), name=name, norm=norm_table(name), stack='sequelize', kind='model', rel=False, gen=False,
                                end=end + 1, db=None, body=(n, end + 1))
                cur_end = end
                if re.search(r'\bindexes\s*:\s*\[', seg):
                    k = next((j for j in range(i, end + 1) if re.search(r'\bindexes\s*:', code[j])), i)
                    self._rec(self.indexes, f, k + 1, mine(k + 1), stack='sequelize', unique=False, table=cur['norm'], gen=False)
                self.file_cls[p].add('model')
            ms = re.search(r'\bnew\s+(?:mongoose\.)?Schema\s*(?:<[^>]*>)?\s*\(', c)
            if ms and (has_mongoose or 'mongoose' in t):
                end = group_end(code, i)
                mv = re.search(r'\b(?:const|let|var)\s+(\w+)\s*=', c) or re.search(r'\b(\w+)\s*=\s*new\s', c)
                var = mv.group(1) if mv else 'schema'
                mm = re.search(r"""\bmodel\s*(?:<[^>]*>)?\(\s*['"`](\w+)['"`]\s*,\s*""" + re.escape(var) + r'\b', t)
                name = mm.group(1) if mm else re.sub(r'(?i)schema$', '', var) or var
                cur = self._rec(self.tables, f, n, mine(n), name=name, norm=norm_table(name), stack='mongoose', kind='model', rel=False, gen=False,
                                end=end + 1, db='MongoDB', body=(n, end + 1))
                cur_end = end
                for j in range(i, end + 1):
                    if re.search(r'\bindex\s*:\s*true\b', code[j]):
                        self._rec(self.indexes, f, j + 1, mine(j + 1), stack='mongoose', unique=False, table=cur['norm'], gen=False)
                    if re.search(r'\bunique\s*:\s*true\b', code[j]):
                        self._rec(self.uniques, f, j + 1, mine(j + 1), stack='mongoose')
                    if re.search(r'\bref\s*:', code[j]) or re.search(r'Types\.ObjectId|Schema\.ObjectId', code[j]):
                        cur['rel'] = True
                        self._rec(self.rels, f, j + 1, mine(j + 1), stack='mongoose')
                self.file_cls[p].add('model')
            if re.search(r'\b\w+[Ss]chema\.index\s*\(', c) or re.search(r'\.createIndex(es)?\s*\(', c):
                self._rec(self.indexes, f, n, mine(n), stack='mongoose' if 'chema.index' in c else 'mongodb', unique='unique' in raw[i], table='?', gen=False)
            mk = re.search(r'\.createTable(IfNotExists)?\s*\(', c)
            if mk and sby.get(i) and ('knex' in self.stacks or 'queryInterface' in c or 'schema' in c):
                end = group_end(code, i)
                name = sby[i][0]
                stk = 'sequelize-migration' if 'queryInterface' in c else 'knex'
                cur = self._rec(self.tables, f, n, mine(n), name=name, norm=norm_table(name), stack=stk, kind='migration', rel=False, gen=False,
                                end=end + 1, db=None, body=(n, end + 1))
                cur_end = end
                self.file_cls[p].add('schema')
            mz = re.search(r'\b(pg|mysql|sqlite)Table\s*\(', c)
            if mz and sby.get(i):
                end = group_end(code, i)
                name = sby[i][0]
                cur = self._rec(self.tables, f, n, mine(n), name=name, norm=norm_table(name), stack='drizzle', kind='model', rel=False, gen=False,
                                end=end + 1, db={'pg': 'PostgreSQL', 'mysql': 'MySQL', 'sqlite': 'SQLite'}[mz.group(1)], body=(n, end + 1))
                cur_end = end
                self.file_cls[p].add('model')
            if cur and i <= cur_end and cur['stack'] in ('sequelize', 'knex', 'drizzle', 'sequelize-migration'):
                if re.search(r'\breferences\s*[:(]|\.references\s*\(|\.foreign\s*\(', c):
                    cur['rel'] = True; self._rec(self.rels, f, n, mine(n), stack=cur['stack'])
                if re.search(r'\.index\s*\(|\bindex\s*\(\s*""\s*\)\s*\.on\(', c) and cur['stack'] != 'sequelize':
                    self._rec(self.indexes, f, n, mine(n), stack=cur['stack'], unique=False, table=cur['norm'], gen=False)
                if re.search(r'\bunique\s*[:(]|\.unique\s*\(', c):
                    self._rec(self.uniques, f, n, mine(n), stack=cur['stack'])
            if re.search(r'\bqueryInterface\.addIndex\s*\(', c):
                self._rec(self.indexes, f, n, mine(n), stack='sequelize-migration', unique='unique' in raw[i], table=norm_table((sby.get(i) or ['?'])[0]), gen=False)
            if re.search(r'\.(belongsTo|hasMany|hasOne|belongsToMany)\s*\(', c) and (has_seq or 'sequelize' in self.stacks):
                self._rec(self.rels, f, n, mine(n), stack='sequelize')
                for tb in self.tables:
                    if tb['path'] == p and tb['stack'] == 'sequelize':
                        tb['rel'] = True
            # 접근(호출)
            acc = None
            if re.search(r'\b(this\.)?(prisma|db|client|prismaService|prismaClient)\.\w+\.(findMany|findUnique\w*|findFirst\w*|create|createMany|update|updateMany|upsert|delete|deleteMany|count|aggregate|groupBy)\s*\(', c) and has_prisma:
                acc = ('prisma', 'Prisma 호출')
            elif re.search(r'\.\$(queryRaw|executeRaw|queryRawUnsafe|executeRawUnsafe)\b', c):
                acc = ('prisma', 'Prisma raw')
            elif re.search(r'\b\w*[Rr]epository\.(find\w*|save|insert|update|delete|remove|count\w*|create|upsert|exist\w*|query|increment|decrement|softDelete|restore|createQueryBuilder)\s*\(', c) and has_typeorm:
                acc = ('typeorm', '리포지토리 호출')
            elif re.search(r'\b(getRepository|createQueryBuilder|getManager)\s*\(|\b(dataSource|manager|entityManager|connection)\.(query|getRepository|save|find\w*|createQueryBuilder)\s*\(', c) and has_typeorm:
                acc = ('typeorm', 'TypeORM 호출')
            elif self.model_names_js and re.search(r'\b(' + '|'.join(map(re.escape, sorted(self.model_names_js))) + r')\.(find\w*|create|bulkCreate|update\w*|destroy|count\w*|upsert|aggregate|insertMany|delete\w*|replaceOne|exists|where|save)\s*\(', c):
                acc = ('mongoose' if has_mongoose and not has_seq else ('sequelize' if has_seq else 'odm'), '모델 호출')
            elif re.search(r'\bsequelize\.query\s*\(', c):
                acc = ('sequelize', 'sequelize.query')
            elif re.search(r'\b(knex|db|trx)\s*\(\s*""\s*\)\s*\.(select|insert|update|del|delete|where|first|join|leftJoin)\b', c) and 'knex' in self.stacks:
                acc = ('knex', 'knex 쿼리')
            elif re.search(r'\bsupabase\w*\s*\.from\s*\(\s*""\s*\)\s*\.(select|insert|update|delete|upsert)\s*\(', c) or re.search(r'\.from\s*\(\s*""\s*\)\s*\.(select|insert|update|delete|upsert)\s*\(', c) and uses('@supabase/supabase-js'):
                acc = ('supabase', 'Supabase 호출')
                self._rec(self.conn, f, n, mine(n), db='PostgreSQL', how='call', stack='supabase')
            elif re.search(r'\b(getDocs?|addDoc|setDoc|updateDoc|deleteDoc|onSnapshot)\s*\(\s*(collection|doc|query)\s*\(', c) or re.search(r'\.collection\s*\(\s*""\s*\)\s*\.(add|get|doc|where|orderBy|onSnapshot)\s*\(', c) and (uses('firebase', 'firebase-admin') or 'firestore' in t.lower()):
                acc = ('firestore', 'Firestore 호출')
                self._rec(self.conn, f, n, mine(n), db='Firestore', how='call', stack='firestore')
            elif re.search(r'\b(DynamoDBClient|DocumentClient|DynamoDBDocumentClient)\b', c) and re.search(r'\bnew\s|\.from\s*\(', c) or re.search(r'\bsend\s*\(\s*new\s+(Put|Get|Query|Scan|Update|Delete|BatchWrite|BatchGet)(Item)?Command\s*\(', c) or re.search(r'\.(put|get|query|scan|update|delete)\s*\(\s*\{\s*$', c) and 'TableName' in ' '.join(raw[i:i + 3]):
                acc = ('dynamodb', 'DynamoDB 호출')
                self._rec(self.conn, f, n, mine(n), db='DynamoDB', how='call', stack='dynamodb')
            if acc:
                self._rec(self.access, f, n, mine(n), stack=acc[0], what=acc[1])
            # 연결
            if re.search(r'\bmongoose\.(connect|createConnection)\s*\(|\bMongooseModule\.forRoot\w*\s*\(|\bnew\s+MongoClient\s*\(|\bMongoClient\.connect\s*\(', c):
                self._rec(self.conn, f, n, mine(n), db='MongoDB', how='call', stack='mongo')
                self.file_cls[p].add('conn')
            if re.search(r'\b(mysql2?|mysql)\.(createConnection|createPool)\s*\(|\bcreatePool\s*\(|\bcreateConnection\s*\(', c) and uses('mysql', 'mysql2', 'mysql2/promise'):
                self._rec(self.conn, f, n, mine(n), db='MySQL', how='call', stack='mysql-js')
                self.file_cls[p].add('conn')
            if re.search(r'\bnew\s+(pg\.)?(Pool|Client)\s*\(', c) and uses('pg'):
                self._rec(self.conn, f, n, mine(n), db='PostgreSQL', how='call', stack='pg')
                self.file_cls[p].add('conn')
            if re.search(r'\bnew\s+(sqlite3\.)?Database\s*\(', c) and uses('sqlite3', 'better-sqlite3'):
                self._rec(self.conn, f, n, mine(n), db='SQLite', how='call', stack='sqlite-js')
                self.file_cls[p].add('conn')
            if re.search(r'\bcreateClient\s*\(', c) and uses('@supabase/supabase-js'):
                self._rec(self.conn, f, n, mine(n), db='PostgreSQL', how='call', stack='supabase')
            if (re.search(r'\bcreateClient\s*\(', c) and uses('redis')) or (re.search(r'\bnew\s+(IORedis|Redis)\s*\(', c) and uses('ioredis')) or re.search(r'\bRedisModule\.forRoot\w*\s*\(|\bredisStore\b', c):
                self._rec(self.conn, f, n, mine(n), db='Redis', how='call', stack='redis-js')
            if re.search(r'\bnew\s+Client\s*\(', c) and uses('@elastic/elasticsearch'):
                self._rec(self.conn, f, n, mine(n), db='Elasticsearch', how='call', stack='es-js')
            if re.search(r'\b(new\s+)?(ChromaClient|Pinecone|QdrantClient)\s*\(|\bChroma\.from\w*\s*\(', c):
                vk = 'Chroma' if 'Chroma' in c else ('Pinecone' if 'Pinecone' in c else 'Qdrant')
                self._rec(self.conn, f, n, mine(n), db=vk, how='call', stack='vector-js')
            for key, rx in (('type', r"""\btype\s*:\s*['"`]"""), ('dialect', r"""\bdialect\s*:\s*['"`]"""), ('client', r"""\bclient\s*:\s*['"`]""")):
                if re.search(rx, raw[i]) and sby.get(i) and (has_typeorm or has_seq or 'knex' in self.stacks or P_CONN.search(p)):
                    v = sby[i][0].lower()
                    if v in ORMTYPE and (key != 'type' or has_typeorm):
                        self._rec(self.conn, f, n, mine(n), db=ORMTYPE[v], how='config', stack=key)
                        self.file_cls[p].add('conn')
            # 트랜잭션
            mtx = re.search(r'\.transaction\s*\(\s*(?:async\s*)?\(?\s*(\w+)?', c)
            if mtx and not re.search(r'\$transaction', c):
                param = mtx.group(1)
                end = min(group_end(code, i), i + 60)
                seg = '\n'.join(code[i:end + 1])
                sure = bool(param and param not in ('async', 'function') and re.search(r'\b' + re.escape(param) + r'\s*\.\w+\s*\(|transaction\s*:\s*' + re.escape(param) + r'\b', seg))
                stk = 'typeorm' if has_typeorm else ('sequelize' if has_seq else ('knex' if 'knex' in self.stacks else 'js'))
                if sure:
                    self._rec(self.tx, f, n, mine(n), stack=stk, sure=True, what='transaction() 안에서 매니저·t로 씀')
                elif has_typeorm or has_seq or 'knex' in self.stacks or 'drizzle' in self.stacks:
                    self._rec(self.amb_tx, f, n, mine(n), stack=stk, sure=False, what='transaction() 호출(매니저·t 사용 확인 못 함)', end=end + 1)
            if re.search(r'\.\$transaction\s*\(', c):
                self._rec(self.tx, f, n, mine(n), stack='prisma', sure=True, what='$transaction')
            if re.search(r'\bqueryRunner\.startTransaction\s*\(|\.startTransaction\s*\(|\.withTransaction\s*\(|\bbeginTransaction\s*\(', c):
                self._rec(self.tx, f, n, mine(n), stack='js', sure=True, what='명시 트랜잭션 시작')
            if has_prisma and re.search(r'\.(create|update|upsert)\s*\(\s*\{', c):
                end = min(group_end(code, i), i + 40)
                for j in range(i + 1, end + 1):
                    if re.search(r'\b(create|createMany|connectOrCreate|upsert)\s*:\s*[\[{]', code[j]):
                        self._rec(self.tx, f, j + 1, mine(j + 1), stack='prisma', sure=True, what='Prisma 중첩 쓰기')
                        break
            # 튜닝
            if re.search(r'\.(leftJoinAndSelect|innerJoinAndSelect|leftJoinAndMapOne|leftJoinAndMapMany)\s*\(', c):
                self._rec(self.tuning, f, n, mine(n), stack='typeorm', what='JoinAndSelect', doc=True)
            if re.search(r'\brelations\s*:\s*[\[{]', c) and has_typeorm:
                self._rec(self.tuning, f, n, mine(n), stack='typeorm', what='relations', doc=True)
            if re.search(r'\binclude\s*:\s*[\[{\w]', c):
                if has_prisma and not has_seq:
                    self._rec(self.tuning, f, n, mine(n), stack='prisma', what='Prisma include(규칙으로 안 셈, S5)', doc=False, prisma=True)
                elif has_seq:
                    self._rec(self.tuning, f, n, mine(n), stack='sequelize', what='include', doc=True)
            if re.search(r'\.populate\s*\(', c) and has_mongoose:
                self._rec(self.tuning, f, n, mine(n), stack='mongoose', what='populate(규칙으로 안 셈, S5)', doc=False, docdb=True)
            # SQL 문자열
            for s in sby.get(i, []):
                if SQLSHAPE.search(s) and (re.search(r'\b(query|execute|exec|run|all|get|prepare|raw|sql|queryRaw\w*|executeRaw\w*)\s*\(\s*(""|``)?', ' '.join(code[max(0, i - 1):i + 1])) or self._assigned_then_executed(code, i, raw)):
                    self.sql_in_string(f, i, s, mine, stack='sql-in-code')
                    if not acc:
                        pass

    # ---------------- XML(MyBatis·Liquibase)
    def scan_xml(self, f, t, mine):
        p = f['path']
        if not re.search(r'<mapper\s+namespace|<databaseChangeLog|<sqlMap\b', t):
            return
        self.parsers[PARSER_RX + ':xml'] += 1
        code, _ = mask(t, 'xml')
        if '<databaseChangeLog' in t:
            self.file_cls[p].add('schema')
            for i, c in enumerate(code):
                n = i + 1
                m = re.search(r'<createTable\b[^>]*tableName="(\w+)"', c)
                if m:
                    self._rec(self.tables, f, n, mine(n), name=m.group(1), norm=norm_table(m.group(1)), stack='liquibase', kind='migration', rel=False, gen=False, end=n, db=None, body=(n, n))
                m = re.search(r'<createIndex\b[^>]*tableName="(\w+)"', c)
                if m:
                    self._rec(self.indexes, f, n, mine(n), stack='liquibase', unique='unique="true"' in c, table=norm_table(m.group(1)), gen=False)
                if re.search(r'<addForeignKeyConstraint\b|references=', c):
                    self._rec(self.rels, f, n, mine(n), stack='liquibase')
            return
        self.stacks.add('mybatis')
        self.file_cls[p].add('repo')
        rm_open = None
        for i, c in enumerate(code):
            n = i + 1
            if re.search(r'<(select|insert|update|delete)\b[^>]*\bid=', c):
                self._rec(self.access, f, n, mine(n), stack='mybatis', what='매퍼 문장')
            if re.search(r'<resultMap\b', c):
                rm_open = n
            if rm_open and re.search(r'<(collection|association)\b', c):
                tag = c + ' '.join(code[i + 1:i + 3])
                if 'select=' not in tag.split('>')[0]:
                    self._rec(self.tuning, f, n, mine(n), stack='mybatis', what='조인 매핑(select 속성 없음)', doc=True)
            if '</resultMap>' in c:
                rm_open = None
        # 매퍼 안의 SQL(DDL)
        body = '\n'.join(code)
        for m in re.finditer(r'\bCREATE\s+TABLE\b', body, re.I):
            ln = body[:m.start()].count('\n')
            seg = '\n'.join(code[ln:ln + 80])
            self.sql_in_string(f, ln, seg.split('</')[0], mine, stack='mybatis-sql')

    # ---------------- 그 밖의 코드(PHP·Go·C#·Dart·Ruby): SQL 문자열 + 흔적
    def scan_other_code(self, f, t, mine, lang):
        p = f['path']
        style = {'PHP': 'php', 'Go': 'go', 'C#': 'c', 'Dart': 'dart', 'Ruby': 'rb'}[lang]
        self.parsers[PARSER_RX + ':' + style] += 1
        code, strs = mask(t, style)
        raw = t.split('\n')
        for a, b, s in strs:
            if SQLSHAPE.search(s) and re.search(r'\b(query|execute\w*|exec\w*|prepare\w*|rawQuery|execSQL|mysqli_query|pg_query|Query\w*|Exec\w*|ExecuteSqlRaw\w*|FromSqlRaw|sql|db)\s*\(', ' '.join(code[max(0, a - 1):a + 1]), re.I):
                self.sql_in_string(f, a, s, mine, stack='sql-in-code')
                self._rec(self.access, f, a + 1, mine(a + 1), stack='sql-in-code-' + style, what='SQL 문자열 실행')
        for i, c in enumerate(code):
            n = i + 1
            if lang == 'PHP':
                if re.search(r'\bmysqli_connect\s*\(|\bnew\s+mysqli\s*\(', c):
                    self._rec(self.conn, f, n, mine(n), db='MySQL', how='call', stack='php-mysqli'); self.file_cls[p].add('conn')
                if re.search(r'\bnew\s+PDO\s*\(', c):
                    db = 'MySQL' if re.search(r'mysql:', raw[i]) else ('PostgreSQL' if 'pgsql:' in raw[i] else ('SQLite' if 'sqlite:' in raw[i] else 'SQL(미상)'))
                    self._rec(self.conn, f, n, mine(n), db=db, how='call', stack='php-pdo'); self.file_cls[p].add('conn')
                if re.search(r'\bmysqli_(query|prepare|stmt_execute|multi_query)\s*\(|->(query|prepare|exec)\s*\(', c):
                    self._rec(self.access, f, n, mine(n), stack='php', what='PHP DB 호출')
                if re.search(r'\bSchema::create\s*\(|extends\s+Model\b|DB::(table|select|transaction)\s*\(', c):
                    self.traces.append(dict(path=p, line=n, var='tables', tech='Eloquent', why='규칙 밖 ORM(Laravel Eloquent)')); self.stacks.add('eloquent')
            elif lang == 'C#':
                if re.search(r'\bDbSet\s*<|:\s*DbContext\b|\bDbContextOptions\b|\.HasIndex\s*\(|\.Include\s*\(', c):
                    self.traces.append(dict(path=p, line=n, var='tables', tech='EF Core', why='규칙 밖 ORM(Entity Framework)')); self.stacks.add('ef')
                if re.search(r'\bnew\s+(SqlConnection|MySqlConnection|NpgsqlConnection|SqliteConnection)\s*\(', c):
                    db = {'SqlConnection': 'SQL Server', 'MySqlConnection': 'MySQL', 'NpgsqlConnection': 'PostgreSQL', 'SqliteConnection': 'SQLite'}[re.search(r'new\s+(\w+)', c).group(1)]
                    self._rec(self.conn, f, n, mine(n), db=db, how='call', stack='ado'); self.file_cls[p].add('conn')
                m = re.search(r'\.Use(SqlServer|MySql|Npgsql|Sqlite|InMemoryDatabase)\s*\(', c)
                if m:
                    db = {'SqlServer': 'SQL Server', 'MySql': 'MySQL', 'Npgsql': 'PostgreSQL', 'Sqlite': 'SQLite', 'InMemoryDatabase': 'H2'}[m.group(1)]
                    self._rec(self.conn, f, n, mine(n), db=db, how='config', stack='ef'); self.file_cls[p].add('conn')
            elif lang == 'Go':
                if re.search(r'\bgorm\.(Open|Model)\b|\.AutoMigrate\s*\(', c):
                    self.traces.append(dict(path=p, line=n, var='tables', tech='GORM', why='규칙 밖 ORM(GORM)')); self.stacks.add('gorm')
                m = re.search(r'\bsql\.Open\s*\(', c)
                if m:
                    s0 = ' '.join(raw[i:i + 1]).lower()
                    db = 'MySQL' if 'mysql' in s0 else ('PostgreSQL' if 'postgres' in s0 or '"pgx"' in s0 else ('SQLite' if 'sqlite' in s0 else 'SQL(미상)'))
                    self._rec(self.conn, f, n, mine(n), db=db, how='call', stack='go-sql'); self.file_cls[p].add('conn')
                if re.search(r'\.(Query|QueryRow|Exec)(Context)?\s*\(', c):
                    self._rec(self.access, f, n, mine(n), stack='go-sql', what='database/sql 호출')
            elif lang == 'Dart':
                if re.search(r'\bopenDatabase\s*\(', c):
                    self._rec(self.conn, f, n, mine(n), db='SQLite', how='call', stack='sqflite'); self.file_cls[p].add('conn')
                if re.search(r'FirebaseFirestore\.instance|\.collection\s*\(\s*\'\'\s*\)', c):
                    self._rec(self.access, f, n, mine(n), stack='firestore', what='Firestore 호출')
                    self._rec(self.conn, f, n, mine(n), db='Firestore', how='call', stack='firestore')
            elif lang == 'Ruby':
                if re.search(r'\bcreate_table\b|ActiveRecord::|\bhas_many\b|\bbelongs_to\b', c):
                    self.traces.append(dict(path=p, line=n, var='tables', tech='ActiveRecord', why='규칙 밖 ORM(ActiveRecord)')); self.stacks.add('activerecord')

    # ---------------- 설정(YAML·properties·compose·INI·TOML)
    def scan_config(self, f, t, mine):
        p = f['path']
        if DEP_FILES.search(p) and not COMPOSE.search(p) and not p.endswith(('.yml', '.yaml')):
            return
        example = bool(EXAMPLE_PATH.search(p))
        testcfg = bool(TESTCFG.search(p))
        dev = bool(DEVCFG.search(p))
        lines = t.split('\n')
        if p.endswith('profiles.yml'):
            for i, ln in enumerate(lines, 1):
                m = re.match(r'\s*type\s*:\s*["\']?(postgres|mysql|sqlite|duckdb|snowflake|bigquery|redshift|databricks|spark|trino)\b', ln.split('#')[0])
                if m:
                    k = {'postgres': 'PostgreSQL', 'mysql': 'MySQL', 'sqlite': 'SQLite', 'duckdb': 'DuckDB', 'snowflake': 'Snowflake', 'bigquery': 'BigQuery',
                         'redshift': 'Redshift', 'databricks': 'Databricks', 'spark': 'Spark SQL', 'trino': 'Trino'}[m.group(1)]
                    self._rec(self.conn, f, i, mine(i), db=k, how='config', stack='dbt-profile', example=example, test=testcfg)
                    self.file_cls[p].add('conn')
        self.parsers['config-lines'] += 1
        is_compose = bool(COMPOSE.search(p))
        if re.search(r'(^|/)\.github/workflows/|\.gitlab-ci\.yml$', p):
            is_compose, testcfg = True, True       # CI 서비스 컨테이너: 흔적으로만
        for i, ln in enumerate(lines, 1):
            s = ln.split('#', 1)[0] if not ln.strip().startswith('#') else ''
            if not s.strip():
                continue
            if is_compose:
                m = re.match(r'\s*image\s*:\s*["\']?([\w./:-]+)', s)
                if m:
                    for rx, k in IMAGE:
                        if rx.search(m.group(1)):
                            self._rec(self.conn, f, i, mine(i), db=k, how='compose', stack='compose', example=example, test=testcfg)
                continue
            for rx, k in SCHEME:
                if rx.search(s) and not re.search(r'^\s*(#|//)', ln):
                    self._rec(self.conn, f, i, mine(i), db=k, how='config', stack='config', example=example, test=testcfg, dev=dev)
                    self.file_cls[p].add('conn')
            if re.search(r'\bdriver-class-name|driverClassName|spring\.datasource|^\s*datasource\s*:|spring\.jpa|^\s*jpa\s*:|hibernate\.|spring\.data\.mongodb|^\s*mongodb\s*:|spring\.r2dbc', s):
                self.file_cls[p].add('conn')
            if re.search(r'(spring\.(data\.)?redis\.(host|url|port|cluster)|^\s*redis\s*:\s*$|cache\.type\s*[:=]\s*redis|CACHE_TYPE\s*[:=]\s*["\']?redis)', s, re.I):
                if not re.search(r'^\s*redis\s*:\s*$', s) or self._yaml_parent(lines, i - 1) in ('data', 'spring', 'cache'):
                    self._rec(self.conn, f, i, mine(i), db='Redis', how='config', stack='config', example=example, test=testcfg)
            if re.search(r'spring\.(data\.)?elasticsearch\.(uris|host|rest)|^\s*elasticsearch\s*:\s*$', s):
                if not re.search(r'^\s*elasticsearch\s*:\s*$', s) or self._yaml_parent(lines, i - 1) in ('data', 'spring'):
                    self._rec(self.conn, f, i, mine(i), db='Elasticsearch', how='config', stack='config', example=example, test=testcfg)
            if re.search(r'^\s*(uri|host|database)\s*:', s) and self._yaml_parent(lines, i - 1) == 'mongodb':
                self._rec(self.conn, f, i, mine(i), db='MongoDB', how='config', stack='config', example=example, test=testcfg)
            if re.search(r'default_batch_fetch_size|default-batch-fetch-size', s) and not example and not testcfg:
                self._rec(self.tuning, f, i, mine(i), stack='jpa', what='hibernate default_batch_fetch_size(설정)', doc=True, config=True)
            if re.search(r'AWS::DynamoDB::Table', s):
                self._rec(self.tables, f, i, mine(i), name=f'dynamo@{i}', norm=f'dynamo{i}', stack='dynamodb-cfn', kind='schema', rel=False, gen=False, end=i, db='DynamoDB', body=(i, i))
                self._rec(self.conn, f, i, mine(i), db='DynamoDB', how='config', stack='cfn')
                self.file_cls[p].add('schema')
            if re.search(r'GlobalSecondaryIndexes|LocalSecondaryIndexes', s):
                self._rec(self.indexes, f, i, mine(i), stack='dynamodb-cfn', unique=False, table='?', gen=False)

    @staticmethod
    def _yaml_parent(lines, idx):
        """YAML 줄 idx(0부터)의 부모 키 이름"""
        cur = lines[idx]
        ind = len(cur) - len(cur.lstrip())
        for j in range(idx - 1, -1, -1):
            s = lines[j]
            if not s.strip() or s.strip().startswith('#'):
                continue
            ind2 = len(s) - len(s.lstrip())
            if ind2 < ind:
                m = re.match(r'\s*([\w.-]+)\s*:', s)
                return m.group(1) if m else None
        return None

    # ---------------- 노트북
    def scan_notebook(self, f, t):
        p = f['path']
        try:
            nb = json.loads(t)
        except Exception:
            self.parse_errors.append(dict(path=p, why='노트북 JSON 오류'))
            return
        cs = [c for c in self.r.commits if any(x['path'] == p for x in c['files'])]
        if not cs:
            return
        own_n = sum(1 for c in cs if c['own'])
        if own_n == 0:
            return
        whole = own_n == len(cs)
        cells = [c for c in nb.get('cells', []) if c.get('cell_type') == 'code']
        src = []
        for k, c in enumerate(cells):
            s = c.get('source', '')
            s = ''.join(s) if isinstance(s, list) else s
            s = '\n'.join(('' if ln.lstrip().startswith(('%', '!')) else ln) for ln in s.split('\n'))
            src.append((k, s))
        found = []
        for k, s in src:
            sub = RepoScan.__new__(RepoScan)
            sub.__dict__.update(dict(r=self.r, tables=[], indexes=[], access=[], conn=[], tx=[], tuning=[], uniques=[], rels=[], traces=[], deps=self.deps,
                                     stacks=self.stacks, file_cls=defaultdict(set), parse_errors=[], amb_tx=[], parsers=self.parsers, notes=[], py_models=self.py_models,
                                     unreadable=[]))
            fake = dict(f, path=p)
            sub.scan_python(fake, s, (lambda n, w=whole: w), notebook_cell=k)
            for lst in ('tables', 'indexes', 'access', 'conn', 'tx', 'tuning', 'uniques', 'rels'):
                for d in getattr(sub, lst):
                    d['cell'] = k
                    d['loc'] = f'{p}#{k}:{d["line"]}'
                    if not whole:
                        d['mine'] = False
                        d['nb_mixed'] = True
                    getattr(self, lst).append(d)
                    found.append(d)
            if sub.parse_errors:
                pass
        if found:
            self.file_cls[p].add('notebook-db')
            if not whole:
                self.notes.append(f'노트북 작성자가 섞임(내 커밋 {own_n}/{len(cs)}): {p}')

    # ---------------- Python(ast)
    def scan_python(self, f, t, mine, notebook_cell=None):
        p = f['path']
        try:
            with warnings.catch_warnings():
                warnings.simplefilter('ignore')
                tree = ast.parse(t.encode('utf-8', errors='replace'))
        except (SyntaxError, ValueError) as e:
            if notebook_cell is None:
                self.parsers['python-ast(error)'] += 1
                if re.search(r'models\.Model|__tablename__|cursor|execute\(|session|sqlite3|psycopg|pymysql|create_engine|MongoClient|objects\.|CREATE\s+TABLE', t, re.I):
                    self.parse_errors.append(dict(path=p, why=f'SyntaxError 줄 {getattr(e, "lineno", None)}'))
            return
        if notebook_cell is None:
            self.parsers[PARSER_PY] += 1
        gen_mig = bool(re.search(r'^# Generated by Django|auto generated by Alembic', t, re.M))
        if gen_mig and notebook_cell is None:
            self.file_cls[p].add('gen')
        is_mig = bool(re.search(r'(^|/)migrations/|alembic/versions/', p))
        imports = {}
        mods = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for a in node.names:
                    imports[(a.asname or a.name).split('.')[0]] = a.name
                    mods.add(a.name)
            elif isinstance(node, ast.ImportFrom) and node.module:
                mods.add(node.module)
                for a in node.names:
                    imports[a.asname or a.name] = node.module + '.' + a.name
        modtop = {m.split('.')[0] for m in mods}
        uses_sqla = bool(modtop & {'sqlalchemy', 'sqlmodel', 'flask_sqlalchemy'})
        uses_django = 'django' in modtop
        dbapi = {k for k in PY_CONNECT if any(m == k or m.startswith(k + '.') for m in mods)}
        if uses_sqla:
            self.stacks.add('sqlalchemy')
        if uses_django:
            self.stacks.add('django')
        if modtop & {'peewee', 'tortoise', 'pony', 'mongoengine'} - {'mongoengine'}:
            self.traces.append(dict(path=p, line=1, var='tables', tech=', '.join(sorted(modtop & {'peewee', 'tortoise', 'pony'})), why='규칙 밖 ORM'))
        consts = {}
        for node in tree.body if hasattr(tree, 'body') else []:
            if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
                s = _strval(node.value)
                if s:
                    consts[node.targets[0].id] = (node.value.lineno, s)

        def dotted(n):
            parts = []
            while True:
                if isinstance(n, ast.Attribute):
                    parts.append(n.attr); n = n.value
                elif isinstance(n, ast.Name):
                    parts.append(n.id); break
                elif isinstance(n, ast.Call):
                    parts.append('()'); n = n.func
                elif isinstance(n, ast.Subscript):
                    parts.append('[]'); n = n.value
                else:
                    parts.append('?'); break
            return '.'.join(reversed(parts))

        # ---- 클래스(테이블)
        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef):
                continue
            bases = [dotted(b) for b in node.bases]
            kws = {k.arg: k.value for k in node.keywords if k.arg}
            body_assign = {}
            meta = None
            for b in node.body:
                if isinstance(b, ast.Assign):
                    for tg in b.targets:
                        if isinstance(tg, ast.Name):
                            body_assign[tg.id] = b
                elif isinstance(b, ast.AnnAssign) and isinstance(b.target, ast.Name):
                    body_assign[b.target.id] = b
                elif isinstance(b, ast.ClassDef) and b.name == 'Meta':
                    meta = b
            stack = None
            name = node.name
            if any(x in ('models.Model',) or x.endswith('models.Model') for x in bases) or \
                    ((uses_django or re.search(r'(^|/)models(\.py$|/)', p)) and not uses_sqla and node.name in self.py_models
                     and any(x in self.py_models or x in ('AbstractUser', 'AbstractBaseUser') for x in bases)):
                stack = 'django'
            if '__tablename__' in body_assign:
                stack = 'sqlalchemy'
                v = _strval(body_assign['__tablename__'].value)
                if v:
                    name = v
            if 'table' in kws and isinstance(kws['table'], ast.Constant) and kws['table'].value is True:
                stack = 'sqlmodel'
            if stack is None and uses_sqla and any(x in ('Base', 'db.Model', 'Model', 'DeclarativeBase') or x.endswith('Base') for x in bases):
                if any(_callname(getattr(body_assign[k], 'value', None)) in ('Column', 'mapped_column', 'db.Column', 'sa.Column', 'relationship', 'db.relationship')
                       for k in body_assign):
                    stack = 'sqlalchemy'
            if stack is None and 'mongoengine' in modtop and any(x.endswith('Document') for x in bases):
                stack = 'mongoengine'
            if stack is None and ('peewee' in modtop) and any(x.endswith('Model') for x in bases):
                self.traces.append(dict(path=p, line=node.lineno, var='tables', tech='peewee', why='규칙 밖 ORM(peewee) 모델'))
                continue
            if stack is None:
                continue
            abstract = False
            if meta:
                for b in meta.body:
                    if isinstance(b, ast.Assign) and any(isinstance(tg, ast.Name) and tg.id == 'abstract' for tg in b.targets):
                        abstract = isinstance(b.value, ast.Constant) and b.value.value is True
                    if isinstance(b, ast.Assign) and any(isinstance(tg, ast.Name) and tg.id == 'db_table' for tg in b.targets):
                        v = _strval(b.value)
                        if v:
                            name = v
                    if isinstance(b, ast.Assign) and any(isinstance(tg, ast.Name) and tg.id in ('indexes',) for tg in b.targets):
                        for sub in ast.walk(b.value):
                            if isinstance(sub, ast.Call) and _callname(sub).endswith('Index'):
                                self._rec(self.indexes, f, sub.lineno, mine(sub.lineno), stack=stack, unique=False, table=norm_table(name), gen=gen_mig)
                    if isinstance(b, ast.Assign) and any(isinstance(tg, ast.Name) and tg.id in ('unique_together', 'constraints') for tg in b.targets):
                        self._rec(self.uniques, f, b.lineno, mine(b.lineno), stack=stack)
            if abstract:
                continue
            end = getattr(node, 'end_lineno', node.lineno)
            tb = self._rec(self.tables, f, node.lineno, mine(node.lineno), name=name, norm=norm_table(name), stack=stack, kind='model', rel=False,
                           gen=gen_mig, end=end, db='MongoDB' if stack == 'mongoengine' else None, body=(node.lineno, end))
            self.file_cls[p].add('model')
            for k, b in body_assign.items():
                v = getattr(b, 'value', None)
                if not isinstance(v, ast.Call):
                    continue
                cn = _callname(v)
                kwv = {kw.arg: kw.value for kw in v.keywords if kw.arg}
                args_calls = [_callname(a) for a in v.args if isinstance(a, ast.Call)]
                if cn.endswith(('ForeignKey', 'OneToOneField', 'ManyToManyField', 'relationship', 'Relationship', 'ReferenceField')) or 'ForeignKey' in args_calls or 'foreign_key' in kwv:
                    tb['rel'] = True
                    self._rec(self.rels, f, b.lineno, mine(b.lineno), stack=stack)
                if _true(kwv.get('db_index')) or _true(kwv.get('index')):
                    self._rec(self.indexes, f, b.lineno, mine(b.lineno), stack=stack, unique=_true(kwv.get('unique')), table=tb['norm'], gen=gen_mig)
                if _true(kwv.get('unique')):
                    self._rec(self.uniques, f, b.lineno, mine(b.lineno), stack=stack)
                lz = kwv.get('lazy')
                if cn.endswith('relationship') and isinstance(lz, ast.Constant) and lz.value in ('joined', 'selectin', 'subquery'):
                    self._rec(self.tuning, f, b.lineno, mine(b.lineno), stack='sqlalchemy', what=f'relationship lazy={lz.value}', doc=False, alt='lazy-eager')
            ta = body_assign.get('__table_args__')
            if ta is not None:
                for sub in ast.walk(ta.value if hasattr(ta, 'value') else ta):
                    if isinstance(sub, ast.Call):
                        cn = _callname(sub)
                        if cn.endswith('Index'):
                            self._rec(self.indexes, f, sub.lineno, mine(sub.lineno), stack=stack, unique=_true({kw.arg: kw.value for kw in sub.keywords}.get('unique')), table=tb['norm'], gen=gen_mig)
                        if cn.endswith('UniqueConstraint'):
                            self._rec(self.uniques, f, sub.lineno, mine(sub.lineno), stack=stack)

        # ---- 함수 단위(단일 commit 규칙)
        for fn in ast.walk(tree):
            if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            writes, commits, rb = [], [], False
            for sub in _walk_no_nested(fn):
                if isinstance(sub, ast.Call) and isinstance(sub.func, ast.Attribute):
                    recv = dotted(sub.func.value).lower()
                    a = sub.func.attr
                    if a in ('add', 'add_all', 'delete', 'merge', 'bulk_save_objects', 'bulk_insert_mappings', 'bulk_update_mappings') and ('session' in recv or recv in ('db', 'sess', 'self.db', 's')):
                        writes.append(sub.lineno)
                    elif a in ('execute', 'executemany') and sub.args and _sql_write(_strval(sub.args[0]) or (consts.get(sub.args[0].id, (0, ''))[1] if isinstance(sub.args[0], ast.Name) else '')):
                        writes.append(sub.lineno)
                    elif a in ('execute', 'executemany') and sub.args and isinstance(sub.args[0], ast.Call) and _callname(sub.args[0]) in ('insert', 'update', 'delete', 'sa.insert', 'sa.update', 'sa.delete'):
                        writes.append(sub.lineno)
                    elif a == 'commit' and not sub.args:
                        commits.append(sub.lineno)
                    elif a == 'rollback':
                        rb = True
            if len(writes) >= 2 and len(commits) == 1 and commits[0] > min(writes):
                raw_api = bool(dbapi) and not uses_sqla
                self._rec(self.tx, f, commits[0], mine(commits[0]), stack='dbapi' if raw_api else 'sqlalchemy', sure=not raw_api,
                          what=('여러 쓰기 + 단일 commit' + ('(DB-API, 문서 표 밖)' if raw_api else '')), writes=len(writes), ext=raw_api)

        # ---- 호출·with·데코레이터
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                for d in node.decorator_list:
                    dn = dotted(d.func if isinstance(d, ast.Call) else d)
                    if dn.endswith('transaction.atomic') or dn == 'atomic':
                        self._rec(self.tx, f, d.lineno, mine(d.lineno), stack='django', sure=True, what='@transaction.atomic')
            if isinstance(node, (ast.With, ast.AsyncWith)):
                for it in node.items:
                    ce = it.context_expr
                    dn = dotted(ce.func if isinstance(ce, ast.Call) else ce)
                    if dn.endswith('transaction.atomic') or dn == 'atomic':
                        self._rec(self.tx, f, ce.lineno, mine(ce.lineno), stack='django', sure=True, what='with transaction.atomic')
                    elif dn.endswith(('.begin', '.begin_nested')) and (uses_sqla or 'session' in dn.lower() or 'engine' in dn.lower() or 'conn' in dn.lower()):
                        body_src = ' '.join(ast.dump(b) for b in node.body)
                        if not re.search(r"'(create_all|drop_all)'", body_src):      # 스키마 만들기용 engine.begin()은 뺀다
                            self._rec(self.tx, f, ce.lineno, mine(ce.lineno), stack='sqlalchemy', sure=True, what='with session.begin()')
                    elif dn.endswith(('.transaction', 'start_transaction')) and dbapi:
                        self._rec(self.tx, f, ce.lineno, mine(ce.lineno), stack='dbapi', sure=True, what='with conn.transaction()')
            if not isinstance(node, ast.Call):
                continue
            n = node.lineno
            fn = dotted(node.func)
            attr = node.func.attr if isinstance(node.func, ast.Attribute) else (node.func.id if isinstance(node.func, ast.Name) else '')
            low = fn.lower()
            # 연결
            for mod, db in PY_CONNECT.items():
                tail = mod.split('.')[-1]
                if (fn in (mod + '.connect', mod + '.create_pool', tail + '.connect') or (fn == 'connect' and imports.get('connect', '').startswith(mod))) and (mod in dbapi):
                    self._rec(self.conn, f, n, mine(n), db=db, how='call', stack='dbapi')
                    self.file_cls[p].add('conn')
            if attr in ('create_engine', 'create_async_engine') or fn.endswith('create_engine'):
                url = _strval(node.args[0]) if node.args else None
                db = None
                if url:
                    for rx, k in SCHEME:
                        if rx.search(url):
                            db = k; break
                self._rec(self.conn, f, n, mine(n), db=db or 'SQL(미상)', how='call', stack='sqlalchemy')
                self.file_cls[p].add('conn')
            if attr in ('MongoClient', 'AsyncIOMotorClient') or fn.endswith(('pymongo.MongoClient', 'motor_asyncio.AsyncIOMotorClient')) or (attr == 'connect' and 'mongoengine' in modtop):
                self._rec(self.conn, f, n, mine(n), db='MongoDB', how='call', stack='pymongo')
                self.file_cls[p].add('conn')
            if fn in ('redis.Redis', 'redis.StrictRedis', 'redis.from_url', 'aioredis.from_url', 'redis.asyncio.Redis', 'redis.asyncio.from_url', 'Redis', 'StrictRedis', 'Redis.from_url') and (('redis' in modtop) or ('aioredis' in modtop)):
                self._rec(self.conn, f, n, mine(n), db='Redis', how='call', stack='redis-py')
            if attr == 'Cluster' and 'cassandra' in modtop:
                self._rec(self.conn, f, n, mine(n), db='Cassandra', how='call', stack='cassandra-py')
                self.file_cls[p].add('conn')
            if any(isinstance(a, ast.Constant) and isinstance(a.value, str) and a.value in ('org.apache.spark.sql.cassandra', 'mongodb', 'mongo', 'jdbc') for a in node.args) and attr == 'format':
                v0 = node.args[0].value
                self._rec(self.conn, f, n, mine(n), db={'org.apache.spark.sql.cassandra': 'Cassandra', 'mongodb': 'MongoDB', 'mongo': 'MongoDB'}.get(v0, 'SQL(미상)'), how='call', stack='spark')
                self._rec(self.access, f, n, mine(n), stack='spark', what='Spark 커넥터 읽기·쓰기', db={'org.apache.spark.sql.cassandra': 'Cassandra', 'mongodb': 'MongoDB', 'mongo': 'MongoDB'}.get(v0))
            if attr in ('Elasticsearch', 'AsyncElasticsearch') and 'elasticsearch' in modtop:
                self._rec(self.conn, f, n, mine(n), db='Elasticsearch', how='call', stack='es-py')
            if attr in ('OpenSearch',) and 'opensearchpy' in modtop:
                self._rec(self.conn, f, n, mine(n), db='OpenSearch', how='call', stack='os-py')
            if (fn.startswith('chromadb.') and attr in ('Client', 'PersistentClient', 'HttpClient', 'EphemeralClient')) or (attr in ('Chroma',) or fn.startswith('Chroma.')) and any('chroma' in m.lower() for m in mods):
                self._rec(self.conn, f, n, mine(n), db='Chroma', how='call', stack='chroma')
            if attr in ('Pinecone', 'QdrantClient', 'PineconeVectorStore', 'Qdrant', 'Milvus', 'Weaviate') and any(x in ' '.join(mods).lower() for x in ('pinecone', 'qdrant', 'milvus', 'weaviate')):
                self._rec(self.conn, f, n, mine(n), db={'Pinecone': 'Pinecone', 'PineconeVectorStore': 'Pinecone', 'QdrantClient': 'Qdrant', 'Qdrant': 'Qdrant', 'Milvus': 'Milvus', 'Weaviate': 'Weaviate'}[attr], how='call', stack='vector')
            if attr in ('PostgresHook', 'MySqlHook', 'SqliteHook', 'MongoHook', 'RedisHook', 'ElasticsearchHook', 'PostgresOperator', 'MySqlOperator', 'SQLExecuteQueryOperator', 'SqliteOperator'):
                db = {'Postgres': 'PostgreSQL', 'MySql': 'MySQL', 'Sqlite': 'SQLite', 'Mongo': 'MongoDB', 'Redis': 'Redis', 'Elasticsearch': 'Elasticsearch'}.get(re.sub(r'(Hook|Operator)$', '', attr))
                self._rec(self.conn, f, n, mine(n), db=db or 'SQL(미상)', how='call', stack='airflow')
                self._rec(self.access, f, n, mine(n), stack='airflow', what=f'Airflow {attr}', db=db)
            # 접근
            acc = None
            parts = fn.split('.')
            if '.objects.' in '.' + fn + '.' and uses_django or (len(parts) >= 2 and parts[-2] == 'objects' and parts[0] in self.py_models):
                acc = ('django', 'ORM 호출(objects)')
            elif attr in ('get_object_or_404', 'get_list_or_404') and uses_django:
                acc = ('django', 'get_object_or_404')
            elif attr in ('query', 'add', 'add_all', 'delete', 'commit', 'execute', 'scalars', 'scalar', 'get', 'merge', 'flush', 'refresh', 'exec') and isinstance(node.func, ast.Attribute) and \
                    uses_sqla and not (modtop & {'requests', 'aiohttp', 'httpx'} and dotted(node.func.value).lower() == 'session') and \
                    ('session' in dotted(node.func.value).lower() or dotted(node.func.value) in ('db', 'self.db', 'sess', 'db.session')):
                acc = ('sqlalchemy', 'Session 호출')
            elif len(parts) >= 3 and parts[-2] == 'query' and parts[0] in self.py_models and uses_sqla:
                acc = ('sqlalchemy', 'Model.query 호출')
            elif attr in ('execute', 'executemany', 'executescript') and (dbapi or uses_sqla or (node.args and SQLSHAPE.search(_strval(node.args[0]) or ''))):
                acc = ('dbapi' if dbapi and not uses_sqla else 'sqlalchemy', 'execute 호출')
            elif attr in ('read_sql', 'read_sql_query', 'read_sql_table', 'to_sql'):
                acc = ('pandas', f'pandas {attr}')
            elif attr in ('insert_one', 'insert_many', 'find_one', 'update_one', 'update_many', 'delete_one', 'delete_many', 'replace_one', 'count_documents', 'bulk_write', 'find_one_and_update') and (modtop & {'pymongo', 'motor'} or 'MongoDB' in self.deps):
                acc = ('pymongo', 'PyMongo 호출')
                self._rec(self.conn, f, n, mine(n), db='MongoDB', how='call', stack='pymongo')
            if acc:
                self._rec(self.access, f, n, mine(n), stack=acc[0], what=acc[1])
            if attr in ('create_index', 'create_indexes') and (modtop & {'pymongo', 'motor'} or 'MongoDB' in self.deps):
                self._rec(self.indexes, f, n, mine(n), stack='pymongo', unique=False, table='?', gen=False)
            # 튜닝
            if attr in ('select_related', 'prefetch_related') or (attr == 'Prefetch' and uses_django):
                self._rec(self.tuning, f, n, mine(n), stack='django', what=attr, doc=True)
            if attr in ('joinedload', 'selectinload') and uses_sqla:
                self._rec(self.tuning, f, n, mine(n), stack='sqlalchemy', what=attr, doc=True)
            if attr in ('subqueryload', 'contains_eager', 'immediateload') and uses_sqla:
                self._rec(self.tuning, f, n, mine(n), stack='sqlalchemy', what=attr, doc=False, alt='sqla-other-eager')
            # 트랜잭션
            if attr == 'atomic' and fn.endswith('transaction.atomic') and not isinstance(getattr(node, '_parent', None), ast.With):
                pass
            if attr in ('begin', 'begin_nested') and isinstance(node.func, ast.Attribute) and 'session' in dotted(node.func.value).lower() and uses_sqla:
                self._rec(self.tx, f, n, mine(n), stack='sqlalchemy', sure=True, what='session.begin()')
            if attr in ('start_transaction', 'with_transaction') and (modtop & {'pymongo', 'motor'}):
                self._rec(self.tx, f, n, mine(n), stack='pymongo', sure=True, what='Mongo 세션 트랜잭션')
            # Alembic
            if fn in ('op.create_table',) and node.args:
                nm = _strval(node.args[0])
                if nm:
                    end = getattr(node, 'end_lineno', n)
                    has_fk = any(isinstance(a, ast.Call) and _callname(a).endswith('ForeignKeyConstraint') for a in node.args) or 'ForeignKey' in ast.dump(node)
                    self._rec(self.tables, f, n, mine(n), name=nm, norm=norm_table(nm), stack='alembic', kind='migration', rel=has_fk, gen=gen_mig, end=end, db=None, body=(n, end))
                    self.file_cls[p].add('schema')
            if fn in ('op.create_index', 'batch_op.create_index'):
                tbl = _strval(node.args[1]) if len(node.args) > 1 else None
                self._rec(self.indexes, f, n, mine(n), stack='alembic', unique=_true({kw.arg: kw.value for kw in node.keywords}.get('unique')), table=norm_table(tbl or '?'), gen=gen_mig)
            if attr == 'Table' and len(node.args) >= 2 and uses_sqla:
                nm = _strval(node.args[0])
                if nm:
                    end = getattr(node, 'end_lineno', n)
                    self._rec(self.tables, f, n, mine(n), name=nm, norm=norm_table(nm), stack='sqlalchemy-core', kind='model', rel='ForeignKey' in ast.dump(node), gen=False, end=end, db=None, body=(n, end))
                    self.file_cls[p].add('model')
            # Django 설정의 DATABASES·CACHES·ATOMIC_REQUESTS 는 아래 Dict 처리에서
            # SQL 문자열(쿼리 API 인자)
            if attr in ('execute', 'executemany', 'executescript', 'text', 'raw', 'read_sql', 'read_sql_query', 'exec_driver_sql', 'run', 'query', 'sql') or any(kw.arg == 'sql' for kw in node.keywords):
                cand = list(node.args[:1]) + [kw.value for kw in node.keywords if kw.arg in ('sql', 'query')]
                for a in cand:
                    s = _strval(a)
                    if s is None and isinstance(a, ast.Name) and a.id in consts:
                        ln0, s = consts[a.id]
                        self._sql_from_py(f, ln0, s, mine)
                        continue
                    if s and SQLSHAPE.search(s):
                        self._sql_from_py(f, a.lineno, s, mine)
        # Django settings (if DEBUG: 분기 안의 DATABASES는 개발용으로 본다)
        devdict = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.If):
                try:
                    test = ast.unparse(node.test)
                except Exception:
                    test = ''
                if re.search(r'\bDEBUG\b|\b(dev|local|development)\b', test, re.I):
                    neg = bool(re.match(r'\s*not\b', test)) or '== False' in test or 'prod' in test.lower()
                    for branch in ((node.orelse,) if neg else (node.body,)):
                        for b in branch:
                            for sub in ast.walk(b):
                                if isinstance(sub, ast.Dict):
                                    devdict.add(id(sub))
        devfile = bool(DEVCFG.search(p))
        for node in ast.walk(tree):
            if isinstance(node, ast.Dict):
                for k, v in zip(node.keys, node.values):
                    ks = _strval(k) if k is not None else None
                    if ks == 'ENGINE':
                        vs = _strval(v) or ''
                        mm = re.search(r'django\.db\.backends\.(\w+)', vs) or re.search(r'^(djongo|mssql|sql_server\.pyodbc)$', vs)
                        if mm and mm.group(1) in DJANGO_ENGINE:
                            self._rec(self.conn, f, v.lineno, mine(v.lineno), db=DJANGO_ENGINE[mm.group(1)], how='config', stack='django-settings',
                                      test=bool(TESTCFG.search(p)), dev=devfile or id(node) in devdict)
                            self.file_cls[p].add('conn')
                    if ks == 'BACKEND':
                        vs = _strval(v) or ''
                        if re.search(r'redis', vs, re.I):
                            self._rec(self.conn, f, v.lineno, mine(v.lineno), db='Redis', how='config', stack='django-cache')
                    if ks == 'ATOMIC_REQUESTS' and _true(v):
                        self._rec(self.tx, f, v.lineno, mine(v.lineno), stack='django', sure=True, what='ATOMIC_REQUESTS=True(설정)')
            if isinstance(node, ast.Assign):
                for tg in node.targets:
                    if isinstance(tg, ast.Name) and re.match(r'(CELERY_)?BROKER_URL|CELERY_RESULT_BACKEND|REDIS_URL|CACHE_REDIS_URL', tg.id):
                        s = _strval(node.value) or ''
                        if s.startswith(('redis://', 'rediss://')):
                            self._rec(self.conn, f, node.lineno, mine(node.lineno), db='Redis', how='config', stack='py-settings')
            if isinstance(node, ast.Call) and _callname(node) in ('dj_database_url.config', 'dj_database_url.parse', 'env.db', 'env.db_url'):
                self._rec(self.conn, f, node.lineno, mine(node.lineno), db='SQL(미상)', how='config', stack='django-settings')

    def _sql_from_py(self, f, line1, s, mine):
        """Python 문자열(줄 line1에서 시작) 안 SQL"""
        if not SQLSHAPE.search(s) and not re.search(r'\bCREATE\s+TABLE\b', s, re.I):
            return
        self.sql_in_string(f, line1 - 1, s, mine, stack='sql-in-code')


def _strval(n):
    if isinstance(n, ast.Constant) and isinstance(n.value, str):
        return n.value
    if isinstance(n, ast.JoinedStr):
        return ''.join(v.value if isinstance(v, ast.Constant) and isinstance(v.value, str) else '{x}' for v in n.values)
    if isinstance(n, ast.BinOp) and isinstance(n.op, ast.Add):
        a, b = _strval(n.left), _strval(n.right)
        if a is not None and b is not None:
            return a + b
    return None


def _true(n):
    return isinstance(n, ast.Constant) and n.value is True


def _callname(n):
    if not isinstance(n, ast.Call):
        return ''
    fn = n.func
    parts = []
    while isinstance(fn, ast.Attribute):
        parts.append(fn.attr); fn = fn.value
    if isinstance(fn, ast.Name):
        parts.append(fn.id)
    return '.'.join(reversed(parts))


def _sql_write(s):
    return bool(s and re.match(r'\s*(INSERT|UPDATE|DELETE|REPLACE|MERGE|UPSERT)\b', s, re.I))


def _walk_no_nested(fn):
    stack = list(fn.body)
    while stack:
        n = stack.pop()
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)):
            continue
        yield n
        stack.extend(ast.iter_child_nodes(n))
