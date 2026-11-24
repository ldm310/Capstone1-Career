#!/usr/bin/env python3
"""run_profile.py / run_pipeline.py 결과 폴더 -> REPORT.md 의 표 부분(숫자·위치는 결과 파일에서 그대로 옮긴다. 판정이 맞는지는 판단하지 않는다).

Usage:
  python3 pipeline/make_report.py --profile out/profile [--local out/local-career-stat] [--variant out/profile-plus-develop] \\
      [--head out/_parts/head.md] [--tail out/_parts/tail.md] [--local-note 글.md] [--variant-note 글.md] [--postings data/postings.json] --out out/REPORT.md
  --head/--tail 은 사람이 쓴 글(만든 파일, 명령, 확인한 것, 이상한 점 등)을 앞뒤에 그대로 붙인다.
  --local-note/--variant-note/--base-note 는 7번·8번 절의 맨 앞에 붙일 글이다.
  --base 는 견줄 결과 폴더(예: 기본 브랜치만 본 이전 결과)다. 주면 8번에 그 결과와 달라진 stat 키를 적는다(--variant 와 함께 쓰지 않는다).
  근거 위치 옆의 「(LV1 근거)」 표시는 결과 폴더의 run.json 이 가리키는 내 근거 파일(repos/…/bundle.mine*.json)을 읽어 붙인다.
  --postings 는 기준표에서 `제외`라 match.json 에 없는 줄이 공고마다 몇 줄인지 세는 데만 쓴다(기본 data/postings.json).
    파일이 없거나 그 결과를 만들 때 쓴 기준표와 맞지 않으면 그 수는 적지 않는다.
레포·공고·점검 에이전트에서 온 글은 표를 깨거나 HTML·코드 글씨·링크·그림으로 읽히지 않게 글자로 바꿔 넣는다(맨 URL 은 코드 글씨로 싸서 링크가 되지 않게 한다).
"""
import argparse, json, os, re, sys
sys.dont_write_bytecode = True                         # 보고서만 만드는 스크립트: pipeline/__pycache__ 를 남기지 않는다
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import identity as ID, keys as K, make_packets as MP

ORDER = ('충족', '기법 충족', '부분', '미충족', '판단 불가')
# identity.py 가 붙이는 표시의 뜻. CERTAIN 은 고르는 근거, 나머지는 사람이 볼 실마리
CERTAIN = ('name', 'noreply', 'email', 'same-email+name~')
HINTS = {'name': '이름이 알려 준 이름과 글자 그대로 같음', 'noreply': '이메일이 내 계정의 GitHub noreply 주소', 'email': '알려 준 이메일과 같음',
         'same-email+name~': '내 이름 커밋과 이메일이 같고 이름은 대소문자·공백·낱말 순서만 다름',
         'name~case': '이름이 대소문자·구분 문자만 다름', 'name~order': '이름의 낱말 순서만 다름', 'name~part': '이름 낱말 일부가 같음', 'same-email': '내 이름 커밋과 이메일이 같은데 이름이 다름',
         'name-in-email': '이메일에 내 이름 낱말이 있음', 'login-in-name': '이름에 계정 이름이 있음', 'login-in-email': '이메일에 계정 이름이 있음',
         'ai-commit-pushed-by-other': 'AI 가 쓴 커밋을 올린 사람이 내가 아님', 'control-chars-in-repo': '작성자 이름·이메일에 제어 문자가 든 커밋이 있는 레포'}
REPO_HEAD = ['레포', 'HEAD', '내 이름으로 고른 git 이름', '내 근거 수', '점검 대상(LV3 이상 활동)', '점검한 판정 수', '통과', '기각', '모름', '비고']
URL = re.compile(r'(?:https?://|www\.)[^\s<>|`]+', re.I)
MAILISH = re.compile(r'[^@\s<>()\[\],;:"]+@[^@\s<>()\[\],;:"]+')      # 이름 칸에 섞여 있을 수 있는 이메일 꼴 조각
GROUP_KEYS = [g for _, g in getattr(K, '_G', [])]      # 공고 줄에 실제로 붙는 묶음 키(정규식이 있는 것만)


class Safe(str):
    """이미 표에 넣어도 되게 만든 글(코드 글씨, 줄바꿈 표시가 든 것)"""


def load(path, default=None):
    if not os.path.exists(path): return default
    with open(path, encoding='utf-8') as f: return json.load(f)


def _plain(t):
    t = t.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
    return t.replace('\\', '\\\\').replace('|', '\\|').replace('`', '\\`').replace('](', ']\\(').replace('![', '!\\[')


def esc(s, links=False):
    """바깥에서 온 글 -> 표 한 칸에 넣을 글자. 줄바꿈·세로줄이 칸을 나누거나, 꺾쇠가 HTML 로, 백틱이 코드 글씨로, `](`·`![` 가 링크·그림으로 읽히지 않게 한다.
    맨 URL 은 코드 글씨로 싸서 링크가 되지 않게 한다(links=True 면 그대로 둔다: 기준표에 있는 공고 주소처럼 눌러 볼 주소)."""
    t = ('' if s is None else str(s)).replace('\r', ' ').replace('\n', ' ').strip()
    if links: return Safe(t) if re.fullmatch(r'https?://[^\s<>|`\\\[\]()]+', t) else Safe(_plain(t))      # 주소 꼴이 아니면 보통 글처럼 바꾼다
    out, pos = [], 0
    for m in URL.finditer(t):
        out.append(_plain(t[pos:m.start()])); out.append(code(m.group(0))); pos = m.end()
    out.append(_plain(t[pos:]))
    return Safe(''.join(out))


