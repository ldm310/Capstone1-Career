"""판정 엔진 규칙 시험(오프라인). Claude 대신 정해 둔 응답을 넣어 ② 규칙 판정 · ③ 재검토 · LV · STAT만 본다.
코드 검토(2026-10-28)에서 확정된 오판 경우를 회귀 시험으로 남긴다.

실행: .venv/bin/python -m unittest test_engine -v
"""
import unittest
from types import SimpleNamespace as NS

import engine as E
import rubric_source as R

APP = 'def run(x):\n    return x * 2\n\ndef helper():\n    return default_value\n'
README = '# App\n입력 x를 받아 두 배로 돌려준다.\n완료 조건: run(2)는 4다.\n'
FACTS = '이 commit의 GitHub Actions 실행: 1건 (결과: success)'
TARGET = dict(tech='Python', repo='me/app', sha='a' * 40, branches='main', signals=['확장자 .py'])
FILES = [('app.py', APP, [[1, 2]])]          # 본인 줄은 1~2줄(run)뿐, helper(4~5줄)는 팀원
DOCS = [('README.md', README, [[1, 3]])]
QUOTE = {'코드형': ('app.py', 'return x * 2'), '문서형': ('README.md', '입력 x를 받아'), '실행 기록형': ('FACTS', 'GitHub Actions 실행: 1건'),
         '활용 기록형': ('FACTS', 'GitHub Actions 실행: 1건'), '혼합': ('README.md', '완료 조건')}
OK = dict(ran=True, run_failed=False, used=True)


def cite(file, quote): return [dict(file=file, quote=quote)]


def answer(**override):
    """모든 조건을 met으로, 유형에 맞는 원문 인용을 붙인 응답. override로 조건을 바꾼다(L0_02=... → L0-02)."""
    item = lambda kind: dict(status='met', reason='근거 있음', evidence=cite(*QUOTE[kind]))
    data = dict(findings={c: item(E.KIND[c]) for c in R.CONDITIONS}, contribution=item('코드형'),
                risks={r: dict(status='no', reason='해당 없음', evidence=cite('README.md', '# App')) for r in E.RISKS})
    for k, v in override.items(): data['findings'][k.replace('_', '-')] = v
    return data


class FakeLLM:
    """API처럼 배열로 돌려준다. drop: 첫 응답에서 뺄 id, fail_on: 몇 번째 호출에서 예외를 낼지."""
    def __init__(self, *replies, drop=(), fail_on=None): self.replies, self.calls, self.drop, self.fail_on = list(replies), 0, set(drop), fail_on

    def __call__(self, blocks, out_schema):
        self.calls += 1
        if self.fail_on == self.calls: raise RuntimeError('network')
        reply = self.replies.pop(0)
        drop = self.drop if self.calls == 1 else set()
        out = dict(findings=[dict(id=k, **v) for k, v in reply['findings'].items() if k not in drop], contribution=reply['contribution'],
                   risks=reply.get('risks_list') or [dict(id=k, **v) for k, v in reply['risks'].items()])
        return out, dict(cost_usd=0.0), 'ok'


def run(llm, shadow=False, cached=None, **flags):
    return E.assess(None, None, TARGET, FACTS, {**OK, **flags}, FILES, DOCS, llm=llm, shadow=shadow, cached=cached)


def note(item, kind, flags=OK): return E.check(item, kind, {'FACTS': FACTS, 'app.py': APP, 'README.md': README}, E.code_index(FILES), flags)


class Levels(unittest.TestCase):
    def test_no_run_record_blocks_lv0_without_calling_llm(self):  # 규칙 먼저 판정(B)
        llm = FakeLLM(answer())
        out = run(llm, ran=False)
        self.assertEqual((llm.calls, out['mode'], out['level'], out['blocked'], out['retries']), (0, 'rule_only', None, 0, 0))
        self.assertEqual(out['final']['L0-03']['note'], '같은 commit의 실행 기록 없음')
        self.assertEqual((out['final']['L0-01']['llm_status'], out['final']['L0-01']['note']), (None, E.RULE_ONLY))

    def test_usage_record_missing_stops_at_lv2(self):
        out = run(FakeLLM(answer()), used=False)
        self.assertEqual((out['level'], out['blocked']), (2, 3))
        self.assertEqual(out['final']['L3-02']['note'], '이슈 기록 없음')

    def test_risk_without_citation_holds_lv2(self):
        data = answer()
        data['risks']['external_input'] = dict(status='no', reason='없음', evidence=[])
        out = run(FakeLLM(data, data, data, data))
        self.assertEqual((out['level'], out['blocked']), (1, 'risk'))

    def test_stat_reach_and_type(self):
        st = E.stat({'Python': None, 'JavaScript': 1})
        self.assertEqual(st['reach'], [0.5, 0.5, 0.0, 0.0, 0.0])
        self.assertEqual((st['blocked'], st['type']), (2, '과제 완성형'))
        self.assertEqual(E.stat({'Python': None})['type'], '기본 수행 미도달')


