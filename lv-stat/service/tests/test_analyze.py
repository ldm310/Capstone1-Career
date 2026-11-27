"""analyze.py(GitHub 계정 하나 분석) 시험.

- GitHub는 127.0.0.1 빈 포트의 가짜 API로만 부른다(test_ghapi·test_s2_port와 같은 방식). 실제 GitHub는 부르지 않는다.
- 레포는 이 시험이 git으로 만든 합성 레포뿐이다. clone_fn(또는 진짜 clone의 runner 자리)이 그 레포를 받는다(git clone).
  받은 레포의 코드는 실행하지 않는다.
- analyze는 s2 단계를 새 프로세스(-I -B)로 돌린다. 시험마다 코드 폴더(s2)에 아무것도 안 생겼는지 본다.
- s2lib는 불러올 때 작업 폴더(LV_S2_HOME, 없으면 코드 폴더) 아래 빈 HOME 폴더를 만든다. analyze는 git 환경(GENV)을 쓰려고 이
  프로세스에서 s2lib를 처음 쓸 때 불러온다. 코드 폴더에 그 폴더가 생기지 않게 setUpModule에서 임시 폴더를 작업 폴더로 두고 먼저
  불러 둔다.
"""
import datetime
import http.server
import json
import os
import shutil
import sys
import tempfile
import threading
import time
import unittest
import uuid
from unittest import mock

from test_s2_port import CODE, OTHER_EMAIL, OWN_EMAIL, base_env, code_tree, git_run

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, CODE)                                          # s2lib(setUpModule)
sys.path.insert(0, os.path.realpath(os.path.join(HERE, "..")))   # analyze

import analyze  # noqa: E402

GITHUB_ENV = ("LV_GITHUB_API", "LV_GITHUB_TOKEN", "LV_GITHUB_OFFLINE")
OWNED = "/users/tester/repos?type=owner&sort=pushed&per_page=100"
SEARCH = "/search/commits?q=author:tester&sort=committer-date&order=desc&per_page=100"
BIG_KB = 400 * 1024 + 1      # GitHub size는 KB. 400MB를 넘음
LABELS = ["2단계 규칙", "LLM 보충 끔", "제안 기준", "본인 확인 안 됨"]
NAMES = {"L": "프로그래밍 활용", "O": "운영 배포", "B": "백엔드 개발", "E": "데이터 엔지니어", "D": "데이터베이스",
         "F": "프론트엔드 앱", "A": "AI 기술"}
STAGES = ["레포 찾기", "레포 받기", "색인", "규칙 적용", "계산"]
RATE_MESSAGE = r"^GitHub 호출 한도에 걸렸습니다\(\d+분 뒤 다시 시도\)$"

# 내 커밋 3개(noreply 이메일), 2026-01-03·06·09. 커밋 3(1단계)·바꾼 줄 2+4+2=8(1단계)·기간 7일(2단계) → Python LV (1+1+2)/3 = 1.3
PY_COMMITS = [
    (OWN_EMAIL, "add add", {"app.py": "def add(a, b):\n    return a + b\n"}),
    (OWN_EMAIL, "add sub", {"app.py": "def add(a, b):\n    return a + b\n\n\ndef sub(a, b):\n    return a - b\n"}),
    (OWN_EMAIL, "add util", {"util.py": "X = 1\nY = 2\n"}),
]
# Go LV도 1.3(커밋 3·줄 3+3+3=9·기간 7일). 제목은 PY_COMMITS와 겹치지 않게 둔다: 2단계는 같은 날짜·제목의 내 커밋을 레포가
# 달라도 사본으로 보고 한 번만 센다(cat_prog_deploy).
GO_COMMITS = [
    (OWN_EMAIL, "add go main", {"main.go": "package main\n\nfunc main() {}\n"}),
    (OWN_EMAIL, "print one", {"main.go": "package main\n\nfunc main() {\n\tprintln(1)\n}\n"}),
    (OWN_EMAIL, "add go util", {"util.go": "package main\n\nvar X = 1\n"}),
]


def lines10(**changed):
    """L1~L10 열 줄. changed = {"l2": "바꾼 줄", ...}"""
    rows = ["L%d" % n for n in range(1, 11)]
    for key, value in changed.items():
        rows[int(key[1:]) - 1] = value
    return "".join(row + "\n" for row in rows)


# 남이 q.py를 고친 뒤 고치면서 p.py로 옮겼고(내용이 달라 이름 바꿈을 트리만으로는 못 찾음), 내가 p.py를 고쳤다.
# 큰 레포(부분 받기)에서는 blame이 받지 않은 q.py의 첫 판을 읽다가 실패한다(test_s2_partial의 EDITED_RENAME).
EDITED_RENAME = [
    (OTHER_EMAIL, "add q", {"q.py": lines10()}),
    (OTHER_EMAIL, "edit q", {"q.py": lines10(l9="o9")}),
    (OTHER_EMAIL, "move q to p with edits", {"q.py": None, "p.py": lines10(l9="o9", l10="o10")}),
    (OWN_EMAIL, "mine p", {"p.py": lines10(l5="mine", l9="o9", l10="o10")}),
]

# run_step 시험용 자식 스크립트: 받은 환경 일부와 실행 방식(-I·-B)을 <LV_S2_HOME>/<스크립트 이름>.json에 쓴다(값은 시험용 가짜).
PROBE_ENV = r"""
import json, os, sys
keys = ("LV_GITHUB_TOKEN", "GH_TOKEN", "ANTHROPIC_API_KEY", "LV_GITHUB_API", "LV_S2_HOME", "GIT_NO_LAZY_FETCH")
out = {k: os.environ.get(k) for k in keys}
out["isolated"] = sys.flags.isolated
out["no_bytecode"] = sys.dont_write_bytecode
with open(os.path.join(os.environ["LV_S2_HOME"], os.path.basename(sys.argv[0]) + ".json"), "w") as f:
    json.dump(out, f)
"""

# 손주 프로세스(60초 잠)를 띄우고 그 번호를 남긴 뒤 자기도 잔다. 시간을 넘기면 묶음 전체가 끝나야 한다.
PROBE_SLOW = r"""
import os, subprocess, sys, time
child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
with open(os.path.join(os.environ["LV_S2_HOME"], "grandchild.pid"), "w") as f:
    f.write(str(child.pid))
time.sleep(60)
"""