def code(s):
    """근거 위치처럼 글자 그대로 보여야 하는 것: 코드 글씨로(경로의 밑줄·별표가 서식이 되지 않게)"""
    t = ('' if s is None else str(s)).replace('\r', ' ').replace('\n', ' ').replace('`', "'").replace('|', '\\|').strip()
    return Safe(f'`{t}`' if t else '')


def who(name):
    """git 이름을 보고서에 적을 때: 이름 칸에 이메일 주소가 들어 있으면(이름 전체이든 일부이든) 그 조각을 가려서 적는다"""
    n = '' if name is None else str(name)
    return MAILISH.sub(lambda m: ID.mask_email(m.group(0)), n)


def label(repo):
    """레포 라벨. 한 레포에 내 이름이 둘이면 '레포#git 이름' 꼴이라, # 뒤 이름에 든 이메일 꼴은 가린다(레포 쪽의 '@develop' 은 건드리지 않는다)"""
    r = '' if repo is None else str(repo)
    if '#' not in r: return r
    a, b = r.split('#', 1)
    return f'{a}#{who(b)}'


def loc(repo, where, note=''):
    return Safe(f'{code(label(repo))} · {code(where)}' + (f' {esc(note)}' if note else ''))


def lines(items):
    """한 칸 안의 여러 줄"""
    return Safe('<br>'.join(x if isinstance(x, Safe) else esc(x) for x in items))


def table(head, rows):
    out = ['| ' + ' | '.join(head) + ' |', '|' + '|'.join('---' for _ in head) + '|']
    out += ['| ' + ' | '.join(c if isinstance(c, Safe) else esc(c) for c in r) + ' |' for r in rows]
    return '\n'.join(out)


def source_of(v):
    return v['source'] + (f" ← {v['by']}" if v.get('by') else '')


def bundle_lv(bundles, verdicts, repo, key, where):
    """stat 의 근거 한 줄이 그 레포 bundle 에서 몇 LV 근거였는지(to_stat.py 와 같은 규칙). 하나로 정해지지 않으면 None"""
    found = set()
    for b in bundles:
        if b['meta']['repo'] != repo: continue
        for e in b['evidence']:
            if e['key'] != key: continue
            lv, w = e['lv'], e['where']
            if e['kind'] != 'activity' and e.get('lifted_by'):
                if verdicts.get((repo, e['lifted_by']), 'pass') != 'pass': lv, w = e.get('own_lv', 0), e.get('own_where', e['where'])
                else: w = e.get('lifted_where', e['where'])
            if w == where: found.add(lv)
    return found.pop() if len(found) == 1 else None


def ev_lines(k, v, lv_of=None):
    """근거 위치 칸. 둘째 줄부터, 그 키의 LV 보다 낮은 LV 의 근거(다른 레포의 근거)는 옆에 표시한다.
    첫 줄은 to_stat.py 가 항상 그 LV 를 준 근거로 두므로 표시하지 않는다. implied 키의 근거는 올려 준 도구의 근거 한 줄이라 표시하지 않는다."""
    out = []
    for i, e in enumerate(v['evidence']):
        lv = lv_of(e['repo'], k, e['where']) if lv_of and i and v.get('source') != 'implied' else None
        out.append(loc(e['repo'], e['where'], f'(LV{lv} 근거)' if lv is not None and lv < v['lv'] else ''))
    return lines(out)


def stat_table(stat, lv_of=None):
    rows = [[k, v['lv'], v['kind'], source_of(v), ev_lines(k, v, lv_of), ''] for k, v in stat['stat'].items()]   # to_stat 이 LV 높은 순(같으면 이름순)으로 정렬해 둠
    return table(['키', 'LV', 'kind', 'source', '근거 위치 (레포 · 경로:줄)', '맞음/틀림'], rows) if rows else '(stat 키 없음)'


def stat_guide(stat, annotated=True):
    return (f"stat 키 {len(stat['stat'])}개 (LV 높은 순). `source`: own 직접 근거 / lifted 그 도구로 한 활동의 LV(← 활동) / implied 다른 도구가 뜻하는 이름(← 도구, 근거도 그 도구의 것). "
            '근거 위치는 키마다 최대 3개까지 나온다. 첫 줄이 그 LV 를 준 근거이고, 둘째 줄부터는 같은 키의 다른 레포 근거다'
            + ('(LV 가 더 낮으면 옆에 `(LV1 근거)` 처럼 적었다).' if annotated else '(LV 가 더 낮을 수 있다. 내 근거 파일 `repos/…/bundle.mine.json` 을 읽지 못해 어느 줄이 낮은지는 표시하지 못했다).'))


def lv_lookup(d, run, vrows):
    """결과 폴더의 내 근거 파일들(run.json 의 stat_inputs) -> (레포, 키, 위치) 로 그 근거의 LV 를 찾는 함수. 파일을 하나라도 못 읽으면 None(표시를 붙이지 않는다)"""
    names = (run or {}).get('stat_inputs') or []
    bundles = [load(os.path.join(d, x)) for x in names]
    if not names or any(b is None for b in bundles): return None
    verdicts = {(r['repo'], r['key']): r['verdict'] for r in vrows or []}
    return lambda repo, key, where: bundle_lv(bundles, verdicts, repo, key, where)