class Retries(unittest.TestCase):
    def test_quote_not_in_source_is_retried_and_fixed(self):
        llm = FakeLLM(answer(L0_02=dict(status='met', reason='지어낸 인용', evidence=cite('app.py', 'return x * 3 + 1'))), answer())
        out = run(llm)
        self.assertEqual((out['retries'], llm.calls, out['final']['L0-02']['status'], out['level']), (1, 2, 'met', 5))

    def test_teammate_line_unresolved_after_three_retries(self):
        other = dict(status='met', reason='팀원 줄 인용', evidence=cite('app.py', 'return default_value'))
        out = run(FakeLLM(*[answer(L0_02=other)] * 4))
        self.assertEqual((out['retries'], out['final']['L0-02']['status'], out['level']), (3, 'unknown', None))
        self.assertTrue(out['final']['L0-02']['note'].endswith(E.HOLD))

    def test_retry_only_when_it_can_raise_level(self):
        bad = dict(status='met', reason='지어낸 인용', evidence=cite('app.py', 'nothing like this here'))
        self.assertEqual(run(FakeLLM(answer(L4_04=bad)), ran=False, shadow=True)['retries'], 0)  # LV0에서 이미 막혀 소용없다

    def test_conflict_on_run_record_without_records_is_not_retried(self):  # 검토 rules-3
        out = run(FakeLLM(answer(L0_03=dict(status='conflict', reason='문서와 FACTS가 다름', evidence=[]))), ran=False, shadow=True)
        self.assertEqual((out['retries'], out['final']['L0-03']['note']), (0, '같은 commit의 실행 기록 없음'))

    def test_missing_condition_is_retried(self):
        out = run(FakeLLM(answer(), answer(), drop={'L1-02'}))
        self.assertEqual((out['retries'], out['final']['L1-02']['status']), (1, 'met'))

    def test_risk_clash_is_retried(self):  # 검토 bugs-8
        first = answer()
        first['risks_list'] = [dict(id=r, **v) for r, v in first['risks'].items()] + [dict(id='external_input', status='yes', reason='다름', evidence=[])]
        out = run(FakeLLM(first, answer()))
        self.assertEqual((out['retries'], out['risks']['external_input']['status'], out['level']), (1, 'no', 5))

    def test_retry_exception_keeps_first_judgment(self):  # 검토 safety-3·bugs-2
        bad = dict(status='met', reason='지어낸 인용', evidence=cite('app.py', 'return x * 3 + 1'))
        out = run(FakeLLM(answer(L0_02=bad), fail_on=2))
        self.assertEqual(out['status'], 'ok')
        self.assertEqual(out['usage'][-1]['error'], 'RuntimeError')
        self.assertTrue(out['final']['L0-02']['note'].endswith(E.HOLD))


