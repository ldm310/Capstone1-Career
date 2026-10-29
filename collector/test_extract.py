"""extract.blame 시험: 빠른 길(한 번만 추가된 파일·본인 commit이 닿지 않은 파일은 blame 없이 줄만 셈)이 모든 파일을 blame하던 결과와 같은지 본다.

네트워크를 쓰지 않는다. 레포는 임시 폴더에 만든다.
"""
import os
import re
import subprocess
import tempfile
import unittest
from pathlib import Path

import extract

GIT = ['git', '-c', 'core.hooksPath=/dev/null', '-c', 'commit.gpgsign=false']
ME, MATE, TWIN = ('Me', 'me@example.com'), ('Mate', 'mate@example.com'), ('Me', 'twin@example.com')  # TWIN: 이름만 같은 사람
EMAILS, NAMES = {'me@example.com'}, {'Me'}


def blame_reference(path, sha, emails, names):
    """정답 기준: 건너뛰지 않는 모든 파일을 blame한다. git 출력은 바이트로 읽고, 줄은 git이 내준 줄 번호 그대로 센다."""
    count, units = dict(own=0, name_only=0, other=0, files=0), []
    for entry in extract.git(path, 'ls-tree', '-r', '-l', '-z', sha).split('\0'):
        if not entry: continue
        meta, p = entry.split('\t', 1)
        _, kind, _, size = meta.split()
        if kind != 'blob' or extract.skipped(p, int(size)): continue
        r = subprocess.run(['git', '-C', str(path), 'blame', '-w', '--line-porcelain', sha, '--', p], capture_output=True)
        if r.returncode: continue
        count['files'] += 1
        mine, by_line, mail, author, line = [], {}, None, None, None
        for row in r.stdout.split(b'\n'):
            if re.match(rb'[0-9a-f]{40,64} \d+ \d+', row): line = int(row.split()[2])
            elif row.startswith(b'author-mail '): mail = row[13:-1].decode('utf-8', 'replace').lower()
            elif row.startswith(b'author '): author = row[7:].decode('utf-8', 'replace')
            elif row.startswith(b'\t'): by_line[line] = (mail, author)
        for n, (mail, author) in sorted(by_line.items()):
            if mail in emails: count['own'] += 1; mine.append(n)
            elif author in names: count['name_only'] += 1
            else: count['other'] += 1
        if mine: units.append(dict(sha=sha, path=p, lines=extract.ranges(mine)))
    return count, units


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


