#!/usr/bin/env python3
"""lv-stat 2단계 S1~S3(받기·계정 확인·색인). 버림용 스파이크(2026-11-26).
2단계 스파이크를 스테이징 서비스로 옮김(2026-11-27): gh 대신 ghapi, 색인은 작업 폴더(LV_S2_HOME) 아래.

usage: python3 -I s2_index.py P01 [P02 ...]
- 계정 확인: GitHub API 'commits?author=<login>&sha=<분석 브랜치>'가 돌려준 SHA만 내 커밋이다(계정에 연결된 커밋).
  noreply 이메일(<id>+<login>@users.noreply.github.com)도 내 커밋으로 본다. 본인이 알려 준 이메일은 후보에게 받을 수 없어 없다.
- GitHub는 ghapi로 GET만 부른다(토큰은 LV_GITHUB_TOKEN, API에만 쓴다). 목록은 끝까지 받는다. 받은 코드는 읽기만 한다.
- 큰 레포(.git/lv-partial 표시, --filter=blob:none으로 받음): 내 경로의 파일 내용(합친 커밋에서만 생긴 판 포함)만 한 번에 받는다
  (prefetch_mine, lazy fetch 없음. 「제안」(확인 전) 남의 경로는 blame이 읽는 판만). 받기 앞뒤로 그 레포의 부분 clone 설정(promisor)을
  지워서, GIT_NO_LAZY_FETCH를 모르는 옛 git(2.45 전)도 그 뒤로는 빠진 내용을 받으러 가지 않는다(close_promisor). 커밋 정보는 모든
  커밋을 받고, 파일 항목(numstat)은 내 경로만 받는다. 경로는 -z로 읽어 이름의 글자 그대로 맞춘다. 받지 않은 판을 읽어야 해서 blame이
  실패한 파일은 내 줄을 세지 않고(my_ranges None) 기록만 한다. 색인 레코드에 partial {paths, blobs, fetched, numstat_ok, blame_failed}를
  더한다. 표시 없는 레포는 2단계 그대로다(numstat이 실패하면 git_lazy로 받아서 다시).
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
BLAME_FAILED_LIST = 20   # partial.blame_failed에 경로를 남기는 파일 수(정렬한 앞에서부터). 「Claude 임시값」(컨트롤러 판정 2026-11-28)
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


RAW = ('-z', '--raw', '--no-abbrev', '-M100%', '--format=%x1e%H%x1f%ae')   # prefetch_mine의 두 log가 같이 쓴다(트리만 읽음)


def path_text(b):
    """-z 출력의 경로 바이트 -> 글자. UTF-8로 읽을 수 없는 바이트도 잃지 않는다(surrogateescape): pathspec_args가 같은 바이트로
    되돌려 git에 준다. 색인 파일에는 shown_path로 바꿔 쓴다."""
    return b.decode('utf-8', 'surrogateescape')


def shown_path(p):
    """path_text로 읽은 경로 -> 색인 파일에 쓰는 글자(snapshot·파일 항목과 같이 못 읽는 바이트는 U+FFFD, JSON에 쓸 수 있음)."""
    return p.encode('utf-8', 'surrogateescape').decode('utf-8', 'replace')


def pathspec_args(paths):
    """경로(path_text 글자) -> (표준 입력, 명령 줄 끝 인자). 경로는 표준 입력('--' 다음 한 줄에 하나)으로 준다(많아도 명령 줄 길이
    상한에 걸리지 않음). git은 표준 입력을 줄 단위로 읽고 줄 끝의 CR도 지우므로(git 2.55 측정), 줄바꿈이 있거나 CR로 끝나는 경로
    (아주 드묾)만 명령 줄의 '--' 뒤에 준다. 둘 다 git이 준 바이트 그대로다. --literal-pathspecs와 같이 쓴다."""
    lines, tail = [b'--'], []
    for p in paths:
        raw = p.encode('utf-8', 'surrogateescape')
        (tail if b'\n' in raw or raw.endswith(b'\r') else lines).append(raw)
    return b''.join(line + b'\n' for line in lines), ([b'--', *tail] if tail else [])


def raw_entries(out):
    """log RAW(-z) 출력 -> [(sha, 이메일, [(옛 모드, 새 모드, 옛 id, 새 id, 상태, [경로(이름 바꿈은 옛·새)])])].
    칸은 NUL로 끝난다: 커밋 머리(\\x1e<sha>\\x1f<이메일>), 항목(:<모드> <모드> <id> <id> <상태>, 커밋의 첫 항목 앞에는 줄바꿈),
    그 뒤 경로 한 칸(이름 바꿈·복사는 옛·새 두 칸). 경로는 칸 수대로 읽으므로 경로에 어떤 글자가 있어도 머리·항목으로 읽지 않는다.
    -z라서 경로는 따옴표로 감싸지 않은 이름 그대로다(path_text). 합친 커밋을 부모마다 비교하면(--diff-merges=separate)
    한 커밋이 부모 수만큼 나온다."""
    res, toks, i = [], out.split(b'\0'), 0
    while i < len(toks):
        t = toks[i].lstrip(b'\n')
        i += 1
        if t.startswith(b'\x1e'):
            sha, _, email = t[1:].decode('utf-8', errors='replace').partition('\x1f')
            res.append((sha.strip(), email.strip(), []))
        elif t.startswith(b':') and res:
            m = t.lstrip(b':').decode('ascii', errors='replace').split()
            n = 2 if len(m) == 5 and m[4][:1] in ('R', 'C') else 1
            paths = [path_text(p) for p in toks[i:i + n]]
            i += n
            if len(m) == 5 and len(paths) == n:
                res[-1][2].append((*m, paths))
    return res


def blob_ids(om, nm, oid, nid):
    """raw 항목의 옛·새 blob id. 0만 있는 id(없는 쪽)와 gitlink(모드 160000, 다른 레포의 커밋이라 받을 수 없음)는 뺀다."""
    return {i for mode, i in ((om, oid), (nm, nid)) if mode != '160000' and i.strip('0')}


# 부분 clone에서 빠진 내용을 받으러 갈 곳(promisor)을 정하는 설정. 하나만 남아도 git은 origin에서 받으러 간다
# (git 2.55 측정: remote.origin.promisor만 지우면 partialclonefilter 때문에 여전히 받으러 간다. extensions.partialClone은 옛 clone이 씀).
PROMISOR_KEYS = ('remote.origin.promisor', 'remote.origin.partialclonefilter', 'extensions.partialClone')
PROMISOR_RE = r'^(remote\..*\.(promisor|partialclonefilter)|extensions\.partialclone)$'


def close_promisor(d):
    """표시한 레포: 빠진 내용을 더는 받으러 가지 않게 그 레포의 부분 clone 설정(PROMISOR_KEYS)을 지운다.
    GIT_NO_LAZY_FETCH는 git 2.45부터라, 그 전 git(스테이징 EC2의 Ubuntu git 2.34·2.43일 수 있음)은 이 값을 모르고 빠진 내용을
    보는 git마다 받으러 간다(snapshot의 cat-file --batch-check는 빠진 파일마다, blame은 빠진 판마다, 뒤에 도는 추출기의 cat-file
    --batch·log -G도). 설정을 지우면 git 판과 관계없이 빠진 내용은 없는 것이 된다: cat-file --batch-check는 missing, blame·numstat은
    실패(rc 128), log --raw·ls-tree는 그대로 된다(GIT_NO_LAZY_FETCH=1일 때와 같음). 받기(fetch --filter=blob:none)는 이 설정을
    다시 만들므로 prefetch_mine이 받은 뒤에도 부른다. 지운 뒤 어느 범위의 설정에도(다른 remote, 환경으로 준 설정 포함) 남지 않았는지
    보고, 지우지 못했거나 남았으면 RuntimeError(그 레포는 error, 받으러 갈 수 있는 채로 색인하지 않는다)."""
    for key in PROMISOR_KEYS:
        L.git(d, 'config', '--local', '--unset-all', key, timeout=60)   # 없으면 rc 5. 지웠는지는 아래에서 본다
    rc, _ = L.git(d, 'config', '--get-regexp', PROMISOR_RE, timeout=60)
    if rc != 1:                          # 1 = 맞는 설정이 없음(0 = 남음, 그 밖 = 설정을 읽지 못함)
        raise RuntimeError(f'부분 clone 설정(promisor)을 지우지 못함 (rc {rc})')


def prefetch_mine(d, refs, own, login):
    """표시한 레포: 부분 clone 설정을 지우고(close_promisor) 내 경로의 파일 내용을 받은 뒤(fetch_mine), 끝날 때 다시 지운다.
    받기가 그 설정을 다시 만들기 때문이다. 앞 단계가 실패하거나 예외가 나도 끝에 지운다. 그래서 옛 git(GIT_NO_LAZY_FETCH를 모름)도
    이 레포에서는 fetch_mine의 받기 한 번 말고는 받으러 가지 않는다(시작 전에도 지우므로 트리가 빠진 clone의 1단계도 받지 않고 실패한다).
    -> fetch_mine과 같다: {"paths": [정렬, path_text 글자], "blobs": n, "fetched": bool}"""
    close_promisor(d)
    try:
        return fetch_mine(d, refs, own, login)
    finally:
        close_promisor(d)


def fetch_mine(d, refs, own, login):
    """표시한 레포(큰 레포를 --filter=blob:none으로 받음)에서 내 경로의 파일 내용(blob)만 한 번에 받는다(lazy fetch 없이).
    1. 머지 아닌 커밋의 log --raw 한 번. 트리만 읽는다: 이름 바꿈은 내용이 같은 것만 찾는다(-M100%). 비슷한 내용까지 찾는 -M은
       지운 파일과 새 파일의 내용을 읽어야 해서, 내용이 없는 이 레포에서는 그런 커밋에서 멈춘다(rc 128). 이 단계가 실패하면
       잘린 결과로 받지 않고 paths=[], fetched=False로 돌려준다. 내 커밋 = sha in own 또는 noreply 이메일(commits_of와 같음).
       -z로 읽는다: -z가 없으면 이름에 "·\\·제어 문자가 있는 경로를 따옴표로 감싸("q\\"x.py") 표준 입력 경로와 맞지 않는다.
    2. 내 경로 = 내 커밋이 바꾼 경로(이름 바꿈은 양쪽 다). 그다음 어느 작성자의 이름 바꿈이든 새 경로가 내 경로면 옛 경로를
       더한다. 더 늘지 않을 때까지 한다(blame이 이름 바꾸기 전 판까지 따라가므로).
    3. 1단계의 모든 커밋에서 경로(이름 바꿈은 어느 쪽이든)가 내 경로인 항목의 옛·새 blob id.
       「제안」(확인 전): 내 경로를 새로 만든 커밋(상태 A)에서는 그 커밋이 없앤 남의 경로(지움, 이름 바꿈의 옛 쪽)의 그 판 blob id도
       더한다(파일마다 판 하나, 개수 상한 없음). blame이 그 커밋에서 옛 이름을 찾으려고 없어진 파일의 내용을 모두 읽어서, 없으면
       그 파일의 blame이 실패한다. 사용자 결정(2026-11-26 '내 커밋이 바꾼 파일만 받는다')보다 넓어서 판정을 기다린다.
    4. 합친 커밋에서만 생긴 내 경로의 판. 양쪽이 고친 파일을 합치면(충돌이 없어도) 생기고 1단계(--no-merges)에는 없다. 없으면 그
       파일의 blame이 실패하고, 끝의 판이면 추출기도 그 파일을 읽지 못한다. 합친 커밋을 부모마다 비교한 raw(--diff-merges=separate)를
       내 경로로만(pathspec_args, 글자 그대로) 한 번 읽어 그 항목의 옛·새 blob id를 더한다(트리만 읽음). 내 커밋은 1단계로만 정한다.
       --full-history: 합친 커밋이 한 부모와 같아도 다른 부모 쪽의 커밋까지 본다(git 2.55는 --diff-merges만으로도 이력을 줄이지
       않지만 그것에 기대지 않는다). 이 단계가 실패하면 1~3단계의 id는 그대로 받고 fetched=False로 둔다(합친 판을 못 받음).
    5. 한 번에 받는다(중복 id는 한 번). 받을 id가 없으면 부르지 않는다. fetched는 4단계와 받기가 모두 되었을 때만 참이다
       (받기가 실패해도 색인은 계속한다).
    -> {"paths": [정렬, path_text 글자], "blobs": n, "fetched": bool}"""
    rc, out = L.git(d, 'log', '--no-merges', *RAW, *refs, timeout=1200)
    if rc != 0:
        return dict(paths=[], blobs=0, fetched=False)
    noreply = noreply_re(login)
    commits = [(sha in own or bool(noreply.match(email.lower())), entries) for sha, email, entries in raw_entries(out)]
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
                blobs |= blob_ids(om, nm, oid, nid)
            elif began and (st == 'D' or st.startswith('R')) and om != '160000':   # 「제안」 위 3
                blobs.add(oid)
    merges_ok = True
    if mine:                         # 경로 없이 부르면 모든 합친 커밋의 모든 경로를 비교한다
        inp, tail = pathspec_args(sorted(mine))
        rc, out = L.git(d, '--literal-pathspecs', 'log', '--merges', '--full-history', '--diff-merges=separate', *RAW, *refs, '--stdin',
                        *tail, inp=inp, timeout=1200)
        merges_ok = rc == 0
        if merges_ok:
            blobs |= {i for _, _, entries in raw_entries(out) for om, nm, oid, nid, _, paths in entries
                      if any(p in mine for p in paths) for i in blob_ids(om, nm, oid, nid)}
    fetched = merges_ok
    if blobs:
        rc, _ = L.git(d, '-c', 'fetch.negotiationAlgorithm=noop', '-c', 'maintenance.auto=false', '-c', 'gc.auto=0',
                      'fetch', 'origin', '--no-tags', '--no-write-fetch-head', '--recurse-submodules=no', '--filter=blob:none',
                      '--stdin', inp=''.join(i + '\n' for i in sorted(blobs)).encode(), timeout=900)
        fetched = merges_ok and rc == 0
    return dict(paths=sorted(mine), blobs=len(blobs), fetched=fetched)


def numstat_by_sha(d, refs, paths):
    """표시한 레포: 주어진 경로(path_text 글자)만의 numstat -> {sha: [파일 항목(path, add, dele, binary)]}, 실패하면 None.
    경로는 pathspec_args로 글자 그대로 준다(--literal-pathspecs). --full-history: 경로를 주면 git은 기본으로 이력을 줄여(합친 커밋이
    한 부모와 그 경로가 같으면 다른 부모 쪽을 보지 않음) 곁가지의 내 커밋을 뺀다. 표시 없는 레포의 numstat처럼 그 경로를 바꾼
    머지 아닌 커밋을 모두 본다. -z로 읽는다(numstat_entries): 따옴표로 감싸지 않은 이름 그대로라 snapshot의 경로와 맞는다."""
    if not paths:
        return {}
    inp, tail = pathspec_args(paths)
    rc, out = L.git(d, '--literal-pathspecs', 'log', '-z', '--no-merges', '--full-history', '--numstat', '--format=%x1e%H', *refs,
                    '--stdin', *tail, inp=inp, timeout=1200)
    return numstat_entries(out) if rc == 0 else None


def numstat_entries(out):
    """log -z --numstat --format=%x1e%H 출력 -> {sha: [파일 항목]}. 칸은 NUL로 끝난다: 커밋 머리(\\x1e<sha>), 항목
    (<add>\\t<dele>\\t<경로>, 커밋의 첫 항목 앞에는 줄바꿈). 이름 바꿈은 <add>\\t<dele>\\t 다음 두 칸이 옛 경로·새 경로다(파일 항목은
    새 경로, 2단계 parse_numstat_path와 같음). 경로 글자는 snapshot과 같이 읽는다(못 읽는 바이트는 U+FFFD). 항목 모양은 commits_of와 같다."""
    res, cur, toks, i = {}, None, out.split(b'\0'), 0
    while i < len(toks):
        t = toks[i].lstrip(b'\n')
        i += 1
        if t.startswith(b'\x1e'):
            cur = res.setdefault(t[1:].decode('ascii', errors='replace').strip(), [])
            continue
        parts = t.split(b'\t', 2)
        if cur is None or len(parts) != 3:
            continue
        a, b, p = parts[0].decode('ascii', errors='replace'), parts[1].decode('ascii', errors='replace'), parts[2]
        if not p:                        # 이름 바꿈: 다음 두 칸이 옛 경로·새 경로
            p = toks[i + 1] if i + 1 < len(toks) else b''
            i += 2
        if p:
            cur.append(dict(path=p.decode('utf-8', errors='replace'), add=int(a) if a.isdigit() else 0,
                            dele=int(b) if b.isdigit() else 0, binary=not a.isdigit()))
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
        if partial is not None:          # 파일 항목은 내 경로만 받은 numstat(-z)에서 읽었다(실패했으면 비움)
            files = (by_sha or {}).get(sha, [])
        else:
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
    failed = []                      # blame이 실패한 파일. 표시한 레포만 partial.blame_failed에 남긴다
    for f in files:
        f['my_ranges'], f['lines'] = None, None
        if f['kind'] in ('code', 'config', 'migration', 'test') and (f.get('size') or 0) <= MAX_BLAME and f['path'] in touched:
            f['my_ranges'], f['lines'] = blame(d, f, own_shas)
            if f['my_ranges'] is None:
                failed.append(f['path'])
        elif f['kind'] in ('code', 'config', 'migration', 'test') and f['path'] not in touched:
            f['my_ranges'] = []
        f['my_lines'] = sum(b - a + 1 for a, b in f['my_ranges']) if f['my_ranges'] else 0
    prs = []
    if r.get('prs'):
        prs = api_prs(f"repos/{r['full_name']}/pulls?state=all&per_page=100")
    tot = len(cs)
    rec = dict(key=r['key'], full_name=r['full_name'], dir=d, refs=refs, commits=cs, files=files, prs=prs,
               own_share=round(len(own_shas) / tot, 3) if tot else 0, api_own=len(own), evidence=r.get('evidence', False))
    if partial is not None:          # 표시한 레포만: {paths, blobs, fetched, numstat_ok, blame_failed}
        rec['partial'] = dict(partial, paths=sorted(shown_path(p) for p in partial['paths']), blame_failed=blame_failed(failed))
    return rec


def blame_failed(paths):
    """표시한 레포에서 blame이 실패한 파일(받지 않은 판을 읽어야 했음) -> {"count": 모두의 수, "paths": [정렬한 앞
    BLAME_FAILED_LIST개], "omitted": 목록에서 뺀 수}. 받기는 넓히지 않는다(받기 한 번). 그 파일은 my_ranges None으로 남는다
    (2단계 코드가 '내 줄을 세지 않음'으로 읽는 값). Task 4가 '큰 레포에서 내 줄을 세지 못한 파일 n개'로 보인다."""
    ps = sorted(paths)
    return dict(count=len(ps), paths=ps[:BLAME_FAILED_LIST], omitted=max(0, len(ps) - BLAME_FAILED_LIST))


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