def setUpModule():
    home = tempfile.mkdtemp(prefix="lv-analyze-s2lib-")
    unittest.addModuleCleanup(shutil.rmtree, home, True)   # 불러오기가 실패해도 지운다
    saved = os.environ.get("LV_S2_HOME")
    os.environ["LV_S2_HOME"] = home
    try:
        import s2lib  # noqa: F401  analyze가 쓰는 s2lib를 임시 작업 폴더로 먼저 불러 둔다(머리 설명)
    finally:
        if saved is None:
            os.environ.pop("LV_S2_HOME", None)
        else:
            os.environ["LV_S2_HOME"] = saved


def new_job(**extra):
    job = {"id": str(uuid.uuid4()), "namespace": "staging", "subjectId": "user-1", "login": "tester",
           "input": "https://github.com/tester", "status": "running", "createdAt": "2026-11-28T00:00:00Z"}
    job.update(extra)
    return job


def repo_obj(full, pushed, size=10, fork=False, private=False, branch="main"):
    """GitHub 레포 정보(목록·repos/{full} 응답에서 analyze가 읽는 칸)."""
    return {"full_name": full, "fork": fork, "private": private, "size": size, "default_branch": branch,
            "pushed_at": pushed, "owner": {"login": full.split("/")[0]}}


def commit_check(r):
    """본인 소유 레포에 내 커밋이 있는지 묻는 요청(기본 브랜치, 한 개만)."""
    return "/repos/%s/commits?author=tester&per_page=1&sha=%s" % (r["full_name"], r["default_branch"])


def index_commits(full, branch="main"):
    """색인(s2_index)이 내 커밋 SHA를 받는 요청."""
    return "/repos/%s/commits?author=tester&sha=%s&per_page=100" % (full, branch)


def pulls(full):
    return "/repos/%s/pulls?state=all&per_page=100" % full


def rate_limited():
    return 403, {"message": "API rate limit exceeded"}, {"X-RateLimit-Remaining": "0",
                                                         "X-RateLimit-Reset": str(int(time.time()) + 150)}


def read_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def is_level(v):
    return type(v) in (int, float) and 0 <= v <= 5


class FakeAPI:
    """127.0.0.1 빈 포트의 가짜 GitHub API. routes[요청 대상] = (상태, 본문, 헤더) 또는 그 셋을 돌려주는 함수. 없는 대상은 404."""

    def __init__(self):
        self.routes = {}
        self.seen = []
        self.release = threading.Event()   # block()으로 막은 응답을 푼다(닫을 때)
        owner = self

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                target = self.requestline.split()[1]  # 받은 그대로(퍼센트 인코딩 포함)
                owner.seen.append(target)
                route = owner.routes.get(target)
                if route is None:
                    status, body, headers = 404, {"message": "Not Found"}, {}
                else:
                    status, body, headers = route() if callable(route) else route
                raw = json.dumps(body).encode("utf-8")
                try:
                    self.send_response(status)
                    for k, v in headers.items():
                        self.send_header(k, v)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(raw)))
                    self.end_headers()
                    self.wfile.write(raw)
                except (BrokenPipeError, ConnectionResetError):
                    pass  # 묻던 쪽이 먼저 끝남(시간 상한 시험)

            def log_message(self, *args):
                pass

        self.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.base = "http://127.0.0.1:%d" % self.server.server_address[1]
        threading.Thread(target=self.server.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True).start()

    def block(self):
        """응답을 release가 풀릴 때까지(최대 60초) 미루는 경로."""
        def route():
            self.release.wait(60)
            return 200, [], {}
        return route

    def close(self):
        self.release.set()
        self.server.shutdown()
        self.server.server_close()


class LocalClone:
    """analyze의 clone_fn 자리: full_name에 맞는 합성 원격을 git clone --no-checkout으로 받는다. 없는 이름은 받지 못함(False).
    부른 차례를 (full_name, big, timeout)으로 남긴다. delay초 기다린 뒤 받는다(받는 데 걸린 시간 흉내)."""

    def __init__(self, srcs, env, delay=0):
        self.srcs, self.env, self.delay, self.calls = srcs, env, delay, []

    def __call__(self, full_name, dest, big, timeout):
        self.calls.append((full_name, big, timeout))
        time.sleep(self.delay)
        src = self.srcs.get(full_name)
        if src is None:
            return False
        git_run(["clone", "-q", "--no-checkout", src, dest], self.env)
        return True


class Runner:
    """진짜 analyze.clone()의 runner 자리: 받은 (argv, env, timeout)을 남기고, 주소(https://github.com/...)를 합성 원격(file://)으로
    바꿔 argv와 같은 --filter로 받는다(네트워크 없음). drop_after의 원격은 받은 뒤 지운다(뒤의 받기가 실패하게)."""

    def __init__(self, srcs, drop_after=()):
        self.srcs, self.drop_after, self.calls = srcs, set(drop_after), []

    def __call__(self, argv, env, timeout):
        self.calls.append((argv, env, timeout))
        url, dest = argv[-2], argv[-1]
        full = url[len("https://github.com/"):-len(".git")]
        flt = [a for a in argv if a.startswith("--filter=")]
        git_run(["clone", "-q", "--no-checkout", "--no-tags", *flt, "file://" + self.srcs[full], dest], env)
        if full in self.drop_after:
            shutil.rmtree(self.srcs[full])
        return 0, "", ""


class Progress:
    """progress 기록. hooks = {단계 이름: 함수}: 그 단계를 처음 받을 때 한 번 부른다(작업 폴더가 남아 있을 때 중간 파일을 본다)."""

    def __init__(self, hooks=None):
        self.calls, self.times, self.hooks = [], [], dict(hooks or {})

    def __call__(self, stage, done, total):
        self.calls.append((stage, done, total))
        self.times.append(time.monotonic())
        hook = self.hooks.pop(stage, None)
        if hook:
            hook()

    def stages(self):
        out = []
        for stage, _, _ in self.calls:
            if not out or out[-1] != stage:
                out.append(stage)
        return out

    def last(self, stage):
        return [(d, t) for s, d, t in self.calls if s == stage][-1]


