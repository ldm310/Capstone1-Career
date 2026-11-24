#!/usr/bin/env python3
"""새로 만든 스크립트(verify_agent, identity, run_profile, make_report)의 자체 시험.
네트워크·API 를 쓰지 않는다(HTTP 는 가짜 응답으로 바꿔 끼움). 받은 레포도 쓰지 않고, 임시 폴더에 만든 **합성** git 레포만 쓴다.

Usage: python3 pipeline/selftest.py        (실패가 있으면 종료 코드 1)
"""
import argparse, io, json, os, shutil, subprocess, sys, tempfile, urllib.error
sys.dont_write_bytecode = True                         # pipeline/__pycache__ 를 남기지 않는다
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import identity as ID, make_report as MR, match as MT, run_profile as RP, to_stat as ST, verify_agent as VA

TMP = tempfile.mkdtemp(prefix='career-selftest-')
GITENV = dict(os.environ, GIT_CONFIG_NOSYSTEM='1', GIT_CONFIG_GLOBAL=os.devnull)
RESULTS = []


def check(name, cond, detail=''):
    RESULTS.append((name, bool(cond)))
    print(('  OK   ' if cond else '  FAIL ') + name + (f'  <- {detail}' if detail and not cond else ''))


# ------------------------------------------------------------------ 합성 git 레포
def make_repo(name, commits):
    """commits: [(작성자 이름, 작성자 이메일, {경로: 내용}, 제목[, (커미터 이름, 커미터 이메일)])]"""
    d = os.path.join(TMP, 'repos', name); os.makedirs(d)
    subprocess.run(['git', 'init', '-q', d], env=GITENV, check=True)
    subprocess.run(['git', '-C', d, 'symbolic-ref', 'HEAD', 'refs/heads/main'], env=GITENV, check=True)
    for c in commits:
        an, ae, files, msg = c[:4]; cn, ce = c[4] if len(c) > 4 else (an, ae)
        for p, text in files.items():
            os.makedirs(os.path.dirname(os.path.join(d, p)) or d, exist_ok=True)
            with open(os.path.join(d, p), 'w', encoding='utf-8') as f: f.write(text)
        env = dict(GITENV, GIT_AUTHOR_NAME=an, GIT_AUTHOR_EMAIL=ae, GIT_COMMITTER_NAME=cn, GIT_COMMITTER_EMAIL=ce)
        subprocess.run(['git', '-C', d, 'add', '-A'], env=env, check=True)
        subprocess.run(['git', '-C', d, 'commit', '-q', '--allow-empty', '-m', msg], env=env, check=True)
    return d


PY = 'def f():\n    return 1\n\n\ndef g():\n    return 2\n\n\nx = f()\ny = g()\nprint(x, y)\n'
DEPLOY = ('apiVersion: apps/v1\nkind: Deployment\nmetadata:\n  name: {n}\nspec:\n  replicas: 2\n  strategy:\n    type: RollingUpdate\n    rollingUpdate:\n      maxUnavailable: {mu}\n'
          '  template:\n    spec:\n      containers:\n        - name: {n}\n          image: shop/{n}:latest\n          resources:\n            limits:\n              cpu: 500m\n'
          '          readinessProbe:\n            httpGet:\n              path: /health\n              port: 8080\n')
PROM = 'scrape_configs:\n  - job_name: order\n    metrics_path: /actuator/prometheus\n    static_configs:\n      - targets: ["order:8080"]\n'
ME = ['ldm310', 'DONGMIN LEE']


def test_identity():
    print('[identity] 합성 레포로 이름 고르기')
    r = ID.resolve(make_repo('two-names', [('ldm310', 'a@example.com', {'a.py': PY}, 'a'), ('DONGMIN LEE', 'b@example.com', {'b.py': PY}, 'b'), ('Other', 'o@example.com', {'c.py': PY}, 'c')]), 'ldm310', ME)
    check('내 이름 둘이 다른 이메일 -> 둘 다 고름', r['status'] == 'ok' and sorted(r['mine']) == ['DONGMIN LEE', 'ldm310'] and not r['candidates'], r)
    r = ID.resolve(make_repo('shared-email', [('Teammate', 's@example.com', {'a.py': PY}, 'a'), ('Teammate', 's@example.com', {'b.py': PY}, 'b'), ('ldm310', 's@example.com', {'c.py': PY}, 'c')]), 'ldm310', ME)
    check('내 이름과 남의 이름이 같은 이메일(한 묶음) -> 고르지 않고 후보로', r['status'] == 'uncertain' and not r['mine'] and r['candidates'], r)
    r = ID.resolve(make_repo('other-noreply', [('DONGMIN LEE', '99+someone-else@users.noreply.github.com', {'a.py': PY}, 'a')]), 'ldm310', ME)
    check('이름은 같지만 다른 계정의 noreply 이메일 -> 고르지 않고 후보로', r['status'] == 'uncertain' and not r['mine'] and r['candidates'] == ['DONGMIN LEE'], r)
    r = ID.resolve(make_repo('case-variant', [('Dongmin Lee', 'x@example.com', {'a.py': PY}, 'a'), ('LEE DONGMIN', 'y@example.com', {'b.py': PY}, 'b'), ('Minsu Lee', 't@example.com', {'c.py': PY}, 'c')]), 'ldm310', ME)
    check('대소문자·순서만 다른 이름 -> 후보로만, 성만 같은 사람은 후보 아님', r['status'] == 'uncertain' and sorted(r['candidates']) == ['Dongmin Lee', 'LEE DONGMIN'], r)
    r = ID.resolve(make_repo('my-noreply', [('idongmin', '123+ldm310@users.noreply.github.com', {'a.py': PY}, 'a')]), 'ldm310', ME)
    check('내 계정의 noreply 이메일이면 이름이 달라도 고름', r['mine'] == ['idongmin'], r)
    r = ID.resolve(make_repo('same-email-variant', [('DONGMIN LEE', 'm@example.com', {'a.py': PY}, 'a'), ('DONGMIN LEE', 'm@example.com', {'b.py': PY}, 'b'), ('Dongmin Lee', 'm@example.com', {'c.py': PY}, 'c')]), 'ldm310', ME)
    check('같은 이메일 + 대소문자만 다른 이름 -> 고름', r['mine'] == ['DONGMIN LEE'], r)
    r = ID.resolve(make_repo('nobody', [('Minsu Lee', 't@example.com', {'a.py': PY}, 'a')]), 'ldm310', ME)
    check('내 이름이 없는 레포 -> none, 후보 없음', r['status'] == 'none' and not r['mine'] and not r['candidates'], r)
    r = ID.resolve(make_repo('ai-author', [('ldm310', 'a@example.com', {'a.py': PY}, 'a'), ('Claude', 'noreply@anthropic.com', {'b.py': PY}, 'b', ('ldm310', 'a@example.com'))]), 'ldm310', ME)
    check('AI 가 쓰고 내가 올린 커밋 -> 올린 사람(나)으로 보고 고름', r['mine'] == ['ldm310'] and r['groups'][0]['commits'] == 1 and len(r['groups'][0]['pairs']) == 1, r)
    r = ID.resolve(make_repo('ai-by-other', [('ldm310', 'a@example.com', {'a.py': PY}, 'init'), ('Claude', 'noreply@anthropic.com', {'b.py': PY}, 'b', ('Kim Chulsoo', 'kim@example.com')),
                                             ('dependabot[bot]', '49699333+dependabot[bot]@users.noreply.github.com', {'c.py': PY}, 'bump')]), 'ldm310', ME)
    check('AI 가 쓰고 남이 올린 커밋이 내 묶음에 들어와 있으면 고르지 않음(봇 커밋은 안 봄)', r['status'] == 'uncertain' and not r['mine'] and r['candidates'] == ['ldm310'], r)
    r = ID.resolve(make_repo('renamed', [('DONGMIN LEE', '12345+old-ldm@users.noreply.github.com', {'a.py': PY}, 'a')]), 'ldm310', ME, ['12345+old-ldm@users.noreply.github.com'])
    check('다른 계정 이름의 noreply 라도 --email 로 직접 알려 주면 고름', r['mine'] == ['DONGMIN LEE'], r)
    check('이메일 가리기: 앞 한 글자만, 두 글자 이하면 전부 가림, noreply 는 그대로',
          (ID.mask_email('dongmin@example.com'), ID.mask_email('me@x.dev'), ID.mask_email('1+ldm310@users.noreply.github.com')) == ('d…@example.com', '…@x.dev', '1+ldm310@users.noreply.github.com'))
    r = ID.resolve(make_repo('ctrl-chars', [('ldm310', 'a@example.com', {'a.py': PY}, 'a'), ('Mallory\x1eX', 'm@example.com', {'b.py': PY}, 'b')]), 'ldm310', ME)
    check('작성자 이름에 제어 문자가 든 커밋이 있는 레포는 고르지 않음(사람 묶기를 믿을 수 없음)', r['status'] == 'uncertain' and not r['mine'] and 'note' in r, r)
    r = ID.resolve(make_repo('short-login', [('Lee Gildong', 'gildong@example.com', {'a.py': PY}, 'a'), ('lee', 'x@example.com', {'b.py': PY}, 'b')]), 'lee', ['lee'])
    check('짧은 계정 이름은 낱말이 같을 때만 실마리로(Lee Gildong 은 후보, 고르는 것은 lee 뿐)', r['mine'] == ['lee'] and r['candidates'] == ['Lee Gildong'], r)
    repo = make_repo('given-email', [('idongmin', 'me@example.com', {'a.py': PY}, 'a')])
    check('--email 로 알려 준 이메일이면 고름 / 안 알려 주면 안 고름', ID.resolve(repo, 'ldm310', ME, ['me@example.com'])['mine'] == ['idongmin'] and not ID.resolve(repo, 'ldm310', ME)['mine'])
    r = ID.resolve(make_repo('name-in-email', [('이동민', 'dongmin.dev@example-host.local', {'a.py': PY}, 'a')]), 'ldm310', ME)
    check('이름은 다르지만 이메일에 내 이름 낱말이 든 경우 -> 후보로만', r['status'] == 'uncertain' and r['candidates'] == ['이동민'], r)


