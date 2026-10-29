import json
import sys
from pathlib import Path
import pytest

sys.path.insert(0,str(Path(__file__).resolve().parent))
from bench import (ROOT, PLAN, Assessment, Citation, Adapter, StopRun, blank, checked,
                   load_case, level_of, evaluate, merge_review, review_targets)

USERS=json.loads((ROOT/'users20.json').read_text())


@pytest.fixture
def case(): return load_case(USERS[0])


def test_all_sources_isolated():
    for u in USERS:
        c=load_case(u)
        assert not any('review_only' in name or 'build.py' in name for name in c['files'])
        assert all(u['user_id'] in name for name in c['files'])
    assert any('#page=1' in n for n in load_case(USERS[1])['files'])
    assert not load_case(USERS[17])['facts'][0]['version_linked']


def test_rubric_exact_ids():
    a=blank().model_dump(); a['findings'][1]['id']=a['findings'][0]['id']
    with pytest.raises(ValueError): Assessment.model_validate(a)
    a=blank().model_dump(); a['level']=True
    with pytest.raises(ValueError): Assessment.model_validate(a)


def test_cumulative_and_contribution():
    a=blank()
    for f in a.findings: f.status='met'
    for r in a.risks: r.applies='no'
    assert level_of(a) is None
    a.contribution.status='met'; assert level_of(a)==5
    next(f for f in a.findings if f.id=='L3-02').status='unknown'
    assert level_of(a)==2
    a.risks[0].applies='unknown'; assert level_of(a)==1


def test_bad_citation_not_sufficiency(case):
    a=blank(); a.findings[0].status='met'; a.findings[0].evidence=[Citation(file='missing',quote='x')]
    b,issues=checked(a,case)
    assert b.findings[0].status=='unknown' and issues
    assert a.findings[0].status=='met'  # original preserved


def test_direct_preserved_shared_review_and_replay(tmp_path,case):
    mock=tmp_path/'mock'; mock.mkdir(); adapter=Adapter('mock',mock)
    outputs={m:evaluate(m,case,0,adapter) for m in 'ABCDE'}
    assert adapter.attempts==4
    assert outputs['B']['result']['level']==5
    assert outputs['C']['result']['level'] is None
    assert outputs['D']['call_keys'][0]==outputs['C']['call_keys'][0]==outputs['E']['call_keys'][0]
    assert outputs['E']['review_targets']
    replay=tmp_path/'replay'; replay.mkdir(); other=Adapter('replay',replay,mock)
    for m in 'ABCDE': assert evaluate(m,case,0,other)==outputs[m]
    assert other.attempts==0
    with pytest.raises(StopRun,match='replay_response_missing'): other.call(case,1,'direct')


def test_selective_cannot_change_unselected():
    a=blank(); b=blank(); b.findings[0].status='met'; b.findings[1].status='met'
    merged=merge_review(a,b,['L0-01'])
    assert merged.findings[0].status=='met' and merged.findings[1].status=='unknown'
    for f in a.findings: f.status='not_met'
    a.contribution.status='met'
    for r in a.risks: r.applies='no'
    assert review_targets(a,[])==[]


def test_live_no_confirmation_no_network(tmp_path,monkeypatch):
    monkeypatch.delenv('CAREER_INCLUDED_USAGE_CONFIRMED',raising=False)
    with pytest.raises(StopRun,match='billing_preflight_required'): Adapter('live',tmp_path)


def test_budget(tmp_path,case,monkeypatch):
    adapter=Adapter('mock',tmp_path)
    monkeypatch.setitem(PLAN['limits'],'session_calls',0)
    with pytest.raises(StopRun,match='call_budget'): adapter.call(case,0,'direct')


def test_path_escape():
    u=json.loads(json.dumps(USERS[0])); u['project']['files'][0]['path']='review_only/design.json'
    with pytest.raises(ValueError,match='source_scope'): load_case(u)


def test_hash_mismatch():
    u=json.loads(json.dumps(USERS[0])); u['project']['files'][0]['sha256']='0'*64
    with pytest.raises(ValueError,match='source_hash'): load_case(u)


def test_provider_error_stops_and_redacts(tmp_path,case):
    class FakeClient:
        def __init__(self): self.chat=self; self.completions=self
        def create(self,**kwargs): raise RuntimeError('secret-provider-body-do-not-log')
    adapter=Adapter('mock',tmp_path); adapter.mode='live'; adapter.client=FakeClient()
    with pytest.raises(StopRun,match='model_error:RuntimeError'): adapter.call(case,0,'direct')
    text=(tmp_path/'calls.jsonl').read_text()
    assert 'secret-provider' not in text
    assert json.loads(text)['status']=='error'
    assert adapter.attempts==1


def test_schema_failure_is_system_error(tmp_path,case,monkeypatch):
    from types import SimpleNamespace
    class FakeClient:
        def __init__(self): self.chat=self; self.completions=self
        def create(self,**kwargs):
            return SimpleNamespace(usage=None,choices=[SimpleNamespace(message=SimpleNamespace(content='not-json'))])
    adapter=Adapter('mock',tmp_path); adapter.mode='live'; adapter.client=FakeClient()
    with pytest.raises(StopRun,match='ValidationError'): adapter.call(case,0,'direct')
    assert json.loads((tmp_path/'calls.jsonl').read_text())['status']=='error'
