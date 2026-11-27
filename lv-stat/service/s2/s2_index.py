#!/usr/bin/env python3
"""lv-stat 2단계 S1~S3(받기·계정 확인·색인). 버림용 스파이크(2026-11-26).
2단계 스파이크를 스테이징 서비스로 옮김(2026-11-27): gh 대신 ghapi, 색인은 작업 폴더(LV_S2_HOME) 아래.

usage: python3 -I s2_index.py P01 [P02 ...]
- 계정 확인: GitHub API 'commits?author=<login>&sha=<분석 브랜치>'가 돌려준 SHA만 내 커밋이다(계정에 연결된 커밋).
  noreply 이메일(<id>+<login>@users.noreply.github.com)도 내 커밋으로 본다. 본인이 알려 준 이메일은 후보에게 받을 수 없어 없다.
- GitHub는 ghapi로 GET만 부른다(토큰은 LV_GITHUB_TOKEN, API에만 쓴다). 받은 코드는 읽기만 한다.
"""
import json
import os
import re
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ghapi as G  # noqa: E402
import s2lib as L  # noqa: E402

MAX_BLAME = 300_000
AI_COAUTHOR = re.compile(r'Co-authored-by:[^\n]*(claude|anthropic|copilot|cursor|codex|openai|chatgpt|gemini|devin|aider|codeium|windsurf)', re.I)


# 「미정」 목록 API 쪽 상한: 100개씩 10쪽(1,000개)까지 받는다(ghapi.get_all 기본값). 옛 gh api --paginate는 끝까지 받았다.
# 넘치면 오래된 내 커밋 SHA·PR이 표시 없이 빠진다. 상한과 잘림 표시는 사용자가 정한다.
API_PAGES = 10


def api_shas(path):
    """커밋 목록 API → SHA 목록(옛 jq '.[].sha'). 없는 레포·빈 레포(404·409)는 []."""
    return [c['sha'] for c in G.get_all(path, max_pages=API_PAGES) if c.get('sha')]


def api_prs(path):
    """PR 목록 API → 옛 jq와 같은 칸만 남긴 목록:
    {number, title, body: ((.body // "") | .[0:4000]), merged_at, merge_commit_sha, user: .user.login,
     head_sha: .head.sha, created_at, labels: [.labels[].name]}"""
    return [dict(number=p.get('number'), title=p.get('title'), body=(p.get('body') or '')[:4000],
                 merged_at=p.get('merged_at'), merge_commit_sha=p.get('merge_commit_sha'),
                 user=(p.get('user') or {}).get('login'), head_sha=(p.get('head') or {}).get('sha'),
                 created_at=p.get('created_at'), labels=[x.get('name') for x in p.get('labels') or []])
            for p in G.get_all(path, max_pages=API_PAGES)]


def ensure_ref(d, branch):
    ref = f'refs/remotes/origin/{branch}'
    rc, out = L.git(d, 'rev-parse', '-q', '--verify', ref + '^{commit}')
    if rc == 0:
        return ref, out.decode().strip()
    rc, _ = L.git(d, 'fetch', '--quiet', '--no-tags', '--filter=blob:limit=1m', 'origin', f'+refs/heads/{branch}:{ref}', timeout=900)
    if rc != 0:
        rc, _ = L.git(d, 'fetch', '--quiet', '--no-tags', 'origin', f'+refs/heads/{branch}:{ref}', timeout=900)
    rc, out = L.git(d, 'rev-parse', '-q', '--verify', ref + '^{commit}')
    return (ref, out.decode().strip()) if rc == 0 else (None, None)


def parse_numstat_path(p):
    # 'src/{a => b}/x.java' 또는 'old => new'
    if '=>' not in p:
        return p
    m = re.match(r'^(.*)\{(.*) => (.*)\}(.*)$', p)
    if m:
        return (m.group(1) + m.group(3) + m.group(4)).replace('//', '/')
    return p.split(' => ', 1)[1]