class FastBlame(unittest.TestCase):
    def check(self, repo):
        sha = repo.head()
        want = blame_reference(repo.path, sha, EMAILS, NAMES)
        got = extract.blame(repo.path, sha, EMAILS, NAMES)
        self.assertEqual(got[0], want[0])
        self.assertEqual(sorted(got[1], key=lambda u: u['path']), sorted(want[1], key=lambda u: u['path']))
        return got

    def test_scenarios_match_blaming_every_file(self):
        with tempfile.TemporaryDirectory() as d:
            r = Repo(d)
            r.commit(ME, {'mine.py': lines('me', 30), 'shared.py': lines('me', 20), 'renamed_later.py': lines('me', 12),
                          'ws.py': lines('me', 8), 'no_newline.txt': 'a\nb\nlast', 'empty.txt': '', 'gone.py': lines('me', 5),
                          'node_modules/x.js': lines('me', 50), 'logo.png': b'\x89PNG\x00\x01\n\x02'})
            r.commit(MATE, {'mate.py': lines('mate', 40), 'shared.py': lines('me', 10) + lines('mate', 5)})  # 내 파일 일부를 팀원이 고침
            r.commit(MATE, move=[('renamed_later.py', 'pkg/renamed.py')])                 # 팀원이 내 파일을 옮김(내용 그대로)
            r.commit(MATE, {'ws.py': lines('me', 8).replace(' with', '  with')})          # 공백만 바꿈(-w로 내 줄 유지)
            r.commit(MATE, {'mate_then_moved_by_me.py': lines('mate', 9)})
            r.commit(ME, move=[('mate_then_moved_by_me.py', 'moved_by_me.py')])          # 내가 옮긴 팀원 파일: 줄은 팀원 것
            r.commit(ME, delete=['gone.py'])
            r.commit(MATE, {'gone.py': lines('mate', 5)})                                  # 지웠다가 다시 추가
            r.commit(TWIN, {'twin.py': lines('twin', 7)})                                  # 이름만 같은 사람
            r.commit(ME, {'binaryish.dat': b'\x00\x01\x02\n\x03'})
            count, units = self.check(r)
            self.assertGreater(count['own'], 0)
            self.assertEqual(count['name_only'], 7)

    def test_lone_carriage_return_is_not_a_line_break(self):  # git은 \n으로만 줄을 나눈다(빌드 결과 .exe 등에 \r이 섞여 있음)
        with tempfile.TemporaryDirectory() as d:
            r = Repo(d)
            r.commit(ME, {'old_mac.txt': b'a\r\tb\r\tc\n', 'mixed.txt': b'x\ny\r\tz\n'})
            r.commit(MATE, {'mixed.txt': b'x\nY\r\tz\n'})
            count, units = self.check(r)
            self.assertEqual(count['own'] + count['other'], 3)  # old_mac 1줄 + mixed 2줄
            self.assertEqual(sorted((u['path'], u['lines']) for u in units), [('mixed.txt', [[1, 1]]), ('old_mac.txt', [[1, 1]])])

    def test_conflict_resolution_in_my_merge_commit_counts_as_mine(self):
        with tempfile.TemporaryDirectory() as d:
            r = Repo(d)
            r.commit(MATE, {'app.py': lines('base', 6)})
            r.git('checkout', '-q', '-b', 'side')
            r.commit(MATE, {'app.py': lines('side', 6)})
            r.git('checkout', '-q', 'main')
            r.commit(MATE, {'app.py': lines('main', 6)})
            r.git('merge', '-q', 'side', '-m', 'merge', check=False, who=ME)
            (r.path / 'app.py').write_text(lines('resolved', 6))
            r.git('add', 'app.py')
            r.git('commit', '-q', '--no-edit', who=ME)
            count, _ = self.check(r)
            self.assertEqual(count['own'], 6)

    def test_bulk_import_is_counted_without_blaming_each_file(self):  # 커널 소스처럼 한 번에 올린 파일 수천 개
        with tempfile.TemporaryDirectory() as d:
            r = Repo(d)
            r.commit(ME, {f'vendor_src/m{i}.c': lines('k', 3) for i in range(400)})
            r.commit(ME, {'vendor_src/m0.c': lines('k', 2) + lines('me', 4)})
            calls = []
            real = subprocess.run
            def spy(cmd, *args, **kw):
                if 'blame' in cmd: calls.append(cmd[-1])
                return real(cmd, *args, **kw)
            extract.subprocess.run = spy
            try: count, _ = extract.blame(r.path, r.head(), EMAILS, NAMES)
            finally: extract.subprocess.run = real
            self.assertEqual(count, blame_reference(r.path, r.head(), EMAILS, NAMES)[0])
            self.assertEqual(calls, ['vendor_src/m0.c'])  # 두 번 이상 바뀐 파일만 blame한다



class ReadFiles(unittest.TestCase):
    """skills.file_lines(파일 하나)와 skills.read_files(한 번에 여러 개)는 git blame과 같은 줄 번호를 내야 한다."""
    def test_lines_match_git_line_numbers_and_batch_reader(self):
        import skills as S
        with tempfile.TemporaryDirectory() as d:
            r = Repo(d)
            bodies = {'cr.txt': b'a\r\tb\nc\n', 'crlf.txt': b'x\r\ny\r\n', 'tail.txt': b'p\nq', 'empty.txt': b'',
                      'latin.txt': b'caf\xe9\n', 'dir/deep name.py': b'import os\n'}
            r.commit(ME, bodies)
            sha = r.head()
            self.assertEqual(S.file_lines(r.path, sha, 'cr.txt'), ['a\r\tb', 'c'])  # 혼자 있는 \r은 줄바꿈이 아니다
            self.assertEqual(S.file_lines(r.path, sha, 'crlf.txt'), ['x', 'y'])
            paths = [*bodies, 'missing.txt']
            got = S.read_files(r.path, sha, paths)
            self.assertEqual(got, {p: S.file_lines(r.path, sha, p) for p in paths})


if __name__ == '__main__': unittest.main()