class Checks(unittest.TestCase):
    def test_quote_spanning_own_and_teammate_lines_fails(self):  # 검토 rules-1
        self.assertEqual(note(dict(status='met', reason='', evidence=cite('app.py', 'return x * 2\n\ndef helper():')), '코드형'), '본인 줄 아님')

    def test_short_code_fragment_rejected(self):  # 검토 rules-1
        self.assertEqual(note(dict(status='met', reason='', evidence=cite('app.py', 'x * 2')), '코드형'), '인용이 너무 짧음')

    def test_doc_own_line_not_accepted_for_code(self):  # 검토 rules-6
        self.assertEqual(note(dict(status='met', reason='', evidence=cite('README.md', '입력 x를 받아 두 배로')), '코드형'), '본인 코드 인용 없음')

    def test_failed_run_blocks_met_but_allows_cited_not_met(self):  # 검토 rules-4·bugs-9
        failed = dict(ran=False, run_failed=True, used=True)
        self.assertEqual(note(dict(status='met', reason='', evidence=cite('FACTS', 'GitHub Actions 실행')), '실행 기록형', failed), '같은 commit의 실행 실패')
        self.assertIsNone(note(dict(status='not_met', reason='실패', evidence=cite('FACTS', 'GitHub Actions 실행')), '실행 기록형', failed))

    def test_run_record_met_needs_facts_citation(self):  # 검토 safety-2
        self.assertEqual(note(dict(status='met', reason='', evidence=cite('README.md', '완료 조건')), '실행 기록형'), '기록 인용 없음')

    def test_not_met_without_citation_becomes_unknown(self):  # 검토 rules-8
        self.assertEqual(note(dict(status='not_met', reason='없음', evidence=[]), '문서형'), '인용 없음')

    def test_duplicate_ids_with_different_status_become_conflict(self):
        data = dict(findings=[dict(id='L0-01', status='met', reason='a', evidence=[]), dict(id='L0-01', status='not_met', reason='b', evidence=[])],
                    contribution=dict(status='met', reason='', evidence=[]), risks=[])
        f = E.normalize(data)['findings']['L0-01']
        self.assertEqual((f['status'], f['clash']), ('conflict', True))

    def test_schema_covers_every_condition(self):
        s = E.schema()
        self.assertEqual(set(s['properties']['findings']['items']['properties']['id']['enum']), set(R.CONDITIONS))
        self.assertEqual([sum(E.KIND[c] == k for c in R.CONDITIONS) for k in ('문서형', '코드형', '실행 기록형', '활용 기록형', '혼합')], [9, 7, 9, 3, 3])


