"""lv-stat 스테이징 계산: out/<pid>/final-*.json → 카테고리 7개 LV(CONTRACT.md의 categories 칸).
2단계 S6 계산(고정 사다리판 s2_calc)을 스테이징 서비스로 옮김(2026-11-27).

- 단계 시작값은 2026-11-26 사용자가 확정한 고정 사다리(FIXED), AI 기술은 「문서」 lv-calc 값(SPEC).
- 「문서」 lv-calc 공통 규칙 1·4: 시작값 이상이면 그 단계(0~5). 단계 평균은 소수 첫째 자리 ROUND_HALF_UP.
  모름(None)은 평균에서 빼고, 모두 모름이면 null(판정 불가). unknown = 그 카테고리에서 단계가 None인 수.
- 변수 값은 variables[vid]의 value다. 모듈이 상태를 비운 채 값을 두었으면 규칙 값으로 쓴다.
- 데이터베이스 깊이는 근거 1곳이면 그 단계다(사용자 결정 2026-11-26): database.depth 값을 그대로 단계로 쓴다.
  2단계 계산의 '3~5단계는 파일 2곳' 규칙은 쓰지 않는다.
- 백엔드: 게이트 통과 레포가 없으면 0.0. 있으면 로그인·WAS·API·로그·DB 깊이·운영 배포 LV의 평균.
  unknown에는 대기·모름이고 값이 없는 SEC·WAS·API·LOG 항목 수를 더한다. 게이트를 모르면(파일 없음) 판정 불가.
- 가점(T/F·부가 기술 수 등)은 이번 판에 넣지 않는다.
- 파일 위치는 s2lib를 따른다(LV_S2_HOME, 불러올 때 정함).
"""
import decimal
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import s2lib as L  # noqa: E402

FIXED = {'prog.commits': [1, 7, 30, 180, 365], 'prog.lines': [1, 200, 1000, 5000, 25000], 'prog.period': [1, 7, 30, 150, 300],
         'deploy.repos': [1, 2, 3, 5, 8], 'deploy.period': [1, 7, 50, 150, 250],
         'dataeng.dags': [1, 2, 5, 10, 20], 'dataeng.period': [1, 7, 30, 100, 250],
         'database.tables': [1, 3, 8, 20, 50], 'database.period': [1, 7, 30, 120, 250],
         'api_calls': [1, 3, 10, 30, 100], 'data_io': [1, 3, 10, 30, 100], 'events': [1, 10, 30, 100, 300]}
SPEC = {'ai.integrations': [1, 2, 4, 8, 15], 'ai.features': [1, 2, 3, 5, 8],
        'ai.techniques.llm': [1, 2, 3, 5, 7], 'ai.techniques.ml': [1, 2, 3, 4, 6]}
NAMES = {'L': '프로그래밍 활용', 'O': '운영 배포', 'B': '백엔드 개발', 'E': '데이터 엔지니어', 'D': '데이터베이스',
         'F': '프론트엔드 앱', 'A': 'AI 기술'}
FILES = ('prog', 'deploy', 'backend_a', 'backend_b', 'de', 'db', 'fe', 'ai')
PROG = ('prog.commits', 'prog.lines', 'prog.period')
ITEM = re.compile(r'^backend\.(login|was|api|log)\.(SEC|WAS|API|LOG)\d+$')     # 백엔드 항목(상한 칸 SEC-C1 등은 아님)


def stage(v, starts):
    """시작값 이상이면 그 단계(0~5). 값이 없으면 None(모름)."""
    if v is None:
        return None
    s = 0
    for i, x in enumerate(starts, 1):
        if v >= x:
            s = i
    return s


def r1(x):
    """소수 첫째 자리 ROUND_HALF_UP(2.25 → 2.3). None은 None."""
    if x is None:
        return None
    return float(decimal.Decimal(str(x)).quantize(decimal.Decimal('0.1'), rounding=decimal.ROUND_HALF_UP))


def mean_known(xs):
    """None을 뺀 평균. 모두 None이면 None."""
    k = [x for x in xs if x is not None]
    return sum(k) / len(k) if k else None


def num(v):
    """수만 받는다(참·거짓·글자·None은 None)."""
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        return None
    return float(v)


def load(pid):
    out = {}
    for key in FILES:
        p = os.path.join(L.OUT, pid, f'final-{key}.json')
        if os.path.exists(p):
            with open(p, encoding='utf-8') as f:
                out[key] = json.load(f)
    return out


