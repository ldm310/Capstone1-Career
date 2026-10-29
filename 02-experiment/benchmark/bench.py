"""A-E fixed-workflow benchmark. No agents, arbitrary filesystem tools, or code execution."""
import argparse
import ast
import csv
import hashlib
import io
import json
import math
import os
import random
import statistics
import subprocess
import time
from collections import Counter
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator, ValidationError
from pypdf import PdfReader
from rubric import CRITERIA, POLICY, RISKS, VERSION

HERE=Path(__file__).resolve().parent
ROOT=HERE.parent
METHODS=['A','B','C','D','E']
METHOD_NAMES={'A':'규칙만','B':'LLM 직접 판정','C':'LLM 해석＋규칙 판정','D':'C＋전체 검토','E':'C＋선별 검토'}
PLAN=json.loads((HERE/'plan.json').read_text())


def digest(value): return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
def read_lines(path): return [json.loads(x) for x in path.read_text().splitlines() if x.strip()] if path.exists() else []
def append(path,data):
    with path.open('a') as f:
        f.write(json.dumps(data,ensure_ascii=False)+'\n'); f.flush(); os.fsync(f.fileno())
def save(path,data):
    temporary=path.with_suffix(path.suffix+'.tmp')
    temporary.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n'); temporary.replace(path)


class Strict(BaseModel):
    model_config=ConfigDict(extra='forbid',strict=True)
class Citation(Strict):
    file: str
    quote: str=Field(min_length=1)
class Finding(Strict):
    id: str
    status: Literal['met','not_met','unknown','conflict']
    reason: str=Field(min_length=1)
    evidence: list[Citation]
class Risk(Strict):
    id: str
    applies: Literal['yes','no','unknown']
    reason: str=Field(min_length=1)
    evidence: list[Citation]
class Assessment(Strict):
    findings: list[Finding]
    contribution: Finding
    risks: list[Risk]
    level: int|None=Field(ge=0,le=5)

    @model_validator(mode='after')
    def validate_ids(self):
        if len(self.findings)!=31 or {f.id for f in self.findings}!=set(CRITERIA): raise ValueError('criterion_ids')
        if len(self.risks)!=8 or {r.id for r in self.risks}!=set(RISKS): raise ValueError('risk_ids')
        if self.contribution.id!='personal_scope': raise ValueError('contribution_id')
        return self


def blank():
    return Assessment(findings=[Finding(id=k,status='unknown',reason='자료의 의미적 충분성 미확인',evidence=[]) for k in CRITERIA],
        contribution=Finding(id='personal_scope',status='unknown',reason='개인 귀속 미확인',evidence=[]),
        risks=[Risk(id=k,applies='unknown',reason='적용 조건 미확인',evidence=[]) for k in RISKS],level=None)


def level_of(a):
    if a.contribution.status!='met': return None
    statuses={f.id:f.status for f in a.findings}; level=None
    for n in range(6):
        if n>=2 and any(r.applies=='unknown' for r in a.risks): break
        if not all(statuses[k]=='met' for k in CRITERIA if k.startswith(f'L{n}-')): break
        level=n
    return level


