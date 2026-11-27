"""lv-stat 스테이징 계산: out/<pid>/final-*.json → 카테고리 7개 LV(CONTRACT.md의 categories 칸).
2단계 S6 계산(고정 사다리판 s2_calc)을 스테이징 서비스로 옮김(2026-11-27).

- 단계 시작값은 2026-11-26 사용자가 확정한 고정 사다리(FIXED), AI 기술은 「문서」 lv-calc 값(SPEC).
- 「문서」 lv-calc 공통 규칙 1·4: 시작값 이상이면 그 단계(0~5). 단계 평균은 소수 첫째 자리 ROUND_HALF_UP
  (평균은 10진수로 정확히 센다: 백엔드 성분은 소수 한 자리라 float로 더하면 x.x5가 내려가는 일이 있다).
  모름(None)은 평균에서 빼고, 모두 모름이면 null(판정 불가). unknown = 그 카테고리에서 단계가 None이거나 대기인 변수 수.
- 변수 값은 variables[vid]의 value다. 모듈이 상태를 비운 채 값을 두었으면 규칙 값으로 쓴다.
- 대기(LLM 보충 끔. 사용자 결정 2026-11-26 '확인된 것만 세고 모름 n개'): 답 없는 LLM 대상이 남은 변수다.
  20명 LLM 끔 마무리 파일에서 확인한 표시는 변수 기록의 대기 수다: s5.waiting(db·fe·ai)·s5.pending(deploy)·
  s5_waiting(ai)·waiting_n(de). 이 수는 대상 목록에 남은 그 변수의 대상 수와 같고, 답을 반영한 2단계 마무리 파일에서는
  0이다(대상 목록은 답이 있어도 남으므로 목록만으로는 대기를 가리지 못한다). 대기 수가 없는 기록은 목록에 남은 그 변수의
  대상 수로 센다. 마무리 파일에서 그런 기록에 대상이 남는 것은 백엔드 게이트뿐이다(cat_backend_a는 통과 레포가 있으면 게이트
  상태를 'value_rule'로 두고, 0개일 때만 'value_rule+대기'로 둔다. 어느 쪽이든 게이트 대상은 목록에 있다). 그 파일이 답 없는
  대상 0개라고 셌으면(stats.s5_waiting == 0) 대기가 아니다. 상태의 '대기'는 게이트와 백엔드 항목에만 나와 따로 보지 않는다.
  대기인 변수는 모름 1개다. 값이 0·없음이면 확인된 값이 아니므로 단계도 없고(평균에서 뺌), 값이 있으면 그 값의 단계
  (확인된 만큼, 아래 한계)를 쓴다. 프로그래밍 변수와 백엔드 성분(login·was·api·log) 기록에는 대상·대기 수가 없다
  (백엔드의 대기는 항목에 있고, 아래 항목 규칙으로 센다).
- 데이터베이스 깊이는 근거 1곳이면 그 단계다(사용자 결정 2026-11-26): database.depth 값을 그대로 단계로 쓴다.
  2단계 계산의 '3~5단계는 파일 2곳' 규칙은 쓰지 않는다.
- 백엔드: 게이트(backend.gate) 0이고 대기가 아니면 0.0(통과 레포 없음, 모름 0). 0인데 대기면 판정 불가(null,
  '백엔드 게이트를 판정하지 못함(LLM 보충 끔)'). 1 이상이면 로그인·WAS·API·로그·DB 깊이·운영 배포 LV의 평균.
  게이트를 모르면(파일 없음) 판정 불가. unknown = 값이 없거나 대기인 성분 수(운영 배포는 그 칸에 모름이 있으면)
  + 대기 게이트 1 + 대기·모름이고 값이 없는 SEC·WAS·API·LOG 항목 수.
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


def dec(x):
    """수 → 10진수. float는 짧은 표기(str) 그대로 읽는다(3.2 → Decimal('3.2'))."""
    return x if isinstance(x, decimal.Decimal) else decimal.Decimal(str(x))


def r1(x):
    """소수 첫째 자리 ROUND_HALF_UP(2.25 → 2.3, 1.35 → 1.4). None은 None."""
    if x is None:
        return None
    return float(dec(x).quantize(decimal.Decimal('0.1'), rounding=decimal.ROUND_HALF_UP))


def mean_known(xs):
    """None을 뺀 평균(Decimal). 10진수로 더하고 나눠 정확한 x.x5가 r1에서 올라간다
    (8.1 / 6 = 1.35 → 1.4. float로 더하면 1.3499… → 1.3). 모두 None이면 None."""
    k = [dec(x) for x in xs if x is not None]
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


def waiting(d, key, vid):
    """그 변수에 남은 답 없는 LLM 대상 수(머리 설명의 '대기')."""
    f = d.get(key) or {}
    rec = variables(d, key).get(vid) or {}
    s5 = rec.get('s5') if isinstance(rec.get('s5'), dict) else {}
    counts = [n for n in (s5.get('waiting'), s5.get('pending'), rec.get('s5_waiting'), rec.get('waiting_n'))
              if isinstance(n, int) and not isinstance(n, bool)]
    if counts:
        return max(counts)
    if (f.get('stats') or {}).get('s5_waiting') == 0:      # 모듈이 답 없는 대상이 없다고 셌다(답을 반영한 파일)
        return 0
    return sum(1 for t in f.get('s5_targets') or [] if t.get('var') == vid)


def read(d, key, vid):
    """-> (값, 대기). 대기인 0·없음은 확인된 값이 아니라 None이다."""
    v = value(d, key, vid)
    held = waiting(d, key, vid) > 0
    return (None if held and not v else v), held


def staged(d, key, vid, starts):
    """-> (단계, 모름). 모름 = 단계가 없거나 대기."""
    v, held = read(d, key, vid)
    s = stage(v, starts)
    return s, s is None or held


def category(code, parts):
    """parts = [(단계, 모름)]"""
    return dict(name=NAMES[code], lv=r1(mean_known([s for s, _ in parts])), unknown=sum(1 for _, u in parts if u))


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


def techniques(d):
    """AI 기법 수: LLM·ML을 따로 단계로 바꿔 높은 쪽. -> (단계, 모름). 값이 없거나 대기인 0이면 단계 없음."""
    v, held = read(d, 'ai', 'ai.techniques')
    if v is None:
        return None, True
    parts = (variables(d, 'ai').get('ai.techniques') or {}).get('parts') or {}
    return max(stage(num(parts.get('llm')) or 0, SPEC['ai.techniques.llm']),
               stage(num(parts.get('ml')) or 0, SPEC['ai.techniques.ml'])), held


def backend(d, depth, deploy):
    """depth = DB 깊이 (단계, 모름), deploy = 운영 배포 칸."""
    gate = value(d, 'backend_a', 'backend.gate')
    held = waiting(d, 'backend_a', 'backend.gate') > 0
    if gate == 0 and not held:
        return dict(name=NAMES['B'], lv=0.0, unknown=0, note='백엔드 게이트 통과 레포 없음')
    comps = [value(d, 'backend_a', 'backend.login'), value(d, 'backend_a', 'backend.was'),
             value(d, 'backend_b', 'backend.api'), value(d, 'backend_b', 'backend.log'), depth[0], deploy['lv']]
    items = 0                         # 값이 없는 대기(상태 없음)·모름(unknown_*) 항목. 'value_rule+대기' 항목은 값이 있다
    for key in ('backend_a', 'backend_b'):
        for vid, v in variables(d, key).items():
            st = v.get('state')
            if ITEM.match(vid) and v.get('value') is None and (st is None or st.startswith('unknown')):
                items += 1
    unknown = comps[:4].count(None) + depth[1] + (deploy['unknown'] > 0) + held + items
    if gate is None:
        return dict(name=NAMES['B'], lv=None, unknown=unknown, note='백엔드 게이트를 판정하지 못함')
    if gate == 0:
        return dict(name=NAMES['B'], lv=None, unknown=unknown, note='백엔드 게이트를 판정하지 못함(LLM 보충 끔)')
    return dict(name=NAMES['B'], lv=r1(mean_known(comps)), unknown=unknown, note=f'백엔드 게이트 통과 레포 {int(gate)}개')


def calc_person(pid):
    """-> {L, O, B, E, D, F, A}: CONTRACT.md의 categories 칸(B는 note를 더함)"""
    d = load(pid)
    deploy = category('O', [staged(d, 'deploy', k, FIXED[k]) for k in ('deploy.repos', 'deploy.period')])
    v, held = read(d, 'db', 'database.depth')
    depth = (v, v is None or held)    # 깊이는 값이 곧 단계
    return dict(
        L=programming(d),
        O=deploy,
        B=backend(d, depth, deploy),
        E=category('E', [staged(d, 'de', k, FIXED[k]) for k in ('dataeng.dags', 'dataeng.period')]),
        D=category('D', [depth] + [staged(d, 'db', k, FIXED[k]) for k in ('database.tables', 'database.period')]),
        F=category('F', [staged(d, 'fe', k, FIXED[k]) for k in ('api_calls', 'data_io', 'events')]),
        A=category('A', [staged(d, 'ai', 'ai.integrations', SPEC['ai.integrations']), techniques(d),
                         staged(d, 'ai', 'ai.features', SPEC['ai.features'])]),
    )
