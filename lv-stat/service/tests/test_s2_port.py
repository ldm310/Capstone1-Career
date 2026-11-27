"""2단계 코드(s2lib·s2_index)를 스테이징 작업 폴더·토큰 규칙에 맞춘 것 시험.

- s2lib는 불러올 때 경로(LV_S2_HOME)와 git 환경(GENV)을 정한다. 그래서 s2 모듈은 언제나 새 하위 프로세스에서
  부른다(같은 프로세스의 다른 시험과 작업 폴더가 섞이지 않게).
- 하위 프로세스는 -I -B로 띄우고 환경은 PATH만 물려준다. 작업 폴더는 늘 임시 폴더라 코드 폴더(s2)에는
  아무것도 생기지 않아야 한다(부를 때마다 확인).
- 레포는 이 시험이 git으로 만든 합성 레포뿐이다. 실제 GitHub는 부르지 않는다(LV_GITHUB_OFFLINE=1 또는 127.0.0.1의 가짜 API).
- 색인을 돌릴 때는 PATH 맨 앞에 가짜 gh를 둔다. 불리면 표시 파일을 남기므로 gh를 한 번이라도 부르면 실패한다.
"""
import http.server
import json
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
CODE = os.path.realpath(os.path.join(HERE, "..", "s2"))

# 시험용 가짜 비밀값(진짜 값 아님). git 자식 프로세스에는 하나도 가면 안 된다.
FAKE_SECRETS = {
    "LV_GITHUB_TOKEN": "test-lv-token",
    "GH_TOKEN": "test-gh-token",
    "GITHUB_TOKEN": "test-github-token",
    "GH_ENTERPRISE_TOKEN": "test-ghe-token",
    "GITHUB_ENTERPRISE_TOKEN": "test-github-enterprise-token",
    "ANTHROPIC_API_KEY": "test-anthropic-key",
}
OWN_EMAIL = "123+tester@users.noreply.github.com"
OTHER_EMAIL = "other@example.com"

# 하위 프로세스에서 s2lib를 불러 값을 JSON 한 줄로 찍는다. argv[1] = s2lib.py가 있는 폴더.
PROBE_PATHS = """
import json, sys
sys.path.insert(0, sys.argv[1])
import s2lib
print(json.dumps({k: getattr(s2lib, k, None) for k in ('CODE', 'S2', 'INDEX', 'OUT', 'EMPTY_HOME', 'LINGUIST')}))
"""

# argv[2] = 쉼표로 이은 비밀값 이름. 값은 찍지 않고 있는지만 본다.
PROBE_GENV = """
import json, os, sys
sys.path.insert(0, sys.argv[1])
import s2lib
names = sys.argv[2].split(',')
print(json.dumps({
    'genv': sorted(n for n in names if n in s2lib.GENV),
    'environ': sorted(n for n in names if n in os.environ),
    'path_kept': s2lib.GENV.get('PATH') == os.environ.get('PATH'),
    'no_lazy': s2lib.GENV.get('GIT_NO_LAZY_FETCH'),
    'home': s2lib.GENV.get('HOME'),
}))
"""

# git이 실제로 받은 환경을 본다: 셸 별칭(!env)은 git 프로세스의 환경을 그대로 물려받는다.
# argv[3:] = 레포 폴더(이 차례로 s2lib.git을 부른다).
PROBE_GIT_ENV = """
import json, sys
sys.path.insert(0, sys.argv[1])
import s2lib
names = sys.argv[2].split(',')
res = {'mark': getattr(s2lib, 'LAZY_MARK', None), 'repos': []}
for d in sys.argv[3:]:
    rc, out = s2lib.git(d, '-c', 'alias.lvenv=!env', 'lvenv')
    env = dict(line.split('=', 1) for line in out.decode('utf-8', 'replace').splitlines() if '=' in line)
    res['repos'].append({'rc': rc, 'no_lazy': env.get('GIT_NO_LAZY_FETCH'),
                         'secrets': sorted(n for n in names if n in env)})
res['genv_no_lazy_after'] = s2lib.GENV.get('GIT_NO_LAZY_FETCH')
print(json.dumps(res))
"""


