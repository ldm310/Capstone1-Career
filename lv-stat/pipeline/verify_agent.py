#!/usr/bin/env python3
"""점검 에이전트 호출: packets.json -> Claude API -> agent_output.json  (LLM은 이 단계에만 쓴다)

Usage:
  python3 pipeline/verify_agent.py <packets.json> --out <agent_output.json> [--log <verify_log.json>]
  그다음: python3 pipeline/run_pipeline.py ... --agent-output <agent_output.json>
  보내지 않고 묶음만 보기: python3 pipeline/verify_agent.py <packets.json> --out x.json --dry-run

- 지시문: pipeline/verifier_prompt.md 전체를 system 으로 그대로 보낸다(내용을 바꾸지 않는다).
- 입력: packet 을 한 번에 50개 이하(그리고 120KB 이하)로 나눠, user 메시지에 JSON 배열로 보낸다. 도구는 주지 않는다.
- 출력: JSON 배열만 받는다. 형식이 깨진 응답(JSON 배열이 아님, 중간에 잘림, 거절)은 버린다.
  빠진 id 는 run_pipeline.py / apply_verdicts.py 가 unsure 로 처리한다(통과로 올리지 않음).
  답이 길어 잘린 묶음(stop_reason=max_tokens)과 너무 큰 묶음(HTTP 413)은 버린 뒤 반으로 나눠 다시 보낸다(1건짜리는 그대로 버림).
- 키: 환경 변수 ANTHROPIC_API_KEY, 없으면 career-stat-handoff/.env 의 ANTHROPIC_API_KEY=... 줄. 키는 출력하지도 기록하지도 않는다.
- 비용: 호출마다 사용량을 out/verifier_spend.json 에 쌓고, 누적 추정액이 --cap-usd 를 넘게 되는 호출은 하지 않는다.
  가격표(PRICE)에 없는 모델은 한도를 계산할 수 없어 거절한다(--cap-usd 0 을 주면 한도 검사 없이 부름).
종료 코드: 0 모든 묶음에서 쓸 수 있는 답을 받음 / 2 키 없음(또는 키 모양이 이상함) / 3 API를 쓸 수 없음(인증·결제·권한·요청 형식, 또는 모든 호출 실패)
          / 4 비용 한도에 걸림 / 5 일부 묶음의 호출이 실패함(agent_output 에는 받은 답만 있음)
          형식이 깨져 버린 응답만 있었던 경우는 0 이다(정해진 처리: 답 없는 id 는 unsure)
표준 라이브러리만 쓴다(Python 3.9 이상).
"""
import argparse, collections, hashlib, http.client, json, os, re, ssl, sys, time
import urllib.error, urllib.request
try:
    import fcntl                 # 장부 잠금(없는 운영체제에서는 잠그지 않음)
except ImportError:
    fcntl = None

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
API_URL = 'https://api.anthropic.com/v1/messages'
API_VERSION = '2026-10-21'
MODEL = 'claude-haiku-5-5'
EFFORT = 'medium'          # Haiku 5.5 의 기본값. 생각(adaptive thinking)은 기본대로 켜 둔다
MAX_TOKENS = 16000         # 생각 토큰 포함. 스트리밍 없이 받는 요청의 권장 크기
BATCH = 50                 # 한 번에 보내는 packet 수 상한
BATCH_BYTES = 120_000      # 한 번에 보내는 packet JSON 크기 상한(UTF-8). 프롬프트가 10만 토큰을 넘으면 요금이 5배라 그 아래로 둔다(실측 약 2.3바이트/토큰)
VERDICTS = ('pass', 'reject', 'unsure')
CODES = ('R1', 'R2', 'R3', 'R4')
# USD / 100만 토큰 (입력, 출력). 프롬프트가 limit 토큰을 넘으면 그 요청 전체가 high 요금
PRICE = {'claude-haiku-5-5': dict(limit=100_000, low=(0.10, 0.50), high=(0.50, 2.50))}
KEY_RX = re.compile(r'[!-~]+')          # 헤더에 넣을 수 있는 글자만(공백·줄바꿈·ASCII 밖 글자 없음)
ENV_LINE = re.compile(r'\s*(?:export\s+)?ANTHROPIC_API_KEY\s*=\s*(.*)$')