def none_note(verify, n_packets, n_answered):
    """'없음' 이 '점검 에이전트가 보고 없다고 했다'로 읽히지 않게, 점검이 실제로 있었는지를 붙인다(n_answered: 실제로 받은 답 수)"""
    if not verify: return '없음 (점검 없이 돌렸다)'
    if not n_packets: return '없음 (점검 대상이 0건이라 점검 에이전트를 부르지 않았다)'
    if not n_answered: return '없음 (점검 대상은 있었지만 받은 답이 0건이다)'
    return '없음'


def weak_table(stat, vrows, none='없음', fill=None):
    """fill: 판정 줄에 근거 위치가 없을 때(run_pipeline.py 가 쓴 verdicts.json) (사람, 키) 로 근거 위치를 찾는 함수"""
    why = {}
    for r in vrows or []:
        if r['verdict'] == 'unsure': why.setdefault(r['key'], []).append(r)
    rows = []
    for k, w in stat['weak'].items():
        ev = w.get('evidence') or []; hit = why.get(k) or []
        if hit and all('evidence' in x for x in hit):      # 점검에서 모름: 실제로 모름을 받은 근거와 이유를 판정 줄에서 가져온다(to_stat 은 키마다 마지막 근거 하나만 남김)
            where = lines(loc(x['repo'], x['evidence']) for x in hit)
            note = lines((x.get('reason') or '') if x.get('answered', True) else '(답 없음: 응답이 버려졌거나, 모델이 이 판정에 답하지 않았거나, 호출 실패)' for x in hit)
        else:
            where = lines(loc(e.get('repo'), e.get('where')) for e in ev)
            note = lines((x.get('reason') or '').strip() or '(이유 없음: 점검 에이전트의 답이 없어 모름으로 채워진 줄일 수 있다)' for x in hit) if hit else ''
        rows.append([k, w.get('claimed_lv') or '-', w.get('reason'), where, note])
    return table(['키', '규칙이 낸 LV', '정황인 이유', '근거 위치', '점검 에이전트가 적은 이유'], rows) if rows else none


def reject_table(vrows, none='없음', fill=None):
    rows = []
    for r in vrows or []:
        if r['verdict'] != 'reject': continue
        lv, where = r.get('lv'), r.get('evidence')
        if (lv is None or where is None) and fill:
            f = fill(r) or {}; lv = f.get('lv') if lv is None else lv; where = f.get('where') if where is None else where
        rows.append([code(label(r['repo'])), r['key'], '' if lv is None else lv, code(where or ''), r.get('reason_code'), r.get('reason')])
    return table(['레포', '기각된 판정', 'LV', '근거 위치', '사유 코드', '점검 에이전트가 적은 이유'], rows) if rows else none


def excluded_counts(path):
    """기준표(postings.json) -> ({공고 번호: (줄 수, 그중 `제외` 줄 수)}, 전체 줄 수, 전체 제외 줄 수). match.py 는 제외 줄을 버려서 match.json 에는 없다"""
    doc = load(path) if path else None
    if not doc: return {}, 0, 0
    per = {str(p['posting_id']): (len(p['lines']), sum(1 for l in p['lines'] if l.get('excluded'))) for p in doc['postings']}
    return per, sum(a for a, _ in per.values()), sum(b for _, b in per.values())


def excl_for(match, excl_all):
    """이 match.json 이 그 기준표로 만든 것이 맞을 때만 제외 줄 수를 쓴다(공고 수가 같고, 공고마다 줄 수 - 제외 줄 수 = match 의 줄 수)"""
    per, n_lines, n_ex = excl_all
    if not per: return {}, 0, 0, '없음'
    ok = len(per) == match['n_postings'] and all(str(p['posting_id']) in per and per[str(p['posting_id'])][0] - per[str(p['posting_id'])][1] == len(p['lines']) for p in match['postings'])
    return (per, n_lines, n_ex, '맞음') if ok else ({}, 0, 0, '다름')


def posting_block(p, i, fold=False, excl=None):
    s = p['summary']
    head = f"**{i}. {esc(p['company'])} — {esc(p['title'])}**" + (f" ({esc(p['position'])})" if p.get('position') else '')
    ex = (excl or {}).get(str(p['posting_id']))
    rate = '-' if s['rate'] is None else s['rate']; rate2 = '-' if s['rate_with_technique'] is None else s['rate_with_technique']
    info = (f"- 공고 번호 {esc(p['posting_id'])} · 경력 {code(p.get('career'))}" + (f" · {esc(p['career_note'])}" if p.get('career_note') else '') + f" · {esc(p.get('link'), links=True)}\n"
            f"- 충족률 **{rate}** (충족 {s['충족']} / 판정한 줄 {s['judged']}) · 기법 충족 포함 {rate2} · " + ', '.join(f"{k} {s[k]}" for k in ORDER)
            + (f" · 기준표의 이 공고 줄 {ex[0]}개 중 `제외` {ex[1]}개는 표에 없음" if ex else ''))
    rows = []
    for l in sorted(p['lines'], key=lambda l: (ORDER.index(l['status']), l['line_id'])):
        keys = ', '.join(f"{d['key']}({d['my_lv']})" + (f"←{d['via']}" if d.get('via') else '') for d in l.get('keys') or [])
        rows.append([l['status'], l['lv_required'] if l['lv_required'] else '-', '-' if l['my_lv'] is None else l['my_lv'], l['section'], l['text'][:110] + ('…' if len(l['text']) > 110 else ''), keys,
                     f"경력 조건: {l['career_rule']}" if l.get('career_rule') else ''])
    t = table(['상태', '요구 LV', '내 LV', '구분', '공고 줄', '줄의 키(내 LV)', '비고'], rows)
    return f"{head}\n{info}\n\n" + (f"<details><summary>줄별 판정 {len(rows)}줄</summary>\n\n{t}\n\n</details>" if fold else t)