class RuleFirst(unittest.TestCase):
    """규칙 먼저 판정(B)·그림자 실행. B는 LLM 답이 결과를 바꿀 수 없을 때만 LLM을 건너뛴다."""
    def test_failed_only_run_keeps_failure_note(self):
        out = run(FakeLLM(answer()), ran=False, run_failed=True)
        self.assertEqual((out['mode'], out['final']['L0-03']['note'], out['final']['L0-04']['note']),
                         ('rule_only', '같은 commit의 실행 실패', '같은 commit의 실행 실패'))

    def test_usage_record_note_without_issues(self):
        out = run(FakeLLM(), ran=False, used=False)
        self.assertEqual(out['final']['L3-02']['note'], '이슈 기록 없음')

    def test_rule_first_never_changes_level(self):  # 같은 자료에 LLM까지 돌린 결과(A)와 LV·막힌 곳이 같다
        unknown = dict(status='unknown', reason='모름', evidence=[])
        variants = [answer(), answer(L0_01=unknown, L0_02=unknown), answer(L0_03=dict(status='met', reason='문서에 통과 기록', evidence=cite(*QUOTE['문서형'])))]
        for data in variants:
            full = run(FakeLLM(*[data] * 4), ran=False, shadow=True)
            first = run(FakeLLM(), ran=False)
            self.assertEqual((first['level'], first['blocked']), (None, 0))
            self.assertEqual((full['level'], full['blocked']), (None, 0))  # 개인 기여가 막혀도 막힌 곳은 실행 기록(LV0)으로 같다

    def test_shadow_never_retries_items_that_cannot_change_level(self):  # 검토 ENG-M1
        llm = FakeLLM(answer(), answer(), drop={'L0-03', 'L0-04'})  # 실행 기록형 답이 빠져도 근거 자체가 없어 재검토하지 않는다
        out = run(llm, ran=False, shadow=True)
        self.assertEqual((llm.calls, out['retries'], out['final']['L0-03']['note']), (1, 0, '같은 commit의 실행 기록 없음'))
        failed = run(FakeLLM(answer(L0_03=dict(status='not_met', reason='실패', evidence=[]))), ran=False, run_failed=True, shadow=True)
        self.assertEqual((failed['retries'], failed['final']['L0-03']['status']), (0, 'unknown'))

    def test_missing_use_record_without_issues_is_not_retried(self):  # 검토 ENG-M1 case3
        llm = FakeLLM(answer(), answer(), drop={'L3-02'})
        out = run(llm, used=False)
        self.assertEqual((llm.calls, out['final']['L3-02']['note']), (1, '이슈 기록 없음'))

    def test_cached_answer_matches_live_after_failed_retry_call(self):  # 검토 ENG-M2: 재검토 호출이 실패해도 같은 표시
        bad = dict(status='conflict', reason='문서와 코드가 다름', evidence=[])
        live = run(FakeLLM(answer(L0_02=bad), fail_on=2))
        again = run(FakeLLM(), cached=live['llm_output'])
        self.assertEqual((live['final']['L0-02']['status'], live['final']['L0-02']['note']), ('unknown', '근거 충돌' + E.HOLD))
        self.assertEqual({k: (v['status'], v['note']) for k, v in again['final'].items()}, {k: (v['status'], v['note']) for k, v in live['final'].items()})

    def test_shadow_runs_llm_and_shows_rule_block(self):
        llm = FakeLLM(answer())
        out = run(llm, ran=False, shadow=True)
        self.assertEqual((llm.calls, out['mode'], out['level']), (1, 'shadow', None))
        self.assertEqual((out['final']['L0-03']['llm_status'], out['final']['L0-03']['status']), ('met', 'unknown'))  # LLM은 충족, 규칙이 막음

    def test_cached_answer_matches_live_judgment(self):
        live = run(FakeLLM(answer(L0_02=dict(status='met', reason='지어낸 인용', evidence=cite('app.py', 'return x * 3 + 1'))), answer()))
        again = run(FakeLLM(), cached=live['llm_output'])  # 답이 없는 FakeLLM: 부르면 실패한다
        self.assertEqual({k: (v['status'], v['note']) for k, v in again['final'].items()}, {k: (v['status'], v['note']) for k, v in live['final'].items()})
        self.assertEqual((again['level'], again['blocked'], again['mode']), (live['level'], live['blocked'], 'llm'))

    def test_cached_answer_keeps_hold_for_items_already_retried(self):
        other = dict(status='met', reason='팀원 줄 인용', evidence=cite('app.py', 'return default_value'))
        live = run(FakeLLM(*[answer(L0_02=other)] * 4))
        again = run(FakeLLM(), cached=live['llm_output'])
        self.assertEqual((again['final']['L0-02']['status'], again['final']['L0-02']['note']), ('unknown', live['final']['L0-02']['note']))
        self.assertTrue(again['final']['L0-02']['note'].endswith(E.HOLD))

    def test_new_rule_failure_on_cached_answer_is_marked_offline(self):
        bad = dict(status='met', reason='지어낸 인용', evidence=cite('app.py', 'return x * 3 + 1'))
        cached = dict(answer=E.normalize(dict(findings=[dict(id=k, **v) for k, v in answer(L0_02=bad)['findings'].items()],
                                              contribution=answer()['contribution'], risks=[dict(id=k, **v) for k, v in answer()['risks'].items()])),
                      retried=[], unresolved=[])
        out = run(FakeLLM(), cached=cached)
        self.assertTrue(out['final']['L0-02']['note'].endswith(E.OFFLINE))

    def test_input_hash_follows_material(self):
        h = E.input_hash(TARGET, FACTS, FILES, DOCS)
        self.assertEqual(h, E.input_hash(TARGET, FACTS, FILES, DOCS))
        self.assertNotEqual(h, E.input_hash(TARGET, FACTS + '\nPR: 1건', FILES, DOCS))
        self.assertEqual(run(FakeLLM(), ran=False)['input_hash'], h)

    def test_rule_hash_is_stable(self):
        self.assertEqual(len(E.rule_hash()), 64)
        self.assertEqual(E.rule_hash(), E.rule_hash())


class FakeClient:
    """count_tokens와 stream만 흉내 낸다. stream에 넘긴 인자를 남긴다(실제 API를 부르지 않는다)."""
    def __init__(self, n, model):
        client, msg = self, NS(content=[NS(type='text', text='{}')], model=model, stop_reason='end_turn', id='m',
                               usage=NS(input_tokens=10, output_tokens=10, cache_read_input_tokens=0, cache_creation_input_tokens=0, iterations=None))

        class Stream:
            def __init__(self, **kw): client.kw = kw
            def __enter__(self): return NS(get_final_message=lambda: msg)
            def __exit__(self, *a): return False
        self.kw = None
        self.beta = NS(messages=NS(count_tokens=lambda **k: NS(input_tokens=n), stream=Stream))