def variables(d, key):
    return (d.get(key) or {}).get('variables') or {}


def value(d, key, vid):
    """variables[vid]의 값(수). 없으면 None(모름)."""
    return num((variables(d, key).get(vid) or {}).get('value'))


def category(code, stages):
    return dict(name=NAMES[code], lv=r1(mean_known(stages)), unknown=stages.count(None))


def programming(d):
    """언어마다 커밋·바꾼 줄·기간 단계 평균. LV는 가장 높은 언어(같으면 먼저 나온 언어)."""
    langs = {}
    for vid, v in variables(d, 'prog').items():
        base, _, lang = vid.partition(':')
        if lang and base in PROG:
            langs.setdefault(lang, {})[base] = num(v.get('value'))
    languages, best, unknown = {}, None, 0
    for lang, vals in langs.items():
        stages = [stage(vals.get(k), FIXED[k]) for k in PROG]
        unknown += stages.count(None)
        lv = mean_known(stages)
        if lv is None:
            continue
        languages[lang] = r1(lv)
        if best is None or lv > best[1]:
            best = (lang, lv)
    if best:
        lv = r1(best[1])
    elif not langs and 'prog' in d:
        lv = 0.0                      # prog 파일은 있는데 언어가 하나도 없음
    else:
        lv = None
    return dict(name=NAMES['L'], lv=lv, unknown=unknown, languages=languages, best=best[0] if best else None)


def techniques_stage(d):
    """AI 기법 수: LLM·ML을 따로 단계로 바꿔 높은 쪽. 값이 없으면(대기) None."""
    v = variables(d, 'ai').get('ai.techniques') or {}
    if num(v.get('value')) is None:
        return None
    parts = v.get('parts') or {}
    return max(stage(num(parts.get('llm')) or 0, SPEC['ai.techniques.llm']),
               stage(num(parts.get('ml')) or 0, SPEC['ai.techniques.ml']))


def backend(d, depth, deploy_lv):
    gate = value(d, 'backend_a', 'backend.gate')
    if gate == 0:
        return dict(name=NAMES['B'], lv=0.0, unknown=0, note='백엔드 게이트 통과 레포 없음')
    comps = [value(d, 'backend_a', 'backend.login'), value(d, 'backend_a', 'backend.was'),
             value(d, 'backend_b', 'backend.api'), value(d, 'backend_b', 'backend.log'), depth, deploy_lv]
    pending = 0                       # 값이 없는 대기(상태 없음)·모름(unknown_*) 항목. 'value_rule+대기' 항목은 값이 있다
    for key in ('backend_a', 'backend_b'):
        for vid, v in variables(d, key).items():
            st = v.get('state')
            if ITEM.match(vid) and v.get('value') is None and (st is None or st.startswith('unknown')):
                pending += 1
    unknown = comps.count(None) + pending
    if gate is None:
        return dict(name=NAMES['B'], lv=None, unknown=unknown, note='백엔드 게이트를 판정하지 못함')
    return dict(name=NAMES['B'], lv=r1(mean_known(comps)), unknown=unknown, note=f'백엔드 게이트 통과 레포 {int(gate)}개')


def calc_person(pid):
    """-> {L, O, B, E, D, F, A}: CONTRACT.md의 categories 칸(B는 note를 더함)"""
    d = load(pid)
    deploy = category('O', [stage(value(d, 'deploy', k), FIXED[k]) for k in ('deploy.repos', 'deploy.period')])
    depth = value(d, 'db', 'database.depth')
    return dict(
        L=programming(d),
        O=deploy,
        B=backend(d, depth, deploy['lv']),
        E=category('E', [stage(value(d, 'de', k), FIXED[k]) for k in ('dataeng.dags', 'dataeng.period')]),
        D=category('D', [depth] + [stage(value(d, 'db', k), FIXED[k]) for k in ('database.tables', 'database.period')]),
        F=category('F', [stage(value(d, 'fe', k), FIXED[k]) for k in ('api_calls', 'data_io', 'events')]),
        A=category('A', [stage(value(d, 'ai', 'ai.integrations'), SPEC['ai.integrations']), techniques_stage(d),
                         stage(value(d, 'ai', 'ai.features'), SPEC['ai.features'])]),
    )