class AnalyzeTest(unittest.TestCase):
    def setUp(self):
        saved = {k: os.environ.get(k) for k in GITHUB_ENV}
        for k in GITHUB_ENV:
            os.environ.pop(k, None)
        self.addCleanup(self._restore_env, saved)
        self.tmp = tempfile.mkdtemp(prefix="lv-analyze-")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.api = FakeAPI()
        self.addCleanup(self.api.close)
        os.environ["LV_GITHUB_API"] = self.api.base
        self.work = os.path.join(self.tmp, "work")
        githome = os.path.join(self.tmp, "githome")
        os.makedirs(githome)
        self.genv = base_env(HOME=githome, XDG_CONFIG_HOME=githome, GIT_CONFIG_NOSYSTEM="1",
                             GIT_AUTHOR_NAME="Tester", GIT_COMMITTER_NAME="Tester", GIT_COMMITTER_EMAIL="committer@example.com")
        before = code_tree()
        self.addCleanup(lambda: self.assertEqual(code_tree(), before, "s2 코드 폴더에 파일이 생기면 안 된다"))

    @staticmethod
    def _restore_env(saved):
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    # ---------------- 준비
    def make_src(self, name, commits, branches=(), partial_ok=False):
        """tmp/src/<name>에 합성 원격(main)을 만든다. commits = [(이메일, 제목, {경로: 내용 또는 None(지움)})],
        i번째 커밋은 2026-01-<3i>. branches: main 끝에서 만들 브랜치. partial_ok: 부분 clone과 blob id 받기를 허락한다."""
        src = os.path.join(self.tmp, "src", name)
        git_run(["init", "-q", src], self.genv)
        git_run(["-C", src, "symbolic-ref", "HEAD", "refs/heads/main"], self.genv)
        if partial_ok:
            git_run(["-C", src, "config", "uploadpack.allowFilter", "true"], self.genv)
            git_run(["-C", src, "config", "uploadpack.allowAnySHA1InWant", "true"], self.genv)
        for i, (email, subject, files) in enumerate(commits, 1):
            for path, text in files.items():
                full = os.path.join(src, path)
                if text is None:
                    os.remove(full)
                    continue
                os.makedirs(os.path.dirname(full), exist_ok=True)
                with open(full, "w", encoding="utf-8") as f:
                    f.write(text)
            when = "2026-01-%02dT10:00:00+09:00" % (3 * i)
            git_run(["-C", src, "add", "-A"], self.genv)
            git_run(["-C", src, "-c", "commit.gpgsign=false", "commit", "-q", "-m", subject],
                    dict(self.genv, GIT_AUTHOR_EMAIL=email, GIT_AUTHOR_DATE=when, GIT_COMMITTER_DATE=when))
        for b in branches:
            git_run(["-C", src, "branch", b], self.genv)
        return src

    def user(self, asked="tester", login="tester", kind="User"):
        self.api.routes["/users/" + asked] = (200, {"login": login, "type": kind}, {})

    def owned(self, repos, without_mine=()):
        """본인 소유 목록(한 쪽). without_mine 말고는 기본 브랜치에 내 커밋이 있다."""
        self.api.routes[OWNED] = (200, repos, {})
        for r in repos:
            if r["full_name"] not in without_mine:
                self.api.routes[commit_check(r)] = (200, [{"sha": "a" * 40}], {})

    def search(self, repos):
        """커밋 검색 결과(레포마다 커밋 하나)와 그 레포 정보(repos/{full})."""
        items = [{"sha": "b" * 40, "repository": {k: r[k] for k in ("full_name", "fork", "private", "owner")}} for r in repos]
        self.api.routes[SEARCH] = (200, {"total_count": len(items), "incomplete_results": False, "items": items}, {})
        for r in repos:
            self.api.routes["/repos/" + r["full_name"]] = (200, r, {})

    def account(self, names):
        """계정 tester가 본인 소유 레포 names(앞일수록 최근에 push)를 가짐. -> 레포 정보 목록"""
        repos = [repo_obj(n, "2026-02-%02dT00:00:00Z" % (28 - i)) for i, n in enumerate(names)]
        self.user()
        self.owned(repos)
        return repos

    def run_analyze(self, job, clone_fn, seconds=1200, progress=None):
        return analyze.analyze(job, self.work, time.time() + seconds, progress or Progress(), clone_fn=clone_fn)

    def home(self, job):
        return os.path.join(self.work, job["id"])

    # ---------------- 확인
    def check_profile(self, p, job, login="tester"):
        """CONTRACT.md의 profile 모양 그대로인지(웹 readProfile이 받는 모양). 칸 이름·종류·범위를 모두 본다."""
        self.assertEqual(set(p), {"schema", "method", "labels", "namespace", "subjectId", "login", "jobId",
                                  "analyzedAt", "repos", "categories"})
        self.assertEqual((p["schema"], p["method"], p["labels"]), ("lv-stat-profile/1", "lv-stat-s2-20261127", LABELS))
        self.assertEqual((p["namespace"], p["subjectId"], p["login"], p["jobId"]),
                         (job["namespace"], job["subjectId"], login, job["id"]))
        when = datetime.datetime.fromisoformat(p["analyzedAt"].replace("Z", "+00:00"))
        self.assertIsNotNone(when.tzinfo)
        repos = p["repos"]
        self.assertEqual(set(repos), {"found", "analyzed", "failed", "notes"})
        for k in ("found", "analyzed", "failed"):
            self.assertIs(type(repos[k]), int, k)
            self.assertGreaterEqual(repos[k], 0, k)
        self.assertIsInstance(repos["notes"], list)
        self.assertTrue(all(isinstance(n, str) for n in repos["notes"]), repos["notes"])
        cats = p["categories"]
        self.assertEqual(set(cats), set(NAMES))
        for code, c in cats.items():
            want = {"name", "lv", "unknown"} | ({"languages", "best"} if code == "L" else set()) | ({"note"} if code == "B" else set())
            self.assertEqual(set(c), want, code)
            self.assertEqual(c["name"], NAMES[code])
            self.assertTrue(c["lv"] is None or is_level(c["lv"]), (code, c["lv"]))
            self.assertIs(type(c["unknown"]), int, code)
            self.assertGreaterEqual(c["unknown"], 0, code)
        langs = cats["L"]["languages"]
        self.assertIsInstance(langs, dict)
        self.assertTrue(all(isinstance(k, str) and is_level(v) for k, v in langs.items()), langs)
        if langs:
            self.assertIn(cats["L"]["best"], langs)
        else:
            self.assertIsNone(cats["L"]["best"])
        self.assertIsInstance(cats["B"]["note"], str)
        json.dumps(p, allow_nan=False)  # JSON으로 쓸 수 있다

    # ---------------- 레포 찾기
    def test_discover_filters_and_orders(self):
        self.user(asked="Tester", login="tester")  # 정식 login은 응답의 login
        mine = repo_obj("tester/app", "2026-03-01T00:00:00Z")
        fork = repo_obj("tester/forked", "2026-03-05T00:00:00Z", fork=True)
        private = repo_obj("tester/secret", "2026-03-06T00:00:00Z", private=True)
        self.owned([mine, fork, private])
        other = repo_obj("someone/lib", "2026-03-03T00:00:00Z")
        other_fork = repo_obj("someone/forklib", "2026-03-04T00:00:00Z", fork=True)
        self.search([other, other_fork])
        notes = []
        login, repos = analyze.discover("Tester", notes)
        self.assertEqual(login, "tester")
        self.assertEqual([r["full_name"] for r in repos], ["someone/lib", "tester/app"])  # pushed_at 최근 순
        self.assertEqual({r["full_name"]: r["owned"] for r in repos}, {"someone/lib": False, "tester/app": True})
        self.assertEqual(notes, ["포크 레포 1개는 뺌"])
        # 포크·비공개는 내 커밋도 정보도 묻지 않는다. 남의 레포는 내 커밋을 묻지 않는다(검색이 찾은 커밋이 있음).
        for target in (commit_check(fork), commit_check(private), commit_check(other), "/repos/someone/forklib"):
            self.assertNotIn(target, self.api.seen)
        self.assertIn("/repos/someone/lib", self.api.seen)

    def test_discover_drops_owned_without_my_commits(self):
        self.user()
        has = repo_obj("tester/has", "2026-03-01T00:00:00Z")
        none = repo_obj("tester/none", "2026-03-02T00:00:00Z")
        empty = repo_obj("tester/empty", "2026-03-03T00:00:00Z", branch="dev#1")
        self.owned([has, none, empty], without_mine={"tester/none", "tester/empty"})
        self.api.routes[commit_check(none)] = (200, [], {})            # 그 브랜치에 내 커밋 없음
        self.api.routes[commit_check(empty).replace("dev#1", "dev%231")] = (409, {"message": "Git Repository is empty."}, {})
        _, repos = analyze.discover("tester", [])
        self.assertEqual([r["full_name"] for r in repos], ["tester/has"])
        self.assertIn(commit_check(empty).replace("dev#1", "dev%231"), self.api.seen)  # 브랜치 이름은 인코딩해 묻는다

    def test_discover_org_rejected(self):
        self.user(asked="acme", login="acme", kind="Organization")
        with self.assertRaises(analyze.UserError) as cm:
            analyze.discover("acme", [])
        self.assertEqual(str(cm.exception), "개인 GitHub 계정 주소를 넣어 주세요(조직 계정은 분석하지 않습니다).")
        self.assertEqual(self.api.seen, ["/users/acme"])

    def test_discover_missing_user(self):
        with self.assertRaises(analyze.UserError) as cm:
            analyze.discover("ghost", [])
        self.assertEqual(str(cm.exception), "GitHub 계정을 찾을 수 없습니다. 주소를 확인해 주세요.")
        self.assertEqual(self.api.seen, ["/users/ghost"])

    def test_discover_caps_40_with_note(self):
        self.user()
        start = datetime.datetime(2026, 1, 1)
        repos = [repo_obj("tester/r%02d" % i, (start + datetime.timedelta(hours=i)).strftime("%Y-%m-%dT%H:%M:%SZ"))
                 for i in range(45)]
        self.owned(repos)  # 목록 차례(오래된 것부터)와 관계없이 pushed_at으로 줄 세운다
        notes = []
        _, got = analyze.discover("tester", notes)
        newest = sorted(repos, key=lambda r: r["pushed_at"], reverse=True)
        self.assertEqual([r["full_name"] for r in got], [r["full_name"] for r in newest[:40]])
        self.assertEqual(notes, ["레포가 많아 최근 40개만 봄"])
        # 자른 레포는 내 커밋을 묻지 않는다(호출 한도를 아낌)
        self.assertEqual([t for t in self.api.seen if t.startswith("/repos/")], [commit_check(r) for r in newest[:40]])

    def test_discover_reads_three_pages(self):
        self.user()
        own = [repo_obj("tester/o%d" % n, "2026-01-%02dT00:00:00Z" % n) for n in range(1, 5)]
        others = [repo_obj("someone/s%d" % n, "2026-02-%02dT00:00:00Z" % n) for n in range(1, 5)]
        self.owned(own)      # 내 커밋 확인 경로
        self.search(others)  # 레포 정보 경로
        # 목록을 한 쪽에 하나씩 4쪽으로 나눈다(다음 쪽은 Link rel="next")
        for first, bodies in ((OWNED, [[r] for r in own]),
                              (SEARCH, [{"items": [{"sha": "b" * 40, "repository": r}]} for r in others])):
            for n, body in enumerate(bodies, 1):
                target = first if n == 1 else "%s&page=%d" % (first, n)
                self.api.routes[target] = (200, body, {"Link": '<%s%s&page=%d>; rel="next"' % (self.api.base, first, n + 1)})
        _, got = analyze.discover("tester", [])
        self.assertEqual(sorted(r["full_name"] for r in got), ["someone/s1", "someone/s2", "someone/s3",
                                                                "tester/o1", "tester/o2", "tester/o3"])
        self.assertNotIn(OWNED + "&page=4", self.api.seen)   # 본인 소유 목록은 3쪽까지
        self.assertNotIn(SEARCH + "&page=4", self.api.seen)  # 커밋 검색도 3쪽까지

    def test_discover_search_failure_is_note(self):
        # 커밋 검색은 best-effort: 한도(RateLimited)·그 밖의 GitHub 오류(2차 한도 403 + Retry-After 등)면 notes에 남기고 계속한다.
        secondary = (403, {"message": "You have exceeded a secondary rate limit."}, {"Retry-After": "60", "X-RateLimit-Remaining": "25"})
        cases = {"search rate limited": {SEARCH: rate_limited()},
                 "search secondary limit": {SEARCH: secondary},
                 "repo info secondary limit": {"/repos/someone/lib": secondary}}
        for name, broken in cases.items():
            with self.subTest(name):
                self.api.routes.clear()
                self.user()
                self.owned([repo_obj("tester/app", "2026-03-01T00:00:00Z")])
                self.search([repo_obj("someone/lib", "2026-03-03T00:00:00Z")])
                self.api.routes.update(broken)
                notes = []
                _, repos = analyze.discover("tester", notes)
                self.assertEqual([r["full_name"] for r in repos], ["tester/app"])
                self.assertEqual(notes, ["커밋 검색을 하지 못해 남의 레포를 다 찾지 못함"])

    # ---------------- 받기
    def test_clone_command_and_env(self):
        calls = []

        def run(argv, env, timeout):
            calls.append((argv, env, timeout))
            os.makedirs(os.path.join(argv[-1], ".git"))   # 받은 것처럼
            return 0, "", ""

        import s2lib
        for big, flt in ((False, "--filter=blob:limit=1m"), (True, "--filter=blob:none")):
            with self.subTest(big=big):
                calls.clear()
                dest = os.path.join(self.tmp, "c-%s" % big)
                self.assertTrue(analyze.clone("tester/demo", dest, big, 30, run=run))
                argv, env, timeout = calls[0]
                self.assertEqual(argv, ["git", "-c", "core.hooksPath=/dev/null", "-c", "protocol.file.allow=never", "clone",
                                        "--no-checkout", "--no-tags", "--quiet", flt, "https://github.com/tester/demo.git", dest])
                self.assertEqual(timeout, 30)
                self.assertEqual(env, s2lib.GENV)  # 토큰 없는 git 환경(test_s2_port가 GENV에 토큰이 없음을 본다)
                self.assertEqual([k for k in s2lib.SECRET_ENV if k in env], [])
                self.assertIs(os.path.exists(os.path.join(dest, ".git", "lv-partial")), big)

        def fail(argv, env, timeout):
            os.makedirs(os.path.join(argv[-1], ".git"))   # 받다 만 폴더
            return 128, "", "fatal: repository not found"

        def hang(argv, env, timeout):
            return None, "", ""                          # 시간을 넘김

        for name, runner in (("fail", fail), ("timeout", hang)):
            with self.subTest(name):
                dest = os.path.join(self.tmp, "c-" + name)
                with self.assertLogs("analyze", "WARNING"):
                    self.assertFalse(analyze.clone("tester/demo", dest, True, 30, run=runner))
                self.assertFalse(os.path.exists(dest))   # 받다 만 폴더는 지운다(표시도 없음)

    # ---------------- 단계 실행
    def test_run_step_passes_token_only_to_index(self):
        scripts = os.path.join(self.tmp, "scripts")
        os.makedirs(scripts)
        for name in ("probe.py", "s2_index.py"):
            with open(os.path.join(scripts, name), "w", encoding="utf-8") as f:
                f.write(PROBE_ENV)
        home = os.path.join(self.tmp, "home")
        os.makedirs(home)
        os.environ["LV_GITHUB_TOKEN"] = "test-token"     # 시험용 가짜 값
        for name in ("probe.py", "s2_index.py"):
            ok, _ = analyze.run_step(os.path.join(scripts, name), os.path.relpath(home), 30)
            self.assertTrue(ok, name)
        probe = read_json(os.path.join(home, "probe.py.json"))
        index = read_json(os.path.join(home, "s2_index.py.json"))
        common = {"GH_TOKEN": None, "ANTHROPIC_API_KEY": None, "LV_S2_HOME": home, "GIT_NO_LAZY_FETCH": "1",
                  "isolated": 1, "no_bytecode": True}  # 작업 폴더는 절대 경로, -I -B로 띄움
        self.assertEqual(probe, dict(common, LV_GITHUB_TOKEN=None, LV_GITHUB_API=None))
        self.assertEqual(index, dict(common, LV_GITHUB_TOKEN="test-token", LV_GITHUB_API=self.api.base))

    def test_run_step_timeout_kills_group(self):
        script = os.path.join(self.tmp, "slow.py")
        with open(script, "w", encoding="utf-8") as f:
            f.write(PROBE_SLOW)
        home = os.path.join(self.tmp, "home")
        os.makedirs(home)
        t = time.time()
        self.assertEqual(analyze.run_step(script, home, 2), (False, analyze.TIMED_OUT))
        self.assertLess(time.time() - t, 20)
        with open(os.path.join(home, "grandchild.pid"), encoding="utf-8") as f:
            pid = int(f.read())
        end = time.time() + 10
        while time.time() < end:
            try:
                os.kill(pid, 0)
            except ProcessLookupError:
                break
            time.sleep(0.1)
        else:
            os.kill(pid, 9)
            self.fail("시간을 넘기면 손주 프로세스까지 끝내야 한다(os.killpg)")

    # ---------------- 분석
    def test_analyze_end_to_end_synthetic(self):
        self.account(["tester/demo"])
        clone = LocalClone({"tester/demo": self.make_src("demo", PY_COMMITS)}, self.genv)
        job = new_job()
        prog = Progress()
        p = self.run_analyze(job, clone, progress=prog)
        self.check_profile(p, job)
        self.assertEqual(p["repos"], {"found": 1, "analyzed": 1, "failed": 0, "notes": []})
        self.assertEqual(p["categories"]["L"], {"name": "프로그래밍 활용", "lv": 1.3, "unknown": 0,
                                                "languages": {"Python": 1.3}, "best": "Python"})
        self.assertEqual(prog.stages(), STAGES)
        self.assertEqual([prog.last(s) for s in STAGES], [(None, None), (1, 1), (1, 1), (7, 7), (None, None)])
        self.assertEqual([(f, b) for f, b, _ in clone.calls], [("tester/demo", False)])
        self.assertFalse(os.path.exists(self.home(job)))  # 작업 폴더를 지웠다

    def test_two_jobs_in_one_process_keep_their_own_folders(self):
        # s2 모듈은 불러올 때 작업 폴더를 정한다. 같은 프로세스에서 두 요청을 차례로 분석해도 결과가 섞이지 않아야 한다.
        self.account(["tester/py"])
        srcs = {"tester/py": self.make_src("py", PY_COMMITS), "tester/go": self.make_src("go", GO_COMMITS)}
        first, second = new_job(), new_job()
        p1 = self.run_analyze(first, LocalClone(srcs, self.genv))
        self.owned([repo_obj("tester/go", "2026-03-01T00:00:00Z")])
        p2 = self.run_analyze(second, LocalClone(srcs, self.genv))
        self.assertEqual(p1["categories"]["L"]["languages"], {"Python": 1.3})
        self.assertEqual(p2["categories"]["L"]["languages"], {"Go": 1.3})
        self.assertEqual((p1["jobId"], p2["jobId"]), (first["id"], second["id"]))
        self.assertEqual(os.listdir(self.work), [])

    def test_job_id_must_be_uuid(self):
        # 요청 id는 작업 폴더 이름이 되고 끝나면 그 폴더를 지운다. uuid가 아니면('..' 등) 아무것도 만들거나 지우지 않고 멈춘다.
        os.makedirs(self.work)
        keep = os.path.join(self.tmp, "keep.txt")
        with open(keep, "w", encoding="utf-8") as f:
            f.write("x")
        clone, prog = LocalClone({}, self.genv), Progress()
        for bad in ("..", "", "../x", "0b8f3c1e-2d4a-4f6b-9c7d-1e2f3a4b5c6d/.."):
            with self.subTest(bad=bad):
                with self.assertRaises(ValueError):
                    analyze.analyze(new_job(id=bad), self.work, time.time() + 1200, prog, clone_fn=clone)
        self.assertTrue(os.path.exists(keep))
        self.assertEqual(os.listdir(self.work), [])
        self.assertEqual((clone.calls, prog.calls, self.api.seen), ([], [], []))

    def test_no_repos_user_error(self):
        self.user()
        self.owned([repo_obj("tester/none", "2026-03-01T00:00:00Z")], without_mine={"tester/none"})
        clone = LocalClone({}, self.genv)
        job = new_job()
        with self.assertRaises(analyze.UserError) as cm:
            self.run_analyze(job, clone)
        self.assertEqual(str(cm.exception), "공개 레포에서 이 계정의 커밋을 찾지 못했습니다.")
        self.assertEqual(clone.calls, [])
        self.assertFalse(os.path.exists(self.home(job)))

    def test_deadline_stops_cloning_with_note(self):
        self.account(["tester/demo"])
        clone = LocalClone({"tester/demo": self.make_src("demo", PY_COMMITS)}, self.genv)
        job = new_job()
        with self.assertRaises(analyze.UserError) as cm:
            self.run_analyze(job, clone, seconds=-1)   # 마감이 이미 지남 → 받지 않음 → 받은 레포 0개
        self.assertEqual(str(cm.exception), "레포를 받지 못했습니다. 잠시 뒤 다시 시도해 주세요.")
        self.assertEqual(clone.calls, [])
        self.assertFalse(os.path.exists(self.home(job)))

    def test_time_limit_keeps_cloned_repos(self):
        # 받는 중에 받기 몫이 60초 아래로 남으면 더 받지 않고, 받은 레포만으로 끝까지 분석한다(검토 1).
        self.account(["tester/new", "tester/old"])
        srcs = {"tester/new": self.make_src("new", PY_COMMITS), "tester/old": self.make_src("old", GO_COMMITS)}
        clone = LocalClone(srcs, self.genv, delay=5)
        job = new_job()
        seconds = (analyze.CLONE_MIN_S + 4) / analyze.CLONE_SHARE   # 처음엔 받기 몫이 64초 남고, 5초 뒤 59초
        p = self.run_analyze(job, clone, seconds=seconds)
        self.check_profile(p, job)
        self.assertEqual([f for f, _, _ in clone.calls], ["tester/new"])
        self.assertGreaterEqual(clone.calls[0][2], analyze.CLONE_MIN_S)  # 받기 몫 안에서만 받는다
        self.assertEqual(p["repos"], {"found": 2, "analyzed": 1, "failed": 0, "notes": ["시간 상한에 닿아 레포 1개는 받지 못함"]})
        self.assertEqual(p["categories"]["L"]["languages"], {"Python": 1.3})

    def test_clone_failure_counted_as_failed(self):
        self.account(["tester/ok", "tester/gone"])
        clone = LocalClone({"tester/ok": self.make_src("ok", PY_COMMITS)}, self.genv)   # tester/gone은 받지 못함
        job = new_job()
        p = self.run_analyze(job, clone)
        self.check_profile(p, job)
        self.assertEqual(p["repos"], {"found": 2, "analyzed": 1, "failed": 1, "notes": ["레포 1개는 받지 못함"]})

    def test_index_rate_limit_fails(self):
        self.account(["tester/demo"])
        self.api.routes[index_commits("tester/demo")] = rate_limited()
        clone = LocalClone({"tester/demo": self.make_src("demo", PY_COMMITS)}, self.genv)
        job = new_job()
        with self.assertRaises(analyze.UserError) as cm:
            self.run_analyze(job, clone)
        self.assertRegex(str(cm.exception), RATE_MESSAGE)
        self.assertIn(index_commits("tester/demo"), self.api.seen)
        self.assertFalse(os.path.exists(self.home(job)))

    def test_index_error_counted_as_failed(self):
        self.account(["tester/ok", "tester/bad"])
        self.api.routes[index_commits("tester/bad")] = (403, {"message": "Forbidden"}, {})   # 한도가 아닌 GitHub 오류
        srcs = {"tester/ok": self.make_src("ok", PY_COMMITS), "tester/bad": self.make_src("bad", GO_COMMITS)}
        job = new_job()
        p = self.run_analyze(job, LocalClone(srcs, self.genv))
        self.check_profile(p, job)
        self.assertEqual(p["repos"], {"found": 2, "analyzed": 1, "failed": 1, "notes": ["레포 1개는 색인하지 못함"]})
        self.assertEqual(p["categories"]["L"]["languages"], {"Python": 1.3})

    def test_nothing_indexed_user_error(self):
        # 색인한 레포가 하나도 없으면 LV를 0으로 보이지 않고 실패로 끝낸다.
        self.account(["tester/bad"])
        self.api.routes[index_commits("tester/bad")] = (403, {"message": "Forbidden"}, {})
        job = new_job()
        with self.assertRaises(analyze.UserError) as cm:
            self.run_analyze(job, LocalClone({"tester/bad": self.make_src("bad", PY_COMMITS)}, self.genv))
        self.assertEqual(str(cm.exception), "레포를 색인하지 못했습니다. 잠시 뒤 다시 시도해 주세요.")
        self.assertFalse(os.path.exists(self.home(job)))

    def test_prs_only_owned_small(self):
        self.user()
        small = repo_obj("tester/small", "2026-03-03T00:00:00Z")
        big = repo_obj("tester/big", "2026-03-02T00:00:00Z", size=BIG_KB)
        other = repo_obj("someone/lib", "2026-03-01T00:00:00Z")
        self.owned([small, big])
        self.search([other])
        srcs = {"tester/small": self.make_src("small", PY_COMMITS, branches=["develop"]),
                "tester/big": self.make_src("big", GO_COMMITS), "someone/lib": self.make_src("lib", GO_COMMITS)}
        job = new_job()
        seen = {}
        prog = Progress({"색인": lambda: seen.update(people=read_json(os.path.join(self.home(job), "people.json")))})
        self.run_analyze(job, LocalClone(srcs, self.genv), progress=prog)
        (person,) = seen["people"]
        self.assertEqual((person["pid"], person["login"]), ("P01", "tester"))
        repos = {r["full_name"]: r for r in person["repos"]}
        self.assertEqual({n: r["prs"] for n, r in repos.items()}, {"tester/small": True, "tester/big": False, "someone/lib": False})
        for r in person["repos"]:
            self.assertEqual(set(r), {"key", "full_name", "dir", "default_branch", "has_develop", "has_dev", "prs", "evidence"})
            self.assertRegex(r["key"], r"^[A-Za-z0-9._-]+$")  # 파일 이름으로 쓰는 키
            self.assertEqual(r["dir"], os.path.join(self.home(job), "repos", r["key"]))
            self.assertIs(r["evidence"], False)
        self.assertEqual(len({r["key"] for r in person["repos"]}), 3)
        self.assertEqual((repos["tester/small"]["has_develop"], repos["tester/small"]["has_dev"]), (True, False))
        self.assertEqual((repos["tester/big"]["has_develop"], repos["tester/big"]["has_dev"]), (False, False))
        # PR 목록은 본인 소유·400MB 이하 레포만 받는다
        self.assertEqual([t for t in self.api.seen if "/pulls?" in t], [pulls("tester/small")])

    def test_big_repo_uses_partial(self):
        self.user()
        huge = repo_obj("tester/huge", "2026-03-02T00:00:00Z", size=BIG_KB)
        edge = repo_obj("tester/edge", "2026-03-01T00:00:00Z", size=400 * 1024)   # 딱 400MB는 큰 레포가 아님
        self.owned([huge, edge])
        runner = Runner({"tester/huge": self.make_src("huge", PY_COMMITS, partial_ok=True),
                         "tester/edge": self.make_src("edge", GO_COMMITS, partial_ok=True)})
        job = new_job()
        marks = {}

        def look():
            for r in read_json(os.path.join(self.home(job), "people.json"))[0]["repos"]:
                marks[r["full_name"]] = os.path.exists(os.path.join(r["dir"], ".git", "lv-partial"))

        p = self.run_analyze(job, lambda f, d, b, t: analyze.clone(f, d, b, t, run=runner), progress=Progress({"색인": look}))
        self.assertEqual(marks, {"tester/huge": True, "tester/edge": False})
        filters = {argv[-2]: [a for a in argv if a.startswith("--filter")] for argv, _, _ in runner.calls}
        self.assertEqual(filters, {"https://github.com/tester/huge.git": ["--filter=blob:none"],
                                   "https://github.com/tester/edge.git": ["--filter=blob:limit=1m"]})
        self.check_profile(p, job)
        self.assertEqual(p["repos"], {"found": 2, "analyzed": 2, "failed": 0, "notes": []})   # 큰 레포도 내 경로는 다 받음
        self.assertEqual(p["categories"]["L"]["languages"], {"Python": 1.3, "Go": 1.3})

    def test_big_repo_partial_notes(self):
        # 표시한 레포의 partial: 파일을 받지 못함(fetched 거짓) → '큰 레포 n개는 파일을 받지 못함',
        # blame이 실패한 파일(blame_failed.count) → '큰 레포에서 내 줄을 세지 못한 파일 n개'(레포마다 더함).
        self.user()
        self.owned([repo_obj("tester/renamed", "2026-03-02T00:00:00Z", size=BIG_KB),
                    repo_obj("tester/lost", "2026-03-01T00:00:00Z", size=BIG_KB)])
        runner = Runner({"tester/renamed": self.make_src("renamed", EDITED_RENAME, partial_ok=True),
                         "tester/lost": self.make_src("lost", PY_COMMITS, partial_ok=True)},
                        drop_after={"tester/lost"})   # 받은 뒤 원격이 없어짐 → 내 경로의 파일을 받지 못함
        job = new_job()
        p = self.run_analyze(job, lambda f, d, b, t: analyze.clone(f, d, b, t, run=runner))
        self.check_profile(p, job)
        self.assertEqual(p["repos"], {"found": 2, "analyzed": 2, "failed": 0,
                                      "notes": ["큰 레포 1개는 파일을 받지 못함", "큰 레포에서 내 줄을 세지 못한 파일 1개"]})

    def test_index_timeout_keeps_indexed(self):
        self.account(["tester/fast", "tester/slow"])
        self.api.routes[index_commits("tester/slow")] = self.api.block()   # 두 번째 레포 색인이 끝나지 않음
        srcs = {"tester/fast": self.make_src("fast", PY_COMMITS), "tester/slow": self.make_src("slow", GO_COMMITS)}
        job = new_job()
        seen = {}
        prog = Progress({"규칙 적용": lambda: seen.update(person=read_json(os.path.join(self.home(job), "index", "P01", "person.json")))})
        t = time.time()
        with mock.patch.object(analyze, "INDEX_SHARE", 0.04), self.assertLogs("analyze", "WARNING"):
            p = self.run_analyze(job, LocalClone(srcs, self.genv), seconds=200, progress=prog)   # 색인은 8초 안에
        self.assertLess(time.time() - t, 40)   # 막힌 색인을 기다리지 않았다(프로세스 묶음을 끝냄)
        # 색인을 기다리는 동안에도 진행(레포 1/2)을 알렸다: 색인이 끝나고 규칙 적용을 시작하기 한참 전이다
        first = {}
        for call, at in zip(prog.calls, prog.times):
            first.setdefault(call, at)
        self.assertLess(first[("색인", 1, 2)], first[("규칙 적용", 0, 7)] - 3)
        self.check_profile(p, job)
        self.assertEqual(p["repos"], {"found": 2, "analyzed": 1, "failed": 0, "notes": ["시간 상한에 닿아 레포 1개는 색인하지 못함"]})
        self.assertEqual(p["categories"]["L"]["languages"], {"Python": 1.3})
        person = seen["person"]
        self.assertEqual(set(person), {"pid", "login", "role", "level", "repo_keys", "index_s"})   # s2_index와 같은 칸
        self.assertEqual((person["pid"], person["login"], person["role"], person["level"]), ("P01", "tester", None, None))
        self.assertEqual(len(person["repo_keys"]), 1)
        self.assertIn("fast", person["repo_keys"][0])

    def test_index_timeout_ignores_half_written_file(self):
        # 색인을 끝낸 순간에 쓰던 레포 파일은 반쯤 쓴 채 남을 수 있다. 그 레포는 색인하지 못한 것으로 세고 person.json에 넣지 않는다
        # (추출기가 읽다 멈추지 않게).
        self.account(["tester/fast", "tester/slow"])
        srcs = {"tester/fast": self.make_src("fast", PY_COMMITS), "tester/slow": self.make_src("slow", GO_COMMITS)}
        job = new_job()
        real = analyze.run_step

        def step(script, home, timeout, poll=None):
            ok, msg = real(script, home, timeout, poll)
            if script != "s2_index.py":
                return ok, msg
            idx = os.path.join(home, "index", "P01")
            os.remove(os.path.join(idx, "person.json"))
            (slow,) = [n for n in os.listdir(idx) if "slow" in n]
            with open(os.path.join(idx, slow), "r+", encoding="utf-8") as f:
                f.truncate(len(f.read()) // 2)
            return False, analyze.TIMED_OUT

        with mock.patch.object(analyze, "run_step", step), self.assertLogs("analyze", "WARNING"):
            p = self.run_analyze(job, LocalClone(srcs, self.genv))
        self.check_profile(p, job)
        self.assertEqual(p["repos"], {"found": 2, "analyzed": 1, "failed": 0, "notes": ["시간 상한에 닿아 레포 1개는 색인하지 못함"]})
        self.assertEqual(p["categories"]["L"]["languages"], {"Python": 1.3})

    def test_rule_failures_are_notes(self):
        # 추출기가 실패하면 notes에 이름을 남기고 계속한다. 마무리(s2_final)가 모듈을 마무리하지 못하면(finalize_error) 그 카테고리를,
        # 마무리 단계 자체가 실패하면 그 사실을 notes에 남긴다. 어느 경우든 프로필은 CONTRACT 모양이다(모른 카테고리는 null).
        real = analyze.run_step

        def broken(script, home, timeout, poll=None):
            if script == "cat_de.py":
                return False, "boom"
            ok, msg = real(script, home, timeout, poll)
            if script == "cat_db.py":   # 모듈의 finalize가 읽지 못하는 vars(마무리 실패 → finalize_error)
                with open(os.path.join(home, "out", "P01", "vars-db.json"), "w", encoding="utf-8") as f:
                    json.dump({"s5_targets": []}, f)
            return ok, msg

        def no_final(script, home, timeout, poll=None):
            return (False, "boom") if script == "s2_final.py" else real(script, home, timeout, poll)

        def half_final(script, home, timeout, poll=None):
            ok, msg = real(script, home, timeout, poll)
            if script != "s2_final.py":
                return ok, msg
            path = os.path.join(home, "out", "P01", "final-fe.json")   # 마무리가 시간을 넘겨 끝난 순간에 쓰던 파일
            with open(path, "r+", encoding="utf-8") as f:
                f.truncate(len(f.read()) // 2)
            return False, analyze.TIMED_OUT

        for name, step, notes, nulls in (
                ("extractor and module", broken, ["규칙 적용 실패: cat_de", "규칙 마무리 실패: db"], {"E", "D"}),
                ("final step", no_final, ["규칙 마무리 실패"], set(NAMES)),
                ("half-written final", half_final, ["규칙 마무리 실패", "규칙 마무리 실패: fe"], {"F"})):
            with self.subTest(name):
                self.api.routes.clear()
                self.account(["tester/demo"])
                job = new_job()
                clone = LocalClone({"tester/demo": self.make_src("demo-" + name.replace(" ", "-"), PY_COMMITS)}, self.genv)
                with mock.patch.object(analyze, "run_step", step), self.assertLogs("analyze", "WARNING"):
                    p = self.run_analyze(job, clone)
                self.check_profile(p, job)
                self.assertEqual(p["repos"], {"found": 1, "analyzed": 1, "failed": 0, "notes": notes})
                self.assertEqual({c for c, v in p["categories"].items() if v["lv"] is None}, nulls)
                self.assertFalse(os.path.exists(self.home(job)))


if __name__ == "__main__":
    unittest.main()