def load_case(user):
    """Allowlist by case and verify manifest, Git blob, PDF page mapping; never load review_only."""
    uid=user['user_id']; project=user['project']; repo_info=project['repository']
    repo=(ROOT/repo_info['local_path']).resolve()
    if repo!=(ROOT/'submissions'/uid/'repository').resolve(): raise ValueError('repository_scope')
    files={}; facts=[]
    for item in project['files']:
        path=(ROOT/item['path']).resolve()
        allowed=path.is_relative_to((ROOT/'submissions'/uid).resolve()) or path==(ROOT/'output/pdf'/f'{uid}-portfolio.pdf').resolve()
        if not allowed or path.is_symlink() or '.git' in path.parts or 'submission.json'==path.name: raise ValueError('source_scope')
        data=path.read_bytes()
        if hashlib.sha256(data).hexdigest()!=item['sha256']: raise ValueError('source_hash')
        if path.is_relative_to(repo):
            name=str(path.relative_to(repo))
            blob=subprocess.check_output(['git','-C',str(repo),'show',repo_info['commit']+':'+name],timeout=10)
            if blob!=data: raise ValueError('commit_blob_mismatch')
        if path.suffix=='.pdf':
            for n,page in enumerate(PdfReader(io.BytesIO(data)).pages,1): files[item['path']+f'#page={n}']=page.extract_text() or ''
        else: files[item['path']]=data.decode('utf8')
    for name,text in files.items():
        if name.endswith('/test-result.json'):
            log=json.loads(text)
            code=files.get(str(Path(repo_info['local_path'])/'app.py'),'')
            tests=files.get(str(Path(repo_info['local_path'])/'test_app.py'),'')
            linked=log.get('commit')==repo_info['commit'] and log.get('source_sha256')==hashlib.sha256(code.encode()).hexdigest() and log.get('test_sha256')==hashlib.sha256(tests.encode()).hexdigest()
            facts.append(dict(file=name,kind='test_result',version_linked=linked,exit_code=log.get('exit_code')))
    case=dict(user_id=uid,role=user['target_role'],commit=repo_info['commit'],files=files,facts=facts)
    if len(json.dumps(case,ensure_ascii=False))>PLAN['limits']['input_characters']: raise ValueError('input_cap')
    return case


def rule_extract(case):
    a=blank(); by_id={f.id:f for f in a.findings}
    for name,text in case['files'].items():
        if name.endswith('/app.py'):
            tree=ast.parse(text)
            if any(isinstance(n,(ast.FunctionDef,ast.ClassDef)) for n in ast.walk(tree)):
                by_id['L0-02'].status='met'; by_id['L0-02'].reason='AST에서 실행 가능한 함수/클래스 구현 확인; 요구 적합성은 별도'
                by_id['L0-02'].evidence=[Citation(file=name,quote=text)]
    for fact in case['facts']:
        f=by_id['L0-03']; f.evidence=[Citation(file=fact['file'],quote=case['files'][fact['file']])]
        f.status='met' if fact['version_linked'] else 'unknown'
        f.reason='현재 코드 및 테스트 해시와 실행 기록 연결 확인' if fact['version_linked'] else '이전 버전 실행 결과이며 현재 버전 실행 미확인'
    return a


def inspect_evidence(a,case):
    issues=[]
    for f in [*a.findings,a.contribution]:
        if f.status=='met' and not f.evidence: issues.append(dict(id=f.id,type='met_without_citation'))
        for c in f.evidence:
            if c.quote not in case['files'].get(c.file,''): issues.append(dict(id=f.id,type='invalid_citation'))
    for r in a.risks:
        if r.applies!='unknown' and not r.evidence: issues.append(dict(id=r.id,type='risk_without_citation'))
        for c in r.evidence:
            if c.quote not in case['files'].get(c.file,''): issues.append(dict(id=r.id,type='invalid_citation'))
    return issues


def checked(a,case):
    b=a.model_copy(deep=True); issues=inspect_evidence(a,case); bad={i['id'] for i in issues}
    for f in [*b.findings,b.contribution]:
        if f.id in bad: f.status='unknown'; f.reason+=' / 자동 근거 검사 실패'
    for r in b.risks:
        if r.id in bad: r.applies='unknown'
    b.level=level_of(b)
    return b,issues


def review_targets(a,issues):
    ids={i['id'] for i in issues}
    ids.update(f.id for f in a.findings if f.status in ('unknown','conflict') or (f.status=='met' and int(f.id[1])>=3))
    if a.contribution.status!='met': ids.add('personal_scope')
    ids.update(r.id for r in a.risks if r.applies=='unknown')
    return sorted(ids)


def merge_review(base,review,targets):
    result=base.model_copy(deep=True); updates={f.id:f for f in review.findings}
    result.findings=[updates[f.id] if f.id in targets else f for f in base.findings]
    if 'personal_scope' in targets: result.contribution=review.contribution
    risks={r.id:r for r in review.risks}
    result.risks=[risks[r.id] if r.id in targets else r for r in base.risks]
    return result


class StopRun(RuntimeError): pass


