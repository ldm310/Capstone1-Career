"""저장·구조 시험(오프라인): v1 DB 옮기기, 현재 판정 표시, 저장된 LLM 답 찾기, SQLite와 PostgreSQL DDL(db/schema.sql)의 표·칸 일치, 정답 비교.

실행: .venv/bin/python -m unittest test_store -v
"""
import csv
import json
import re
import sqlite3
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace as NS

import engine as E
import gold
import rubric_source as R
import store
from test_engine import TARGET, FakeLLM, answer, run

HERE = Path(__file__).resolve().parent
V1 = """
CREATE TABLE collect_run (id INTEGER PRIMARY KEY, login TEXT NOT NULL, github_id INTEGER, started_at TEXT NOT NULL, finished_at TEXT NOT NULL,
  token_used INTEGER NOT NULL, api_calls INTEGER NOT NULL, stopped TEXT, identity_emails TEXT NOT NULL);
CREATE TABLE repo (id INTEGER PRIMARY KEY, run_id INTEGER NOT NULL, full_name TEXT NOT NULL, fork INTEGER NOT NULL, default_branch TEXT,
  size_kb INTEGER, default_sha TEXT, develop_sha TEXT, develop_contains_main INTEGER, reachable_commits INTEGER, pulls INTEGER, pulls_merged INTEGER,
  pulls_own INTEGER, issues INTEGER, deployments INTEGER, actions_all INTEGER, error TEXT, source TEXT, UNIQUE (run_id, full_name));
CREATE TABLE assessment (id INTEGER PRIMARY KEY, run_id INTEGER NOT NULL, repo TEXT NOT NULL, sha TEXT NOT NULL, tech TEXT NOT NULL,
  created_at TEXT NOT NULL, model TEXT, effort TEXT, status TEXT NOT NULL, level INTEGER, blocked_at TEXT, retries INTEGER, input_tokens INTEGER,
  output_tokens INTEGER, cache_read_tokens INTEGER, cache_write_tokens INTEGER, cost_usd REAL, shown_files TEXT, omitted_files TEXT,
  reused_from INTEGER, in_dictionary INTEGER);
CREATE TABLE finding (assessment_id INTEGER NOT NULL, cond_id TEXT NOT NULL, kind TEXT, llm_status TEXT, final_status TEXT, reason TEXT,
  rule_note TEXT, evidence TEXT, PRIMARY KEY (assessment_id, cond_id));
CREATE TABLE risk_item (assessment_id INTEGER NOT NULL, risk_id TEXT NOT NULL, llm_status TEXT, final_status TEXT, reason TEXT, rule_note TEXT,
  evidence TEXT, PRIMARY KEY (assessment_id, risk_id));
CREATE TABLE stat (id INTEGER PRIMARY KEY, run_id INTEGER NOT NULL, created_at TEXT NOT NULL, levels TEXT NOT NULL, reach TEXT NOT NULL,
  blocked_at INTEGER, type TEXT, note TEXT);
"""


def v1_db(path):
    """job-skill에 맞추기 전 구조의 DB: 같은 기술 × 레포에 판정 두 번(두 번째가 최신), STAT 하나."""
    db = sqlite3.connect(path)
    db.executescript(V1)
    db.execute("INSERT INTO collect_run VALUES (1, 'MeUser', 7, '2026-10-28T14:00:00+0900', '2026-10-28T14:01:00+0900', 0, 10, NULL, '[]')")
    for aid in (1, 2):
        db.execute("INSERT INTO assessment (id, run_id, repo, sha, tech, created_at, model, effort, status, level, blocked_at, retries, shown_files, "
                   "omitted_files) VALUES (?, 1, 'me/app', ?, 'Python', ?, 'claude-opus-5-5', 'high', 'ok', NULL, '0', 0, '[\"app.py\"]', '[]')",
                   (aid, 'a' * 40, f'2026-10-28T14:0{aid}:00+0900'))
        for c in ['personal_scope', *R.CONDITIONS]:
            note = '같은 commit의 실행 기록 없음' if c in E.RUN_RECORD else ('응답 충돌' if c == 'L5-07' else None)
            db.execute('INSERT INTO finding VALUES (?, ?, ?, ?, ?, ?, ?, ?)',
                       (aid, c, E.KIND.get(c, '개인 기여'), 'conflict' if c == 'L5-07' else 'met', 'unknown' if note else 'met', '이유', note,
                        json.dumps([dict(file='app.py', quote='return x * 2')])))
        for r in E.RISKS: db.execute("INSERT INTO risk_item VALUES (?, ?, 'no', 'no', '없음', NULL, '[]')", (aid, r))
    db.execute("INSERT INTO stat VALUES (1, 1, '2026-10-28T14:03:00+0900', '{\"Python\": null}', '[0,0,0,0,0]', 0, '기본 수행 미도달', '메모')")
    db.commit()
    db.close()