# ------------------------------------------------------------------ 점검 호출(가짜 HTTP)
class Resp:
    def __init__(self, body): self.b = json.dumps(body).encode('utf-8'); self.headers = {'request-id': 'req_selftest'}
    def read(self): return self.b
    def __enter__(self): return self
    def __exit__(self, *a): return False


def api_ok(text, stop='end_turn', **kw):
    return dict(content=[dict(type='thinking', thinking='', signature='s'), dict(type='text', text=text)], stop_reason=stop, usage=dict(input_tokens=1000, output_tokens=200), **kw)


def api_err(code, etype='api_error', headers=None):
    return urllib.error.HTTPError('u', code, 'm', headers or {}, io.BytesIO(json.dumps(dict(type='error', error=dict(type=etype, message='msg'))).encode('utf-8')))


def packets(n):
    return [dict(id=f'{i:04d}', repo='x/y', judgment='캐시 도입', lv=3, claim='c', person='p', evidence=f'a.py:{i + 1}', path='a.py', snippet='>>    1 x = 1') for i in range(n)]


def answers(ids, verdict='pass'):
    return json.dumps([dict(id=i, verdict=verdict, reason_code=None, reason='r') for i in ids], ensure_ascii=False)


def fake_verify(script, n=3, **kw):
    """script: 차례로 돌려줄 응답(dict) 또는 던질 오류 -> (보낸 요청 본문들, agent_output, info) 또는 (본문들, None, 예외)"""
    sent, led = [], os.path.join(TMP, f'ledger{len(RESULTS)}.json')

    def fake(req, timeout=None, context=None):
        sent.append((json.loads(req.data.decode('utf-8')), dict(req.header_items())))
        r = script.pop(0) if script else api_err(500)
        if isinstance(r, Exception): raise r
        return Resp(r)
    real_open, real_sleep = VA.urllib.request.urlopen, VA.time.sleep
    VA.urllib.request.urlopen, VA.time.sleep = fake, lambda s: None
    try:
        out, info = VA.verify(packets(n), 'TEST-KEY', ledger=led, log=lambda s: None, **kw)
        return sent, out, info
    except VA.Unavailable as e:
        return sent, None, e
    finally:
        VA.urllib.request.urlopen, VA.time.sleep = real_open, real_sleep