def postings_top(match, n=5, fold=False, excl=None):
    ps = match['postings'][:n]                             # match.py 가 충족률 높은 순(같으면 판정한 줄이 많은 순)으로 정렬해 둠
    return '\n\n'.join(posting_block(p, i + 1, fold, excl) for i, p in enumerate(ps)) if ps else '(공고 없음)'


def postings_guide(match, excl):
    """공고 표 읽는 법(5번 머리 글). 판정 방식은 match.py·HANDOFF 3번 그대로이고, 여기서는 표에 안 보이는 것만 적는다. excl: excl_for() 의 결과"""
    _, n_lines, n_ex, state = excl
    out = [f"공고 {match['n_postings']}개 중 match.py 정렬(충족률 높은 순, 같으면 판정한 줄이 많은 순)의 앞 {min(5, match['n_postings'])}개. 줄 판정 방식 `{esc(match['line_mode'])}`.", '',
           '- 요구 LV 는 기준표의 `기술 LV(줄 기준)` 칸이다(HANDOFF 3번). 기준표의 `LV` 칸이 아니다. 요구 LV `-` 는 기준표에 기술 LV 가 없는 줄(기준표 상태가 `판단 불가`)이고, 내 LV `-` 는 판단 불가 줄이다.',
           '- 「줄의 키(내 LV)」 칸은 그 줄에 붙은 키와 그 키의 내 LV 다(0 은 내 stat 에 없음). `RDB(2)←JPA` 처럼 `←` 가 붙은 것은 묶음 키'
           + (f"({', '.join(GROUP_KEYS)})" if GROUP_KEYS else '') + '를 내 stat 의 그 도구로 채웠다는 뜻이다.',
           '- 비고의 `경력 조건: …` 은 기준표의 `경력 규칙` 칸 글을 그대로 옮긴 것이다. 경력 조건이 붙은 줄도 위 요구 LV 로 판정해 충족률에 넣었다. 판정하지 않은 것은 경력 조건 자체이고, 머리 줄의 「경력 조건 있음(판정 안 함)」도 그 뜻이다(9번 가-6).']
    if state == '맞음': out.append(f"- 기준표에서 `기술 LV(줄 기준)` 이 `제외`인 줄은 match.py 가 버려서 match.json 과 아래 표에 없다(기준표 {n_lines:,}줄 중 {n_ex:,}줄). 공고마다 빠진 줄 수는 머리 줄에 적었다.")
    else: out.append('- 기준표에서 `기술 LV(줄 기준)` 이 `제외`인 줄은 match.py 가 버려서 match.json 과 아래 표에 없다. ' + ('`--postings` 로 준 기준표가 이 결과를 만들 때 쓴 것과 달라서' if state == '다름' else '기준표 파일이 없어서') + ' 빠진 줄 수는 적지 않았다.')
    return '\n'.join(out)


def tie_text(pool, shown, what, where='위 목록'):
    """shown 의 마지막 공고와 정렬 키(충족률, 판정한 줄 수)가 같은 공고들. match.py 의 정렬은 안정 정렬이라 그 안의 순서는 postings.json 에 실린 순서다"""
    last = shown[-1]; key = (last['summary']['rate'], last['summary']['judged'])
    same = [p for p in pool if (p['summary']['rate'], p['summary']['judged']) == key]
    ids = [str(p['posting_id']) for p in same]; left = [str(p['posting_id']) for p in same if p not in shown]

    def nums(xs, cap=12):                                  # 12개가 넘으면 앞 12개만 적는다
        return ', '.join(xs[:cap]) + '번' + (f' 외 {len(xs) - cap}개' if len(xs) > cap else '')
    t = f"{what} {len(shown)}번째({esc(last['posting_id'])}번)와 충족률·판정한 줄 수가 모두 같은 공고는 {len(same)}개다({esc(nums(ids))})."
    if not left: return t + f' 모두 {where} 안에 있다.'
    return t + f" 그 안의 순서는 `data/postings.json` 에 실린 순서이고, 그중 {esc(nums(left))}{'는' if len(left) > 12 else '은'} {where}에 들지 못했다."