class Adapter:
    def __init__(self,mode,out,source=None):
        self.mode=mode; self.out=out; self.attempts=0; self.last=0
        self.cache={r['key']:r for r in read_lines(out/'calls.jsonl') if r['status']=='ok'}
        if mode=='replay':
            if source is None: raise ValueError('replay_source_required')
            self.cache={r['key']:r for r in read_lines(source/'calls.jsonl') if r['status']=='ok'}
        self.client=None
        if mode=='live':
            if PLAN.get('provider')=='gemini':
                if os.environ.get('CAREER_GEMINI_FREE_CONFIRMED')!='yes': raise StopRun('gemini_free_preflight_required')
                from google import genai
                from google.genai import types
                path=Path.home()/'.config/career-benchmark/gemini.env'
                if path.stat().st_mode & 0o077: raise StopRun('gemini_key_file_permissions_require_600')
                entries=[line.split('=',1)[1].strip().strip('\"\'') for line in path.read_text().splitlines() if line.startswith('GEMINI_API_KEY=')]
                if len(entries)!=1 or not entries[0]: raise StopRun('gemini_key_missing_or_duplicate')
                self.client=genai.Client(api_key=entries[0],vertexai=False,http_options=types.HttpOptions(
                    base_url='https://generativelanguage.googleapis.com',timeout=PLAN['limits']['request_timeout']*1000,
                    retry_options=types.HttpRetryOptions(attempts=1)))
                return
            if os.environ.get('CAREER_INCLUDED_USAGE_CONFIRMED')!='yes': raise StopRun('billing_preflight_required')
            import yaml
            from openai import OpenAI
            config=yaml.safe_load((Path.home()/'.config/cliproxyapi-career/config.yaml').read_text())
            if config['server']['host']!='127.0.0.1': raise StopRun('local_proxy_only')
            self.client=OpenAI(base_url=f"http://127.0.0.1:{int(config['server']['port'])}/v1",api_key=config['access']['api-keys'][0],max_retries=0,timeout=PLAN['limits']['request_timeout'])

    def call(self,case,rep,stage,base=None,targets=None):
        payload=dict(case=case,rubric=CRITERIA,risk_ids=RISKS,contribution_id='personal_scope',
            output_requirements='Return all 31 findings and all 8 risks with exact IDs, plus contribution and level. For extract/review set level to null; do not omit it. Return JSON only.',
            rubric_source=(HERE/'RUBRIC_SOURCE.md').read_text(),stage=stage,base=base.model_dump() if base else None,targets=targets)
        if PLAN.get('compact_output'):
            payload['output_requirements']+=' Keep each reason within 100 characters; at most 2 citations per item, each quote within 160 characters. Preserve all criteria; never truncate an essential quotation misleadingly.'
        messages=[dict(role='system',content=POLICY+'\nSchema: '+json.dumps(Assessment.model_json_schema())),dict(role='user',content=json.dumps(payload,ensure_ascii=False))]
        key=digest([PLAN,VERSION,rep,messages])
        if key in self.cache:
            return Assessment.model_validate(self.cache[key]['response']),key
        if self.mode=='replay': raise StopRun('replay_response_missing')
        limits=PLAN['limits']; prior=[x for x in self.cache.values() if x['user']==case['user_id'] and x['repeat']==rep]
        # UTF-8 bytes is a conservative preflight token budget estimate, not measured usage.
        estimate=len(json.dumps(messages,ensure_ascii=False).encode())+limits['max_output_tokens']
        if len(prior)>=limits['calls_per_user_repeat'] or self.attempts>=limits['session_calls']: raise StopRun('call_budget')
        if sum(x['reserved_tokens'] for x in prior)+estimate>limits['estimated_token_budget_per_user_repeat']: raise StopRun('token_budget')
        if self.mode=='live' and self.last: time.sleep(max(0,limits['interval_seconds']-(time.monotonic()-self.last)))
        event=dict(key=key,user=case['user_id'],repeat=rep,stage=stage,status='error',input_tokens=None,output_tokens=None,cost=None,reserved_tokens=estimate,provided_files=sorted(case['files']),mode=self.mode)
        start=time.monotonic(); self.attempts+=1
        try:
            if self.mode=='mock':
                response=rule_extract(case)
                if stage in ('direct','extract'):
                    response.findings[0].status='met'
                    response.findings[0].reason='MOCK injected citation error: tests plumbing only'
                    response.findings[0].evidence=[Citation(file='missing.txt',quote='injected')]
                response.level=5 if stage=='direct' else None
            elif PLAN.get('provider')=='gemini':
                raw=self.client.models.generate_content(model=PLAN['model'],contents=messages[1]['content'],config={
                    'system_instruction':messages[0]['content'],'max_output_tokens':limits['max_output_tokens'],
                    'response_mime_type':'application/json',
                    'response_json_schema':Assessment.model_json_schema()})
                if raw.usage_metadata:
                    u=raw.usage_metadata
                    event.update(input_tokens=u.prompt_token_count,output_tokens=u.candidates_token_count,
                        thinking_tokens=u.thoughts_token_count,total_tokens=u.total_token_count)
                event['raw_content']=raw.text or ''
                event['provider']='gemini'
                response=Assessment.model_validate_json(event['raw_content'])
            else:
                raw=self.client.chat.completions.create(model=PLAN['model'],messages=messages,max_completion_tokens=limits['max_output_tokens'],stream=False)
                if raw.usage:
                    event.update(input_tokens=raw.usage.prompt_tokens,output_tokens=raw.usage.completion_tokens)
                event['raw_content']=raw.choices[0].message.content or ''
                event['finish_reason']=getattr(raw.choices[0],'finish_reason',None)
                response=Assessment.model_validate_json(event['raw_content'])
            event.update(status='ok',response=response.model_dump())
        except Exception as exc:
            event.update(error_type=type(exc).__name__,http_status=getattr(exc,'status_code',getattr(exc,'code',None)))
            if PLAN.get('provider')=='gemini' and hasattr(exc,'message'):
                import re
                message=str(exc.message)
                for line in (Path.home()/'.config/career-benchmark/gemini.env').read_text().splitlines():
                    if line.startswith('GEMINI_API_KEY='):
                        secret=line.split('=',1)[1].strip().strip('\"\'')
                        if secret: message=message.replace(secret,'[REDACTED]')
                event['provider_message']=re.sub(r'https?://\S+','[URL]',message)[:1600]
            if isinstance(exc,ValidationError):
                event['validation_errors']=exc.errors(include_input=False,include_context=False,include_url=False)
            raise StopRun('model_error:'+type(exc).__name__) from None
        finally:
            event['seconds']=time.monotonic()-start; self.last=time.monotonic(); append(self.out/'calls.jsonl',event)
        self.cache[key]=event
        return response,key