def test_verify():
    print('[verify_agent] 가짜 HTTP 응답')
    sent, out, info = fake_verify([api_ok(answers(['0000', '0001', '0002']))])
    body, hdr = sent[0]
    with open(os.path.join(HERE, 'verifier_prompt.md'), encoding='utf-8') as f: prompt = f.read()
    check('요청: 지시문 전체가 system 그대로, 사용자 글은 packet JSON 배열 하나, 도구 없음, 모델 claude-haiku-5-5',
          body['system'] == prompt and json.loads(body['messages'][0]['content']) == packets(3) and len(body['messages']) == 1 and 'tools' not in body and body['model'] == 'claude-haiku-5-5'
          and sorted(body) == ['max_tokens', 'messages', 'model', 'output_config', 'system'], sorted(body))
    check('요청 헤더: x-api-key, anthropic-version', {k.lower(): v for k, v in hdr.items()}.get('x-api-key') == 'TEST-KEY' and {k.lower(): v for k, v in hdr.items()}.get('anthropic-version') == VA.API_VERSION)
    check('정상 응답 -> 답 3건', [x['verdict'] for x in out] == ['pass'] * 3 and info['complete'] and not info['missing'])
    leds = [open(os.path.join(TMP, f), encoding='utf-8').read() for f in os.listdir(TMP) if f.startswith('ledger')]
    check('기록(info, 비용 장부)에 키가 남지 않음', 'TEST-KEY' not in json.dumps(info) and leds and all('TEST-KEY' not in x for x in leds))
    _, out, info = fake_verify([api_ok('```json\n' + answers(['0000', '0001', '0002']) + '\n```')])
    check('```json 블록 하나에 든 배열은 받음', len(out) == 3)
    _, out, info = fake_verify([api_ok('결과입니다:\n' + answers(['0000', '0001', '0002']))])
    check('배열 앞에 글이 붙은 응답은 버림 -> 답 없음(파이프라인에서 unsure). 호출 실패로는 세지 않음', out == [] and info['missing'] == ['0000', '0001', '0002'] and not info['complete'] and info['failed_calls'] == 0)
    _, out, info = fake_verify([api_ok(answers(['0000'])[:20], stop='max_tokens')], n=1)
    check('잘린 응답(max_tokens)은 버림(1건짜리는 더 나누지 않음)', out == [] and len(info['missing']) == 1 and not info['complete'])
    _, out, info = fake_verify([api_ok('', stop='refusal', stop_details=dict(type='refusal', category='cyber'))])
    check('거절(refusal)은 버림', out == [] and len(info['missing']) == 3)
    _, out, info = fake_verify([api_ok(json.dumps([dict(id='0000', verdict='pass'), dict(id='9999', verdict='pass'), dict(id='0001', verdict='maybe'), 'x', dict(id='0002', verdict='reject', reason_code='R9', reason=5)]))])
    check('모르는 id·틀린 verdict 항목만 버리고 나머지는 받음', [(x['id'], x['verdict'], x['reason_code'], x['reason']) for x in out] == [('0000', 'pass', None, ''), ('0002', 'reject', None, '')] and info['missing'] == ['0001'])
    _, out, info = fake_verify([api_ok(json.dumps([dict(id='0000', verdict='pass'), dict(id='0000', verdict='reject', reason_code='R1'), dict(id='0001', verdict='unsure')]))])
    check('같은 id 에 서로 다른 답 -> 그 id 는 버림(통과로 올리지 않음)', [x['id'] for x in out] == ['0001'])
    sent, out, info = fake_verify([api_err(429, 'rate_limit_error', {'retry-after': '1'}), api_ok(answers(['0000', '0001', '0002']))])
    check('429 는 다시 불러 성공', len(sent) == 2 and len(out) == 3)
    sent, out, info = fake_verify([api_err(500), api_err(500), api_err(500), api_ok(answers(['0002']))], batch=2)
    check('5xx 가 계속되면 그 묶음만 답 없음으로 두고 다음 묶음 계속', len(sent) == 4 and [x['id'] for x in out] == ['0002'] and info['missing'] == ['0000', '0001'] and not info['complete'] and info['failed_calls'] == 1)
    sent, out, err = fake_verify([api_err(401, 'authentication_error')])
    check('401 은 Unavailable(다시 부르지 않음)', out is None and isinstance(err, VA.Unavailable) and len(sent) == 1 and 'TEST-KEY' not in str(err))
    sent, out, info = fake_verify([api_ok(answers(['0000', '0001'])), api_err(401, 'authentication_error')], batch=2)
    check('앞 묶음 성공 뒤 401 -> 받은 답은 남기고 멈춤', [x['id'] for x in out] == ['0000', '0001'] and info['stopped'] and info['missing'] == ['0002'])
    sent, out, info = fake_verify([api_ok(answers([f'{i:04d}' for i in range(50)])), api_ok(answers([f'{i:04d}' for i in range(50, 60)]))], n=60)
    check('60건 -> 50건 + 10건으로 나눠 보냄', [len(json.loads(b['messages'][0]['content'])) for b, _ in sent] == [50, 10] and len(out) == 60)
    sent, out, info = fake_verify([api_ok(answers(['0000', '0001', '0002']))], batch=500)
    check('--batch 를 50보다 크게 줘도 50개 이하', len(sent) == 1 and VA.split_batches(packets(120), min(500, VA.BATCH))[0].__len__() == 50)
    sent, out, info = fake_verify([api_ok(answers(['0000', '0001', '0002']))], cap_usd=0.00001)
    check('비용 한도를 넘게 되면 부르지 않음', len(sent) == 0 and info['stopped'] and info['stopped'].startswith('비용 한도'))
    sent, out, info = fake_verify([api_ok('oops'), api_ok(answers(['0000', '0001', '0002']))], retry_malformed=1)
    check('--retry-malformed 1 이면 형식 깨진 응답을 한 번 다시 받음', len(sent) == 2 and len(out) == 3)
    why = {}
    got = VA.parse_output(json.dumps([dict(id='v000', verdict='pass'), dict(id='0001', verdict='PASS'), 7]), {'0000', '0001'}, why)
    check('항목을 버린 까닭과 모델이 돌려준 id·verdict 보기를 남기고, 받아들일 항목이 하나도 없으면 깨진 응답으로 봄',
          got == ([], '받아들일 항목이 하나도 없음', 3) and why.get('counts') == {'id 가 보낸 packet 에 없음': 1, 'verdict 가 pass/reject/unsure 가 아님': 1, '항목이 객체가 아님': 1} and why.get('samples') == ["'v000'", "'PASS'"], (got, why))
    sent, out, info = fake_verify([api_ok(answers(['v000', 'v001', 'v002']))])
    check('답은 왔는데 id 가 모두 안 맞으면 응답을 버리고(전부 답 없음), 호출 기록에 까닭을 남김',
          out == [] and info['missing'] == ['0000', '0001', '0002'] and not info['complete'] and info['batches'][0]['outcome'] == '응답 버림'
          and info['batches'][0]['tries'][0]['dropped_why']['counts'] == {'id 가 보낸 packet 에 없음': 3}, info['batches'])
    sent, out, info = fake_verify([api_ok(answers(['v000', 'v001', 'v002'])), api_ok(answers(['0000', '0001', '0002']))], retry_malformed=1)
    check('--retry-malformed 1 이면 그런 응답도 한 번 다시 받음', len(sent) == 2 and len(out) == 3 and info['complete'])
    why = {}
    VA.parse_output(json.dumps([dict(id='x' * 50 + str(i), verdict='pass') for i in range(12)] + [dict(id='\x1b[31mA\nB', verdict='pass')]), {'0000'}, why)
    check('버린 항목의 보기는 8개·20자까지만, 제어 문자는 글자로 바꿔 남김', len(why['samples']) == 8 and all(len(x) <= 20 for x in why['samples']) and why['counts'] == {'id 가 보낸 packet 에 없음': 13}
          and '\x1b' not in repr(VA.parse_output(json.dumps([dict(id='\x1b[31mA', verdict='pass')]), {'0000'}, why2 := {}) and why2['samples'][0]).replace('\\x1b', ''), why)
    check('빈 배열이나 일부만 답한 응답은 깨진 응답이 아님(답 없는 판정만 모름)', VA.parse_output('[]', {'0000'}) == ([], None, 0) and VA.parse_output(answers(['0000']), {'0000', '0001'})[1] is None)
    sent, out, info = fake_verify([api_ok(answers(['0000', '0001', '0002']))], retry_malformed=-1)
    check('--retry-malformed 가 음수여도 한 번은 부름', len(sent) == 1 and len(out) == 3)
    sent, out, info = fake_verify([api_ok('', stop='refusal'), api_ok(answers(['0000', '0001', '0002']))], retry_malformed=2)
    check('거절은 같은 요청을 다시 보내지 않음', len(sent) == 1 and out == [])
    sent, out, info = fake_verify([api_ok('[', stop='max_tokens'), api_ok(answers(['0000', '0001'])), api_ok(answers(['0002', '0003']))], n=4)
    check('잘린 묶음은 반으로 나눠 다시 보냄', [len(json.loads(b['messages'][0]['content'])) for b, _ in sent] == [4, 2, 2] and len(out) == 4 and info['complete'])
    sent, out, info = fake_verify([api_err(413, 'request_too_large'), api_ok(answers(['0000'])), api_ok(answers(['0001']))], n=2)
    check('413(묶음이 너무 큼)도 반으로 나눠 다시 보냄', len(sent) == 3 and len(out) == 2)
    sent, out, info = fake_verify([api_err(520), api_ok(answers(['0000', '0001', '0002']))])
    check('목록에 없는 5xx(520)도 다시 부름', len(sent) == 2 and len(out) == 3)
    sent, out, err = fake_verify([OSError('boom')] * 9)
    check('모든 호출이 실패하면 Unavailable(점검을 못 한 것으로 알림)', out is None and isinstance(err, VA.Unavailable))
    sent, out, info = fake_verify([urllib.error.HTTPError('u', 502, 'm', {}, io.BytesIO(b'{"error": "upstream connect error"}')), api_ok(answers(['0000', '0001', '0002']))])
    check('오류 본문의 error 가 글자여도 죽지 않고 다시 부름', len(sent) == 2 and len(out) == 3)
    leak = []
    for bad in ('abc123\n# note', 'ab cd', '', 'ab\u201cx\u201d'):
        try:
            VA.verify(packets(1), bad, ledger=os.path.join(TMP, 'ledger-bad.json'), log=lambda s: None); leak.append('통과됨')
        except VA.Unavailable as e:
            if bad.strip() and bad in str(e): leak.append('키가 오류 글에 있음')
    check('공백·줄바꿈·ASCII 밖 글자가 든 키는 부르기 전에 거절하고 값은 찍지 않음', not leak, leak)
    try:
        VA.verify(packets(1), 'TEST-KEY', model='no-such-model', ledger=os.path.join(TMP, 'ledger-bad.json'), log=lambda s: None); ok = False
    except VA.Unavailable:
        ok = True
    check('가격표에 없는 모델은 비용 한도를 계산할 수 없어 거절', ok)
    big = [dict(packets(1)[0], id=f'{i:04d}', snippet='가' * 30000) for i in range(6)]
    check('묶음 크기 상한(120KB)으로도 나눔', [len(b) for b in VA.split_batches(big)] == [1, 1, 1, 1, 1, 1] and [len(b) for b in VA.split_batches(packets(7))] == [7])
    check('비용 계산: 10만 토큰 이하/초과 요금표', abs(VA.cost_usd('claude-haiku-5-5', dict(input_tokens=100_000, output_tokens=10_000)) - 0.015) < 1e-9 and abs(VA.cost_usd('claude-haiku-5-5', dict(input_tokens=100_001, output_tokens=10_000)) - 0.0750005) < 1e-9)
    env = os.path.join(TMP, 'env-test'); saved = os.environ.pop('ANTHROPIC_API_KEY', None)
    try:
        with open(env, 'w') as f: f.write('# c\nOTHER=1\nexport ANTHROPIC_API_KEY="abc-123"\n')
        check('.env 의 ANTHROPIC_API_KEY 줄 읽기(export·따옴표)', VA.load_key(env) == ('abc-123', '.env') and VA.load_key(os.path.join(TMP, 'nope')) == (None, None))
        got = []
        for text in ('ANTHROPIC_API_KEY=k1 # 주석\n', 'ANTHROPIC_API_KEY="k2" # 주석\n', 'ANTHROPIC_API_KEY = k3\n', '\ufeffANTHROPIC_API_KEY=k4\r\n', 'ANTHROPIC_API_KEY=old\nANTHROPIC_API_KEY=k5\n', "export\tANTHROPIC_API_KEY='k6'\n",
                     'ANTHROPIC_API_KEY=\nOTHER=1\n'):
            with open(env, 'w', encoding='utf-8') as f: f.write(text)
            got.append(VA.load_key(env)[0])
        check('.env: 줄 끝 주석, = 양쪽 공백, BOM·CRLF, 같은 줄이 둘이면 마지막, 빈 값', got == ['k1', 'k2', 'k3', 'k4', 'k5', 'k6', None], got)
        os.environ['ANTHROPIC_API_KEY'] = 'from-env'
        check('환경 변수가 .env 보다 먼저', VA.load_key(env) == ('from-env', 'env'))
    finally:
        os.environ.pop('ANTHROPIC_API_KEY', None)
        if saved is not None: os.environ['ANTHROPIC_API_KEY'] = saved


# ------------------------------------------------------------------ 프로필 실행 조각
def ns(**kw):
    base = dict(name=ME, email=[], timeout=600, no_verify=True, keep_packets=False, keep_full_bundle=False, model=VA.MODEL, effort=VA.EFFORT, cap_usd=1.0, ledger=os.path.join(TMP, 'ledger-profile.json'))
    base.update(kw); return argparse.Namespace(**base)