def git_lazy(d, *a, timeout=1800):
    """부분 clone에서 빠진 큰 파일 내용이 필요할 때만: 받으러 가는 것을 허용해 다시 부른다(읽기만)."""
    env = dict(L.GENV)
    env.pop('GIT_NO_LAZY_FETCH', None)
    p = subprocess.run(['git', '-C', d, '-c', 'core.hooksPath=/dev/null', '-c', 'core.quotePath=false', *a], capture_output=True, env=env, timeout=timeout)
    return p.returncode, p.stdout


def commits_of(d, refs, own, login):
    args = ('log', '--no-merges', '--numstat', '--format=%x1e%H%x1f%aI%x1f%ae%x1f%s%x1f%b%x1f', *refs)
    rc, out = L.git(d, *args, timeout=1200)
    if rc != 0:                      # 빠진 큰 파일 때문에 실패 → 받아서 다시
        rc, out = git_lazy(d, *args)
    text = out.decode('utf-8', errors='replace')
    noreply = re.compile(r'^(\d+\+)?' + re.escape(login.lower()) + r'@users\.noreply\.github\.com$')
    res = []
    for rec in text.split('\x1e'):
        if not rec.strip():
            continue
        f = rec.split('\x1f')
        if len(f) < 6:
            continue
        sha, date, email, subj, body, rest = f[0].strip(), f[1], f[2].strip().lower(), f[3], f[4], f[5]
        files = []
        for line in rest.splitlines():
            parts = line.split('\t')
            if len(parts) != 3:
                continue
            a, b, p = parts
            files.append(dict(path=parse_numstat_path(p), add=int(a) if a.isdigit() else 0, dele=int(b) if b.isdigit() else 0, binary=not a.isdigit()))
        is_own = sha in own or bool(noreply.match(email))
        res.append(dict(sha=sha, date=date, date_kst=str(L.kst_date(date)), subject=subj[:300], body=body[:3000], own=is_own,
                        ai_coauthor=bool(AI_COAUTHOR.search(body)), files=files))
    # PR 번호: 'Merge pull request #N' 머지 커밋의 두 부모 사이 커밋, 제목 끝 '(#N)'
    rc, out = L.git(d, 'log', '--merges', '--format=%H%x1f%s%x1f%P', *refs, timeout=600)
    pr_of = {}
    for line in out.decode('utf-8', errors='replace').splitlines():
        f = line.split('\x1f')
        if len(f) < 3:
            continue
        mo = re.search(r'Merge pull request #(\d+)', f[1])
        ps = f[2].split()
        if mo and len(ps) == 2:
            rc2, o2 = L.git(d, 'rev-list', f'{ps[0]}..{ps[1]}', timeout=120)
            for s in o2.decode().split():
                pr_of.setdefault(s, int(mo.group(1)))
    for c in res:
        mo = re.search(r'\(#(\d+)\)\s*$', c['subject'])
        c['pr'] = int(mo.group(1)) if mo else pr_of.get(c['sha'])
    return res


def snapshot(d, refs):
    files, seen = [], set()
    for r in refs:
        rc, out = L.git(d, 'ls-tree', '-r', '-z', r['ref'], timeout=300)
        for rec in out.split(b'\0'):
            if b'\t' not in rec:
                continue
            meta, path = rec.split(b'\t', 1)
            parts = meta.split()
            if len(parts) < 3 or parts[1] != b'blob':
                continue
            p = path.decode('utf-8', errors='replace')
            if p in seen:
                continue
            seen.add(p)
            files.append(dict(path=p, sha=parts[2].decode(), ref=r['ref'], **L.classify(p)))
    if files:
        rc, out = L.git(d, 'cat-file', '--batch-check=%(objectname) %(objectsize)', inp=('\n'.join(f['sha'] for f in files) + '\n').encode(), timeout=300)
        size = {}
        for line in out.decode().splitlines():
            a = line.split()
            if len(a) == 2 and a[1].isdigit():
                size[a[0]] = int(a[1])
        for f in files:
            f['size'] = size.get(f['sha'])
    return files