def evaluate(method,case,rep,adapter):
    keys=[]; targets=[]; before=None
    if method=='A': raw=rule_extract(case)
    elif method=='B': raw,key=adapter.call(case,rep,'direct'); keys.append(key)
    else:
        raw,key=adapter.call(case,rep,'extract'); keys.append(key)
        before,first_issues=checked(raw,case)
        if method in ('D','E'):
            targets=([*CRITERIA,'personal_scope',*RISKS] if method=='D' else review_targets(before,first_issues))
            if targets:
                review,key=adapter.call(case,rep,'review_all' if method=='D' else 'review_selected',before,targets)
                keys.append(key); raw=merge_review(before,review,targets)
    final,issues=checked(raw,case)
    if method=='B': final=raw  # Inspect and report but NEVER replace B's claimed level/statuses.
    return dict(result=final.model_dump(),raw=raw.model_dump(),issues=issues,review_targets=targets,
        before_review=before.model_dump() if before else None,call_keys=keys,
        logical_seconds=sum(adapter.cache[k]['seconds'] for k in keys),
        logical_input_tokens=sum(adapter.cache[k]['input_tokens'] or 0 for k in keys) if all(adapter.cache[k]['input_tokens'] is not None for k in keys) else None,
        logical_output_tokens=sum(adapter.cache[k]['output_tokens'] or 0 for k in keys) if all(adapter.cache[k]['output_tokens'] is not None for k in keys) else None)


def ratio(n,d): return f'{n}/{d} ({100*n/d:.1f}%)' if d else 'N/A'