def postings_note(match, n=5, min_judged=5):
    """상위 n개가 어떤 동률 속에서 뽑혔는지와, 판정한 줄이 min_judged 줄 이상인 공고만 봤을 때의 상위 n개(요약만)"""
    ps = match['postings']
    if not ps: return ''
    rated = [p for p in ps if p['summary']['rate'] is not None]
    top = ps[:n]; cut = top[-1]['summary']['rate']
    one = sum(1 for p in top if p['summary']['judged'] == 1)
    big = [p for p in ps if p['summary']['judged'] >= min_judged][:n]
    rows = [[p['posting_id'], p['company'], p['title'][:40] + ('…' if len(p['title']) > 40 else ''), p['summary']['rate'], f"{p['summary']['충족']}/{p['summary']['judged']}", p['summary']['부분'], p['summary']['미충족'], p['summary']['판단 불가']] for p in big]
    cut_text = (f"{len(top)}번째 공고는 판정한 줄이 0줄이라 충족률이 없다." if cut is None
                else f"{len(top)}번째 공고의 충족률 {cut} 과 충족률이 같은 공고는 {sum(1 for p in rated if p['summary']['rate'] == cut)}개다.")
    return (f"- 충족률을 낼 수 있는 공고는 {len(rated)}개다(판정한 줄이 0줄인 공고 {len(ps) - len(rated)}개 제외). {cut_text} 위 {len(top)}개 중 판정한 줄이 1줄뿐인 공고가 {one}개다.\n"
            f"- {tie_text(ps, top, '위 목록의')}\n"
            + (f"- 참고: 판정한 줄이 {min_judged}줄 이상인 공고만 보면 앞 {len(big)}개는 아래 표와 같다(같은 정렬). {tie_text([p for p in ps if p['summary']['judged'] >= min_judged], big, '이 표의', '이 표')}\n\n"
               + table(['공고 번호', '회사', '제목', '충족률', '충족/판정한 줄', '부분', '미충족', '판단 불가'], rows) if big else f"- 판정한 줄이 {min_judged}줄 이상인 공고는 없다."))


def repo_table(run):
    rows = []
    for t in run['targets']:
        v = t.get('verdicts'); ok = t['status'] == 'ok'
        note = [t.get('verify') or '', t.get('clone') or '']
        if t['status'] == 'failed': note = [f"실패 — {t.get('stage')}: {t.get('reason')}"]
        if t['status'] == 'excluded': note = [f"stat 에서 뺌 — {t.get('reason')}"]
        if t.get('verify_stopped'): note.append('점검이 중간에 멈춤: ' + t['verify_stopped'])
        if t.get('missing'): note.append(f"답 없음 {t['missing']}건은 모름으로 처리")
        nc = len(t.get('candidates') or [])                    # 고르지 않은 후보 이름은 남이라고 단정하지 않는다
        if ok and t.get('others'):
            if t['others'] - nc > 0: note.append(f"다른 기여자 {t['others'] - nc}명")
            if nc: note.append(f"고르지 않은 후보 이름 {nc}개")
        rows.append([code(t['label']), code((t.get('head') or '')[:7]), ', '.join(who(x) for x in t.get('mine') or []) or '-', t.get('evidence', '-') if ok else '-', t.get('packets', '-') if ok else '-',
                     t.get('answered', 0) if ok else '-', v['pass'] if v else '-', v['reject'] if v else '-', v['unsure'] if v else '-', ' · '.join(x for x in note if x)])
    return table(REPO_HEAD, rows)


def cand_text(x, counts=True):
    return who(x['display']) + ': ' + ', '.join(f"{who(p['name'])} ({p['email']})" + (f" {p['commits']}커밋" if counts else '') + f" [{', '.join(p['signals'])}]" for p in x.get('pairs', []))


def hint_legend(groups):
    """후보 표 아래에 붙이는 표시 설명(그 표에 나온 것만). 고르는 근거와 실마리를 나눠 적는다"""
    seen = []
    for x in groups:
        for q in x.get('pairs', []):
            for sg in q['signals']:
                if sg not in seen: seen.append(sg)
    if not seen: return ''

    def one(sg):
        return f"{code(sg)} " + (HINTS.get(sg) or ('다른 계정의 noreply 주소가 섞임' if sg.startswith('conflict:noreply=') else '')) + (' (고르는 근거)' if sg in CERTAIN else ' (실마리)')
    tail = ' 실마리는 고르는 근거가 아니라 사람이 볼 단서다.'
    if any(sg in CERTAIN for sg in seen): tail += ' 고르는 근거가 있는 이름도, 근거가 없는 쌍이 같은 묶음에 섞였거나 다른 계정의 noreply 주소가 있으면 고르지 않는다.'
    return '\n\n대괄호 안 표시의 뜻: ' + ' · '.join(one(sg) for sg in seen) + '.' + tail


def cand_groups(idents, targets):
    return [x for t in targets for x in (idents.get(t['label']) or {}).get('groups', []) if x['verdict'] == 'candidate']