def base_env(**extra):
    """하위 프로세스 환경: PATH만 물려받는다(개발자 셸의 토큰·git 설정이 섞이지 않게)."""
    env = {"PATH": os.environ.get("PATH", os.defpath)}
    env.update(extra)
    return env


def code_tree():
    return sorted(
        os.path.relpath(os.path.join(d, n), CODE)
        for d, dirs, files in os.walk(CODE)
        for n in dirs + files
    )


def git_run(args, env):
    p = subprocess.run(["git", *args], env=env, capture_output=True, timeout=60)
    if p.returncode != 0:
        raise AssertionError("git %s 실패: %s" % (args[:2], p.stderr.decode("utf-8", "replace")))
    return p.stdout.decode("utf-8", "replace")


def make_repo(root, branch, commits):
    """합성 레포를 root/src에 만들고 root/clone으로 받는다(받은 레포처럼 refs/remotes/origin/<branch>가 생김).
    commits = [(작성자 이메일, 제목, {경로: 내용})]. -> (clone 폴더, 커밋 SHA 목록(오래된 순))"""
    githome = os.path.join(root, "githome")
    os.makedirs(githome)
    env = base_env(HOME=githome, XDG_CONFIG_HOME=githome, GIT_CONFIG_NOSYSTEM="1",
                   GIT_AUTHOR_NAME="Tester", GIT_COMMITTER_NAME="Tester",
                   GIT_COMMITTER_EMAIL="committer@example.com")
    src = os.path.join(root, "src")
    git_run(["init", "-q", src], env)
    git_run(["-C", src, "symbolic-ref", "HEAD", "refs/heads/" + branch], env)
    for i, (email, subject, files) in enumerate(commits, 1):
        for path, text in files.items():
            full = os.path.join(src, path)
            os.makedirs(os.path.dirname(full), exist_ok=True)
            with open(full, "w", encoding="utf-8") as f:
                f.write(text)
        when = "2026-01-%02dT10:00:00+09:00" % i
        git_run(["-C", src, "add", "-A"], env)
        git_run(["-C", src, "-c", "commit.gpgsign=false", "commit", "-q", "-m", subject],
                dict(env, GIT_AUTHOR_EMAIL=email, GIT_AUTHOR_DATE=when, GIT_COMMITTER_DATE=when))
    shas = git_run(["-C", src, "rev-list", "--reverse", "HEAD"], env).split()
    clone = os.path.join(root, "clone")
    git_run(["clone", "-q", "--no-checkout", src, clone], env)
    return clone, shas


def write_people(home, clone, branch, prs):
    os.makedirs(home, exist_ok=True)
    people = [{"pid": "P01", "login": "tester", "role": None, "level": None,
               "repos": [{"key": "tester__demo", "full_name": "tester/demo", "dir": clone,
                          "default_branch": branch, "prs": prs}]}]
    with open(os.path.join(home, "people.json"), "w", encoding="utf-8") as f:
        json.dump(people, f)


def fake_gh(root):
    """PATH 맨 앞에 둘 가짜 gh. 불리면 표시 파일에 인자를 남기고 실패한다. -> (bin 폴더, 표시 파일)"""
    bin_dir = os.path.join(root, "bin")
    os.makedirs(bin_dir)
    mark = os.path.join(root, "gh-called")
    path = os.path.join(bin_dir, "gh")
    with open(path, "w", encoding="utf-8") as f:
        f.write('#!/bin/sh\necho "$*" >> %s\necho "fake gh must not run" >&2\nexit 1\n' % shlex.quote(mark))
    os.chmod(path, 0o755)
    return bin_dir, mark


class FakeAPI:
    """127.0.0.1 빈 포트의 가짜 GitHub API. routes[요청 대상] = (본문, 헤더). 없는 대상은 404."""

    def __init__(self):
        self.routes = {}
        self.seen = []  # (요청 대상, Authorization 헤더 또는 None)
        owner = self

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                target = self.requestline.split()[1]  # 받은 그대로(퍼센트 인코딩 포함)
                owner.seen.append((target, self.headers.get("Authorization")))
                if target in owner.routes:
                    status, (body, headers) = 200, owner.routes[target]
                else:
                    status, body, headers = 404, {"message": "Not Found"}, {}
                raw = json.dumps(body).encode("utf-8")
                self.send_response(status)
                for k, v in headers.items():
                    self.send_header(k, v)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)

            def log_message(self, *args):
                pass

        self.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.base = "http://127.0.0.1:%d" % self.server.server_address[1]
        threading.Thread(target=self.server.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True).start()

    def close(self):
        self.server.shutdown()
        self.server.server_close()


