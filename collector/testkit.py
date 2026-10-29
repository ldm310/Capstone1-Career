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


class FakeApi:
    """extract.Api의 get·pages를 흉내 낸다. routes = {경로(쿼리 없이): 응답 값}. 값이 예외면 던지고, 없는 경로는 진짜 API처럼 404다.
    호출마다 calls를 1 올리고 (경로, params)를 seen에 쌓는다. pages도 진짜처럼 첫 반복 때 요청한다."""
    def __init__(self, routes):
        self.routes, self.calls, self.seen, self.remaining = dict(routes), 0, [], None

    def _ask(self, path, params):
        """요청 하나를 기록하고 (경로가 있는지, 값)을 돌려준다. 값이 예외면 던진다."""
        self.calls += 1
        self.seen.append((path, params))
        if path not in self.routes: return False, None
        value = self.routes[path]
        if isinstance(value, Exception): raise value
        return True, value

    def get(self, path, params=None, ok=(200,)):
        found, value = self._ask(path, params)
        if found: return value, {}, 200
        if 404 in ok: return None, {}, 404
        raise extract.StopCheck(f'GET {path} → HTTP 404')

    def pages(self, path, params, max_pages=10):
        found, value = self._ask(path, params)
        if not found: raise extract.StopCheck(f'GET {path} → HTTP 404')
        yield from value or []