def trouble(run, idents):
    out = []
    bad = [t for t in run['targets'] if t['status'] == 'failed']
    out.append('**실패한 레포**\n\n' + (table(['레포', '단계', '이유'], [[code(t['label']), t.get('stage'), t.get('reason')] for t in bad]) if bad else '없음'))
    if not (run.get('listing') or {}).get('ok'): out.append(f"**레포 목록을 받지 못함**: {esc((run.get('listing') or {}).get('error'))}")
    out.append('**받지 않은 레포(포크·비공개·없는 주소)**\n\n' + (table(['레포', '이유'], [[code(s['repo']), s['reason']] for s in run['skipped']]) if run.get('skipped') else '없음'))
    rows = []
    for t in run['targets']:
        if t['status'] != 'excluded': continue
        g = (idents.get(t['label']) or {}).get('groups') or []
        rows.append([code(t['label']), t.get('reason'), lines(cand_text(x) for x in g if x['verdict'] == 'candidate') or '후보 없음', ', '.join(f"{who(x['display'])}({x['commits']})" for x in g)])
    out.append('**내 이름이 확실하지 않아 stat 에서 뺀 레포**\n\n' + (table(['레포', '이유', '후보 이름', '그 레포의 기여자 이름(커밋 수)'], rows) if rows else '없음')
               + hint_legend(cand_groups(idents, [t for t in run['targets'] if t['status'] == 'excluded'])))
    extra = [[code(t['label']), lines(cand_text(x) for x in (idents.get(t['label']) or {}).get('groups', []) if x['verdict'] == 'candidate')] for t in run['targets'] if t['status'] == 'ok' and t.get('candidates')]
    out.append('**stat 에는 넣었지만, 고르지 않은 후보 이름이 더 있는 레포** — 본인 것이면 `--name`(이름이 다를 때)이나 `--email`(이메일이 다를 때)로 알려 주고 다시 돌린다\n\n'
               + (table(['레포', '고르지 않은 후보 — 이름 (가린 이메일) 커밋 수 [표시]'], extra) if extra else '없음')
               + hint_legend(cand_groups(idents, [t for t in run['targets'] if t['status'] == 'ok' and t.get('candidates')])))
    return '\n\n'.join(out)


def check_run(run, d):
    if run is None: sys.exit(f'{d}/run.json 이 없음')
    if run.get('aborted') or not run.get('finished'):
        sys.exit(f"{d}: 끝까지 가지 못한 실행이라 표를 만들지 않음({run.get('aborted') or '끝난 시각이 없음'}). 같은 폴더의 stat.json 은 이전 실행 것일 수 있음")


def profile_sections(d, excl_all=({}, 0, 0), title_prefix=''):
    run = load(os.path.join(d, 'run.json')); check_run(run, d)
    stat, match = load(os.path.join(d, 'stat.json')), load(os.path.join(d, 'match.json'))
    vrows, idents = load(os.path.join(d, 'verdicts.json'), []), load(os.path.join(d, 'identity.json'), {})
    okt = [t for t in run['targets'] if t['status'] == 'ok']
    n_p = sum(t.get('packets') or 0 for t in okt); n_a = sum(t.get('answered') or 0 for t in okt)
    agent = f"{esc(run.get('model'))}, effort {esc(run.get('effort'))}"
    mode = ('**점검 없이 돌림(--no-verify, 규칙만)**' if not run['verify'] else f"점검 에이전트 켬({agent}) — **점검 대상이 0건이라 호출은 없었다**" if not n_p else f"점검 에이전트 사용({agent})")
    none = none_note(run['verify'], n_p, n_a); ex = excl_for(match, excl_all); lv_of = lv_lookup(d, run, vrows)
    more = run.get('also_branch') or []
    out = [f"## {title_prefix}1. 레포마다\n\n실행 방식: {mode} · stat 사람 이름 {code(run['canonical'])} · 알려 준 git 이름 {', '.join(code(x) for x in run['names']) or '없음'} · "
           + (f"기본 브랜치 말고 더 읽은 브랜치 {', '.join(code(x) for x in more)}(기본 브랜치에 아직 안 들어간 것이 있는 레포만, 표의 `@브랜치` 줄) · " if more else '')
           +
           f"점검 대상(LV3 이상 활동 근거) 합계 {n_p}건, 그중 점검한 판정 {n_a}건 · 점검 비용 약 ${run.get('usd', 0):.4f}\n\n" + repo_table(run),
           f"## {title_prefix}2. stat 표\n\n" + stat_guide(stat, bool(lv_of)) + '\n\n' + stat_table(stat, lv_of),
           f"## {title_prefix}3. weak(정황) 목록과 이유\n\n" + weak_table(stat, vrows, none),
           f"## {title_prefix}4. 기각된 판정 목록과 점검 에이전트가 적은 이유\n\n" + reject_table(vrows, none),
           f"## {title_prefix}5. 충족률이 높은 공고 5개\n\n" + postings_guide(match, ex) + '\n\n' + postings_top(match, excl=ex[0]) + '\n\n' + postings_note(match),
           f"## {title_prefix}6. 실패·제외한 레포\n\n" + trouble(run, idents)]
    return '\n\n'.join(out)