def test_profile():
    print('[run_profile] 주소 읽기, 합성 레포 처리, 내 이름이 둘인 레포')
    check('프로필·레포 주소 읽기', RP.parse_login('https://github.com/ldm310/') == 'ldm310' and RP.parse_login('ldm310') == 'ldm310'
          and RP.parse_repo('https://github.com/synthetic-org2/Synthetic_agent.git') == 'synthetic-org2/Synthetic_agent' and RP.parse_repo('a/b') == 'a/b'
          and RP.parse_repo('https://github.com/ldm310/.github') == 'ldm310/.github' and RP.parse_repo('SyntheticCo/_s') == 'SyntheticCo/_s')
    bad = 0
    for s_ in ('not a url', 'https://github.com/a', 'a/b;rm -rf x', 'a/..', '../b', 'https://github.com/a/$(id)', '-x/b', 'a/b c'):
        try:
            RP.parse_repo(s_)
        except ValueError:
            bad += 1
    check('이상한 레포 주소는 거절(셸·경로로 넘어가지 않게)', bad == 8, bad)
    repo = make_repo('shop', [('ldm310', 'a@example.com', {'k8s/order-deployment.yaml': DEPLOY.format(n='order', mu=0)}, 'infra: order'),
                              ('DONGMIN LEE', 'b@example.com', {'k8s/pay-deployment.yaml': DEPLOY.format(n='pay', mu=1), 'monitoring/prometheus.yml': PROM}, 'infra: pay'),
                              ('Other Person', 'o@example.com', {'src/other.py': PY}, 'feat: other')])
    RP.harden_env()
    A, B = 'synthetic/shop#ldm310', 'synthetic/shop#DONGMIN LEE'
    odir = os.path.join(TMP, 'out', 'shop'); rec = dict(label='synthetic/shop', repo='synthetic/shop')
    mbs, rows = RP.process(rec, repo, odir, ns(), None, 'ldm310', 'ldm310')
    check('합성 레포(--no-verify): 내 이름 둘을 고르고 이름마다 bundle 을 따로 만들되 사람 이름은 하나로 맞춤. packet 4건은 세기만 하고 저장 안 함',
          rec['status'] == 'ok' and sorted(rec['mine']) == ['DONGMIN LEE', 'ldm310'] and rec['packets'] == 4 and rec['answered'] == 0 and rows == [] and sorted(mb['meta']['repo'] for mb in mbs) == sorted([A, B])
          and {e['person'] for mb in mbs for e in mb['evidence'] + mb['weak']} == {'ldm310'} and sum(len(mb['evidence']) for mb in mbs) == rec['evidence']
          and not os.path.exists(os.path.join(odir, 'packets.json')) and sorted(os.path.basename(f) for f in rec['_files']) == ['bundle.mine.1.json', 'bundle.mine.2.json'], rec)
    saved = json.dumps([json.load(open(f, encoding='utf-8')) for f in rec['_files']], ensure_ascii=False)
    check('저장한 파일에는 다른 기여자의 이름·근거가 없음(기본). --keep-full-bundle 일 때만 통째로 남김', 'Other Person' not in saved and not os.path.exists(os.path.join(odir, 'bundle.json'))
          and RP.process(dict(label='synthetic/shop', repo='synthetic/shop'), repo, os.path.join(TMP, 'out', 'shop-full'), ns(keep_full_bundle=True), None, 'ldm310', 'ldm310')
          and 'Other Person' in open(os.path.join(TMP, 'out', 'shop-full', 'bundle.json'), encoding='utf-8').read())
    stat = ST.build_stat(mbs, 'ldm310', {})
    check('맞춘 bundle 로 stat 이 만들어짐(규칙만)', stat['stat'].get('무중단 배포', {}).get('lv') == 5 and stat['stat'].get('Kubernetes 운영 설정', {}).get('lv') == 4 and stat['stat'].get('모니터링 설정', {}).get('lv') == 3, list(stat['stat']))
    calls = []

    def canned(pk, key, **kw):
        """무중단 배포는 답 없음, 모니터링 설정은 기각, Kubernetes 운영 설정은 ldm310 것만 통과하고 DONGMIN LEE 것은 기각"""
        calls.append(len(pk)); out = []
        for p in pk:
            if p['judgment'] == '무중단 배포': continue
            rej = p['judgment'] == '모니터링 설정' or p['person'] == 'DONGMIN LEE'
            out.append(dict(id=p['id'], verdict='reject' if rej else 'pass', reason_code='R3' if rej else None, reason='시험-기각' if rej else '시험-통과'))
        return out, dict(complete=True, packets_sha256=RP.hashlib.sha256(json.dumps(pk, ensure_ascii=False, sort_keys=True).encode('utf-8')).hexdigest(),
                         prompt_sha256=RP.hashlib.sha256(open(os.path.join(HERE, 'verifier_prompt.md'), encoding='utf-8').read().encode('utf-8')).hexdigest(), model=VA.MODEL, effort=VA.EFFORT, usd=0.001, stopped=None)
    real = VA.verify; VA.verify = canned
    try:
        odir2 = os.path.join(TMP, 'out', 'shop-verify'); rec = dict(label='synthetic/shop', repo='synthetic/shop')
        mbs, rows = RP.process(rec, repo, odir2, ns(no_verify=False), 'TEST-KEY', 'ldm310', 'ldm310')
        v = {(r['repo'], r['key']): r['verdict'] for r in rows}
        check('점검 경로: 판정이 근거마다(이름마다) 따로 붙음. 수는 packet 하나하나로 셈',
              v == {(A, '무중단 배포'): 'unsure', (A, 'Kubernetes 운영 설정'): 'pass', (B, 'Kubernetes 운영 설정'): 'reject', (B, '모니터링 설정'): 'reject'}
              and rec['verdicts'] == dict(**{'pass': 1}, reject=2, unsure=1) and rec['missing'] == 1 and rec['answered'] == 3 and len({r['repo'] + r['key'] for r in rows}) == 4, (v, rec))
        stat = ST.build_stat(mbs, 'ldm310', {(r['repo'], r['person'], r['key']): r['verdict'] for r in rows})
        k8s = stat['stat'].get('Kubernetes 운영 설정', {})
        check('stat: 한 이름의 근거가 기각돼도 다른 이름의 통과한 근거는 남고, 기각은 빠지고, 답 없는 것은 정황으로',
              k8s.get('lv') == 4 and [e['repo'] for e in k8s['evidence']] == [A] and '모니터링 설정' not in stat['stat'] and '무중단 배포' not in stat['stat'] and '무중단 배포' in stat['weak']
              and stat['stat']['Kubernetes']['lv'] <= 4, (list(stat['stat']), stat['weak'], k8s))
        cli = subprocess.run([sys.executable, os.path.join(HERE, 'to_stat.py')] + rec['_files'] + ['--person', 'ldm310', '--verdicts', os.path.join(odir2, 'verdicts.json')],
                             capture_output=True, text=True, encoding='utf-8', env=dict(os.environ, PYTHONIOENCODING='utf-8', PYTHONDONTWRITEBYTECODE='1')).stdout
        check('저장된 bundle.mine.*.json 과 verdicts.json 을 to_stat.py 에 넣어도 같은 stat', json.loads(cli) == stat, cli[:200])
        rec = dict(label='synthetic/shop', repo='synthetic/shop'); RP.process(rec, repo, odir2, ns(no_verify=False), 'TEST-KEY', 'ldm310', 'ldm310')
        check('같은 packet 이면 저장된 답을 다시 씀(다시 부르지 않음)', calls == [4] and rec['verify'] == '저장된 답 다시 씀', calls)
        seen = {}

        def quiet(outcome):
            def f(pk, key, **kw):
                seen.update(kw)
                return [], dict(complete=False, failed_calls=0, stopped=None, usd=0.0, batches=[dict(outcome=outcome, tries=[dict(dropped_items=4 if outcome == '응답 버림' else 0)])])
            return f
        VA.verify = quiet('답 받음'); rec = dict(label='synthetic/shop', repo='synthetic/shop')
        RP.process(rec, repo, os.path.join(TMP, 'out', 'shop-quiet'), ns(no_verify=False, retry_malformed=2), 'TEST-KEY', 'ldm310', 'ldm310')
        VA.verify = quiet('응답 버림'); rec2 = dict(label='synthetic/shop', repo='synthetic/shop')
        RP.process(rec2, repo, os.path.join(TMP, 'out', 'shop-dropped'), ns(no_verify=False), 'TEST-KEY', 'ldm310', 'ldm310')
        check('--retry-malformed 가 점검 호출까지 전해지고, 답이 없을 때 상태 글이 까닭(모델이 답하지 않음 / 응답을 버림)에 맞음',
              seen.get('retry_malformed') == 0 and rec['verify'] == '점검함(모델이 답하지 않은 판정은 모름으로 처리)' and rec['answered'] == 0 and rec['missing'] == 4
              and rec2['verify'] == '점검함(버린 응답이 있어 답 없는 판정은 모름으로 처리)', (seen.get('retry_malformed'), rec['verify'], rec2['verify']))
        seen.clear(); VA.verify = quiet('답 받음')
        RP.process(dict(label='synthetic/shop', repo='synthetic/shop'), repo, os.path.join(TMP, 'out', 'shop-quiet2'), ns(no_verify=False, retry_malformed=2), 'TEST-KEY', 'ldm310', 'ldm310')
        check('--retry-malformed 2 를 주면 그 값이 전해짐', seen.get('retry_malformed') == 2, seen.get('retry_malformed'))
    finally:
        VA.verify = real
    empty = os.path.join(TMP, 'repos', 'not-a-repo'); os.makedirs(empty)
    try:
        RP.process(dict(label='x/empty', repo='x/empty'), empty, os.path.join(TMP, 'out', 'empty'), ns(), None, 'ldm310', 'ldm310'); ok = False
    except RuntimeError as e:
        ok = '받은 레포 폴더가 아님' in str(e)
    check('.git 이 없는 폴더는 분석하지 않음(바깥 레포를 대신 읽지 않게)', ok)
    nobody = make_repo('nobody2', [('Minsu Lee', 't@example.com', {'a.py': PY}, 'a')])
    rec = dict(label='synthetic/nobody', repo='synthetic/nobody')
    mbs2, rows2 = RP.process(rec, nobody, os.path.join(TMP, 'out', 'nobody'), ns(), None, 'ldm310', 'ldm310')
    check('내 이름이 없는 레포는 stat 에서 뺌', mbs2 == [] and rows2 == [] and rec['status'] == 'excluded' and rec['people'] == ['Minsu Lee'], rec)
    # 보고서 표: 위 결과로 작은 결과 폴더를 꾸며 죽지 않고 나오는지
    d = os.path.join(TMP, 'out', 'profile'); os.makedirs(d)
    ok = dict(label='synthetic/shop', status='ok', head='0' * 40, mine=['ldm310', 'DONGMIN LEE'], evidence=8, packets=4, answered=3, verify='점검함', verdicts=dict(**{'pass': 1}, reject=2, unsure=1), missing=1, clone='새로 받음')
    run = dict(profile='ldm310', canonical='ldm310', names=ME, verify=True, model=VA.MODEL, effort=VA.EFFORT, listing=dict(ok=True, n=2), skipped=[dict(repo='a/b', reason='포크')], usd=0.001, finished='2026-01-01T00:00:00+0900',
               targets=[ok, dict(label='synthetic/nobody', status='excluded', reason='내 이름으로 볼 근거가 없음', head='1' * 40, people=['Minsu Lee']), dict(label='x/y', status='failed', stage='받기(clone.sh)', reason='받기 실패')])
    posts = dict(postings=[dict(posting_id='1', company='회사', title='제목', position='자리', link='http://x', career='신입', lines=[
        dict(line_id='1', section='자격요건', text='Kubernetes 운영 경험 <b>|</b>', lv_line=4, lv_final=4, excluded=False, undecided=False, career_rule=None, tools=['Kubernetes'], activities=['Kubernetes 운영 설정'], scale=False),
        dict(line_id='2', section='우대사항', text='성실한 분', lv_line=0, lv_final=0, excluded=False, undecided=False, career_rule=None, tools=[], activities=[], scale=False)])])
    RP.dump(os.path.join(d, 'run.json'), run); RP.dump(os.path.join(d, 'stat.json'), stat); RP.dump(os.path.join(d, 'verdicts.json'), rows)
    RP.dump(os.path.join(d, 'identity.json'), {'synthetic/nobody': ID.resolve(nobody, 'ldm310', ME)}); RP.dump(os.path.join(d, 'match.json'), MT.match_all(stat, posts))
    try:
        MR.profile_sections(os.path.join(TMP, 'out', 'shop-verify')); ok2 = False      # run.json 이 없는 폴더
    except SystemExit:
        ok2 = True
    RP.dump(os.path.join(d, 'run.json'), dict(run, aborted='점검 호출을 쓸 수 없음(시험)'))
    try:
        MR.profile_sections(d); ok3 = False
    except SystemExit:
        ok3 = True
    check('끝까지 못 간 실행(중단 표시)이나 run.json 이 없는 폴더로는 보고서를 만들지 않음', ok2 and ok3)
    RP.dump(os.path.join(d, 'run.json'), run)
    text = MR.profile_sections(d)
    miss = [w for w in [f'## {i}.' for i in range(1, 7)] + ['시험-기각', '무중단 배포', '맞음/틀림', '받기 실패', 'Minsu Lee', '포크', '답 없음', '&lt;b&gt;\\|&lt;/b&gt;'] if w not in text]
    check('보고서 표가 만들어짐: 1~6번 제목, 기각 이유, 정황, 빈 맞음/틀림 칸, 실패·제외 레포, 자료 속 꺾쇠·세로줄은 글자로', not miss and '시험-통과' not in text.split('## 4.')[1].split('## 5.')[0], miss)


