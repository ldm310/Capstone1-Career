"""추출·판정 결과를 SQLite에 저장한다.

실행마다 새로 쌓아서 재평가 때 이전 결과와 비교할 수 있다. 표·칸 이름은 db/schema.sql(PostgreSQL, eval 스키마)과 같다.
그 DDL은 feature/job-skill의 job 스키마와 같은 DB·같은 규칙으로 만들었다. 옮길 때는 기술 이름으로 job.tech의 ID만 채우면 된다(최종 DB는 미정).
원래 이메일은 저장하지 않고(가린 값만), 다른 사람의 commit은 개수만 남긴다. 분석하는 계정은 동의 기록(account)이 있어야 한다.
"""
import json
import sqlite3
import time
from pathlib import Path

VERSION = 3  # PRAGMA user_version. 1 이하는 job-skill에 맞추기 전 구조, 2는 정답 세트 키에 commit이 없던 구조

TABLES = """
CREATE TABLE IF NOT EXISTS account (            -- 분석하는 GitHub 계정과 동의 기록
  id INTEGER PRIMARY KEY,
  login TEXT NOT NULL UNIQUE COLLATE NOCASE,
  github_id INTEGER,
  relation TEXT NOT NULL CHECK (relation IN ('본인', '지인')),
  consent_note TEXT NOT NULL,                   -- 동의 받은 방법·범위
  consented_at TEXT NOT NULL,                   -- 동의 날짜
  revoked_at TEXT,                              -- 동의 철회 날짜(철회되면 새로 수집하지 않음)
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS collect_run (        -- 수집 실행 1회
  id INTEGER PRIMARY KEY,
  account_id INTEGER REFERENCES account(id),
  login TEXT NOT NULL,
  github_id INTEGER,
  started_at TEXT NOT NULL,
  finished_at TEXT NOT NULL,
  token_used INTEGER NOT NULL,
  api_calls INTEGER NOT NULL,
  stopped TEXT,                                 -- 중단 이유(한도 소진 등)
  identity_emails TEXT NOT NULL                 -- 가린 이메일 JSON 목록
);
CREATE TABLE IF NOT EXISTS repo (               -- 공개 레포 1개 + 활용 기록 개수
  id INTEGER PRIMARY KEY,
  run_id INTEGER NOT NULL REFERENCES collect_run(id),
  full_name TEXT NOT NULL,
  fork INTEGER NOT NULL,
  default_branch TEXT,
  size_kb INTEGER,
  default_sha TEXT,
  develop_sha TEXT,
  develop_contains_main INTEGER,                -- 1 포함 · 0 갈라짐 · NULL 같은 commit이거나 develop 없음
  reachable_commits INTEGER,
  pulls INTEGER, pulls_merged INTEGER, pulls_own INTEGER,
  issues INTEGER, deployments INTEGER, actions_all INTEGER,
  error TEXT,
  source TEXT,                                  -- owner · member · search(commit·PR 검색)
  UNIQUE (run_id, full_name)
);
CREATE TABLE IF NOT EXISTS own_commit (         -- 본인(또는 이름만 일치) commit
  repo_id INTEGER NOT NULL REFERENCES repo(id),
  sha TEXT NOT NULL,
  kind TEXT NOT NULL CHECK (kind IN ('api', 'email', 'name_only')),
  authored_at TEXT,
  added INTEGER, deleted INTEGER, files INTEGER, is_merge INTEGER,
  PRIMARY KEY (repo_id, sha)
);
CREATE TABLE IF NOT EXISTS eval_commit (        -- 평가 commit: 본인 줄 요약 + 같은 commit의 실행 기록
  repo_id INTEGER NOT NULL REFERENCES repo(id),
  sha TEXT NOT NULL,
  branches TEXT NOT NULL,
  own_lines INTEGER, name_only_lines INTEGER, other_lines INTEGER, files INTEGER,
  actions INTEGER, check_runs INTEGER, statuses INTEGER, conclusions TEXT,
  run_details TEXT,                             -- 같은 commit의 workflow·check run·status 이름과 결과(JSON)
  PRIMARY KEY (repo_id, sha)
);
CREATE TABLE IF NOT EXISTS evidence_line (      -- 본인 줄 증거 단위 {레포, commit, 파일, 줄 범위}
  repo_id INTEGER NOT NULL REFERENCES repo(id),
  sha TEXT NOT NULL,
  path TEXT NOT NULL,
  line_start INTEGER NOT NULL,
  line_end INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS external_pr_repo (   -- 본인 소유가 아닌 레포에 낸 PR
  run_id INTEGER NOT NULL REFERENCES collect_run(id),
  full_name TEXT NOT NULL,
  PRIMARY KEY (run_id, full_name)
);
CREATE TABLE IF NOT EXISTS assessment (         -- 판정 실행: 기술 하나 × 레포 하나 × 평가 commit 하나(job.extraction_run과 같은 칸)
  id INTEGER PRIMARY KEY,
  run_id INTEGER NOT NULL REFERENCES collect_run(id),
  repo TEXT NOT NULL, sha TEXT NOT NULL,
  tech TEXT NOT NULL,                           -- 사전 표준 이름(사전에 없으면 찾은 이름 그대로)
  created_at TEXT NOT NULL,
  model TEXT, effort TEXT,
  status TEXT NOT NULL,                         -- ok · refusal · max_tokens · bad_json · budget · no_material
  mode TEXT,                                    -- llm(LLM 해석 + 규칙) · rule_only(규칙만으로 확정) · shadow(그림자 실행, LV 반영 안 함)
  is_current INTEGER NOT NULL DEFAULT 0,        -- 추출 실행 × 기술 × 레포마다 현재 판정 하나(그림자는 늘 0)
  shadow_of INTEGER REFERENCES assessment(id),  -- 그림자 실행이 비교하는 현재 판정
  level INTEGER,                                -- NULL = 미확인(LV0이 아님)
  blocked_at TEXT,                              -- 막힌 LV 또는 personal_scope · risk
  retries INTEGER,
  input_tokens INTEGER, output_tokens INTEGER, cache_read_tokens INTEGER, cache_write_tokens INTEGER,
  cost_usd REAL,                                -- skill 표 단가로 계산한 추정치
  shown_files TEXT, omitted_files TEXT,
  reused_from INTEGER,                          -- LLM 답을 다시 쓴 판정 id(비용 0)
  in_dictionary INTEGER,                        -- 팀 사전(capabilities.json)에 있는 기술인지. 0이면 공고와 비교 불가
  prompt_version TEXT, rule_version TEXT,       -- 사람이 붙인 버전 이름
  rule_hash TEXT,                               -- 규칙 지문(engine.rule_hash). 다르면 옛 규칙으로 나온 판정
  dict_version TEXT,                            -- 사전 버전(capabilities.json의 version)
  input_hash TEXT,                              -- LLM 입력 해시. 같으면 저장된 답을 다시 쓴다
  review_reasons TEXT NOT NULL DEFAULT '[]',    -- 사람이 확인할 사유 JSON 목록(비면 확인 불필요)
  review_result TEXT CHECK (review_result IN ('문제없음', '고침')),
  reviewed_at TEXT,
  llm_output_raw TEXT                           -- 재검토까지 합친 LLM 답(JSON). 규칙이 바뀌면 여기에 새 규칙만 다시 적용한다
);
CREATE TABLE IF NOT EXISTS finding (            -- 조건별 판정(31개 + personal_scope)
  assessment_id INTEGER NOT NULL REFERENCES assessment(id),
  cond_id TEXT NOT NULL, kind TEXT,
  llm_status TEXT,                              -- NULL = LLM을 부르지 않음(rule_only)
  final_status TEXT, reason TEXT, rule_note TEXT, evidence TEXT,
  PRIMARY KEY (assessment_id, cond_id)
);
CREATE TABLE IF NOT EXISTS risk_item (          -- 위험 8개 적용 여부
  assessment_id INTEGER NOT NULL REFERENCES assessment(id),
  risk_id TEXT NOT NULL,
  llm_status TEXT, final_status TEXT, reason TEXT, rule_note TEXT, evidence TEXT,
  PRIMARY KEY (assessment_id, risk_id)
);
CREATE TABLE IF NOT EXISTS stat (               -- 내 STAT(7단계)
  id INTEGER PRIMARY KEY,
  run_id INTEGER NOT NULL REFERENCES collect_run(id),
  created_at TEXT NOT NULL,
  levels TEXT NOT NULL,                         -- {기술: LV 또는 null}
  reach TEXT NOT NULL,                          -- 단계별 도달률
  blocked_at INTEGER, type TEXT, note TEXT,
  threshold REAL,                               -- 막힌 단계 기준값
  rule_version TEXT, rule_hash TEXT, dict_version TEXT
);
CREATE TABLE IF NOT EXISTS stat_tech (          -- STAT의 기술별 LV(공고 요건과 기술 이름으로 잇는다)
  stat_id INTEGER NOT NULL REFERENCES stat(id),
  tech TEXT NOT NULL,
  in_dictionary INTEGER,
  level INTEGER,                                -- NULL = 미확인
  assessment_ids TEXT,                          -- 이 LV를 낸 현재 판정 id JSON 목록. []면 판정 못 해 미확인으로 셈, NULL이면 v1 기록이라 모름
  PRIMARY KEY (stat_id, tech)
);
CREATE TABLE IF NOT EXISTS gold_label (         -- 정답 세트: 사람이 시스템과 별개로 적은 기대 LV·조건 판정
  id INTEGER PRIMARY KEY,
  account_id INTEGER NOT NULL REFERENCES account(id),
  repo TEXT NOT NULL,
  tech TEXT NOT NULL,
  sha TEXT NOT NULL,                            -- 정답을 매길 때 본 commit(빈 표에 적힌 평가 commit)
  cond_id TEXT NOT NULL,                        -- LV(기술 LV 정답) · L0-01~L5-07 · personal_scope
  expected TEXT NOT NULL,                       -- LV: 미확인 · LV0~LV5, 조건: 충족 · 미충족 · 근거 부족 · 충돌
  case_tag TEXT NOT NULL DEFAULT '',            -- 경계 사례 표시(예: CI 없이 결과 파일만)
  note TEXT NOT NULL DEFAULT '',
  labeler TEXT NOT NULL,
  labeled_at TEXT NOT NULL,                     -- 처음 넣은 시각(같은 값을 다시 넣으면 그대로 둔다)
  UNIQUE (account_id, repo, tech, sha, cond_id, labeler)
);
"""
INDEXES = """
CREATE INDEX IF NOT EXISTS evidence_line_repo ON evidence_line (repo_id, sha);
CREATE UNIQUE INDEX IF NOT EXISTS assessment_one_current ON assessment (run_id, tech, repo) WHERE is_current = 1;
CREATE INDEX IF NOT EXISTS assessment_input ON assessment (input_hash);
CREATE INDEX IF NOT EXISTS assessment_review_queue ON assessment (created_at) WHERE review_reasons <> '[]' AND review_result IS NULL;
CREATE UNIQUE INDEX IF NOT EXISTS account_github_id ON account (github_id) WHERE github_id IS NOT NULL;
"""