def local_section(d, excl_all=({}, 0, 0)):
    b, stat, match, vrows = load(os.path.join(d, 'bundle.json')), load(os.path.join(d, 'stat.json')), load(os.path.join(d, 'match.json')), load(os.path.join(d, 'verdicts.json'), [])
    me = stat['person']
    n_p = sum(1 for e in b['evidence'] if e['person'] == me and e['kind'] == 'activity' and e['lv'] >= 3 and e['key'] in MP.CLAIM)
    cnt = {v: sum(1 for r in vrows if r['verdict'] == v) for v in ('pass', 'reject', 'unsure')} if vrows else None
    # run_pipeline.py 가 쓴 verdicts.json 에는 답을 받았는지 표시가 없다: 이유가 빈 모름은 답이 없어 채워진 줄일 수 있다
    # run_profile.py 꼴(answered 표시가 있음)이면 그 표시를 따른다
    blank = sum(1 for r in vrows if r.get('answered') is False or ('answered' not in r and r['verdict'] == 'unsure' and not (r.get('reason') or '').strip()))
    guessed = any('answered' not in r for r in vrows)
    ai = ', '.join(f'{who(k)} {v}개' for k, v in (b['meta'].get('ai_commits') or {}).items()) or '없음'
    note = f"기여자 {', '.join(who(x) for x in b['meta']['people'])} · AI가 쓰거나 함께 쓴 커밋 {ai} · 생성물로 뺀 파일 {b['meta'].get('generated_files')}개"
    if blank: note += f" · 판정 줄 {len(vrows)}건 중 " + (f"이유가 빈 모름 {blank}건(답이 없어 모름으로 채워진 줄일 수 있다)" if guessed else f"답을 못 받은 줄 {blank}건")
    row = [[code(b['meta']['repo']), code(b['meta']['head'][:7]), who(me), sum(1 for e in b['evidence'] if e['person'] == me), n_p, len(vrows) - blank, cnt['pass'] if cnt else '-', cnt['reject'] if cnt else '-', cnt['unsure'] if cnt else '-', note]]
    none = none_note(bool(vrows) or not n_p, n_p, len(vrows) - blank)     # run_pipeline.py 결과에는 run.json 이 없다: 점검 대상이 있는데 판정 파일이 없으면 점검 없이 돌린 것
    if vrows and guessed and len(vrows) == blank: none = '없음 (판정 줄의 이유가 모두 비어 있다. 점검 에이전트의 답을 받지 못했을 수 있다)'
    evof = {(e['person'], e['key']): e for e in b['evidence']}
    fill = lambda r: evof.get((r.get('person'), r['key']))               # 판정 줄에 없는 LV·근거 위치는 bundle 에서 채운다
    ex = excl_for(match, excl_all)
    return '\n\n'.join([
        '### 레포\n\n' + table(REPO_HEAD, row),
        f"### stat 표 (키 {len(stat['stat'])}개)\n\n" + stat_table(stat),
        '### weak(정황)\n\n' + weak_table(stat, vrows, none, fill),
        '### 기각된 판정\n\n' + reject_table(vrows, none, fill),
        '### 충족률이 높은 공고 5개\n\n표 읽는 법은 5번과 같다.\n\n' + postings_top(match, fold=True, excl=ex[0]) + '\n\n' + postings_note(match)])


def stat_diff(stat, base, lv_of, base_of, a='기본', b='브랜치 포함', mark=True, rest='나머지 키는 LV 와 근거 위치가 2번 표와 같다.'):
    """두 stat 의 차이: [LV 가 달라졌거나 새로 생긴 키 표, LV 는 같고 근거 위치만 달라진 키 표]. a 는 견줄 쪽(base), b 는 이쪽(stat)의 이름"""
    rows, moved, src_only = [], [], []
    m = [''] if mark else []
    for k, v in stat['stat'].items():
        o = base['stat'].get(k)
        if o is None or o['lv'] != v['lv']: rows.append([k, '없음' if o is None else o['lv'], v['lv'], v['kind'], source_of(v), ev_lines(k, v, lv_of)] + m)
        elif o['evidence'] != v['evidence']:                                       # LV 는 같고 근거 위치(또는 그 순서)가 달라진 키
            src = source_of(v) if source_of(o) == source_of(v) else f"{source_of(o)} → {source_of(v)}"       # source 도 함께 달라졌으면 a → b
            moved.append([k, v['lv'], src, ev_lines(k, o, base_of), ev_lines(k, v, lv_of)] + m)
        elif source_of(o) != source_of(v): src_only.append(f"{k} ({source_of(o)} → {source_of(v)})")
    gone = [k for k in base['stat'] if k not in stat['stat']]
    h = ['맞음/틀림'] if mark else []
    return [f"**stat 키 {len(base['stat'])}개 → {len(stat['stat'])}개.** LV 가 달라졌거나 새로 생긴 키(근거 위치 읽는 법은 2번과 같다):\n\n"
            + (table(['키', f'{a} LV', f'{b} LV', 'kind', 'source', '근거 위치'] + h, rows) if rows else '없음')
            + (f"\n\n{a} 결과에만 있는 키: {esc(', '.join(gone))}" if gone else ''),
            'LV 는 같고 근거 위치만 달라진 키(근거 위치는 키마다 최대 3개까지 나와서, 새 근거가 들어오면 있던 근거가 밀려나기도 한다):\n\n'
            + (table(['키', 'LV', 'source', f'{a}의 근거 위치', f'{b}의 근거 위치'] + h, moved) if moved else '없음')
            + (f"\n\nLV 와 근거 위치는 같고 source 만 달라진 키: {esc(', '.join(src_only))}" if src_only else '') + '\n\n' + rest]