class Unavailable(Exception):
    """API를 쓸 수 없음(키·결제·권한·요청 형식, 또는 모든 호출 실패). 다시 불러도 같은 결과라 멈춘다."""


def retryable(status):
    return status in (408, 409, 429) or status >= 500


class ApiError(Exception):
    def __init__(self, status, etype, message, retry_after=None, request_id=None):
        super().__init__(f'HTTP {status} {etype}: {message}')
        self.status, self.etype, self.message, self.retry_after, self.request_id = status, etype, message, retry_after, request_id


def load_key(env_file=None):
    """-> (키, 출처 'env'|'.env') 또는 (None, None). 키 값은 어디에도 찍지 않는다.
    모양이 이상한 값(공백·줄바꿈이 섞임 등)도 그대로 돌려주므로, 쓰는 쪽에서 KEY_RX 로 확인한다(verify 가 부르기 전에 거절)."""
    k = (os.environ.get('ANTHROPIC_API_KEY') or '').strip()
    if k: return k, 'env'
    found = None
    try:
        with open(env_file or os.path.join(ROOT, '.env'), encoding='utf-8-sig', errors='replace') as f:
            for line in f:
                m = ENV_LINE.match(line.rstrip('\r\n'))
                if not m: continue
                v = m.group(1).strip()
                if v[:1] in ('"', "'"):                # 따옴표로 시작하면 닫는 따옴표까지만(뒤의 주석은 버림)
                    end = v.find(v[0], 1)
                    v = v[1:end] if end > 0 else v[1:]
                else:
                    v = re.split(r'\s+#', v, maxsplit=1)[0]     # 값 뒤의 ' # 주석' 은 버림
                if v.strip(): found = v.strip()        # 같은 줄이 여러 번이면 마지막 줄을 씀
    except OSError:
        pass
    return (found, '.env') if found else (None, None)


def ssl_context():
    """기본 인증서 묶음이 없는 Python(예: 일부 macOS 설치)에서는 시스템 묶음을 직접 읽는다. 검증은 끄지 않는다."""
    ctx = ssl.create_default_context()
    vp = ssl.get_default_verify_paths()
    if not (vp.cafile or vp.capath) and not ctx.cert_store_stats().get('x509_ca'):
        for ca in (os.environ.get('SSL_CERT_FILE'), '/etc/ssl/cert.pem', '/etc/ssl/certs/ca-certificates.crt', '/etc/pki/tls/certs/ca-bundle.crt'):
            if ca and os.path.isfile(ca):
                try:
                    ctx.load_verify_locations(cafile=ca); break
                except (OSError, ssl.SSLError):
                    continue
        else:
            try:
                import certifi
                ctx.load_verify_locations(cafile=certifi.where())
            except Exception:
                pass
    return ctx


def split_batches(packets, max_n=BATCH, max_bytes=BATCH_BYTES):
    """packet 목록 -> 묶음 목록. 묶음마다 max_n 개 이하, JSON 크기 max_bytes 이하(하나가 그보다 크면 혼자 보냄)"""
    out, cur, size = [], [], 0
    for p in packets:
        n = len(json.dumps(p, ensure_ascii=False).encode('utf-8'))
        if cur and (len(cur) >= max_n or size + n > max_bytes): out.append(cur); cur, size = [], 0
        cur.append(p); size += n
    if cur: out.append(cur)
    return out


def cost_usd(model, usage):
    """실제 사용량 -> 추정 비용(USD). 가격표에 없는 모델이면 None"""
    p = PRICE.get(model)
    if not p or not usage: return None
    i, cw, cr, o = (int(usage.get(k) or 0) for k in ('input_tokens', 'cache_creation_input_tokens', 'cache_read_input_tokens', 'output_tokens'))
    rin, rout = p['high'] if i + cw + cr > p['limit'] else p['low']
    return (i * rin + cw * rin * 1.25 + cr * rin * 0.1 + o * rout) / 1e6


def worst_case_usd(model, n_bytes, max_tokens):
    """보내기 전 최악 비용(USD): 입력을 바이트/1.5 토큰으로 넉넉히 잡고 비싼 요금표로 계산"""
    p = PRICE.get(model)
    if not p: return None
    rin, rout = p['high']
    return ((n_bytes / 1.5 + 3000) * rin + max_tokens * rout) / 1e6