def report(out,users,repeats,mode):
    latest={r['id']:r for r in read_lines(out/'results.jsonl')}
    calls=read_lines(out/'calls.jsonl'); rows=[]
    split={r['user_id']:r['split'] for r in json.loads((ROOT/'review_only/design.json').read_text())}
    for method in METHODS:
        group=[r for r in latest.values() if r['method']==method]; ok=[r for r in group if r['status']=='ok']; failed=[r for r in group if r['status']=='error']
        times=sorted(r['wall_seconds'] for r in ok); groups={}
        for r in ok: groups.setdefault(r['user'],[]).append(r)
        complete=[g for g in groups.values() if len(g)==repeats]
        consistent=sum(len({digest(x['result']) for x in g})==1 for g in complete)
        lvconsistent=sum(len({x['result']['level'] for x in g})==1 for g in complete)
        evalok=[r for r in ok if split[r['user']]=='evaluation']
        row=dict(method=method,planned=len(users)*repeats,completed=len(ok),failed=len(failed),pending=len(users)*repeats-len(ok)-len(failed),
            success=ratio(len(ok),len(ok)+len(failed)),level_distribution=dict(Counter('근거 부족' if r['result']['level'] is None else str(r['result']['level']) for r in ok)),
            eval_completed=len(evalok),lv_consistency=ratio(lvconsistent,len(complete)) if repeats>1 else 'N/A',
            full_output_consistency=ratio(consistent,len(complete)) if repeats>1 else 'N/A',
            mean_seconds=statistics.mean(times) if times else None,p95_seconds=times[max(0,math.ceil(.95*len(times))-1)] if times else None,
            logical_calls=sum(len(r['call_keys']) for r in ok),
            citation_issues=sum(len(r['issues']) for r in ok),accuracy=None,cost=None)
        rows.append(row)
    save(out/'summary.json',rows)
    with (out/'comparison.csv').open('w') as f:
        w=csv.DictWriter(f,fieldnames=rows[0]); w.writeheader(); w.writerows(rows)
    lines=[f'# A~E 벤치마크: {mode}', '', '**synthetic / draft. 실제 사용자 정확도 또는 우승을 의미하지 않음.**',
        f'사용자 {len(users)}명 × {repeats}회 × 5구성. 반복은 독립 사용자 수가 아님.',
        ('mock 응답에는 의도적 잘못된 인용과 B의 LV5 응답이 삽입됨. 이를 실제 모델 성능으로 해석하지 말 것.' if mode=='mock' else 'live는 실제 모델 응답, replay는 저장 응답 재생이다. 사람 검토 정답과는 구분한다.'), '',
        '| 구성 | 완료/계획 | 오류 | 대기 | LV 반복 일치 | 논리 호출 | 평균/95백분위 실행 초 |',
        '|---|---:|---:|---:|---|---:|---|']
    for r in rows:
        timing=f"{r['mean_seconds']:.4f}/{r['p95_seconds']:.4f}" if r['mean_seconds'] is not None else 'N/A'
        lines.append(f"| {r['method']}. {METHOD_NAMES[r['method']]} | {r['completed']}/{r['planned']} | {r['failed']} | {r['pending']} | {r['lv_consistency']} | {r['logical_calls']} | {timing} |")
    lines += ['',f"호출 원장: {len(calls)}회 ({sum(c['status']=='ok' for c in calls)} 성공). mock은 실제 API 요청 0회. replay는 저장 응답을 재사용하며 API 요청 0회.",
        'C의 추출 호출을 D/E와 공유한다. 논리 호출 수에는 각 후보의 공유 추출을 각각 포함; 실제 원장은 중복 제외.',
        '시간은 로컬 실행 벽시계이며 mock/replay 시간은 실제 모델 지연을 나타내지 않음. 재개 시 캐시 적중 시간과 최초 실행 시간도 다름.', '',
        '## 품질·비용', '',
        'LV/조건별 정확도, 과대·과소 인정, 의미적 근거 정확성, 불필요 보류, 검토 교정/훼손률: **N/A — 사람 검토 정답 없음**.',
        '비용: **N/A**. 가격·과금 미확인. tokens는 calls.jsonl의 공급자 usage이며 mock/replay 원시 usage 없는 값은 null.',
        '재평가 정확도: **N/A — 현재 자료는 최초 제출 묶음**. LV3~5 실제 활용 긍정 사례 부족.',
        '전체/개발/평가 결과는 results.jsonl의 split으로 구분. 기준별 상태, 검토 전후, 인용 오류, 입력 파일 범위를 보존.',
        'E는 unknown을 포함하는 보수적 선택 규칙이므로 모든 사례가 검토 대상으로 잡힐 수 있음. 비용 절감 효과를 보장하지 않음.',
        '순수 규칙 A는 AST/해시/로그의 사실만 일부 인정하며 의미적 조건/개인 귀속은 보류. 규칙 방식 전체의 성능 대표가 아님.',
        '**우승 선정 없음.** 품질 gate·가격·사람 검토·실제 호출 비교 후 초기 후보 선정.']
    (out/'RESULTS.md').write_text('\n'.join(lines)+'\n')