def test_main():
    print('[run_profile] main() 전체 흐름(목록·받기는 가짜, 분석은 합성 레포로 실제 실행, --no-verify)')
    shop = make_repo('m-shop', [('ldm310', 'a@example.com', {'k8s/order-deployment.yaml': DEPLOY.format(n='order', mu=0), 'app.py': PY}, 'infra: order')])
    other = make_repo('m-other', [('Minsu Lee', 't@example.com', {'a.py': PY}, 'a')])
    extra = make_repo('m-extra', [('DONGMIN LEE', 'b@example.com', {'monitoring/prometheus.yml': PROM, 'b.py': PY}, 'mon')])
    listing = [dict(full_name='me/shop', fork=False, private=False, size=10, default_branch='main', pushed_at='2026-01-01T00:00:00Z'),
               dict(full_name='me/forked', fork=True, private=False, size=10), dict(full_name='me/secret', fork=False, private=True, size=10),
               dict(full_name='me/other', fork=False, private=False, size=10), dict(full_name='me/broken', fork=False, private=False, size=0)]
    dirs = {'me/shop': shop, 'me/other': other, 'org/extra': extra}

    def fake_gh(path, ctx):
        if path == '/repos/org/extra': return dict(private=False, fork=True, size=5, default_branch='main', pushed_at='2026-01-02T00:00:00Z')
        raise urllib.error.HTTPError('u', 404, 'Not Found', {}, io.BytesIO(b'{}'))

    def fake_clone(full, repos_dir, timeout):
        if full not in dirs: raise RuntimeError('받기 실패: (시험) 커밋이 없음')
        return dirs[full], False
    out = os.path.join(TMP, 'out', 'main'); posts = os.path.join(TMP, 'posts.json')
    RP.dump(posts, dict(postings=[dict(posting_id='1', company='회사', title='제목', position='자리', link='http://x', career='신입', lines=[
        dict(line_id='1', section='자격요건', text='Python 개발 경험', lv_line=1, lv_final=1, excluded=False, undecided=False, career_rule=None, tools=['Python'], activities=[], scale=False)])]))
    saved = (RP.list_repos, RP.gh, RP.clone, sys.argv, dict(os.environ))
    RP.list_repos, RP.gh, RP.clone = (lambda login, ctx: listing), fake_gh, fake_clone
    sys.argv = ['run_profile.py', 'https://github.com/me', '--repo', 'https://github.com/org/extra', '--repo', 'https://github.com/org/gone', '--repo', 'https://github.com/ME/SHOP', '--repo', 'not a url',
                '--name', 'ldm310', '--name', 'DONGMIN LEE', '--out', out, '--repos-dir', os.path.join(TMP, 'main-repos'), '--postings', posts, '--no-verify']
    try:
        RP.main()
    finally:
        RP.list_repos, RP.gh, RP.clone, sys.argv = saved[:4]
        os.environ.clear(); os.environ.update(saved[4])
    run, stat = RP.load(os.path.join(out, 'run.json')), RP.load(os.path.join(out, 'stat.json'))
    skip = {x['repo']: x['reason'] for x in run['skipped']}; tg = {t['label']: t for t in run['targets']}
    check('포크·비공개는 받지 않음, 없는 레포·이상한 주소는 건너뛰고 이유를 적음', skip.get('me/forked') == '포크' and skip.get('me/secret') == '비공개' and '없거나 비공개' in skip.get('org/gone', '') and 'not a url' in skip, skip)
    check('직접 준 레포는 포크여도 넣음, 목록과 겹치는 주소(대소문자만 다름)는 한 번만', tg.get('org/extra', {}).get('status') == 'ok' and sum(1 for t in run['targets'] if t['label'].lower() == 'me/shop') == 1, list(tg))
    check('레포 하나가 실패해도 다음 레포로 넘어가고 이유를 적음', tg['me/broken']['status'] == 'failed' and '받기 실패' in tg['me/broken']['reason'] and tg['me/other']['status'] == 'excluded' and tg['me/shop']['status'] == 'ok', tg['me/broken'])
    check('레포마다 다른 내 이름(ldm310 / DONGMIN LEE)을 하나로 맞춰 stat 하나로', stat['person'] == 'me' and stat['repos'] == ['me/shop', 'org/extra'] and tg['me/shop']['mine'] == ['ldm310'] and tg['org/extra']['mine'] == ['DONGMIN LEE']
          and {'무중단 배포', '모니터링 설정', 'Python', 'Git'} <= set(stat['stat']) and run['verify'] is False and run['n_ok'] == 2 and run['n_failed'] == 1 and run['n_excluded'] == 1, (stat['repos'], list(stat['stat'])))
    cli = subprocess.run([sys.executable, os.path.join(HERE, 'to_stat.py')] + [os.path.join(out, x) for x in run['stat_inputs']] + ['--person', 'me', '--verdicts', os.path.join(out, 'verdicts.json')],
                         capture_output=True, text=True, encoding='utf-8', env=dict(os.environ, PYTHONIOENCODING='utf-8', PYTHONDONTWRITEBYTECODE='1')).stdout
    check('저장된 입력을 to_stat.py 에 넣으면 같은 stat.json', cli == open(os.path.join(out, 'stat.json'), encoding='utf-8').read())
    text = MR.profile_sections(out)
    check('그 결과로 보고서 표가 만들어짐(점검 없이 돌림 표시 포함)', '점검 없이 돌림' in text and 'me/broken' in text and 'Minsu Lee' in text and '포크' in text)