def load_ledger(path):
    if not path or not os.path.exists(path): return dict(total_usd=0.0, calls=[])
    with open(path, encoding='utf-8') as f: d = json.load(f)          # 깨진 장부는 고치지 않고 멈춘다(한도 검사를 건너뛰지 않게)
    if not (isinstance(d, dict) and isinstance(d.get('calls'), list)): raise ValueError(f'비용 장부 형식이 다름: {path}')
    return d


class ledger_lock:
    """장부를 읽고 부르고 적는 동안 다른 실행이 끼어들지 못하게 잠근다(같은 장부를 쓰는 실행은 차례로 호출하게 됨)."""
    def __init__(self, path): self.path, self.f = path, None

    def __enter__(self):
        if self.path and fcntl:
            os.makedirs(os.path.dirname(os.path.abspath(self.path)), exist_ok=True)
            self.f = open(self.path + '.lock', 'w'); fcntl.flock(self.f, fcntl.LOCK_EX)
        return self

    def __exit__(self, *exc):
        if self.f:
            fcntl.flock(self.f, fcntl.LOCK_UN); self.f.close()
        return False


def save_ledger(path, led):
    if not path: return
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    led['total_usd'] = round(sum(c.get('usd') or 0 for c in led['calls']), 6)
    tmp = f'{path}.{os.getpid()}.tmp'
    with open(tmp, 'w', encoding='utf-8') as f: json.dump(led, f, ensure_ascii=False, indent=1)
    os.replace(tmp, path)


def post(key, body, timeout, ctx):
    """Messages API 한 번 호출 -> (응답 dict, request-id). 키는 헤더로만 간다."""
    req = urllib.request.Request(API_URL, data=json.dumps(body, ensure_ascii=False).encode('utf-8'), method='POST',
                                 headers={'Content-Type': 'application/json', 'x-api-key': key, 'anthropic-version': API_VERSION})
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as r:
            return json.loads(r.read().decode('utf-8')), r.headers.get('request-id')
    except urllib.error.HTTPError as e:
        raw = e.read().decode('utf-8', 'replace')
        try:
            err = json.loads(raw).get('error')
        except (ValueError, AttributeError):
            err = None
        if not isinstance(err, dict): err = {}          # 중간 프록시가 {"error": "..."} 나 HTML 로 답하는 경우
        raise ApiError(e.code, str(err.get('type') or 'http_error'), str(err.get('message') or raw or '')[:300], e.headers.get('retry-after'), e.headers.get('request-id'))


def call(key, body, timeout, ctx, retries, log):
    """다시 해 볼 만한 실패(408·409·429, 5xx, 네트워크)만 다시 부른다.
    그래도 안 되거나 413(묶음이 너무 큼)이면 ApiError(그 묶음만 실패), 그 밖의 4xx 는 Unavailable(전체 중단)."""
    for attempt in range(retries + 1):
        try:
            return post(key, body, timeout, ctx)
        except ApiError as e:
            if retryable(e.status) and attempt < retries:
                try:
                    wait = min(60.0, float(e.retry_after))
                except (TypeError, ValueError):
                    wait = 2.0 * 2 ** attempt
                log(f'  HTTP {e.status} {e.etype} -> {wait:.0f}초 뒤 다시 시도 ({attempt + 1}/{retries})'); time.sleep(wait); continue
            if retryable(e.status) or e.status == 413: raise
            raise Unavailable(str(e).replace(key, '***'))
        except (urllib.error.URLError, http.client.HTTPException, OSError, json.JSONDecodeError) as e:
            if attempt < retries:
                wait = 2.0 * 2 ** attempt
                log(f'  네트워크 오류 {type(e).__name__} -> {wait:.0f}초 뒤 다시 시도 ({attempt + 1}/{retries})'); time.sleep(wait); continue
            raise ApiError(0, 'network_error', f'{type(e).__name__}: {e}'.replace(key, '***')[:300])
        except ValueError as e:                          # 요청 자체를 만들 수 없음(예: 헤더에 넣을 수 없는 값). 값이 섞일 수 있어 내용은 싣지 않는다
            raise Unavailable(f'요청을 만들 수 없음({type(e).__name__})')