class Upgrade(unittest.TestCase):
    def test_v1_db_is_backed_up_and_filled_without_losing_rows(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / 'github.sqlite'
            v1_db(path)
            db = store.connect(path)
            self.assertEqual(db.execute('PRAGMA user_version').fetchone()[0], store.VERSION)
            self.assertEqual(len(list((Path(d) / 'backup').glob('github-v0-*.sqlite'))), 1)
            self.assertEqual(db.execute('SELECT login, relation FROM account').fetchall(), [('MeUser', '본인')])
            self.assertEqual(db.execute('SELECT account_id FROM collect_run').fetchone()[0], 1)
            self.assertEqual(db.execute('SELECT id, is_current, mode FROM assessment ORDER BY id').fetchall(), [(1, 0, 'llm'), (2, 1, 'llm')])
            self.assertEqual(db.execute('SELECT COUNT(*) FROM finding').fetchone()[0], 2 * 32)
            out = json.loads(db.execute('SELECT llm_output_raw FROM assessment WHERE id = 2').fetchone()[0])
            self.assertEqual((out['answer']['findings']['L5-07'].get('clash'), out['answer']['contribution']['status']), (True, 'met'))
            self.assertEqual(db.execute('SELECT tech, level, assessment_ids FROM stat_tech').fetchall(), [('Python', None, None)])
            self.assertEqual(db.execute('SELECT threshold FROM stat').fetchone()[0], 0.5)
            db.close()
            store.connect(path).close()  # 두 번째 연결은 아무것도 바꾸지 않는다
            self.assertEqual(len(list((Path(d) / 'backup').glob('*'))), 1)

    def test_reapplying_rules_to_migrated_answer_gives_stored_result(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / 'github.sqlite'
            v1_db(path)
            db = store.connect(path)
            out = store.output_of(db, 2)
            db.close()
            final, risks = E.judge(out['answer'], {}, {}, dict(ran=False, run_failed=False, used=True))
            self.assertEqual(final['L0-03']['note'], '같은 commit의 실행 기록 없음')
            self.assertEqual((final['L5-07']['status'], final['L5-07']['note']), ('unknown', '응답 충돌'))


class Current(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.path = Path(self.dir.name) / 'github.sqlite'
        db = store.connect(self.path)
        with db:
            db.execute("INSERT INTO account (login, relation, consent_note, consented_at, created_at) VALUES ('me', '본인', '본인', '2026-10-28', 'x')")
            db.execute("INSERT INTO collect_run (account_id, login, started_at, finished_at, token_used, api_calls, identity_emails) "
                       "VALUES (1, 'me', 's', 'f', 0, 1, '[]')")
        db.close()

    def tearDown(self): self.dir.cleanup()

    def save(self, out, **kw): return store.save_assessment(self.path, 1, out, '2026-10-28T15:00:00+0900', E.MODEL, E.EFFORT, **kw)

    def test_new_official_replaces_current_and_shadow_never_current(self):
        first = self.save(run(FakeLLM(), ran=False))
        second = self.save(run(FakeLLM(answer())))
        shadow = self.save(run(FakeLLM(answer()), ran=False, shadow=True), shadow_of=second)
        db = store.connect(self.path)
        rows = db.execute('SELECT id, mode, is_current, shadow_of FROM assessment ORDER BY id').fetchall()
        self.assertEqual(rows, [(first, 'rule_only', 0, None), (second, 'llm', 1, None), (shadow, 'shadow', 0, second)])
        self.assertIsNone(db.execute("SELECT llm_status FROM finding WHERE assessment_id = ? AND cond_id = 'L0-01'", (first,)).fetchone()[0])
        with self.assertRaises(sqlite3.IntegrityError):  # 현재 판정은 기술 × 레포마다 하나
            db.execute('UPDATE assessment SET is_current = 1 WHERE id = ?', (first,))
        db.close()

    def test_cache_lookup_by_input_hash_then_legacy_key(self):
        live = run(FakeLLM(answer()))
        aid = self.save(live)
        hit = store.find_cached(self.path, live['input_hash'], TARGET, E.MODEL, E.EFFORT, 1)
        self.assertEqual((hit['id'], hit['legacy'], hit['output']), (aid, False, live['llm_output']))
        self.assertIsNone(store.find_cached(self.path, live['input_hash'], TARGET, E.MODEL, E.EFFORT, 2))  # 다른 계정의 답은 쓰지 않는다
        db = store.connect(self.path)
        with db: db.execute('UPDATE assessment SET input_hash = NULL WHERE id = ?', (aid,))
        db.close()
        self.assertIsNone(store.find_cached(self.path, 'f' * 64, TARGET, E.MODEL, E.EFFORT, 1))  # 옛 답은 기본으로 쓰지 않는다
        old = store.find_cached(self.path, 'f' * 64, TARGET, E.MODEL, E.EFFORT, 1, legacy=True)
        self.assertEqual((old['id'], old['legacy']), (aid, True))
        self.assertIsNone(store.find_cached(self.path, 'f' * 64, TARGET, E.MODEL, E.EFFORT, 2, legacy=True))
        self.assertEqual(store.find_cached(self.path, 'f' * 64, TARGET, E.MODEL, E.EFFORT, 1, legacy=True, readonly=True)['id'], aid)

    def test_rule_only_row_is_not_a_cache_answer(self):
        out = run(FakeLLM(), ran=False)
        self.save(out)
        self.assertIsNone(store.find_cached(self.path, out['input_hash'], dict(TARGET, sha='c' * 40), E.MODEL, E.EFFORT, 1))

    def test_gold_compare_counts_agreement_and_shadow_signal(self):
        official = self.save(run(FakeLLM(), ran=False))
        self.save(run(FakeLLM(answer()), ran=False, shadow=True), shadow_of=official)
        rows = [dict(login='me', repo=TARGET['repo'], tech=TARGET['tech'], sha=TARGET['sha'], cond_id=c, condition='', expected=e,
                     case_tag='CI 없이 결과 파일만' if c == 'L0-03' else '', note='')
                for c, e in [('LV', '미확인'), ('L0-03', '충족'), ('L0-04', '근거 부족'), ('L0-01', '')]]
        csv_path = Path(self.dir.name) / 'gold.csv'
        with open(csv_path, 'w', newline='', encoding='utf-8-sig') as fh:
            w = csv.DictWriter(fh, gold.COLUMNS); w.writeheader(); w.writerows(rows)
        a = NS(db=self.path, cache=Path(self.dir.name), min_own_lines=50, labeler='나')
        gold.import_labels(a, csv_path)
        summary = gold.compare(a, 'me')
        self.assertEqual((summary['compared'], summary['lv']['agree'], summary['conditions']['agree']), (3, '1/1 (100%)', '1/2 (50%)'))
        self.assertEqual(summary['shadow_signals'], dict(llm_met_rule_blocked=2, gold_sides_with_llm=1, gold_sides_with_rule=1))
        self.assertEqual(summary['boundary_cases'], {'CI 없이 결과 파일만': '0/1 (0%)'})
        self.assertEqual(summary['conditions']['by_decider'], {'규칙': '1/2 (50%)'})  # 실행 기록 없음은 규칙이 정한 값
        gold.import_labels(a, csv_path)  # 같은 정답을 다시 넣어도 처음 넣은 시각은 그대로
        db = store.connect(self.path)
        self.assertEqual(db.execute('SELECT COUNT(DISTINCT labeled_at), COUNT(*) FROM gold_label').fetchone(), (1, 3))
        db.close()


class Consent(unittest.TestCase):
    def test_missing_or_revoked_consent_stops_analysis(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / 'g.sqlite'
            with self.assertRaises(SystemExit): store.require_consent(path, 'nobody')
            store.add_account(path, 'Friend', '지인', '2026-10-29 카톡, 공개 레포 분석 동의', '2026-10-29')
            self.assertEqual(store.require_consent(path, 'friend')[0], 'Friend')  # 계정 이름은 대소문자를 가리지 않는다
            db = store.connect(path)
            with db: db.execute("UPDATE account SET revoked_at = '2026-11-01'")
            db.close()
            with self.assertRaises(SystemExit): store.require_consent(path, 'Friend', readonly=True)

    def test_account_carries_github_id_for_the_identity_check(self):  # check_github.py가 clone 전에 사용자 번호를 대조한다
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / 'g.sqlite'
            store.add_account(path, 'Friend', '지인', '2026-10-29 카톡, 공개 레포 분석 동의', '2026-10-29')
            self.assertIsNone(store.get_account(path, 'Friend')['github_id'])  # 처음 수집 전에는 모른다
            db = store.connect(path)
            with db: db.execute("UPDATE account SET github_id = 42 WHERE login = 'Friend'")
            db.close()
            self.assertEqual(store.get_account(path, 'friend')['github_id'], 42)


class Plan(unittest.TestCase):
    def test_plan_matches_engine_order(self):
        import assess as A
        from test_engine import DOCS, FACTS, FILES
        opts = NS(fresh=False, reuse_legacy=False)
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / 'g.sqlite'
            flags = dict(ran=True, run_failed=False, used=True)
            ih = E.input_hash(TARGET, FACTS, FILES, DOCS)
            self.assertEqual(A.plan(path, 1, TARGET, FACTS, flags, [], DOCS, ih, opts)[0], 'no_material')  # 보여 줄 코드가 없으면 부르지 않음
            self.assertEqual(A.plan(path, 1, TARGET, FACTS, dict(flags, ran=False), FILES, DOCS, ih, opts)[0], 'rule_only')
            self.assertEqual(A.plan(path, 1, TARGET, FACTS, dict(flags, ran=False), FILES, DOCS, ih, opts, shadow=True)[0], 'call')
            self.assertEqual(A.plan(path, None, TARGET, FACTS, flags, FILES, DOCS, ih, opts)[0], 'call')  # 계정을 모르면 저장된 답을 찾지 않는다


class GoldImport(unittest.TestCase):
    def write(self, d, rows):
        path = Path(d) / 'g.csv'
        with open(path, 'w', newline='', encoding='utf-8-sig') as fh:
            w = csv.DictWriter(fh, gold.COLUMNS); w.writeheader(); w.writerows(rows)
        return path

    def test_duplicate_rows_and_missing_sha_are_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            db = Path(d) / 'g.sqlite'
            store.add_account(db, 'me', '본인', '본인', '2026-10-28')
            row = dict(login='me', repo='me/app', tech='Python', sha='a' * 40, cond_id='LV', condition='', expected='LV1', case_tag='', note='')
            a = NS(db=db, labeler='나')
            with self.assertRaises(SystemExit): gold.import_labels(a, self.write(d, [row, dict(row, expected='LV2')]))
            with self.assertRaises(SystemExit): gold.import_labels(a, self.write(d, [dict(row, sha='')]))
            gold.import_labels(a, self.write(d, [row, dict(row, sha='b' * 40, expected='LV2')]))  # 다른 commit의 정답은 따로 남는다
            conn = store.connect(db)
            self.assertEqual(conn.execute('SELECT sha, expected FROM gold_label ORDER BY sha').fetchall(), [('a' * 40, 'LV1'), ('b' * 40, 'LV2')])
            conn.close()

    def test_v2_gold_table_is_rebuilt_with_commit_in_key(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / 'g.sqlite'
            store.connect(path).close()
            db = sqlite3.connect(path)  # v2 구조로 되돌려 정답 한 줄을 넣는다
            db.executescript("""DROP TABLE gold_label; CREATE TABLE gold_label (id INTEGER PRIMARY KEY, account_id INTEGER NOT NULL, repo TEXT NOT NULL,
                tech TEXT NOT NULL, sha TEXT, cond_id TEXT NOT NULL, expected TEXT NOT NULL, case_tag TEXT NOT NULL DEFAULT '', note TEXT NOT NULL DEFAULT '',
                labeler TEXT NOT NULL, labeled_at TEXT NOT NULL, UNIQUE (account_id, repo, tech, cond_id, labeler));
                INSERT INTO account (id, login, relation, consent_note, consented_at, created_at) VALUES (1, 'me', '본인', '본인', '2026-10-28', 'x');
                INSERT INTO gold_label VALUES (1, 1, 'me/app', 'Python', NULL, 'LV', 'LV1', '', '', '나', '2026-10-28T10:00:00+0900');
                PRAGMA user_version = 2;""")
            db.close()
            db = store.connect(path)
            self.assertEqual(db.execute('SELECT id, sha, expected, labeled_at FROM gold_label').fetchall(), [(1, '', 'LV1', '2026-10-28T10:00:00+0900')])
            self.assertIn('sha, cond_id, labeler', db.execute("SELECT sql FROM sqlite_master WHERE name = 'gold_label'").fetchone()[0])
            self.assertEqual(len(list((Path(d) / 'backup').glob('g-v2-*.sqlite'))), 1)
            db.close()


class Schema(unittest.TestCase):
    TYPES = r'(bigint|text|integer|smallint|boolean|timestamptz|date|jsonb|real|numeric|char)'

    def test_sqlite_and_postgres_ddl_have_same_tables_and_columns(self):
        ddl = (HERE / 'db' / 'schema.sql').read_text()
        pg = {t: {m.group(1) for m in re.finditer(rf'^\s+([a-z_]+)\s+{self.TYPES}\b', body, re.M)}
              for t, body in re.findall(r'CREATE TABLE (\w+) \((.*?)\n\);', ddl, re.S)}
        with tempfile.TemporaryDirectory() as d:
            db = store.connect(Path(d) / 'x.sqlite')
            lite = {t: {r[1] for r in db.execute(f'PRAGMA table_info({t})')} for (t,) in db.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
            db.close()
        self.assertEqual(set(pg), set(lite))
        for t in pg: self.assertEqual(pg[t] - {'tech_id'}, lite[t], t)  # tech_id는 job.tech를 가리키는 PostgreSQL 쪽 칸


if __name__ == '__main__': unittest.main()
