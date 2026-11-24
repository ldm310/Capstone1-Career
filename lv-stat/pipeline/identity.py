#!/usr/bin/env python3
"""GitHub 계정 <-> 레포마다 git에 찍힌 이름 잇기.

bundle 의 meta.people 은 git 이름(extract.people 이 같은 사람의 이름·이메일을 묶은 뒤 고른 표시 이름)이라 레포마다 다를 수 있다.
이 모듈은 받은 레포의 git log(HEAD)에서 작성자 이름·이메일을 보고, 그 레포에서 '나'인 표시 이름을 고른다. 추측하지 않는다.

작성자 (이름, 이메일) 한 쌍이 확실히 나라고 보는 근거:
  name         이름이 내가 알려 준 이름과 글자 그대로 같음(앞뒤 공백·연속 공백만 정리, 대소문자 구분)
  noreply      이메일이 내 계정의 GitHub noreply 주소([숫자+]<계정>@users.noreply.github.com)
  email        이메일이 내가 알려 준 이메일과 같음(--email)
  same-email+name~  이름이 글자 그대로 같은 커밋과 이메일이 같고, 이름은 대소문자·공백·낱말 순서만 다름
표시 이름 하나(묶음)에 든 모든 쌍이 위 근거를 가지면 mine. 일부만 가지면(예: 추출기가 내 이름과 남의 이름을 한 묶음으로 합친 경우)
그 묶음의 근거를 나눌 수 없으므로 고르지 않고 candidate 로 남긴다. 다른 계정의 noreply 주소가 섞였거나, 이름·이메일이 비슷하기만 한 것도 candidate 다.
candidate 의 표시(고르는 근거가 아니라 사람이 볼 실마리): name~case 대소문자·구분 문자만 다름 / name~order 낱말 순서만 다름 / name~part 이름 낱말 일부가 같음
/ same-email 내 이름 커밋과 이메일이 같은데 이름이 다름 / name-in-email 이메일에 내 이름 낱말이 있음 / login-in-name, login-in-email / conflict:noreply=<다른 계정>
/ ai-commit-pushed-by-other AI 가 쓴 커밋을 올린 사람이 내가 아님 / control-chars-in-repo.
mine 이 하나도 없는 레포는 stat 에서 뺀다.
봇이 작성자인 커밋은 보지 않는다. AI 가 작성자인 커밋은 추출기가 올린 사람(커미터) 몫으로 주므로, 그 커밋의 커미터 이름·이메일을 대신 본다
(남이 올린 AI 커밋이 내 묶음에 들어와 있으면 그 묶음은 확실하지 않은 것으로 남는다).

Usage: python3 pipeline/identity.py <clone 폴더> --login ldm310 --name ldm310 --name "DONGMIN LEE" [--email me@example.com]
"""
import argparse, collections, json, os, re, subprocess, sys
sys.dont_write_bytecode = True                         # pipeline/__pycache__ 를 남기지 않는다
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import extract as X

NOREPLY = re.compile(r'^(?:\d+\+)?([A-Za-z0-9-]+)@users\.noreply\.github\.com$', re.I)
CTRL = re.compile('[\x00-\x1f\x7f\x85\u2028\u2029]')     # 이름·이메일에 있으면 안 되는 제어·줄 구분 문자


def norm(s):
    return ' '.join((s or '').split())


def fold(s):
    return re.sub(r'[\s._-]+', '', (s or '').casefold())


def name_tokens(s):
    return frozenset(t for t in re.split(r'[\s._-]+', (s or '').casefold()) if t)


def mask_email(e):
    """보고용: noreply 주소(공개 계정 이름)는 그대로, 그 밖에는 @ 앞의 첫 글자만 남김(@ 앞이 두 글자 이하면 모두 가림)"""
    if not e or NOREPLY.match(e): return e or ''
    if '@' not in e: return e[:1] + '…'
    local, dom = e.rsplit('@', 1)
    return f"{local[:1] if len(local) > 2 else ''}…@{dom}"


def pairs_by_display(repo):
    """-> ({표시 이름: Counter{(작성자 이름, 작성자 이메일): 커밋 수}}, {표시 이름: Counter{AI 가 쓴 커밋을 올린 (커미터 이름, 이메일): 커밋 수}},
    extract.people 결과, 이상한 커밋 수). 묶는 방식은 추출기와 같다.
    커밋 기록은 바이트로 받아 NUL 로 나눈다(이름에 줄 구분 문자를 넣어 가짜 줄을 끼우지 못하게). 이름·이메일에 제어 문자가 있거나 칸 수가 안 맞는 커밋은 '이상한 커밋'으로 센다."""
    P = X.people(repo); who = P['who']
    out, ai_by, bad = collections.defaultdict(collections.Counter), collections.defaultdict(collections.Counter), 0
    raw = subprocess.run(['git', '-C', repo, 'log', '-z', '--format=%H%x1f%an%x1f%ae%x1f%cn%x1f%ce', 'HEAD'], capture_output=True, check=True).stdout.decode('utf-8', 'replace')
    for rec in raw.split('\0'):
        if not rec: continue
        parts = rec.split('\x1f')
        if len(parts) != 5 or CTRL.search(''.join(parts[1:])):
            bad += 1; continue
        sha, an, ae, cn, ce = parts
        if X.is_bot(an, ae) or not who.get(sha): continue
        if X.is_ai(an, ae):                           # AI 가 쓴 커밋: 추출기가 이 묶음 몫으로 줬으면 올린 사람(커미터)을 본다
            if not X.is_ai(cn, ce) and not X.is_bot(cn, ce): ai_by[who[sha]][(cn, ce)] += 1
            continue
        out[who[sha]][(an, ae)] += 1
    return out, ai_by, P, bad