def main():
    p=argparse.ArgumentParser(); p.add_argument('--mode',choices=['mock','replay','live'],required=True)
    p.add_argument('--output',required=True,type=Path); p.add_argument('--replay-source',type=Path)
    p.add_argument('--limit',type=int,default=20); p.add_argument('--repeats',type=int,default=3)
    p.add_argument('--provider',choices=['proxy','gemini'],default='proxy')
    args=p.parse_args()
    if args.provider=='gemini':
        PLAN.update(provider='gemini',model='gemini-3.8-flash',sampling='provider_default; JSON mime; no fallback')
    if not 1<=args.limit<=20 or not 1<=args.repeats<=3: p.error('limit 1..20, repeats 1..3')
    os.umask(0o077); out=args.output.resolve(); out.mkdir(parents=True,exist_ok=True)
    import fcntl
    with (out/'.lock').open('w') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        users=json.loads((ROOT/'users20.json').read_text())[:args.limit]
        cases=[load_case(u) for u in users]
        manifest=dict(mode=args.mode,plan=PLAN,rubric=VERSION,input_hash=digest(cases),repeats=args.repeats,
            code={f.name:hashlib.sha256(f.read_bytes()).hexdigest() for f in (HERE/'bench.py',HERE/'rubric.py',HERE/'RUBRIC_SOURCE.md')})
        if (out/'manifest.json').exists() and json.loads((out/'manifest.json').read_text())!=manifest: raise StopRun('manifest_changed_use_new_output')
        if args.mode=='replay':
            previous=json.loads((args.replay_source/'manifest.json').read_text())
            if any(previous[k]!=manifest[k] for k in ('plan','rubric','input_hash','repeats','code')): raise StopRun('replay_manifest_mismatch')
        save(out/'manifest.json',manifest)
        adapter=Adapter(args.mode,out,args.replay_source)
        done={r['id'] for r in read_lines(out/'results.jsonl') if r['status']=='ok'}
        splits={r['user_id']:r['split'] for r in json.loads((ROOT/'review_only/design.json').read_text())}
        stop=None
        try:
            for rep in range(args.repeats):
                order=list(cases); random.Random(rep+73).shuffle(order)
                for case in order:
                    case_start=time.monotonic()
                    methods=list(METHODS); random.Random(f"{case['user_id']}:{rep}").shuffle(methods)
                    for method in methods:
                        rid=f"{case['user_id']}:{rep}:{method}"
                        if rid in done: continue
                        start=time.monotonic(); row=dict(id=rid,user=case['user_id'],repeat=rep,method=method,split=splits[case['user_id']],provided_files=sorted(case['files']))
                        try:
                            if time.monotonic()-case_start>PLAN['limits']['seconds_per_user_repeat']: raise StopRun('time_budget')
                            row.update(evaluate(method,case,rep,adapter),status='ok')
                        except Exception as exc:
                            row.update(status='error',error=str(exc) if isinstance(exc,StopRun) else type(exc).__name__)
                            stop=row['error']
                        row['wall_seconds']=time.monotonic()-start; append(out/'results.jsonl',row)
                        report(out,users,args.repeats,args.mode)
                        if stop: raise StopRun(stop)
        except (StopRun,KeyboardInterrupt) as exc:
            stop=str(exc) or 'operator_interrupt'
        finally:
            save(out/'completion.json',dict(status='stopped' if stop else 'completed',reason=stop))
            report(out,users,args.repeats,args.mode)
        print(json.dumps(dict(output=str(out),status='stopped' if stop else 'completed',calls=adapter.attempts)))


if __name__=='__main__': main()