MIGRATIONS = [('repo', 'source', 'TEXT'),               # 이전 DB에 새 칸을 더한다(값은 upgrade가 채운다)
              ('assessment', 'reused_from', 'INTEGER'),
              ('assessment', 'in_dictionary', 'INTEGER'),
              ('eval_commit', 'run_details', 'TEXT'),
              ('collect_run', 'account_id', 'INTEGER REFERENCES account(id)'),
              ('assessment', 'mode', 'TEXT'),
              ('assessment', 'is_current', 'INTEGER NOT NULL DEFAULT 0'),
              ('assessment', 'shadow_of', 'INTEGER REFERENCES assessment(id)'),
              ('assessment', 'prompt_version', 'TEXT'),
              ('assessment', 'rule_version', 'TEXT'),
              ('assessment', 'rule_hash', 'TEXT'),
              ('assessment', 'dict_version', 'TEXT'),
              ('assessment', 'input_hash', 'TEXT'),
              ('assessment', 'review_reasons', "TEXT NOT NULL DEFAULT '[]'"),
              ('assessment', 'review_result', "TEXT CHECK (review_result IN ('문제없음', '고침'))"),
              ('assessment', 'reviewed_at', 'TEXT'),
              ('assessment', 'llm_output_raw', 'TEXT'),
              ('stat', 'threshold', 'REAL'),
              ('stat', 'rule_version', 'TEXT'),
              ('stat', 'rule_hash', 'TEXT'),
              ('stat', 'dict_version', 'TEXT')]