class Models(unittest.TestCase):
    """판정 모델 바꾸기: 가격표·긴 프롬프트 단가·fallback 지원 여부(사용자 결정 2026-10-28: 기본 Haiku 5.5)."""
    def setUp(self): self.saved = (E.MODEL, E.EFFORT)

    def tearDown(self): E.configure(*self.saved)

    def call_with(self, model, n):
        E.configure(model, 'high')
        cl, budget = FakeClient(n, model), E.Budget(10.0)
        E.call(cl, budget, 'system', [{'type': 'text', 'text': 'x'}], {'type': 'object'})
        return cl.kw, budget

    def test_haiku_long_prompt_tier_covers_whole_request(self):
        self.assertEqual(E.prices('claude-haiku-5-5', 100_000), E.PRICES['claude-haiku-5-5'])
        self.assertEqual(E.prices('claude-haiku-5-5', 100_001), E.LONG_PROMPT['claude-haiku-5-5'][1])
        u = NS(input_tokens=1_000, output_tokens=10_000, cache_read_input_tokens=60_000, cache_creation_input_tokens=40_000)
        self.assertAlmostEqual(E.price_of('claude-haiku-5-5', u), (1_000 * 0.5 + 10_000 * 2.5 + 60_000 * 0.05 + 40_000 * 0.625) / 1e6)
        self.assertEqual(E.prices('claude-opus-5-5', 500_000), E.PRICES['claude-opus-5-5'])  # 다른 모델은 길이와 상관없음

    def test_haiku_request_has_no_fallback_and_budget_skips_fallback_term(self):
        kw, budget = self.call_with('claude-haiku-5-5', 50_000)
        self.assertNotIn('fallbacks', kw)
        self.assertEqual(kw['model'], 'claude-haiku-5-5')
        ok, n, worst = budget.allow(FakeClient(50_000, 'claude-haiku-5-5'), E.request('s', [], {}))
        self.assertAlmostEqual(worst, (50_000 * 0.125 + E.MAX_TOKENS * 0.50) / 1e6)

    def test_opus_request_keeps_fallback(self):
        kw, _ = self.call_with('claude-opus-5-5', 50_000)
        self.assertEqual((kw['fallbacks'], kw['betas']), ('default', [E.FALLBACK_BETA]))

    def test_unknown_model_rejected_and_input_hash_differs_by_model(self):
        with self.assertRaises(SystemExit): E.configure('claude-unknown', 'high')
        E.configure('claude-haiku-5-5', 'high'); h = E.input_hash(TARGET, FACTS, FILES, DOCS)
        E.configure('claude-sonnet-5-5', 'high')
        self.assertNotEqual(h, E.input_hash(TARGET, FACTS, FILES, DOCS))  # 저장된 답은 같은 모델의 답만 다시 쓴다


class Compare(unittest.TestCase):
    """compare_models의 잠재 LV: 실행 기록형만 충족으로 가정한다(판정 아님). 나머지 조건·개인 기여·위험은 그대로 본다."""
    def test_potential_level_assumes_only_run_records(self):
        import compare_models as C
        unknown = dict(status='unknown', reason='모름', evidence=[])
        for data, want in [(answer(), 5), (answer(L1_03=unknown), 0), (answer(L3_01=unknown), 2), (dict(answer(), contribution=unknown), None)]:
            out = run(FakeLLM(data), ran=False, shadow=True)
            self.assertEqual((out['level'], out['blocked'], C.potential(out['final'], out['risks'])), (None, 0, want))


class Money(unittest.TestCase):
    def test_fallback_usage_priced_per_model(self):  # 검토 api-1·safety-1
        it = lambda t, m: NS(type=t, model=m, input_tokens=1000, output_tokens=100, cache_read_input_tokens=0, cache_creation_input_tokens=0)
        msg = NS(model='claude-opus-4-8', usage=NS(iterations=[it('message', 'claude-opus-5-5'), it('fallback_message', 'claude-opus-4-8')]))
        u = E.usage_of(msg)
        self.assertAlmostEqual(u['cost_usd'], (1000 * 4 + 100 * 20 + 1000 * 5 + 100 * 25) / 1e6)
        self.assertTrue(u['fallback'])

    def test_parse_reads_text_after_fallback(self):  # 검토 api-4·safety-5
        content = [NS(type='text', text='{"partial'), NS(type='fallback'), NS(type='text', text='{"a": 1}')]
        self.assertEqual(E.parse(content)[0], {'a': 1})

    def test_no_code_shown_means_no_call(self):  # 검토 bugs-5
        llm = FakeLLM(answer())
        out = E.assess(None, None, TARGET, FACTS, OK, [], DOCS, llm=llm)
        self.assertEqual((out['status'], llm.calls), ('no_material', 0))


if __name__ == '__main__': unittest.main()
