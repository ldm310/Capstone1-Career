"""시험용 도구: 임시 git 레포 만들기(Repo)와 GitHub API 흉내(FakeApi). 네트워크를 쓰지 않는다."""
import os
import subprocess
from pathlib import Path

import extract

GIT = ['git', '-c', 'core.hooksPath=/dev/null', '-c', 'commit.gpgsign=false']
ME, MATE, TWIN = ('Me', 'me@example.com'), ('Mate', 'mate@example.com'), ('Me', 'twin@example.com')  # TWIN: 이름만 같은 사람
EMAILS, NAMES = {'me@example.com'}, {'Me'}


class Repo:
    def __init__(self, root):
        self.path, self.t = Path(root), 1_760_000_000
        self.git('init', '-q', '-b', 'main')

    def git(self, *args, who=None, check=True):
        env = os.environ
        if who:
            self.t += 60
            env = {**env, 'GIT_AUTHOR_NAME': who[0], 'GIT_AUTHOR_EMAIL': who[1], 'GIT_COMMITTER_NAME': who[0], 'GIT_COMMITTER_EMAIL': who[1],
                   'GIT_AUTHOR_DATE': f'@{self.t} +0900', 'GIT_COMMITTER_DATE': f'@{self.t} +0900'}
        return subprocess.run([*GIT, '-C', str(self.path), *args], check=check, capture_output=True, text=True, env=env)

    def commit(self, who, files=None, delete=(), move=()):
        for p, body in (files or {}).items():
            (self.path / p).parent.mkdir(parents=True, exist_ok=True)
            (self.path / p).write_bytes(body.encode() if isinstance(body, str) else body)
        for old, new in move: (self.path / new).parent.mkdir(parents=True, exist_ok=True); self.git('mv', old, new)
        for p in delete: self.git('rm', '-q', p)
        self.git('add', '-A')
        self.git('commit', '-q', '--allow-empty', '-m', 'work', who=who)
        return self

    def head(self): return self.git('rev-parse', 'HEAD').stdout.strip()


def lines(tag, n): return ''.join(f'{tag} line {i} with some words\n' for i in range(n))


class Paged:
    """쪽으로 나뉜 응답(진짜 API의 Link 다음 쪽 흉내). 쪽마다 진짜 본문 모양(목록, 또는 검색처럼 {"items": [...]})을 둔다."""
    def __init__(self, *pages): self.pages = list(pages)


class Status:
    """본문 없이 상태만 있는 답. 예: Status(410) = 이슈를 끈 레포. 없는 경로는 Status(404)로 본다."""
    def __init__(self, code): self.code = code


class FakeApi:
    """extract.Api의 get·pages를 흉내 낸다. routes = {경로(쿼리 없이): 응답 값}. 값이 예외면 던지고, 없는 경로는 진짜 API처럼 404다.
    값이 Paged면 get은 첫 쪽을, pages는 max_pages쪽까지(None이면 끝까지) 돌려준다. pages의 key는 본문에서 목록이 든 칸이다(검색의 'items').
    값이 Status면 그 상태로 답한다: get은 ok에, pages는 empty에 있으면 값 없이 끝나고, 아니면 진짜처럼 StopCheck를 던진다.
    호출마다 calls를 1 올리고 (경로, params)를 seen에 쌓는다. pages도 진짜처럼 첫 반복 때 요청한다."""
    def __init__(self, routes):
        self.routes, self.calls, self.seen, self.remaining = dict(routes), 0, [], None

    def _ask(self, path, params):
        """요청 하나를 기록하고 값을 돌려준다. 값이 예외면 던지고, 없는 경로는 Status(404)다."""
        self.calls += 1
        self.seen.append((path, params))
        value = self.routes.get(path, Status(404))
        if isinstance(value, Exception): raise value
        return value

    def get(self, path, params=None, ok=(200,)):
        value = self._ask(path, params)
        if isinstance(value, Status):
            if value.code in ok: return None, {}, value.code
            raise extract.StopCheck(f'GET {path} → HTTP {value.code}')
        return (value.pages[0] if isinstance(value, Paged) else value), {}, 200

    def pages(self, path, params, max_pages=10, key=None, empty=(409,)):
        value = self._ask(path, params)
        if isinstance(value, Status):
            if value.code in empty: return
            raise extract.StopCheck(f'GET {path} → HTTP {value.code}')
        for page in value.pages[:max_pages] if isinstance(value, Paged) else [value]:
            yield from ((page or {}).get(key) if key else page) or []