def test_report():
    print('[make_report] 공고 표의 빠진 줄·동률 설명, 후보 이름 구분, 근거만 달라진 키, 낮은 LV 근거 표시, 7·8번과 보고서 조립')

    def post(pid, rate, judged, ok=None, title='제목'):
        return dict(posting_id=pid, company='회사', title=title, position='자리', link='http://x', career='신입', career_note=None, lines=[],
                    summary={'충족': judged if ok is None else ok, '기법 충족': 0, '부분': 0, '미충족': 0, '판단 불가': 0, 'judged': judged, 'rate': rate, 'rate_with_technique': rate})
    pool = [post('a', 1.0, 6), post('b', 1.0, 1), post('c', 1.0, 1), post('d', 1.0, 1), post('e', 0.5, 6, 3), post('f', 0.5, 6, 3, 'x' * 43), post('g', None, 0)]
    t1 = MR.tie_text(pool, pool[:3], '위 목록의'); t2 = MR.tie_text(pool, pool[:1], '위 목록의')
    check('동률 설명: 마지막 공고와 정렬 키가 같은 공고 수, 목록에 들지 못한 공고 번호', '3개다(b, c, d번)' in t1 and '그중 d번은 위 목록에 들지 못했다' in t1 and '1개다(a번)' in t2 and '모두 위 목록 안에 있다' in t2, (t1, t2))
    many = [post(str(i), 0.5, 6, 3) for i in range(1, 16)]
    t3 = MR.tie_text(many, many[:2], '이 표의', '이 표')
    check('동률 설명: 12개가 넘으면 줄여 적고, 아래 표를 가리킬 때는 「이 표」', '15개다(1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12번 외 3개)' in t3 and '14번 외 1개는 이 표에 들지 못했다' in t3 and '위 목록' not in t3, t3)
    note = MR.postings_note(dict(postings=pool), n=3)
    check('공고 요약: 충족률을 낼 수 있는 공고 수, 5줄 이상 표의 동률 설명은 그 표를 가리킴, 긴 제목은 … 로 줄임',
          '공고는 6개다' in note and '0줄인 공고 1개 제외' in note and '이 표의 3번째(f번)' in note and '2개다(e, f번). 모두 이 표 안에 있다' in note and 'x' * 40 + '… |' in note, note)
    note0 = MR.postings_note(dict(postings=[post('a', 1.0, 1), post('g', None, 0)]), n=5)
    check('공고 요약: 마지막 공고에 충족률이 없으면 그렇게 적고, 5줄 이상 공고가 없으면 표를 만들지 않음', '판정한 줄이 0줄이라 충족률이 없다' in note0 and 'None' not in note0 and '5줄 이상인 공고는 없다' in note0, note0)
    pj = os.path.join(TMP, 'excl.json')
    RP.dump(pj, dict(postings=[dict(posting_id='7', lines=[dict(excluded=True), dict(excluded=True), dict(excluded=False)]), dict(posting_id='8', lines=[dict(excluded=False)])]))
    per, n_all, n_ex = MR.excluded_counts(pj)
    line = dict(line_id='1', status='충족', lv_required=2, my_lv=2, section='자격요건', text='Python 3년 `x<y>` https://evil.example/a?b=1', keys=[dict(key='Python', my_lv=2, via=None)], career_rule='LV면 LV6(자리 최소 3년)')
    blk = MR.posting_block(dict(post('7', 1.0, 1), lines=[line], link='https://jobs.example/view?id=7'), 1, excl=per)
    check('기준표에서 제외라 표에 없는 줄 수와 경력 규칙 원문을 적음', per == {'7': (3, 2), '8': (1, 0)} and (n_all, n_ex) == (4, 2) and '줄 3개 중 `제외` 2개는 표에 없음' in blk and '경력 조건: LV면 LV6(자리 최소 3년)' in blk
          and MR.excluded_counts(os.path.join(TMP, 'none.json')) == ({}, 0, 0) and '제외' not in MR.posting_block(post('9', 1.0, 1), 1), blk)
    check('바깥 글: 백틱은 코드 글씨가 되지 않게, 맨 URL 은 코드 글씨로 싸서 링크가 되지 않게, 공고 주소는 그대로',
          '\\`x&lt;y&gt;\\`' in blk and '`https://evil.example/a?b=1`' in blk and '· https://jobs.example/view?id=7\n' in blk and '충족률 **-**' in MR.posting_block(post('g', None, 0), 1), blk)
    m2 = dict(n_postings=2, line_mode='any', postings=[dict(posting_id='7', lines=[line]), dict(posting_id='8', lines=[line])])
    ok_ex = MR.excl_for(m2, (per, n_all, n_ex)); bad_ex = MR.excl_for(dict(m2, postings=[dict(posting_id='7', lines=[line, line]), dict(posting_id='8', lines=[line])]), (per, n_all, n_ex))
    guide = MR.postings_guide(m2, ok_ex)
    check('기준표가 그 결과를 만들 때 쓴 것과 맞을 때만 제외 줄 수를 적음', ok_ex[3] == '맞음' and ok_ex[0] == per and bad_ex == ({}, 0, 0, '다름') and MR.excl_for(m2, ({}, 0, 0))[3] == '없음'
          and '4줄 중 2줄' in guide and '달라서 빠진 줄 수는 적지 않았다' in MR.postings_guide(m2, bad_ex) and '파일이 없어서 빠진 줄 수는 적지 않았다' in MR.postings_guide(m2, MR.excl_for(m2, ({}, 0, 0))), guide)
    check('공고 표 읽는 법: 요구 LV 가 어느 칸인지, 요구 LV - 의 뜻, 공고 줄에 붙는 묶음 키만 적음',
          '기술 LV(줄 기준)' in guide and '요구 LV `-` 는 기준표에 기술 LV 가 없는 줄' in guide and '(RDB, NoSQL, 클라우드, 컨테이너, ORM)' in guide and 'LLM API' not in guide and '앞 2개' in guide, guide)
    rt = MR.repo_table(dict(targets=[dict(label='a/b@develop', status='ok', head='2' * 40, mine=['DONGMIN LEE'], evidence=1, packets=0, answered=0, verify='점검 대상 없음', others=3, candidates=['이동민']),
                                     dict(label='a/c', status='ok', head='3' * 40, mine=['someone.real@example.org'], evidence=1, packets=0, answered=0, verify='점검 대상 없음', others=1, candidates=['이동민'])]))
    check('레포 표: 고르지 않은 후보 이름을 다른 기여자 수에 넣지 않음, 이름 칸에 적힌 이메일은 가림',
          '다른 기여자 2명 · 고르지 않은 후보 이름 1개' in rt and rt.count('다른 기여자') == 1 and rt.count('고르지 않은 후보 이름 1개') == 2 and 's…@example.org' in rt and 'someone.real' not in rt, rt)
    g = [dict(display='이동민', verdict='candidate', commits=7, pairs=[dict(name='이동민', email='d…@example-host.local', commits=7, signals=['name-in-email', 'conflict:noreply=someone'])])]
    leg = MR.hint_legend(g)
    leg2 = MR.hint_legend([dict(display='DONGMIN LEE', verdict='candidate', commits=1, pairs=[dict(name='DONGMIN LEE', email='9+x@users.noreply.github.com', commits=1, signals=['name', 'conflict:noreply=x'])])])
    check('후보 표 아래에 표시의 뜻을 적음(나온 표시만, 고르는 근거와 실마리를 구분), 후보가 없으면 적지 않음',
          '`name-in-email` 이메일에 내 이름 낱말이 있음 (실마리)' in leg and '다른 계정의 noreply 주소가 섞임 (실마리)' in leg and 'name~case' not in leg and '고르는 근거가 있는 이름도' not in leg and MR.hint_legend([]) == ''
          and '`name` 이름이 알려 준 이름과 글자 그대로 같음 (고르는 근거)' in leg2 and '고르는 근거가 있는 이름도' in leg2, (leg, leg2))
    check("'없음' 에 점검이 실제로 있었는지를 붙임(받은 답 수 기준)", '점검 없이 돌렸다' in MR.none_note(False, 3, 0) and '부르지 않았다' in MR.none_note(True, 0, 0) and '받은 답이 0건' in MR.none_note(True, 3, 0) and MR.none_note(True, 3, 2) == '없음')

    ev = lambda r, w: dict(repo=r, where=w)
    bl = [dict(meta=dict(repo='r/x'), evidence=[dict(key='Redis', kind='tool', lv=3, where='Redis 내 줄 3줄', own_lv=1, own_where='c.py:1', lifted_by='캐시 도입', lifted_where='c.py:9'), dict(key='캐시 도입', kind='activity', lv=3, where='c.py:9')]),
          dict(meta=dict(repo='r/y'), evidence=[dict(key='Redis', kind='tool', lv=2, where='d.py:2')])]
    rej = {('r/x', '캐시 도입'): 'reject'}
    check('근거의 bundle LV: 올려 준 활동이 통과면 올라간 LV 와 그 위치, 기각이면 원래 LV 와 원래 위치, 다른 레포의 근거와 섞지 않음',
          MR.bundle_lv(bl, {}, 'r/x', 'Redis', 'c.py:9') == 3 and MR.bundle_lv(bl, {}, 'r/x', 'Redis', 'c.py:1') is None and MR.bundle_lv(bl, rej, 'r/x', 'Redis', 'c.py:1') == 1 and MR.bundle_lv(bl, rej, 'r/x', 'Redis', 'c.py:9') is None
          and MR.bundle_lv(bl, {}, 'r/y', 'Redis', 'd.py:2') == 2 and MR.bundle_lv(bl, {}, 'r/y', 'Redis', 'c.py:9') is None and MR.bundle_lv(bl, {}, 'r/z', 'Redis', 'd.py:2') is None)
    st2 = dict(stat={'Spring': dict(lv=4, kind='tool', source='implied', by='Spring Data', evidence=[ev('r/x', 'O.java:15')]),
                     'Redis': dict(lv=3, kind='tool', source='lifted', by='캐시 도입', evidence=[ev('r/x', 'c.py:9'), ev('r/y', 'd.py:2')])})
    low = lambda repo, key, where: {('r/x', 'Spring', 'O.java:15'): 3, ('r/x', 'Redis', 'c.py:9'): 1, ('r/y', 'Redis', 'd.py:2'): 2}.get((repo, key, where))
    tb = MR.stat_table(st2, low)
    check('낮은 LV 표시는 둘째 줄부터만 붙이고, implied 키에는 붙이지 않음', '`O.java:15` (LV' not in tb and '`c.py:9` (LV' not in tb and '`d.py:2` (LV2 근거)' in tb, tb)
    check('내 근거 파일을 못 읽으면 표시를 붙이지 않고 안내 글도 그렇게 적음',
          MR.lv_lookup(TMP, dict(stat_inputs=['no-such/bundle.mine.json']), []) is None and MR.lv_lookup(TMP, dict(), []) is None and '표시하지 못했다' in MR.stat_guide(st2, False) and '처럼 적었다' in MR.stat_guide(st2, True))
    check('이름 칸에 섞인 이메일 꼴은 조각만 가리고, 레포 라벨의 # 뒤 이름에도 적용(@develop 은 그대로)',
          MR.who('Hong (hong.gd@example.com)') == 'Hong (h…@example.com)' and MR.who('DONGMIN LEE') == 'DONGMIN LEE' and MR.who('9+x@users.noreply.github.com') == '9+x@users.noreply.github.com'
          and MR.label('a/b@develop#someone.real@example.org') == 'a/b@develop#s…@example.org' and MR.label('a/b@develop') == 'a/b@develop'
          and 'someone.real' not in MR.loc('a/b#someone.real@example.org', 'x.py:1') and 'someone.real' not in MR.reject_table([dict(repo='a/b#someone.real@example.org', key='k', verdict='reject', lv=3, evidence='x.py:1')]))

    # 참고판(8번)과 프로필(1~6번): 작은 결과 폴더를 꾸며 조립까지 확인
    one = lambda k, lv, w, **kw: dict(person='me', key=k, kind='activity' if k in ('캐시 도입', '모니터링 설정') else 'tool', lv=lv, where=w, n=1, **kw)
    base = dict(person='me', repos=['a/b'], weak={}, stat={'Python': dict(lv=2, kind='tool', source='own', by=None, evidence=[ev('a/b', 'x.py:1')]), 'Java': dict(lv=2, kind='tool', source='own', by=None, evidence=[ev('a/b', 'J.java:1')]),
                                                           'Go': dict(lv=2, kind='tool', source='own', by=None, evidence=[ev('a/b', 'g.go:1')]),
                                                           'Git': dict(lv=1, kind='tool', source='own', by=None, evidence=[ev('a/b', '커밋 1111111')])})
    var = dict(person='me', repos=['a/b', 'a/b@develop'], weak={}, stat={'NumPy': dict(lv=2, kind='tool', source='own', by=None, evidence=[ev('a/b@develop', 'z.py:3')]),
                                                                     'Python': dict(lv=2, kind='tool', source='own', by=None, evidence=[ev('a/b', 'x.py:1'), ev('a/b@develop', 'Python 내 줄 9줄')]),
                                                                     'Java': dict(lv=2, kind='tool', source='lifted', by='API 개발', evidence=[ev('a/b', 'J.java:1')]),
                                                                     'Go': dict(lv=2, kind='tool', source='lifted', by='외부 API 연동', evidence=[ev('a/b@develop', 'g2.go:2'), ev('a/b', 'g.go:1')]),
                                                                     'Git': dict(lv=1, kind='tool', source='own', by=None, evidence=[ev('a/b', '커밋 1111111')])})
    bd, vd = os.path.join(TMP, 'out', 'rep-base'), os.path.join(TMP, 'out', 'rep-var')
    for d, st in ((bd, base), (vd, var)):
        os.makedirs(os.path.join(d, 'repos', 'm'), exist_ok=True); os.makedirs(os.path.join(d, 'repos', 'dv'), exist_ok=True)
        RP.dump(os.path.join(d, 'stat.json'), st); RP.dump(os.path.join(d, 'verdicts.json'), []); RP.dump(os.path.join(d, 'identity.json'), {})
        RP.dump(os.path.join(d, 'match.json'), dict(person='me', line_mode='any', n_postings=len(pool), postings=pool))
        RP.dump(os.path.join(d, 'repos', 'm', 'bundle.mine.json'), dict(meta=dict(repo='a/b'), evidence=[one('Python', 2, 'x.py:1'), one('Java', 2, 'J.java:1'), one('Git', 1, '커밋 1111111')], weak=[]))
        RP.dump(os.path.join(d, 'repos', 'dv', 'bundle.mine.json'), dict(meta=dict(repo='a/b@develop'), evidence=[one('Python', 1, 'Python 내 줄 9줄'), one('NumPy', 2, 'z.py:3')], weak=[]))
        tg = [dict(label='a/b', status='ok', head='4' * 40, mine=['me'], evidence=3, packets=0, answered=0, verify='점검 대상 없음', clone='새로 받음')]
        if d == vd: tg.append(dict(label='a/b@develop', branch='develop', status='ok', head='5' * 40, mine=['me'], evidence=2, packets=0, answered=0, verify='점검 대상 없음'))
        RP.dump(os.path.join(d, 'run.json'), dict(finished='2026-01-01T00:00:00+0900', verify=True, model=VA.MODEL, effort=VA.EFFORT, canonical='me', names=['me'], usd=0, listing=dict(ok=True, n=1), skipped=[],
                                                  also_branch=['develop'] if d == vd else [], stat_inputs=['repos/m/bundle.mine.json'] + (['repos/dv/bundle.mine.json'] if d == vd else []), targets=tg))
    vt = MR.variant_section(vd, bd)
    check('참고판: 점검을 켰지만 대상이 0건이면 없음 옆에 호출이 없었다고 적음', '정황(weak): 없음 · 기각: 없음 — 점검 대상이 0건이라 점검 에이전트를 부르지 않았다' in vt, vt[-500:])
    a, b = vt.split('LV 는 같고 근거 위치만 달라진 키')
    check('참고판: 새 키는 달라진 키 표에, 근거만 달라진 키는 따로(낮은 LV 근거 표시), source 만 달라진 키는 한 줄로, 그대로인 키는 어느 표에도 없음, 공고 동률 설명 포함',
          '| NumPy | 없음 | 2 |' in a and '| Python |' not in a and '| Python | 2 |' in b and '`Python 내 줄 9줄` (LV1 근거)' in b and '`x.py:1` (LV' not in b and '| Java |' not in vt
          and 'source 만 달라진 키: Java (own → lifted ← API 개발)' in b and '| Git |' not in vt and '위 목록의 5번째' in b
          and '| Go | 2 | own → lifted ← 외부 API 연동 | `a/b` · `g.go:1` | `a/b@develop` · `g2.go:2`<br>`a/b` · `g.go:1` |' in b, vt[:900])
    bt = MR.base_section(vd, bd)
    check('견줄 결과와의 차이 절: 두 결과의 설정과 키 수, 새 키·근거만 달라진 키·source 만 달라진 키, 맞음/틀림 칸 없음',
          '견줄 결과 `rep-base/`' in bt and 'stat 키 4개' in bt and 'stat 키 5개' in bt and '브랜치 줄 1개: `a/b@develop`' in bt and '| NumPy | 없음 | 2 |' in bt and '`Python 내 줄 9줄` (LV1 근거)' in bt
          and 'source 만 달라진 키: Java (own → lifted ← API 개발)' in bt and '맞음/틀림' not in bt and '두 결과에서 같다' in bt, bt[:700])
    pt = MR.profile_sections(bd)
    check('프로필: 점검을 켰지만 대상이 0건이면 1번·3번·4번에 호출이 없었다고 적음', '점검 대상이 0건이라 호출은 없었다' in pt and pt.count('없음 (점검 대상이 0건이라 점검 에이전트를 부르지 않았다)') == 2 and '첫 줄이 그 LV 를 준 근거' in pt, pt[:700])

    r0 = RP.load(os.path.join(bd, 'run.json'))
    RP.dump(os.path.join(bd, 'run.json'), dict(r0, targets=[dict(r0['targets'][0], packets=2, answered=0, missing=2, verdicts=dict(**{'pass': 0}, reject=0, unsure=2), verify='점검함(버린 응답이 있어 답 없는 판정은 모름으로 처리)')]))
    RP.dump(os.path.join(bd, 'verdicts.json'), [dict(repo='a/b', person='me', key=k, verdict='unsure', reason_code=None, reason='', git_name='me', lv=3, evidence='x.py:1', answered=False) for k in ('캐시 도입', '모니터링 설정')])
    pt0 = MR.profile_sections(bd)
    RP.dump(os.path.join(bd, 'run.json'), r0); RP.dump(os.path.join(bd, 'verdicts.json'), [])
    check('프로필: 점검 대상은 있었는데 받은 답이 0건이면 4번의 없음 옆에 그렇게 적음', '없음 (점검 대상은 있었지만 받은 답이 0건이다)' in pt0 and '합계 2건, 그중 점검한 판정 0건' in pt0 and '점검 에이전트 사용(' in pt0, pt0[:500])

    # 로컬 폴더(7번): run_pipeline.py 가 쓰는 꼴(판정 줄에 LV·근거 위치·답 여부가 없음)
    ld = os.path.join(TMP, 'out', 'rep-local'); os.makedirs(ld)
    lb = dict(meta=dict(repo='proj', head='6' * 40, people=['me', 'other.person@example.org'], ai_commits={'me': 3}, generated_files=1),
              evidence=[one('캐시 도입', 3, 'app/c.py:5'), one('모니터링 설정', 3, 'mon/p.yml 5줄'), one('Python', 2, 'app/c.py:5')], weak=[])
    lstat = dict(person='me', repos=['proj'], weak={'모니터링 설정': dict(claimed_lv=3, evidence=[ev('proj', 'mon/p.yml 5줄')], reason='점검에서 모름')}, stat={'Python': dict(lv=2, kind='tool', source='own', by=None, evidence=[ev('proj', 'app/c.py:5')])})
    RP.dump(os.path.join(ld, 'bundle.json'), lb); RP.dump(os.path.join(ld, 'stat.json'), lstat); RP.dump(os.path.join(ld, 'match.json'), dict(person='me', line_mode='any', n_postings=len(pool), postings=pool))
    RP.dump(os.path.join(ld, 'verdicts.json'), [dict(repo='proj', person='me', key='캐시 도입', verdict='reject', reason_code='R2', reason='캐시가 아님'), dict(repo='proj', person='me', key='모니터링 설정', verdict='unsure', reason_code=None, reason='')])
    lt = MR.local_section(ld)
    check('로컬: 판정 줄에 없는 LV·근거 위치는 bundle 에서 채우고, 이유가 빈 모름은 답 없는 줄일 수 있다고 적음',
          '| `proj` | 캐시 도입 | 3 | `app/c.py:5` | R2 | 캐시가 아님 |' in lt and '(이유 없음: 점검 에이전트의 답이 없어 모름으로 채워진 줄일 수 있다)' in lt and '| 2 | 1 | 0 | 1 | 1 |' in lt
          and '이유가 빈 모름 1건' in lt and '기여자 me, o…@example.org' in lt and 'other.person' not in lt and 'AI가 쓰거나 함께 쓴 커밋 me 3개' in lt, lt[:900])
    RP.dump(os.path.join(ld, 'verdicts.json'), [dict(repo='proj', person='me', key='캐시 도입', verdict='unsure', reason_code=None, reason='', lv=3, evidence='app/c.py:5', answered=False),
                                                dict(repo='proj', person='me', key='모니터링 설정', verdict='unsure', reason_code=None, reason='판단할 정보 부족', lv=3, evidence='mon/p.yml 5줄', answered=True)])
    lt4 = MR.local_section(ld)
    RP.dump(os.path.join(ld, 'verdicts.json'), [dict(repo='proj', person='me', key='모니터링 설정', verdict='unsure', reason_code=None, reason='')])
    lt5 = MR.local_section(ld)
    check('로컬: 답 여부 표시가 있으면 그 표시로 세고, 이유가 모두 빈 판정 줄뿐이면 답을 못 받았을 수 있다고 적음',
          '| 2 | 1 | 0 | 0 | 2 |' in lt4 and '답을 못 받은 줄 1건' in lt4 and '없음 (판정 줄의 이유가 모두 비어 있다. 점검 에이전트의 답을 받지 못했을 수 있다)' in lt5, (lt4[:500], lt5[-400:]))
    os.remove(os.path.join(ld, 'verdicts.json')); lt2 = MR.local_section(ld)
    RP.dump(os.path.join(ld, 'bundle.json'), dict(lb, evidence=[one('Python', 2, 'app/c.py:5')])); RP.dump(os.path.join(ld, 'stat.json'), dict(lstat, weak={})); lt3 = MR.local_section(ld)
    check('로컬: 점검 대상이 있는데 판정 파일이 없으면 점검 없이 돌렸다고, 대상이 0건이면 부르지 않았다고 적음', '없음 (점검 없이 돌렸다)' in lt2 and lt3.count('없음 (점검 대상이 0건이라 점검 에이전트를 부르지 않았다)') == 2, (lt2[-300:], lt3[-300:]))

    # 보고서 조립(main): 머리 글·7번·8번·꼬리 글이 붙고, --postings 로 준 기준표에서 제외 줄 수를 적음
    posts = os.path.join(TMP, 'rep-posts.json'); RP.dump(posts, dict(postings=[dict(posting_id=x['posting_id'], lines=[dict(excluded=True)] * 2) for x in pool]))
    for name, text in (('h.md', '# 머리'), ('t.md', '## 9. 꼬리'), ('ln.md', '로컬 글'), ('vn.md', '참고판 글')):
        with open(os.path.join(TMP, name), 'w', encoding='utf-8') as f: f.write(text + '\n')
    rep = os.path.join(TMP, 'REPORT_test.md'); saved = sys.argv
    sys.argv = ['make_report.py', '--profile', bd, '--local', ld, '--variant', vd, '--head', os.path.join(TMP, 'h.md'), '--tail', os.path.join(TMP, 't.md'),
                '--local-note', os.path.join(TMP, 'ln.md'), '--variant-note', os.path.join(TMP, 'vn.md'), '--postings', posts, '--out', rep]
    try:
        MR.main()
    finally:
        sys.argv = saved
    doc = open(rep, encoding='utf-8').read()
    order = [doc.find(x) for x in ('# 머리', '## 1. 레포마다', '## 6. 실패·제외한 레포', '## 7. 로컬 폴더 결과', '로컬 글', '## 8. (요청 밖 참고)', '참고판 글', '## 9. 꼬리')]
    check('보고서 조립: 머리 글 → 1~6번 → 7번(글 + 표) → 8번(글 + 표) → 꼬리 글 순서로 붙고, 준 기준표로 제외 줄 수를 적음',
          all(x >= 0 for x in order) and order == sorted(order) and doc.count('기준표의 이 공고 줄 2개 중 `제외` 2개는 표에 없음') == 15 and '기준표 14줄 중 14줄' in doc, order)


def main():
    try:
        for t in (test_identity, test_verify, test_profile, test_main, test_report):
            try:
                t()
            except (Exception, SystemExit) as e:        # 시험 하나가 죽어도 나머지는 계속
                import traceback
                traceback.print_exc(); check(f'{t.__name__} 가 예외 없이 끝남', False, repr(e))
    finally:
        shutil.rmtree(TMP, ignore_errors=True)
    bad = [n for n, ok in RESULTS if not ok]
    print(f'\n{len(RESULTS) - len(bad)}/{len(RESULTS)} 통과' + (f' | 실패: {bad}' if bad else ''))
    sys.exit(1 if bad else 0)


if __name__ == '__main__':
    main()