def parse_output(text, ids, why=None):
    """모델이 낸 글 -> (받아들인 항목들, 문제 설명 또는 None, 버린 항목 수).
    JSON 배열 그대로이거나, 지시문 예시처럼 ```json 블록 하나에 든 배열만 받는다. 그 밖의 모양은 응답 전체를 버린다.
    why 에 dict 를 주면 항목을 버린 까닭별 건수와, 모델이 돌려준 id·verdict 의 보기(앞 8개, 20자까지)를 적어 준다(코드 조각이나 이유 글은 적지 않는다)."""
    def note(reason, sample=None):
        if why is None: return
        why.setdefault('counts', {}); why['counts'][reason] = why['counts'].get(reason, 0) + 1
        if sample is not None and len(why.setdefault('samples', [])) < 8: why['samples'].append(str(sample)[:20])
    t = (text or '').strip()
    m = re.fullmatch(r'```(?:json)?[ \t]*\n(.*?)\n?```', t, re.S)
    if m: t = m.group(1).strip()
    try:
        arr = json.loads(t)
    except (ValueError, RecursionError):                # 깊게 겹친 대괄호 같은 것도 깨진 응답으로 보고 버림
        return [], 'JSON으로 읽을 수 없음', 0
    if not isinstance(arr, list): return [], 'JSON 배열이 아님', 0
    got, dropped, conflict = {}, 0, set()
    for x in arr:
        if not isinstance(x, dict): note('항목이 객체가 아님'); dropped += 1; continue
        if not isinstance(x.get('id'), str): note('id 가 글자가 아님', repr(x.get('id'))); dropped += 1; continue
        if x['id'] not in ids: note('id 가 보낸 packet 에 없음', repr(x['id'])); dropped += 1; continue      # repr: 제어 문자가 화면·기록에 그대로 나가지 않게
        if x.get('verdict') not in VERDICTS: note('verdict 가 pass/reject/unsure 가 아님', repr(x.get('verdict'))); dropped += 1; continue
        item = dict(id=x['id'], verdict=x['verdict'], reason_code=x.get('reason_code') if x.get('reason_code') in CODES else None,
                    reason=x['reason'] if isinstance(x.get('reason'), str) else '')
        if x['id'] in got and got[x['id']]['verdict'] != item['verdict']: conflict.add(x['id'])       # 같은 id 에 다른 답: 둘 다 버림
        got.setdefault(x['id'], item)
    for i in conflict: got.pop(i, None); dropped += 1; note('같은 id 에 서로 다른 답', repr(i))
    if arr and not got: return [], '받아들일 항목이 하나도 없음', dropped       # 답은 왔는데 전부 형식이 틀림: 형식이 깨진 응답으로 본다(--retry-malformed 대상)
    return list(got.values()), None, dropped