def resolve(repo, login, names, emails=()):
    """-> dict(status 'ok'|'uncertain'|'none', mine=[표시 이름], candidates=[표시 이름], groups=[...], people=[...])"""
    known = {norm(n) for n in names if norm(n)}
    known_fold = {fold(n) for n in known}; known_tok = {name_tokens(n) for n in known}
    long_tok = {t for ts in known_tok for t in ts if len(t) >= 4}
    login_l = login.casefold(); given = {e.casefold() for e in emails if e}
    by_disp, ai_by, P, bad = pairs_by_display(repo)

    def sure(an, ae):
        m = NOREPLY.match(ae)
        mine_nr = bool(m) and m.group(1).casefold() == login_l
        other = m.group(1) if m and not mine_nr and ae.casefold() not in given else None      # 다른 계정의 noreply 주소(직접 알려 준 이메일이면 예외: 계정 이름을 바꾼 경우)
        sig = []
        if norm(an) in known: sig.append('name')
        if mine_nr: sig.append('noreply')
        if ae.casefold() in given: sig.append('email')
        return sig, other

    name_emails = set()                              # 이름이 글자 그대로 같은 커밋의 이메일(다른 계정의 noreply 주소는 뺌)
    for c in by_disp.values():
        for an, ae in c:
            if norm(an) in known and not sure(an, ae)[1]: name_emails.add(ae.casefold())
    groups = []
    for d, c in sorted(by_disp.items(), key=lambda kv: (-sum(kv[1].values()), kv[0])):
        ps, all_ok, any_hit = [], True, False
        for (an, ae), n in sorted(c.items(), key=lambda kv: (-kv[1], kv[0])):
            sig, other = sure(an, ae)
            hints = []
            if not sig:
                toks = name_tokens(an); low = ae.casefold(); local = low.rsplit('@', 1)[0]
                variant = fold(an) in known_fold or toks in known_tok          # 대소문자·공백·구분 문자·낱말 순서만 다른 이름
                if variant and not other and low in name_emails: sig = ['same-email+name~']
                else:
                    if fold(an) in known_fold: hints.append('name~case')
                    elif toks in known_tok: hints.append('name~order')
                    elif toks & long_tok: hints.append('name~part')            # 이름 낱말 일부가 같음(4글자 이상)
                    if low in name_emails: hints.append('same-email')          # 내 이름 커밋과 이메일이 같지만 이름이 다름: 확실하지 않음
                    if not NOREPLY.match(ae) and any(t in low for t in long_tok - {login_l}): hints.append('name-in-email')
                    if login_l and (login_l in fold(an) if len(login_l) >= 4 else login_l in toks): hints.append('login-in-name')        # 짧은 계정 이름은 낱말이 같을 때만
                    if login_l and not NOREPLY.match(ae) and (login_l in local if len(login_l) >= 4 else login_l in re.split(r'[._+-]+', local)): hints.append('login-in-email')
            if other and (sig or hints): hints.append(f'conflict:noreply={other}')     # 내 이름 같은데 다른 계정의 noreply 주소: 고르지 않음
            ok = bool(sig) and not other
            all_ok = all_ok and ok; any_hit = any_hit or bool(sig) or bool(hints)
            ps.append(dict(name=an, email=mask_email(ae), commits=n, signals=sig + hints))
        for (cn, ce), n in sorted(ai_by.get(d, {}).items(), key=lambda kv: (-kv[1], kv[0])):      # AI 가 쓴 커밋을 올린 사람이 내가 아니면 이 묶음은 확실하지 않다
            sig, other = sure(cn, ce)
            if not sig and not other and ce.casefold() in name_emails and (fold(cn) in known_fold or name_tokens(cn) in known_tok): sig = ['same-email+name~']
            if not sig or other:
                all_ok = False; any_hit = True
                ps.append(dict(name=cn, email=mask_email(ce), commits=n, signals=['ai-commit-pushed-by-other']))
        if bad and all_ok:                               # 사람 묶기 자체를 믿을 수 없는 레포: 고르지 않고 후보로만
            all_ok = False
            for x in ps: x['signals'].append('control-chars-in-repo')
        verdict = 'mine' if all_ok else 'candidate' if any_hit else 'other'
        g = dict(display=d, commits=sum(c.values()), verdict=verdict)
        if verdict != 'other': g['pairs'] = ps                                         # 남의 이메일은 가린 것도 남기지 않음
        groups.append(g)
    mine = [g['display'] for g in groups if g['verdict'] == 'mine']
    cands = [g['display'] for g in groups if g['verdict'] == 'candidate']
    res = dict(login=login, names=sorted(known), status='ok' if mine else 'uncertain' if cands else 'none', mine=mine, candidates=cands, groups=groups, people=P['humans'])
    if bad: res['note'] = f'작성자 이름·이메일에 제어 문자가 든 커밋 {bad}개: 추출기의 사람 묶기를 믿을 수 없어 이 레포에서는 고르지 않음'
    return res


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description='레포에서 내 git 이름(표시 이름) 고르기')
    ap.add_argument('repo'); ap.add_argument('--login', required=True); ap.add_argument('--name', action='append', default=[]); ap.add_argument('--email', action='append', default=[])
    a = ap.parse_args()
    json.dump(resolve(a.repo, a.login, a.name, a.email), sys.stdout, ensure_ascii=False, indent=1); print()
