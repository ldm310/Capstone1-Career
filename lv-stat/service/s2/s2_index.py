#!/usr/bin/env python3
"""lv-stat 2단계 S1~S3(받기·계정 확인·색인). 버림용 스파이크(2026-11-26).
2단계 스파이크를 스테이징 서비스로 옮김(2026-11-27): gh 대신 ghapi, 색인은 작업 폴더(LV_S2_HOME) 아래.

usage: python3 -I s2_index.py P01 [P02 ...]
- 계정 확인: GitHub API 'commits?author=<login>&sha=<분석 브랜치>'가 돌려준 SHA만 내 커밋이다(계정에 연결된 커밋).
  noreply 이메일(<id>+<login>@users.noreply.github.com)도 내 커밋으로 본다. 본인이 알려 준 이메일은 후보에게 받을 수 없어 없다.
- GitHub는 ghapi로 GET만 부른다(토큰은 LV_GITHUB_TOKEN, API에만 쓴다). 목록은 끝까지 받는다. 받은 코드는 읽기만 한다.
- 큰 레포(.git/lv-partial 표시, --filter=blob:none으로 받음): 내 경로의 파일 내용만 한 번에 받는다(prefetch_mine, lazy fetch 없음.
  남의 경로는 blame이 읽는 판만). 커밋 정보는 모든 커밋을 받고, 파일 항목(numstat)은 내 경로만 받는다. 색인 레코드에
  partial {paths, blobs, fetched, numstat_ok}를 더한다. 표시 없는 레포는 2단계 그대로다(numstat이 실패하면 git_lazy로 받아서 다시).
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


# 목록 API는 옛 gh api --paginate처럼 다음 쪽이 없을 때까지 받는다(쪽 수 상한 없음).
# ghapi.get_all 기본값(10쪽)에서 멈추면 1,000개가 넘는 내 커밋 SHA·PR이 표시 없이 빠진다.
# 옛 gh 호출과 다른 점: 목록 하나를 300초로 묶던 제한(subprocess timeout)이 없고(ghapi는 요청마다 30초),
# 쪽마다 줄이지 않고 모든 쪽을 메모리에 받은 뒤 줄인다.
# 커밋 목록은 작성자로 거른 것이지만 PR 목록은 레포의 모든 PR이다. 그래서 PR이 많은 레포는 요청 수·시간·메모리가
# PR 수만큼 늘고, 한 쪽이라도 실패하면(호출 한도 포함) 그 레포 색인 전체가 error가 된다(main).
# 2단계는 본인 소유·포크 아님·400MB 이하 레포만 PR을 받았다(가장 많은 레포가 PR 122개). prs를 켤 레포는
# people.json을 만드는 쪽이 정한다.
API_PAGES = sys.maxsize


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
    flt = '--filter=blob:none' if L.is_partial(d) else '--filter=blob:limit=1m'   # 표시한 레포는 파일 내용 없이 받는다
    rc, _ = L.git(d, 'fetch', '--quiet', '--no-tags', flt, 'origin', f'+refs/heads/{branch}:{ref}', timeout=900)
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


def noreply_re(login):
    """GitHub noreply 이메일(<id>+<login>@users.noreply.github.com). 소문자로 바꾼 이메일과 맞춘다."""
    return re.compile(r'^(\d+\+)?' + re.escape(login.lower()) + r'@users\.noreply\.github\.com$')


def prefetch_mine(d, refs, own, login):
    """표시한 레포(큰 레포를 --filter=blob:none으로 받음)에서 내 경로의 파일 내용(blob)만 한 번에 받는다(lazy fetch 없이).
    1. log --raw 한 번. 트리만 읽는다: 이름 바꿈은 내용이 같은 것만 찾는다(-M100%). 비슷한 내용까지 찾는 -M은 지운 파일과
       새 파일의 내용을 읽어야 해서, 내용이 없는 이 레포에서는 그런 커밋에서 멈춘다(rc 128). 이 단계가 실패하면 잘린 결과로
       받지 않고 paths=[], fetched=False로 돌려준다. 내 커밋 = sha in own 또는 noreply 이메일(commits_of와 같음).
    2. 내 경로 = 내 커밋이 바꾼 경로(이름 바꿈은 양쪽 다). 그다음 어느 작성자의 이름 바꿈이든 새 경로가 내 경로면 옛 경로를
       더한다. 더 늘지 않을 때까지 한다(blame이 이름 바꾸기 전 판까지 따라가므로).
    3. 모든 커밋에서 경로(이름 바꿈은 어느 쪽이든)가 내 경로인 항목의 옛·새 blob id. 내 경로를 새로 만든 커밋(상태 A)에서는
       그 커밋이 없앤 경로(지움, 이름 바꿈의 옛 쪽)의 옛 blob id도 더한다: blame은 그 커밋에서 옛 이름을 찾으려고 없어진 파일의
       내용을 모두 읽는다. 0만 있는 id, gitlink(모드 160000, 다른 레포의 커밋이라 받을 수 없음)와 중복은 뺀다.
    4. 한 번에 받는다. 받을 id가 없으면 부르지 않는다(fetched 참). 실패하면 fetched=False로 두고 계속한다.
    -> {"paths": [정렬], "blobs": n, "fetched": bool}"""
    rc, out = L.git(d, 'log', '--no-merges', '--raw', '--no-abbrev', '-M100%', '--format=%x1e%H%x1f%ae', *refs, timeout=1200)
    if rc != 0:
        return dict(paths=[], blobs=0, fetched=False)
    noreply = noreply_re(login)
    commits = []                     # [(내 커밋인가, [(옛 모드, 새 모드, 옛 id, 새 id, 상태, [경로(이름 바꿈은 옛·새)])])]
    for rec in out.decode('utf-8', errors='replace').split('\x1e'):
        head, _, body = rec.partition('\n')
        sha, _, email = head.partition('\x1f')
        if not sha.strip():
            continue
        entries = []
        for line in body.splitlines():
            meta, *paths = line.split('\t')
            m = meta.lstrip(':').split()
            if line.startswith(':') and len(m) == 5 and paths:
                entries.append((*m, paths))
        commits.append((sha.strip() in own or bool(noreply.match(email.strip().lower())), entries))
    mine = {p for is_mine, entries in commits if is_mine for *_, paths in entries for p in paths}
    while True:
        more = {paths[0] for _, entries in commits for *_, st, paths in entries
                if st.startswith('R') and len(paths) == 2 and paths[1] in mine and paths[0] not in mine}
        if not more:
            break
        mine |= more
    blobs = set()
    for _, entries in commits:
        began = any(st == 'A' and paths[0] in mine for *_, st, paths in entries)
        for om, nm, oid, nid, st, paths in entries:
            if any(p in mine for p in paths):
                blobs.update(i for mode, i in ((om, oid), (nm, nid)) if mode != '160000' and i.strip('0'))
            elif began and (st == 'D' or st.startswith('R')) and om != '160000':
                blobs.add(oid)
    fetched = True
    if blobs:
        rc, _ = L.git(d, '-c', 'fetch.negotiationAlgorithm=noop', '-c', 'maintenance.auto=false', '-c', 'gc.auto=0',
                      'fetch', 'origin', '--no-tags', '--no-write-fetch-head', '--recurse-submodules=no', '--filter=blob:none',
                      '--stdin', inp=''.join(i + '\n' for i in sorted(blobs)).encode(), timeout=900)
        fetched = rc == 0
    return dict(paths=sorted(mine), blobs=len(blobs), fetched=fetched)


def numstat_by_sha(d, refs, paths):
    """표시한 레포: 주어진 경로만의 numstat -> {sha: 그 커밋의 numstat 줄}, 실패하면 None.
    경로는 표준 입력('--' 다음 한 줄에 하나)으로 글자 그대로 준다(--literal-pathspecs). --full-history: 경로를 주면 git은
    기본으로 이력을 줄여(합친 커밋이 한 부모와 그 경로가 같으면 다른 부모 쪽을 보지 않음) 곁가지의 내 커밋을 뺀다.
    표시 없는 레포의 numstat처럼 그 경로를 바꾼 머지 아닌 커밋을 모두 본다."""
    if not paths:
        return {}
    rc, out = L.git(d, '--literal-pathspecs', 'log', '--no-merges', '--full-history', '--numstat', '--format=%x1e%H', *refs, '--stdin',
                    inp=''.join(p + '\n' for p in ['--', *paths]).encode(), timeout=1200)
    if rc != 0:
        return None
    res = {}
    for rec in out.decode('utf-8', errors='replace').split('\x1e'):
        sha, _, rest = rec.partition('\n')
        if sha.strip():
            res[sha.strip()] = rest
    return res


COMMIT_FORMAT = '--format=%x1e%H%x1f%aI%x1f%ae%x1f%s%x1f%b%x1f'


def commits_of(d, refs, own, login, partial=None):
    """머지 아닌 모든 커밋(모든 작성자)과 파일 항목(numstat).
    partial(표시한 레포의 prefetch_mine 결과)이 있으면 커밋 정보는 diff 없이 받고, 파일 항목은 partial['paths']만 받는다.
    그 경로를 건드리지 않은 커밋은 files == []. 그 numstat이 실패하면 모든 커밋의 files를 []로 두고
    partial['numstat_ok'] = False(성공하면 True). 표시한 레포에서는 git_lazy를 부르지 않는다."""
    if partial is None:
        args = ('log', '--no-merges', '--numstat', COMMIT_FORMAT, *refs)
        rc, out = L.git(d, *args, timeout=1200)
        if rc != 0:                      # 빠진 큰 파일 때문에 실패 → 받아서 다시
            rc, out = git_lazy(d, *args)
    else:
        rc, out = L.git(d, 'log', '--no-merges', COMMIT_FORMAT, *refs, timeout=1200)
        by_sha = numstat_by_sha(d, refs, partial['paths'])
        partial['numstat_ok'] = by_sha is not None
    text = out.decode('utf-8', errors='replace')
    noreply = noreply_re(login)
    res = []
    for rec in text.split('\x1e'):
        if not rec.strip():
            continue
        f = rec.split('\x1f')
        if len(f) < 6:
            continue
        sha, date, email, subj, body, rest = f[0].strip(), f[1], f[2].strip().lower(), f[3], f[4], f[5]
        if partial is not None:          # 파일 항목은 내 경로만 받은 numstat에서(실패했으면 비움)
            rest = (by_sha or {}).get(sha, '')
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
    partial = prefetch_mine(d, [x['ref'] for x in refs], own, login) if L.is_partial(d) else None
    cs = commits_of(d, [x['ref'] for x in refs], own, login, partial)
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
    rec = dict(key=r['key'], full_name=r['full_name'], dir=d, refs=refs, commits=cs, files=files, prs=prs,
               own_share=round(len(own_shas) / tot, 3) if tot else 0, api_own=len(own), evidence=r.get('evidence', False))
    if partial is not None:          # 표시한 레포만: {paths, blobs, fetched, numstat_ok}
        rec['partial'] = partial
    return rec


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