def verify(packets, key, model=MODEL, effort=EFFORT, max_tokens=MAX_TOKENS, batch=BATCH, batch_bytes=BATCH_BYTES, timeout=600, retries=2,
           retry_malformed=0, cap_usd=1.0, ledger=None, source='', log=None, prompt_path=None):
    """packets(list) -> (agent_output list, info dict). API를 아예 쓸 수 없으면 Unavailable.
    info['missing'] 의 id 는 답을 못 받은 것(파이프라인이 unsure 로 처리)."""
    log = log or (lambda s: print(s, file=sys.stderr))
    if not KEY_RX.fullmatch(key or ''): raise Unavailable('ANTHROPIC_API_KEY 에 공백·줄바꿈·ASCII 밖 글자가 있거나 비어 있어 쓸 수 없음')       # 값은 찍지 않는다
    if cap_usd and model not in PRICE: raise Unavailable(f'가격표(PRICE)에 없는 모델 {model}: 비용 한도를 계산할 수 없음. PRICE 에 요금을 넣거나 --cap-usd 0 으로 한도 검사를 끄고 실행')
    with open(prompt_path or os.path.join(HERE, 'verifier_prompt.md'), encoding='utf-8') as f: system = f.read()
    ids = [p.get('id') for p in packets]
    if len(set(ids)) != len(ids) or not all(isinstance(i, str) for i in ids): raise ValueError('packet id 가 없거나 겹침')
    info = dict(model=model, effort=effort, api_version=API_VERSION, max_tokens=max_tokens, n_packets=len(packets), batches=[], usd=0.0, input_tokens=0, output_tokens=0,
                stopped=None, prompt_sha256=hashlib.sha256(system.encode('utf-8')).hexdigest(),
                packets_sha256=hashlib.sha256(json.dumps(packets, ensure_ascii=False, sort_keys=True).encode('utf-8')).hexdigest())
    answers, ctx = {}, ssl_context()
    mem = dict(calls=[])                               # 장부 파일을 쓰지 않을 때의 누적
    queue = collections.deque(split_batches(packets, max(1, min(batch, BATCH)), batch_bytes))
    while queue and not info['stopped']:
        chunk = queue.popleft(); bi = len(info['batches'])
        text = json.dumps(chunk, ensure_ascii=False, indent=1)
        body = dict(model=model, max_tokens=max_tokens, system=system, output_config=dict(effort=effort), messages=[dict(role='user', content=text)])   # tools 없음
        rec = dict(batch=bi, ids=[p['id'] for p in chunk], bytes=len(text.encode('utf-8')), tries=[], outcome=None)
        info['batches'].append(rec)
        too_long = False
        for attempt in range(max(0, retry_malformed) + 1):
            wc = worst_case_usd(model, rec['bytes'], max_tokens)
            t0 = time.time(); tr = dict(attempt=attempt)
            with ledger_lock(ledger):                  # 한도 확인 -> 호출 -> 장부 기록을 한 덩어리로
                led = load_ledger(ledger) if ledger else mem
                spent = sum(c.get('usd') or 0 for c in led['calls'])
                if cap_usd and wc is not None and spent + wc > cap_usd:
                    info['stopped'] = f'비용 한도: 누적 ${spent:.4f} + 이번 최악 ${wc:.4f} > 한도 ${cap_usd:.2f}'; rec['outcome'] = '보내지 않음(비용 한도)'; log('  ' + info['stopped']); break
                rec['tries'].append(tr)
                try:
                    resp, rid = call(key, body, timeout, ctx, retries, log)
                except ApiError as e:                  # 다시 해도 안 된 일시 오류 또는 413: 이 묶음만 실패
                    tr.update(error=str(e)[:300], seconds=round(time.time() - t0, 1)); too_long = e.status == 413
                    rec['outcome'] = '호출 실패'; log(f'  묶음 {bi}: 실패 {e}'); break
                except Unavailable as e:
                    tr.update(error=str(e)[:300], seconds=round(time.time() - t0, 1)); info['stopped'] = f'API를 쓸 수 없음: {e}'; rec['outcome'] = '호출 실패'
                    if not answers: raise
                    log('  ' + info['stopped']); break
                usage = resp.get('usage') or {}
                usd = cost_usd(model, usage)
                led['calls'].append(dict(ts=time.strftime('%Y-%m-%dT%H:%M:%S%z'), model=model, effort=effort, source=source, packets=len(chunk), input_tokens=usage.get('input_tokens'),
                                         cache_creation_input_tokens=usage.get('cache_creation_input_tokens'), cache_read_input_tokens=usage.get('cache_read_input_tokens'),
                                         output_tokens=usage.get('output_tokens'), usd=round(usd, 6) if usd is not None else None, request_id=rid))
                save_ledger(ledger, led)
            info['usd'] += usd or 0; info['input_tokens'] += int(usage.get('input_tokens') or 0); info['output_tokens'] += int(usage.get('output_tokens') or 0)
            stop = resp.get('stop_reason')
            out_text = ''.join(b.get('text', '') for b in (resp.get('content') or []) if isinstance(b, dict) and b.get('type') == 'text')
            tr.update(stop_reason=stop, usage={k: usage.get(k) for k in ('input_tokens', 'output_tokens')}, usd=round(usd, 6) if usd is not None else None, request_id=rid, seconds=round(time.time() - t0, 1))
            if stop != 'end_turn':                     # max_tokens(잘림), refusal(거절) 등: 형식이 깨진 응답으로 보고 버림
                items, problem, dropped = [], f'stop_reason={stop}', 0
                if stop == 'refusal': tr['refusal'] = (resp.get('stop_details') or {}).get('category')
            else:
                why = {}
                items, problem, dropped = parse_output(out_text, set(rec['ids']), why)
                if why: tr['dropped_why'] = why
            tr.update(problem=problem, kept=len(items), dropped_items=dropped)
            wtxt = ''
            if dropped and tr.get('dropped_why'):
                w = tr['dropped_why']; wtxt = ': ' + ', '.join(f'{k} {v}건' for k, v in w.get('counts', {}).items()) + (f" (돌려준 값 보기: {', '.join(w['samples'])})" if w.get('samples') else '')
            log(f"  묶음 {bi}: packet {len(chunk)}건 -> 답 {len(items)}건" + (f" (응답 버림: {problem})" if problem else '') + (f" (형식 틀린 항목 {dropped}건 버림{wtxt})" if dropped else '')
                + f" | 입력 {usage.get('input_tokens')} 출력 {usage.get('output_tokens')} 토큰" + (f" | 약 ${usd:.4f}" if usd is not None else ''))
            if not problem:
                for it in items: answers[it['id']] = it
                rec['outcome'] = '답 받음'; break
            rec['outcome'] = '응답 버림'
            if stop != 'end_turn':                     # 같은 요청을 다시 보내도 같은 결과(거절·잘림): --retry-malformed 대상이 아님
                too_long = stop == 'max_tokens'; break
        if too_long and len(chunk) > 1:                # 답이 잘렸거나 묶음이 너무 큼: 반으로 나눠 다시 보냄
            mid = len(chunk) // 2
            queue.appendleft(chunk[mid:]); queue.appendleft(chunk[:mid]); rec['outcome'] += ' -> 반으로 나눠 다시 보냄'
            log(f'  묶음 {bi}: {len(chunk)}건을 {mid}건 + {len(chunk) - mid}건으로 나눠 다시 보냄')
    out = [answers[i] for i in ids if i in answers]
    info.update(n_answered=len(out), missing=[i for i in ids if i not in answers], usd=round(info['usd'], 6),
                counts={v: sum(1 for x in out if x['verdict'] == v) for v in VERDICTS})
    info['complete'] = not info['stopped'] and not queue and not info['missing']      # 모든 packet 에 쓸 수 있는 답을 받았나(다시 돌릴 때 저장된 답을 쓸지 정함)
    fails = [b for b in info['batches'] if b['outcome'] == '호출 실패']                # 다시 불러도 안 된 묶음(반으로 나눠 다시 보낸 것은 빼고)
    info['failed_calls'] = len(fails)
    if packets and not answers and fails and len(fails) == len(info['batches']):      # 한 번도 답을 못 받음: 점검을 못 한 것으로 알린다
        raise Unavailable('모든 묶음의 호출이 실패함: ' + fails[-1]['tries'][-1]['error'])
    return out, info