def base_section(d, base_dir):
    """지금 결과(d)를 견줄 결과(base_dir: 예를 들어 기본 브랜치만 본 결과)와 견준 stat 차이"""
    run, brun = load(os.path.join(d, 'run.json')), load(os.path.join(base_dir, 'run.json')); check_run(run, d); check_run(brun, base_dir)
    stat, base = load(os.path.join(d, 'stat.json')), load(os.path.join(base_dir, 'stat.json'))
    lv_of = lv_lookup(d, run, load(os.path.join(d, 'verdicts.json'), [])); base_of = lv_lookup(base_dir, brun, load(os.path.join(base_dir, 'verdicts.json'), []))
    names = lambda r: ', '.join(code(x) for x in r.get('names') or []) or '없음'
    br = lambda r: ', '.join(code(x) for x in r.get('also_branch') or []) or '없음'
    extra = [t['label'] for t in run['targets'] if t.get('branch')]
    info = (f"- 견줄 결과 {code(os.path.basename(os.path.normpath(base_dir)) + '/')}: 알려 준 git 이름 {names(brun)} · 더 읽은 브랜치 {br(brun)} · 분석 대상 {len(brun['targets'])}개 · stat 키 {len(base['stat'])}개\n"
            f"- 지금 결과(1~6번): 알려 준 git 이름 {names(run)} · 더 읽은 브랜치 {br(run)} · 분석 대상 {len(run['targets'])}개"
            + (f"(그중 브랜치 줄 {len(extra)}개: {', '.join(code(x) for x in extra)})" if extra else '') + f" · stat 키 {len(stat['stat'])}개")
    return '\n\n'.join([info] + stat_diff(stat, base, lv_of, base_of, '견줄 결과', '지금', mark=False, rest='나머지 키는 LV 와 근거 위치가 두 결과에서 같다.'))


def variant_section(d, base_dir, excl_all=({}, 0, 0)):
    run = load(os.path.join(d, 'run.json')); check_run(run, d)
    stat, base = load(os.path.join(d, 'stat.json')), load(os.path.join(base_dir, 'stat.json'))
    vrows, match, idents = load(os.path.join(d, 'verdicts.json'), []), load(os.path.join(d, 'match.json')), load(os.path.join(d, 'identity.json'), {})
    extra = dict(run, targets=[t for t in run['targets'] if t.get('branch')])
    okt = [t for t in run['targets'] if t['status'] == 'ok']
    n_p = sum(t.get('packets') or 0 for t in okt); n_a = sum(t.get('answered') or 0 for t in okt)
    lv_of = lv_lookup(d, run, vrows)
    base_of = lv_lookup(base_dir, load(os.path.join(base_dir, 'run.json')), load(os.path.join(base_dir, 'verdicts.json'), []))
    cands = [[code(t['label']), lines(cand_text(x) for x in (idents.get(t['label']) or {}).get('groups', []) if x['verdict'] == 'candidate')] for t in extra['targets'] if t.get('candidates')]
    ex = excl_for(match, excl_all)
    return '\n\n'.join([
        '**더 분석한 브랜치** (기본 브랜치에 아직 안 들어간 ' + ', '.join(code(x) for x in run.get('also_branch') or []) + ' 끝)\n\n' + (repo_table(extra) if extra['targets'] else '해당 브랜치가 있는 레포 없음'),
        '**그 브랜치에서 고르지 않은 후보 이름**\n\n' + (table(['레포', '고르지 않은 후보 — 이름 (가린 이메일) 커밋 수 [표시]'], cands) if cands else '없음')
        + hint_legend(cand_groups(idents, [t for t in extra['targets'] if t.get('candidates')])),
        *stat_diff(stat, base, lv_of, base_of),
        '정황(weak): ' + (esc(', '.join(stat['weak'])) or '없음') + ' · 기각: ' + (esc(', '.join(f"{r['repo']} {r['key']}" for r in vrows if r['verdict'] == 'reject')) or '없음')
        + (' — ' + none_note(run['verify'], n_p, n_a)[3:].strip(' ()') if not stat['weak'] and not any(r['verdict'] == 'reject' for r in vrows) and not (run['verify'] and n_a) else ''),
        '**충족률이 높은 공고 5개(브랜치 포함)**\n\n표 읽는 법은 5번과 같다.\n\n' + postings_top(match, fold=True, excl=ex[0]) + '\n\n' + postings_note(match)])


def main():
    ap = argparse.ArgumentParser(description='결과 폴더 -> REPORT.md')
    ap.add_argument('--profile', required=True); ap.add_argument('--local'); ap.add_argument('--variant'); ap.add_argument('--head'); ap.add_argument('--tail'); ap.add_argument('--local-note'); ap.add_argument('--variant-note'); ap.add_argument('--base'); ap.add_argument('--base-note'); ap.add_argument('--out', required=True)
    ap.add_argument('--postings', default=os.path.join(HERE, '..', 'data', 'postings.json'))
    a = ap.parse_args()
    if a.base and a.variant: ap.error('--base 와 --variant 는 함께 쓰지 않는다(둘 다 8번 절이다)')
    excl_all = excluded_counts(a.postings)

    def read(p):
        if not p or not os.path.exists(p): return ''
        with open(p, encoding='utf-8') as f: return f.read().rstrip()
    parts = [read(a.head), profile_sections(a.profile, excl_all)]
    if a.local: parts.append('## 7. 로컬 폴더 결과 (프로필 결과와 섞지 않음)\n\n' + read(a.local_note) + '\n\n' + local_section(a.local, excl_all))
    if a.variant: parts.append('## 8. (요청 밖 참고) develop 브랜치까지 넣으면\n\n' + read(a.variant_note) + '\n\n' + variant_section(a.variant, a.profile, excl_all))
    if a.base: parts.append('## 8. (참고) 기본 브랜치만 봤을 때와 달라진 것\n\n' + (read(a.base_note) + '\n\n' if read(a.base_note) else '') + base_section(a.profile, a.base))
    parts.append(read(a.tail))
    with open(a.out, 'w', encoding='utf-8') as f: f.write('\n\n'.join(p for p in parts if p.strip()) + '\n')
    print(f'{a.out} ({os.path.getsize(a.out):,}바이트)')


if __name__ == '__main__':
    main()