def now(): return time.strftime('%Y-%m-%dT%H:%M:%S%z')


def connect(path):
    """DB를 열고 지금 구조(VERSION)로 맞춘다. 옛 구조면 먼저 백업하고, 표·칸을 더한 뒤 기존 기록으로 값을 채운다(지우는 것은 없다)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path)
    db.execute('PRAGMA foreign_keys = ON')
    version = db.execute('PRAGMA user_version').fetchone()[0]
    if version >= VERSION: return db
    old = db.execute("SELECT COUNT(*) FROM sqlite_master WHERE type = 'table'").fetchone()[0] > 0
    if old: backup(db, path, version)
    db.executescript(TABLES)
    for table, column, kind in MIGRATIONS:
        if column not in {row[1] for row in db.execute(f'PRAGMA table_info({table})')}:
            db.execute(f'ALTER TABLE {table} ADD COLUMN {column} {kind}')
    with db:
        if old and version < 2: upgrade(db)
        if old and version < 3: upgrade_v3(db)
    db.executescript(INDEXES)
    db.execute(f'PRAGMA user_version = {VERSION}')
    db.commit()
    return db


def backup(db, path, version):
    """구조를 바꾸기 전에 DB 전체를 out/backup/에 복사한다."""
    dest = path.parent / 'backup' / f"{path.stem}-v{version}-{time.strftime('%Y%m%d-%H%M%S')}{path.suffix}"
    dest.parent.mkdir(parents=True, exist_ok=True)
    copy = sqlite3.connect(dest)
    db.backup(copy)
    copy.close()
    return dest


def output_of(db, aid):
    """판정의 LLM 답(재검토까지 합친 것). llm_output_raw가 없으면(v1 기록) finding·risk_item의 LLM 상태·이유·인용으로 만든다.
    LLM을 부르지 않은 판정(rule_only)이면 None."""
    raw = db.execute('SELECT llm_output_raw FROM assessment WHERE id = ?', (aid,)).fetchone()
    if raw and raw[0]: return json.loads(raw[0])
    from engine import HOLD  # store는 판정 엔진 없이도 쓰이므로 여기서만 불러온다
    item = lambda st, reason, ev, note: dict(status=st, reason=reason, evidence=json.loads(ev or '[]'),
                                             **({'missing': True} if note == '응답 누락' else {'clash': True} if note == '응답 충돌' else {}))
    f = {k: item(st, r, e, n) for k, st, r, e, n in db.execute(
        'SELECT cond_id, llm_status, reason, evidence, rule_note FROM finding WHERE assessment_id = ?', (aid,))}
    rk = {k: item(st, r, e, n) for k, st, r, e, n in db.execute(
        'SELECT risk_id, llm_status, reason, evidence, rule_note FROM risk_item WHERE assessment_id = ?', (aid,))}
    if 'personal_scope' not in f or any(v['status'] is None for v in f.values()): return None
    held = sorted(k for k, n in db.execute('SELECT cond_id, rule_note FROM finding WHERE assessment_id = ? UNION ALL '
                                           'SELECT risk_id, rule_note FROM risk_item WHERE assessment_id = ?', (aid, aid)) if n and HOLD in n)
    return dict(answer=dict(findings={k: v for k, v in f.items() if k != 'personal_scope'}, contribution=f['personal_scope'], risks=rk),
                retried=held, unresolved=held)


def upgrade(db):
    """v1 → v2 값 채우기. 동의 기록·현재 판정 표시·LLM 답·STAT 기술별 행을 기존 기록에서 만든다."""
    # v1에는 동의 기록이 없었다. 수집한 계정을 본인 계정으로 옮기고, 아니면 고치라고 남긴다.
    for login, github_id, first in db.execute('SELECT login, MAX(github_id), MIN(started_at) FROM collect_run GROUP BY lower(login)').fetchall():
        db.execute('INSERT OR IGNORE INTO account (login, github_id, relation, consent_note, consented_at, created_at) VALUES (?, ?, ?, ?, ?, ?)',
                   (login, github_id, '본인', 'v1에서 옮김: 동의 기록을 만들기 전에 수집한 계정. 본인 계정이 아니면 고칠 것', first[:10], now()))
    db.execute('UPDATE collect_run SET account_id = (SELECT id FROM account WHERE lower(account.login) = lower(collect_run.login)) '
               'WHERE account_id IS NULL')
    # v1 판정은 모두 LLM 해석을 거쳤다. 추출 실행 × 기술 × 레포마다 가장 최근의 성공 판정을 현재 판정으로 둔다.
    db.execute("UPDATE assessment SET mode = 'llm' WHERE mode IS NULL")
    db.execute("UPDATE assessment SET is_current = 1 WHERE id IN (SELECT MAX(id) FROM assessment WHERE status = 'ok' GROUP BY run_id, tech, repo)")
    for (aid,) in db.execute("SELECT id FROM assessment WHERE llm_output_raw IS NULL AND status = 'ok'").fetchall():
        out = output_of(db, aid)
        if out: db.execute('UPDATE assessment SET llm_output_raw = ? WHERE id = ?', (json.dumps(out, ensure_ascii=False), aid))
    # v1 STAT의 기준값은 engine.stat 기본값(0.5)이었다. 어느 판정을 썼는지는 v1에 남아 있지 않아 assessment_ids는 NULL로 둔다.
    db.execute('UPDATE stat SET threshold = 0.5 WHERE threshold IS NULL')
    for sid, run_id, levels in db.execute('SELECT id, run_id, levels FROM stat').fetchall():
        for tech, level in json.loads(levels).items():
            known = db.execute('SELECT in_dictionary FROM assessment WHERE run_id = ? AND tech = ? AND in_dictionary IS NOT NULL '
                               'ORDER BY id DESC LIMIT 1', (run_id, tech)).fetchone()
            db.execute('INSERT OR IGNORE INTO stat_tech (stat_id, tech, in_dictionary, level, assessment_ids) VALUES (?, ?, ?, ?, NULL)',
                       (sid, tech, known[0] if known else None, level))


def upgrade_v3(db):
    """v2 → v3: 정답 세트의 고유 키에 commit(sha)을 넣는다. 표를 새로 만들고 행을 그대로 옮긴다(sha가 비어 있던 행은 빈 문자열)."""
    if 'UNIQUE (account_id, repo, tech, sha, cond_id, labeler)' in (db.execute("SELECT sql FROM sqlite_master WHERE name = 'gold_label'").fetchone() or [''])[0]:
        return
    db.execute('ALTER TABLE gold_label RENAME TO gold_label_v2')
    db.execute(TABLES[TABLES.index('CREATE TABLE IF NOT EXISTS gold_label'):].split(');', 1)[0] + ');')
    db.execute('INSERT INTO gold_label (id, account_id, repo, tech, sha, cond_id, expected, case_tag, note, labeler, labeled_at) '
               "SELECT id, account_id, repo, tech, COALESCE(sha, ''), cond_id, expected, case_tag, note, labeler, labeled_at FROM gold_label_v2")
    db.execute('DROP TABLE gold_label_v2')


def require_consent(path, login, readonly=False):
    """분석 전에 동의 기록을 확인한다: 기록이 없거나 철회됐으면 멈춘다. 철회된 계정의 기존 기록을 지울지는 미정이다."""
    db = sqlite3.connect(f'file:{path}?mode=ro', uri=True) if readonly else connect(path)
    row = db.execute('SELECT login, relation, consent_note, revoked_at FROM account WHERE login = ?', (login,)).fetchone()
    db.close()
    if not row: raise SystemExit(f'{login}의 동의 기록이 없습니다. check_github.py --consent로 동의를 기록한 뒤 수집하세요')
    if row[3]: raise SystemExit(f'{login}은 {row[3]}에 동의를 철회했습니다. 분석하지 않습니다')
    if row[2].startswith('v1에서 옮김'): print(f'  ! {login}의 동의 기록은 v1에서 옮긴 것입니다(본인 계정이 아니면 account 표를 고칠 것)')
    return row


def flag(value): return None if value is None else int(value)


def get_account(path, login):
    db = connect(path)
    keys = ('id', 'login', 'github_id', 'relation', 'consent_note', 'consented_at', 'revoked_at')
    row = db.execute(f"SELECT {', '.join(keys)} FROM account WHERE login = ?", (login,)).fetchone()
    db.close()
    return dict(zip(keys, row)) if row else None


def add_account(path, login, relation, consent_note, consented_at):
    db = connect(path)
    with db:
        aid = db.execute('INSERT INTO account (login, relation, consent_note, consented_at, created_at) VALUES (?, ?, ?, ?, ?)',
                         (login, relation, consent_note, consented_at, now())).lastrowid
    db.close()
    return aid


def save(path, res, account_id):
    db = connect(path)
    with db:
        db.execute('UPDATE account SET github_id = COALESCE(github_id, ?) WHERE id = ?', (res['github_id'], account_id))
        run_id = db.execute(
            'INSERT INTO collect_run (account_id, login, github_id, started_at, finished_at, token_used, api_calls, stopped, identity_emails) '
            'VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)',
            (account_id, res['login'], res['github_id'], res['started_at'], res['finished_at'], int(res['token']), res['api_calls'],
             res['stopped'], json.dumps(res['identity']['emails']))).lastrowid
        db.executemany('INSERT INTO external_pr_repo VALUES (?, ?)', [(run_id, f) for f in res['external_pr_repos']])
        ids = {}
        for r in res['repos']:
            heads, a = r.get('heads', {}), r.get('activity', {})
            error = r.get('error') or (None if a else '처리 전에 중단됨')
            ids[r['full']] = rid = db.execute(
                'INSERT INTO repo (run_id, full_name, fork, default_branch, size_kb, default_sha, develop_sha, develop_contains_main, '
                'reachable_commits, pulls, pulls_merged, pulls_own, issues, deployments, actions_all, error, source) '
                'VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
                (run_id, r['full'], int(r['fork']), r['default_branch'], r['size_kb'], heads.get(r['default_branch']), heads.get('develop'),
                 flag(r.get('develop_contains_main')), r.get('reachable'), a.get('pulls'), a.get('pulls_merged'), a.get('pulls_own'),
                 a.get('issues'), a.get('deployments'), a.get('actions_all'), error, r.get('source'))).lastrowid
            db.executemany('INSERT INTO own_commit VALUES (?, ?, ?, ?, ?, ?, ?, ?)',
                           [(rid, c['sha'], c['kind'], c['date'], c['added'], c['deleted'], c['files'], flag(c['merge']))
                            for c in r.get('commits', [])])
            db.executemany('INSERT INTO eval_commit (repo_id, sha, branches, own_lines, name_only_lines, other_lines, files, actions, check_runs, '
                           'statuses, conclusions, run_details) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
                           [(rid, sha, ','.join(e['branches']), e['own'], e['name_only'], e['other'], e['files'], e.get('actions'),
                             e.get('check_runs'), e.get('statuses'), json.dumps(e.get('conclusions', [])),
                             json.dumps(e['details'], ensure_ascii=False) if e.get('details') else None) for sha, e in r.get('evals', {}).items()])
        db.executemany('INSERT INTO evidence_line VALUES (?, ?, ?, ?, ?)',
                       [(ids[u['repo']], u['sha'], u['path'], s, e) for u in res['evidence'] for s, e in u['lines']])
    db.close()
    return run_id


def save_assessment(path, run_id, out, created_at, model, effort, versions=None, shadow_of=None, review=()):
    """판정 1건 저장. 성공한 현재 판정(llm·rule_only)이면 같은 추출 실행 × 기술 × 레포의 이전 현재 판정을 내린다. 그림자는 현재 판정이 되지 않는다."""
    db = connect(path)
    t, u, v = out['target'], out['usage'], versions or {}
    current = out['status'] == 'ok' and out.get('mode') != 'shadow'
    if out.get('mode') == 'rule_only': model = effort = None  # LLM을 부르지 않은 판정에는 모델을 남기지 않는다
    total = lambda k: sum((x.get(k) or 0) for x in u)
    with db:
        if current:
            db.execute('UPDATE assessment SET is_current = 0 WHERE run_id = ? AND tech = ? AND repo = ? AND is_current = 1', (run_id, t['tech'], t['repo']))
        aid = db.execute(
            'INSERT INTO assessment (run_id, repo, sha, tech, created_at, model, effort, status, mode, is_current, shadow_of, level, blocked_at, retries, '
            'input_tokens, output_tokens, cache_read_tokens, cache_write_tokens, cost_usd, shown_files, omitted_files, reused_from, in_dictionary, '
            'prompt_version, rule_version, rule_hash, dict_version, input_hash, review_reasons, llm_output_raw) '
            'VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
            (run_id, t['repo'], t['sha'], t['tech'], created_at, ','.join(sorted({x['model'] for x in u if x.get('model')})) or model, effort,
             out['status'], out.get('mode'), int(current), shadow_of, out.get('level'), None if out.get('blocked') is None else str(out['blocked']),
             out['retries'], total('input_tokens'), total('output_tokens'), total('cache_read_input_tokens'), total('cache_creation_input_tokens'),
             round(sum(x.get('cost_usd') or 0 for x in u), 4), json.dumps(out['shown'], ensure_ascii=False),
             json.dumps(out['omitted'], ensure_ascii=False), out.get('reused_from'), flag(t.get('in_dictionary')),
             v.get('prompt_version'), v.get('rule_version'), v.get('rule_hash'), v.get('dict_version'), out.get('input_hash'),
             json.dumps(list(review), ensure_ascii=False),
             json.dumps(out['llm_output'], ensure_ascii=False) if out.get('llm_output') else None)).lastrowid
        db.executemany('INSERT INTO finding VALUES (?, ?, ?, ?, ?, ?, ?, ?)',
                       [(aid, k, x.get('kind'), x['llm_status'], x['status'], x['reason'], x['note'], json.dumps(x['evidence'], ensure_ascii=False))
                        for k, x in out.get('final', {}).items()])
        db.executemany('INSERT INTO risk_item VALUES (?, ?, ?, ?, ?, ?, ?)',
                       [(aid, k, x['llm_status'], x['status'], x['reason'], x['note'], json.dumps(x['evidence'], ensure_ascii=False))
                        for k, x in out.get('risks', {}).items()])
    db.close()
    return aid


def refresh_runs(path, login, fetch):
    """최신 추출 실행에서 실행 기록이 있는 평가 commit만 다시 조회해 개수·내용을 고친다(전체 재추출 없이). 고친 commit 수를 돌려준다."""
    db = connect(path)
    run = db.execute('SELECT id FROM collect_run WHERE lower(login) = lower(?) AND stopped IS NULL ORDER BY id DESC LIMIT 1', (login,)).fetchone()
    rows = db.execute('SELECT e.repo_id, e.sha, r.full_name FROM eval_commit e JOIN repo r ON r.id = e.repo_id WHERE r.run_id = ? '
                      'AND COALESCE(e.actions, 0) + COALESCE(e.check_runs, 0) + COALESCE(e.statuses, 0) > 0', (run[0],)).fetchall() if run else []
    with db:
        for repo_id, sha, full in rows:
            x = fetch(full, sha)
            db.execute('UPDATE eval_commit SET actions = ?, check_runs = ?, statuses = ?, conclusions = ?, run_details = ? WHERE repo_id = ? AND sha = ?',
                       (x['actions'], x['check_runs'], x['statuses'], json.dumps(x['conclusions']), json.dumps(x['details'], ensure_ascii=False), repo_id, sha))
    db.close()
    return len(rows)


def find_cached(path, input_hash, target, model, effort, account_id, legacy=False, readonly=False):
    """같은 계정이 같은 입력으로 받은 LLM 답(재검토까지 합친 것). legacy면 입력 해시를 남기기 전(v1)의 판정도 레포·commit·기술·모델로 찾는다.
    readonly면 DB를 읽기 전용으로 열고 구조를 바꾸지 않는다(옛 구조면 찾지 않음). {id, output, shown, legacy} 또는 None."""
    if account_id is None: return None
    db = sqlite3.connect(f'file:{path}?mode=ro', uri=True) if readonly else connect(path)
    if readonly and db.execute('PRAGMA user_version').fetchone()[0] < VERSION: db.close(); return None
    q = ("SELECT id, llm_output_raw, shown_files FROM assessment WHERE {} AND run_id IN (SELECT id FROM collect_run WHERE account_id = ?) "
         "AND llm_output_raw IS NOT NULL AND status = 'ok' ORDER BY id DESC LIMIT 1")
    row, old = db.execute(q.format('input_hash = ?'), (input_hash, account_id)).fetchone(), False
    if row is None and legacy:
        row, old = db.execute(q.format('input_hash IS NULL AND repo = ? AND sha = ? AND tech = ? AND model = ? AND effort = ?'),
                              (target['repo'], target['sha'], target['tech'], model, effort, account_id)).fetchone(), True
    db.close()
    return dict(id=row[0], output=json.loads(row[1]), shown=row[2], legacy=old) if row else None


def save_stat(path, run_id, created_at, levels, st, note, techs=(), versions=None):
    """techs: [{tech, in_dictionary, level, assessment_ids}] — 공고 요건과 이을 기술별 행."""
    db = connect(path)
    v = versions or {}
    with db:
        sid = db.execute('INSERT INTO stat (run_id, created_at, levels, reach, blocked_at, type, note, threshold, rule_version, rule_hash, dict_version) '
                         'VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
                         (run_id, created_at, json.dumps(levels, ensure_ascii=False), json.dumps(st['reach']), st['blocked'], st['type'], note,
                          st.get('threshold'), v.get('rule_version'), v.get('rule_hash'), v.get('dict_version'))).lastrowid
        db.executemany('INSERT INTO stat_tech (stat_id, tech, in_dictionary, level, assessment_ids) VALUES (?, ?, ?, ?, ?)',
                       [(sid, x['tech'], flag(x.get('in_dictionary')), x['level'], json.dumps(x['assessment_ids'])) for x in techs])
    db.close()
    return sid


def counts(path, run_id):
    """저장 확인용: 실행 1회의 표별 행 수와 증거 줄 합계."""
    db = connect(path)
    joined = 'JOIN repo ON repo.id = repo_id WHERE run_id = ?'
    q = lambda sql: db.execute(sql, (run_id,)).fetchone()[0]
    out = dict(repo=q('SELECT COUNT(*) FROM repo WHERE run_id = ?'),
               own_commit=q(f'SELECT COUNT(*) FROM own_commit {joined}'),
               eval_commit=q(f'SELECT COUNT(*) FROM eval_commit {joined}'),
               evidence_line=q(f'SELECT COUNT(*) FROM evidence_line {joined}'),
               evidence_lines_total=q(f'SELECT COALESCE(SUM(line_end - line_start + 1), 0) FROM evidence_line {joined}'),
               own_lines_total=q(f'SELECT COALESCE(SUM(own_lines), 0) FROM eval_commit {joined}'))
    db.close()
    return out