class S2PortTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="lv-s2-port-")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.home = os.path.join(self.tmp, "home")

    def run_py(self, args, env):
        """s2 모듈을 새 프로세스로 부르고, 코드 폴더에 아무것도 안 생겼는지 확인한다."""
        before = code_tree()
        p = subprocess.run([sys.executable, "-I", "-B", *args], env=env, capture_output=True, timeout=120)
        self.assertEqual(code_tree(), before, "s2 코드 폴더에 파일이 생기면 안 된다")
        return p.returncode, p.stdout.decode("utf-8", "replace"), p.stderr.decode("utf-8", "replace")

    def probe(self, code, *argv, env):
        rc, out, err = self.run_py(["-c", code, *argv], env)
        self.assertEqual(rc, 0, err)
        return json.loads(out)

    def run_index(self, clone, branch, prs, **env_extra):
        """people.json을 쓰고 s2_index.py P01을 돌린다. gh는 한 번도 불리면 안 된다. -> (person.json, 레포 색인)"""
        write_people(self.home, clone, branch, prs)
        bin_dir, gh_mark = fake_gh(self.tmp)
        env = base_env(LV_S2_HOME=self.home, **env_extra)
        env["PATH"] = bin_dir + os.pathsep + env["PATH"]
        rc, _, err = self.run_py([os.path.join(CODE, "s2_index.py"), "P01"], env)
        self.assertFalse(os.path.exists(gh_mark), "gh를 부르면 안 된다")
        self.assertEqual(rc, 0, err)
        idx = os.path.join(self.home, "index", "P01")
        with open(os.path.join(idx, "person.json"), encoding="utf-8") as f:
            person = json.load(f)
        with open(os.path.join(idx, "tester__demo.json"), encoding="utf-8") as f:
            data = json.load(f)
        return person, data

    # ---------------- s2lib: 경로
    def test_paths_follow_home(self):
        out = self.probe(PROBE_PATHS, CODE, env=base_env(LV_S2_HOME=self.home))
        self.assertEqual(out["S2"], self.home)
        self.assertEqual(out["INDEX"], os.path.join(self.home, "index"))
        self.assertEqual(out["OUT"], os.path.join(self.home, "out"))
        self.assertEqual(out["EMPTY_HOME"], os.path.join(self.home, ".emptyhome"))
        self.assertTrue(os.path.isdir(out["EMPTY_HOME"]))  # 불러올 때 만든다
        # Linguist 자료는 작업 폴더가 아니라 코드 폴더에서 읽는다.
        self.assertEqual(out["CODE"], CODE)
        self.assertEqual(out["LINGUIST"], os.path.join(CODE, "data", "linguist", "languages.yml"))
        self.assertTrue(os.path.isfile(out["LINGUIST"]))

    def test_unset_home_falls_back_to_code_folder(self):
        # 추출기(cat_*)는 LV_S2_HOME 없이도 s2lib를 불러야 한다.
        # 진짜 코드 폴더에 .emptyhome이 생기지 않게 s2lib.py 사본을 임시 폴더에서 부른다.
        code = os.path.join(self.tmp, "code")
        os.makedirs(code)
        shutil.copy(os.path.join(CODE, "s2lib.py"), code)
        for name, env in (("없음", base_env()), ("빈 값", base_env(LV_S2_HOME=""))):
            with self.subTest(name):
                shutil.rmtree(os.path.join(code, ".emptyhome"), ignore_errors=True)
                out = self.probe(PROBE_PATHS, code, env=env)
                self.assertEqual(out["CODE"], code)
                self.assertEqual(out["S2"], code)
                self.assertEqual(out["INDEX"], os.path.join(code, "index"))
                self.assertTrue(os.path.isdir(os.path.join(code, ".emptyhome")))

    # ---------------- s2lib: git 환경
    def test_genv_has_no_tokens(self):
        out = self.probe(PROBE_GENV, CODE, ",".join(FAKE_SECRETS),
                         env=base_env(LV_S2_HOME=self.home, **FAKE_SECRETS))
        self.assertEqual(out["genv"], [])  # git 자식 프로세스 환경에는 없다
        self.assertEqual(out["environ"], sorted(FAKE_SECRETS))  # 같은 프로세스의 ghapi는 그대로 읽는다
        self.assertTrue(out["path_kept"])
        self.assertEqual(out["no_lazy"], "1")
        self.assertEqual(out["home"], os.path.join(self.home, ".emptyhome"))

    def test_lazy_marker_per_repo(self):
        lazy, plain = os.path.join(self.tmp, "lazy"), os.path.join(self.tmp, "plain")
        for d in (lazy, plain):
            git_run(["init", "-q", d], base_env(HOME=self.tmp, GIT_CONFIG_NOSYSTEM="1"))
        open(os.path.join(lazy, ".git", "lv-allow-lazy"), "w").close()
        out = self.probe(PROBE_GIT_ENV, CODE, ",".join(FAKE_SECRETS), lazy, plain,
                         env=base_env(LV_S2_HOME=self.home, **FAKE_SECRETS))
        self.assertEqual(out["mark"], "lv-allow-lazy")
        lazy_env, plain_env = out["repos"]
        # 표시한 레포만 빠진 파일 내용을 받으러 갈 수 있다. 어느 쪽이든 토큰은 없다.
        self.assertEqual(lazy_env, {"rc": 0, "no_lazy": None, "secrets": []})
        # 앞의 호출이 공통 환경(GENV)을 바꾸지 않았다.
        self.assertEqual(plain_env, {"rc": 0, "no_lazy": "1", "secrets": []})
        self.assertEqual(out["genv_no_lazy_after"], "1")

    # ---------------- s2_index: gh 대신 ghapi
    def test_index_offline_noreply_is_own(self):
        clone, _ = make_repo(self.tmp, "main", [
            (OWN_EMAIL, "mine 1", {"app.py": "a = 1\n"}),
            (OTHER_EMAIL, "theirs", {"other.py": "b = 2\n"}),
            (OWN_EMAIL, "mine 2", {"app.py": "a = 1\nc = 3\n"}),
            (OWN_EMAIL, "mine 3", {"lib/util.py": "def f():\n    return 4\n"}),
        ])
        person, data = self.run_index(clone, "main", prs=True, LV_GITHUB_OFFLINE="1")
        self.assertEqual(person["login"], "tester")
        self.assertEqual(person["repo_keys"], ["tester__demo"])
        self.assertNotIn("error", data)
        self.assertEqual(len(data["commits"]), 4)
        self.assertEqual(sorted(c["subject"] for c in data["commits"] if c["own"]),
                         ["mine 1", "mine 2", "mine 3"])
        self.assertEqual(data["api_own"], 0)  # 오프라인: API는 빈 목록, 내 커밋은 noreply 이메일로만 찾았다
        self.assertEqual(data["prs"], [])
        lines = {f["path"]: f["my_lines"] for f in data["files"]}
        self.assertEqual(lines, {"app.py": 2, "other.py": 0, "lib/util.py": 2})

    def test_index_commit_query_encodes_branch(self):
        branch = "기능#1"  # 한글과 '#'(인코딩하지 않으면 뒤가 잘린다)
        clone, shas = make_repo(self.tmp, branch, [
            ("dev@example.com", "mine via api", {"app.py": "a = 1\n"}),
            (OTHER_EMAIL, "theirs", {"other.py": "b = 2\n"}),
        ])
        api = FakeAPI()
        self.addCleanup(api.close)
        want = "/repos/tester/demo/commits?author=tester&sha=%EA%B8%B0%EB%8A%A5%231&per_page=100"
        api.routes[want] = ([{
            "sha": shas[0], "node_id": "C_1", "html_url": "https://github.com/tester/demo/commit/" + shas[0],
            "commit": {"author": {"name": "Tester", "email": "dev@example.com", "date": "2026-01-01T01:00:00Z"},
                       "committer": {"name": "Tester", "email": "committer@example.com", "date": "2026-01-01T01:00:00Z"},
                       "message": "mine via api"},
            "author": {"login": "tester", "id": 123, "type": "User"},
            "committer": None,
            "parents": [],
        }], {})
        _, data = self.run_index(clone, branch, prs=False, LV_GITHUB_API=api.base, LV_GITHUB_TOKEN="test-api-token")
        self.assertEqual([t for t, _ in api.seen], [want])
        self.assertEqual({a for _, a in api.seen}, {"Bearer test-api-token"})  # 토큰은 API에만 간다
        self.assertEqual(data["api_own"], 1)
        self.assertEqual([c["subject"] for c in data["commits"] if c["own"]], ["mine via api"])

    def test_index_pr_fields_match_old_jq(self):
        clone, _ = make_repo(self.tmp, "main", [(OWN_EMAIL, "mine 1", {"app.py": "a = 1\n"})])
        api = FakeAPI()
        self.addCleanup(api.close)
        first = "/repos/tester/demo/pulls?state=all&per_page=100"
        second = first + "&page=2"
        merged = {
            "url": api.base + "/repos/tester/demo/pulls/7", "id": 1007, "node_id": "PR_7",
            "html_url": "https://github.com/tester/demo/pull/7", "number": 7, "state": "closed", "locked": False,
            "title": "로그인 추가", "user": {"login": "tester", "id": 123, "type": "User"},
            "body": "가" * 4001,
            "labels": [{"id": 1, "name": "feature", "color": "00ff00"}, {"id": 2, "name": "백엔드", "color": "0000ff"}],
            "created_at": "2026-01-03T01:00:00Z", "updated_at": "2026-01-04T01:00:00Z",
            "closed_at": "2026-01-04T01:00:00Z", "merged_at": "2026-01-04T01:00:00Z",
            "merge_commit_sha": "a" * 40, "draft": False, "author_association": "OWNER",
            "head": {"label": "tester:login", "ref": "login", "sha": "b" * 40,
                     "user": {"login": "tester"}, "repo": {"full_name": "tester/demo"}},
            "base": {"label": "tester:main", "ref": "main", "sha": "c" * 40,
                     "user": {"login": "tester"}, "repo": {"full_name": "tester/demo"}},
        }
        open_pr = {
            "url": api.base + "/repos/tester/demo/pulls/8", "id": 1008, "node_id": "PR_8",
            "html_url": "https://github.com/tester/demo/pull/8", "number": 8, "state": "open", "locked": False,
            "title": "WIP", "user": None, "body": None, "labels": [],
            "created_at": "2026-01-05T01:00:00Z", "updated_at": "2026-01-05T01:00:00Z",
            "closed_at": None, "merged_at": None, "merge_commit_sha": None, "draft": True,
            "author_association": "NONE",
            "head": {"label": "x:wip", "ref": "wip", "sha": "d" * 40, "user": None, "repo": None},
            "base": {"label": "tester:main", "ref": "main", "sha": "c" * 40,
                     "user": {"login": "tester"}, "repo": {"full_name": "tester/demo"}},
        }
        api.routes[first] = ([merged], {"Link": '<%s%s>; rel="next"' % (api.base, second)})
        api.routes[second] = ([open_pr], {})
        _, data = self.run_index(clone, "main", prs=True, LV_GITHUB_API=api.base)
        self.assertIn(second, [t for t, _ in api.seen])  # 다음 쪽도 받았다(옛 gh api --paginate)
        # 옛 jq: {number, title, body: ((.body // "") | .[0:4000]), merged_at, merge_commit_sha,
        #         user: .user.login, head_sha: .head.sha, created_at, labels: [.labels[].name]}
        self.assertEqual(data["prs"], [
            {"number": 7, "title": "로그인 추가", "body": "가" * 4000, "merged_at": "2026-01-04T01:00:00Z",
             "merge_commit_sha": "a" * 40, "user": "tester", "head_sha": "b" * 40,
             "created_at": "2026-01-03T01:00:00Z", "labels": ["feature", "백엔드"]},
            {"number": 8, "title": "WIP", "body": "", "merged_at": None, "merge_commit_sha": None,
             "user": None, "head_sha": "d" * 40, "created_at": "2026-01-05T01:00:00Z", "labels": []},
        ])


if __name__ == "__main__":
    unittest.main()