def main():
    ap = argparse.ArgumentParser(description='packets.json 을 점검 에이전트(Claude API)에 보내 agent_output.json 을 만든다')
    ap.add_argument('packets'); ap.add_argument('--out', required=True); ap.add_argument('--log', help='호출 기록(JSON). 코드 내용과 키는 들어가지 않음')
    ap.add_argument('--model', default=MODEL); ap.add_argument('--effort', default=EFFORT, choices=['low', 'medium', 'high', 'xhigh', 'max']); ap.add_argument('--max-tokens', type=int, default=MAX_TOKENS)
    ap.add_argument('--batch', type=int, default=BATCH, help='한 번에 보내는 packet 수(1~50)'); ap.add_argument('--batch-bytes', type=int, default=BATCH_BYTES)
    ap.add_argument('--timeout', type=float, default=600); ap.add_argument('--retries', type=int, default=2, help='429·5xx·네트워크 오류 때 다시 부르는 횟수')
    ap.add_argument('--retry-malformed', type=int, default=0, help='형식이 깨진 응답을 다시 받아 보는 횟수(기본 0: 그냥 버림)')
    ap.add_argument('--env-file', default=os.path.join(ROOT, '.env')); ap.add_argument('--ledger', default=os.path.join(ROOT, 'out', 'verifier_spend.json'))
    ap.add_argument('--cap-usd', type=float, default=1.0, help='장부 누적 추정액 한도(USD). 0이면 검사 안 함'); ap.add_argument('--dry-run', action='store_true')
    a = ap.parse_args()
    if a.retry_malformed < 0: ap.error('--retry-malformed 는 0 이상이어야 함')
    if not 1 <= a.batch <= BATCH: ap.error(f'--batch 는 1~{BATCH}')
    if a.cap_usd and a.model not in PRICE and not a.dry_run: ap.error(f'가격표(PRICE)에 없는 모델 {a.model}: 비용 한도를 계산할 수 없음. --cap-usd 0 을 주면 한도 검사 없이 부름')
    with open(a.packets, encoding='utf-8') as f: packets = json.load(f)
    if not isinstance(packets, list): sys.exit('packets.json 은 JSON 배열이어야 함')
    for path in (a.out, a.log):                        # 호출을 끝낸 뒤 저장 폴더가 없어 답을 잃지 않게 먼저 만든다
        if path and not a.dry_run: os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    if a.dry_run:
        for i, c in enumerate(split_batches(packets, a.batch, a.batch_bytes)):
            n = len(json.dumps(c, ensure_ascii=False, indent=1).encode('utf-8')); wc = worst_case_usd(a.model, n, a.max_tokens)
            print(f'묶음 {i}: packet {len(c)}건, {n:,}바이트' + (f', 최악 약 ${wc:.4f}' if wc is not None else ''))
        return
    def dump(path, obj):
        with open(path, 'w', encoding='utf-8') as f: json.dump(obj, f, ensure_ascii=False, indent=1)
    if not packets:
        dump(a.out, []); print('점검할 packet 0건 -> 호출 없음'); return
    key, src = load_key(a.env_file)
    if not key:
        print('ANTHROPIC_API_KEY 가 환경 변수에도 .env 에도 없음 -> 호출하지 않음. 규칙만 쓰려면 run_pipeline.py --no-verify', file=sys.stderr); sys.exit(2)
    if not KEY_RX.fullmatch(key):
        print(f'ANTHROPIC_API_KEY({src}) 값에 공백·줄바꿈·ASCII 밖 글자가 있음 -> 호출하지 않음(값은 찍지 않음). 규칙만 쓰려면 run_pipeline.py --no-verify', file=sys.stderr); sys.exit(2)
    try:
        out, info = verify(packets, key, model=a.model, effort=a.effort, max_tokens=a.max_tokens, batch=a.batch, batch_bytes=a.batch_bytes, timeout=a.timeout, retries=a.retries,
                           retry_malformed=a.retry_malformed, cap_usd=a.cap_usd, ledger=a.ledger, source=os.path.abspath(a.packets))
    except Unavailable as e:
        print(f'점검 호출 실패(답 0건, agent_output 을 만들지 않음): {e}\n규칙만 쓰려면 run_pipeline.py --no-verify', file=sys.stderr); sys.exit(3)
    except ValueError as e:
        sys.exit(str(e))
    info['key_source'] = src
    if info['stopped'] and not out:                    # 한 건도 답을 못 받고 멈춤: 빈 agent_output 을 남기면 전부 unsure 로 읽히므로 만들지 않는다
        if a.log: dump(a.log, info)
        print('점검 호출을 하지 못함(답 0건, agent_output 을 만들지 않음): ' + info['stopped'], file=sys.stderr); sys.exit(4 if info['stopped'].startswith('비용 한도') else 3)
    dump(a.out, out)
    if a.log: dump(a.log, info)
    c = info['counts']
    print(f"packet {info['n_packets']}건 -> 답 {info['n_answered']}건 (pass {c['pass']}, reject {c['reject']}, unsure {c['unsure']}), 답 없음 {len(info['missing'])}건(파이프라인에서 unsure) | "
          f"호출 {sum(len(b['tries']) for b in info['batches'])}회 | 입력 {info['input_tokens']:,} / 출력 {info['output_tokens']:,} 토큰 | 약 ${info['usd']:.4f} | {a.out}")
    if info['stopped']:
        print('중간에 멈춤: ' + info['stopped'], file=sys.stderr); sys.exit(4 if info['stopped'].startswith('비용 한도') else 3)
    if info['failed_calls']:
        print(f"묶음 {info['failed_calls']}개의 호출이 실패함(답 없음 {len(info['missing'])}건은 파이프라인에서 unsure). 다시 실행하면 전체를 다시 보낸다", file=sys.stderr); sys.exit(5)


if __name__ == '__main__':
    main()