def blame(d, f, own):
    rc, out = L.git(d, 'blame', '--porcelain', f['ref'], '--', f['path'], timeout=300)
    if rc != 0:
        return None, None
    lines, mine, cur = 0, [], None
    for line in out.decode('utf-8', errors='replace').splitlines():
        m = re.match(r'^([0-9a-f]{40}) \d+ (\d+)', line)
        if m:
            cur = (m.group(1), int(m.group(2)))
            continue
        if line.startswith('\t') and cur:
            lines += 1
            if cur[0] in own:
                mine.append(cur[1])
            cur = None
    ranges = []
    for n in sorted(mine):
        if ranges and n == ranges[-1][1] + 1:
            ranges[-1][1] = n
        else:
            ranges.append([n, n])
    return ranges, lines


def index_repo(pid, login, r):
    d = r['dir']
    refs = []
    for name in [r['default_branch']] + [b for b in ('develop', 'dev') if b != r['default_branch'] and r.get('has_' + b)]:
        ref, sha = ensure_ref(d, name)
        if ref:
            refs.append(dict(name=name, ref=ref, sha=sha))
    if not refs:
        rc, out = L.git(d, 'rev-parse', '-q', '--verify', 'HEAD^{commit}')
        if rc != 0:
            return dict(key=r['key'], full_name=r['full_name'], dir=d, refs=[], commits=[], files=[], error='empty')
        refs = [dict(name='HEAD', ref='HEAD', sha=out.decode().strip())]
    own = set()
    for x in refs:
        own.update(api_shas(f"repos/{r['full_name']}/commits?author={G.q(login)}&sha={G.q(x['name'] if x['name'] != 'HEAD' else r['default_branch'])}&per_page=100"))
    cs = commits_of(d, [x['ref'] for x in refs], own, login)
    own_shas = {c['sha'] for c in cs if c['own']}
    touched = {f['path'] for c in cs if c['own'] for f in c['files']}
    files = snapshot(d, refs)
    for f in files:
        f['my_ranges'], f['lines'] = None, None
        if f['kind'] in ('code', 'config', 'migration', 'test') and (f.get('size') or 0) <= MAX_BLAME and f['path'] in touched:
            f['my_ranges'], f['lines'] = blame(d, f, own_shas)
        elif f['kind'] in ('code', 'config', 'migration', 'test') and f['path'] not in touched:
            f['my_ranges'] = []
        f['my_lines'] = sum(b - a + 1 for a, b in f['my_ranges']) if f['my_ranges'] else 0
    prs = []
    if r.get('prs'):
        prs = api_prs(f"repos/{r['full_name']}/pulls?state=all&per_page=100")
    tot = len(cs)
    return dict(key=r['key'], full_name=r['full_name'], dir=d, refs=refs, commits=cs, files=files, prs=prs,
                own_share=round(len(own_shas) / tot, 3) if tot else 0, api_own=len(own), evidence=r.get('evidence', False))


def main():
    ppl = {p['pid']: p for p in L.people()}
    for pid in sys.argv[1:]:
        p = ppl[pid]
        od = os.path.join(L.INDEX, pid)
        os.makedirs(od, exist_ok=True)
        t0 = time.time()
        keys = []
        for r in p['repos']:
            dst = os.path.join(od, r['key'] + '.json')
            keys.append(r['key'])
            if os.path.exists(dst):
                continue
            t = time.time()
            try:
                data = index_repo(pid, p['login'], r)
            except Exception as e:      # 레포 하나가 실패해도 계속(설계 5.4)
                data = dict(key=r['key'], full_name=r['full_name'], dir=r['dir'], refs=[], commits=[], files=[], error=repr(e)[:300])
            data['index_s'] = round(time.time() - t, 1)
            json.dump(data, open(dst, 'w'), ensure_ascii=False)
            print(pid, r['full_name'], data['index_s'], 's', 'own', sum(1 for c in data['commits'] if c['own']), data.get('error', ''), file=sys.stderr, flush=True)
        json.dump(dict(pid=pid, login=p['login'], role=p['role'], level=p['level'], repo_keys=keys, index_s=round(time.time() - t0, 1)),
                  open(os.path.join(od, 'person.json'), 'w'), ensure_ascii=False, indent=1)
        print(pid, '끝', round(time.time() - t0, 1), file=sys.stderr, flush=True)


if __name__ == '__main__':
    main()
