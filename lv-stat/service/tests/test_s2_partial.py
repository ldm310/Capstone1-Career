"""큰 레포 부분 받기(.git/lv-partial을 표시한 레포의 s2_index) 시험.

- 합성 원격(uploadpack.allowFilter·uploadpack.allowAnySHA1InWant)을 file://로 --filter=blob:none --no-checkout
  clone하고 .git/lv-partial을 만든다. 시험 준비에서 clone이 정말 부분 clone인지(원격의 blob이 하나도 없는지) 먼저 본다.
- 내 커밋은 noreply 이메일이고 LV_GITHUB_OFFLINE=1이다(GitHub API는 빈 목록). gh는 불리면 실패한다(test_s2_port 도구).
- blob이 있는지는 GIT_NO_LAZY_FETCH=1 git cat-file -e로 본다(확인하는 쪽이 받으러 가지 않게). 기대 blob id는 내용에서 직접 셈한다.
- git 한 단계의 인자·표준 입력 확인과 실패는 PATH 맨 앞의 시험용 git(spy_git)으로 한다. 정한 인자가 있는 호출만 기록하고
  (실패시키거나 진짜 git에 넘김), 나머지는 진짜 git이다.
- GIT_NO_LAZY_FETCH(git 2.45부터)를 모르는 옛 git은 PATH 맨 앞의 시험용 git(old_git)이 그 값을 지우고 진짜 git을 불러 흉내 낸다.
- 원격·clone은 임시 폴더에만 만든다. 코드 폴더(s2)에는 아무것도 생기지 않아야 한다(부를 때마다 확인). 네트워크는 쓰지 않는다.
"""
import hashlib
import json
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
import unittest

from test_s2_port import CODE, OTHER_EMAIL, OWN_EMAIL, base_env, code_tree, fake_gh, git_run

MV = "mv"          # 바꿈 값 (MV, 옛 경로): 내용 그대로 옮긴다(git mv)
LINK = "gitlink"   # 바꿈 값 (LINK, 커밋 id): 하위 모듈 자리(gitlink, 모드 160000)

# 원격: 내가 두 번 고친 a.py(남이 만듦), 남만 고친 b.py(판 3개)·c.txt, 남이 만든 x.py를 남이 y.py로 옮긴 뒤 내가 고친 경로.
BASE = [
    (OTHER_EMAIL, "add a b c", {"a.py": "a = 1\nb = 2\n", "b.py": "b = 1\n", "c.txt": "note 1\n"}),
    (OTHER_EMAIL, "add x", {"x.py": "def f():\n    return 1\n"}),
    (OTHER_EMAIL, "edit b", {"b.py": "b = 2\n"}),
    (OWN_EMAIL, "mine 1", {"a.py": "a = 1\nb = 2\nc = 3\n"}),
    (OTHER_EMAIL, "edit x", {"x.py": "def f():\n    return 1\n# x\n"}),
    (OTHER_EMAIL, "rename x to y", {"y.py": (MV, "x.py")}),
    (OTHER_EMAIL, "edit b c", {"b.py": "b = 3\n", "c.txt": "note 2\n"}),
    (OWN_EMAIL, "mine 2", {"a.py": "a = 10\nb = 2\nc = 3\nd = 4\n"}),
    (OWN_EMAIL, "mine 3", {"y.py": "def f():\n    return 2\n# x\n"}),
]
BASE_LOG = [s for _, s, _ in reversed(BASE)]  # git log 차례(새것부터)
MINE = ["mine 1", "mine 2", "mine 3"]


def numstat(path, add, dele):
    return {"path": path, "add": add, "dele": dele, "binary": False}


def blob_id(text):
    """git blob id(SHA-1)를 내용에서 직접 셈한다."""
    data = text.encode("utf-8")
    return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()


def remote_env(root):
    home = os.path.join(root, "githome")
    os.makedirs(home, exist_ok=True)
    return base_env(HOME=home, XDG_CONFIG_HOME=home, GIT_CONFIG_NOSYSTEM="1",
                    GIT_AUTHOR_NAME="Tester", GIT_COMMITTER_NAME="Tester",
                    GIT_COMMITTER_EMAIL="committer@example.com")


def commit_all(src, env, commits, versions, start):
    """commits = [(작성자 이메일, 제목, 바꿈)]을 지금 브랜치에 차례로 커밋한다. i번째 커밋 날짜는 2026-01-(start+i).
    바꿈 = {경로: 내용 | None(지움) | (MV, 옛 경로) | (LINK, 커밋 id)}. versions[경로]에 판마다 내용을 더한다."""
    for i, (email, subject, changes) in enumerate(commits, start):
        for path, value in changes.items():
            if value is None:
                git_run(["-C", src, "--literal-pathspecs", "rm", "-q", "--", path], env)
            elif isinstance(value, tuple) and value[0] == MV:
                git_run(["-C", src, "mv", value[1], path], env)
                versions.setdefault(path, []).append(versions[value[1]][-1])
            elif isinstance(value, tuple) and value[0] == LINK:
                git_run(["-C", src, "update-index", "--add", "--cacheinfo", "160000,%s,%s" % (value[1], path)], env)
            else:
                full = os.path.join(src, path)
                os.makedirs(os.path.dirname(full), exist_ok=True)
                with open(full, "w", encoding="utf-8") as f:
                    f.write(value)
                git_run(["-C", src, "--literal-pathspecs", "add", "--", path], env)  # 이름의 \ 등을 경로 패턴으로 읽지 않게
                versions.setdefault(path, []).append(value)
        when = "2026-01-%02dT10:00:00+09:00" % i
        git_run(["-C", src, "-c", "commit.gpgsign=false", "commit", "-q", "-m", subject],
                dict(env, GIT_AUTHOR_EMAIL=email, GIT_AUTHOR_DATE=when, GIT_COMMITTER_DATE=when))


def make_remote(root, commits):
    """root/src에 부분 clone을 받을 수 있는 원격(main)을 만든다. -> (src, git 환경, {경로: [판마다 내용]})"""
    env = remote_env(root)
    src = os.path.join(root, "src")
    git_run(["init", "-q", "-b", "main", src], env)
    git_run(["-C", src, "config", "uploadpack.allowFilter", "true"], env)
    git_run(["-C", src, "config", "uploadpack.allowAnySHA1InWant", "true"], env)
    versions = {}
    commit_all(src, env, commits, versions, 1)
    return src, env, versions


def lines10(**changed):
    """L1~L10 열 줄. changed = {"l2": "바꾼 줄", ...}(l<번호>의 줄을 바꾼다)"""
    rows = ["L%d" % n for n in range(1, 11)]
    for key, value in changed.items():
        rows[int(key[1:]) - 1] = value
    return "".join(row + "\n" for row in rows)


def merge_in(src, env, branch, subject, day):
    """지금 브랜치에 branch를 --no-ff로 합친다(남이 합침, 충돌 없는 자동 합치기). 날짜는 2026-01-<day>."""
    when = "2026-01-%02dT10:00:00+09:00" % day
    git_run(["-C", src, "-c", "commit.gpgsign=false", "merge", "-q", "--no-ff", "-m", subject, branch],
            dict(env, GIT_AUTHOR_EMAIL=OTHER_EMAIL, GIT_AUTHOR_DATE=when, GIT_COMMITTER_DATE=when))


def spy_git(root, flag, fail=False):
    """PATH 맨 앞에 둘 git. 인자에 flag가 있는 호출은 인자(한 줄에 하나)와 표준 입력을 root/spy-argv·root/spy-stdin에 남긴 뒤,
    fail이면 아무것도 하지 않고 실패하고(rc 128) 아니면 진짜 git이 같은 입력으로 한다. 나머지 호출은 진짜 git 그대로다.
    -> (bin 폴더, 인자 파일, 표준 입력 파일)"""
    q = shlex.quote
    real = shutil.which("git")
    bin_dir = os.path.join(root, "gitbin")
    os.makedirs(bin_dir)
    argv_file, stdin_file = os.path.join(root, "spy-argv"), os.path.join(root, "spy-stdin")
    then = 'echo "test: injected failure" >&2; exit 128' if fail else 'exec %s "$@" < %s' % (q(real), q(stdin_file))
    path = os.path.join(bin_dir, "git")
    with open(path, "w", encoding="utf-8") as f:
        f.write('#!/bin/sh\nfor a in "$@"; do\n  if [ "$a" = %s ]; then\n    printf "%%s\\n" "$@" > %s\n    cat > %s\n    %s\n  fi\n'
                'done\nexec %s "$@"\n' % (q(flag), q(argv_file), q(stdin_file), then, q(real)))
    os.chmod(path, 0o755)
    return bin_dir, argv_file, stdin_file


def old_git(root):
    """PATH 맨 앞에 둘 git: GIT_NO_LAZY_FETCH(git 2.45부터)를 모르는 옛 git처럼 그 값을 지우고 진짜 git을 부른다.
    lazy fetch로 띄우는 fetch도 이 환경을 물려받는다. -> (bin 폴더, 그 git 경로)"""
    bin_dir = os.path.join(root, "oldgit")
    os.makedirs(bin_dir)
    path = os.path.join(bin_dir, "git")
    with open(path, "w", encoding="utf-8") as f:
        f.write('#!/bin/sh\nunset GIT_NO_LAZY_FETCH\nexec %s "$@"\n' % shlex.quote(shutil.which("git")))
    os.chmod(path, 0o755)
    return bin_dir, path


def trace_names(trace):
    """GIT_TRACE2_EVENT 파일 -> git 실행마다 cmd_name(차례대로)"""
    with open(trace, encoding="utf-8") as f:
        return [ev["name"] for ev in map(json.loads, f) if ev.get("event") == "cmd_name"]


PROMISOR_CONFIG = r"^(remote\..*\.(promisor|partialclonefilter)|extensions\.partialclone)$"


def promisor_config(clone, env):
    """clone에서 빠진 내용을 받으러 갈 곳(부분 clone 설정) 줄. 없으면 []."""
    p = subprocess.run(["git", "-C", clone, "config", "--get-regexp", PROMISOR_CONFIG], env=env, capture_output=True, timeout=60)
    return p.stdout.decode("utf-8", "replace").splitlines()


def commit_to_index(src, env, path, text, email, subject, day, versions):
    """파일 시스템에 만들 수 없는 이름(UTF-8이 아닌 바이트 path, APFS는 거부함)을 색인에 바로 넣어 커밋한다(작업 폴더에는 없음).
    날짜는 2026-01-<day>. versions[path]에 내용을 더한다."""
    p = subprocess.run(["git", "-C", src, "hash-object", "-w", "--stdin"], input=text.encode("utf-8"), env=env,
                       capture_output=True, timeout=60, check=True)
    subprocess.run(["git", "-C", src, "update-index", "--add", "--cacheinfo", b"100644," + p.stdout.strip() + b"," + path],
                   env=env, capture_output=True, timeout=60, check=True)
    when = "2026-01-%02dT10:00:00+09:00" % day
    git_run(["-C", src, "-c", "commit.gpgsign=false", "commit", "-q", "-m", subject],
            dict(env, GIT_AUTHOR_EMAIL=email, GIT_AUTHOR_DATE=when, GIT_COMMITTER_DATE=when))
    versions.setdefault(path, []).append(text)


def merge_by_hand(src, env, branch, subject, day, resolved):
    """지금 브랜치에 branch를 --no-ff로 합치다 충돌이 나면 resolved({경로: 내용})로 손으로 풀어 남이 커밋한다.
    날짜는 2026-01-<day>. -> 합치기 rc(충돌이면 1)"""
    when = "2026-01-%02dT10:00:00+09:00" % day
    env = dict(env, GIT_AUTHOR_EMAIL=OTHER_EMAIL, GIT_AUTHOR_DATE=when, GIT_COMMITTER_DATE=when)
    p = subprocess.run(["git", "-C", src, "merge", "-q", "--no-ff", "--no-commit", branch], env=env, capture_output=True, timeout=60)
    for path, text in resolved.items():
        with open(os.path.join(src, path), "w", encoding="utf-8") as f:
            f.write(text)
        git_run(["-C", src, "--literal-pathspecs", "add", "--", path], env)
    git_run(["-C", src, "-c", "commit.gpgsign=false", "commit", "-q", "-m", subject], env)
    return p.returncode


# 남이 q.py를 고치면서 p.py로 옮기고(내용이 같지 않은 이름 바꿈) 그 뒤 내가 p.py의 5번 줄을 고쳤다. 옮기기 전 q.py는 판이 둘이다.
# 1단계(-M100%)는 내용이 같은 이름 바꿈만 보므로 q.py는 내 경로가 아니다(「제안」 3으로 옮기기 바로 전 판 하나만 받는다).
# blame은 내용으로 이름 바꿈을 찾아 q.py의 첫 판까지 읽으려다 실패한다(전체 clone이면 p.py는 (1, 10, [[5, 5]])).
EDITED_RENAME = [
    (OTHER_EMAIL, "add q", {"q.py": lines10()}),
    (OTHER_EMAIL, "edit q", {"q.py": lines10(l9="o9")}),
    (OTHER_EMAIL, "move q to p with edits", {"q.py": None, "p.py": lines10(l9="o9", l10="o10")}),
    (OWN_EMAIL, "mine p", {"p.py": lines10(l5="mine", l9="o9", l10="o10")}),
]

# -z 없는 raw·numstat 출력이 따옴표로 감싸는 이름("q\"\\x.py" 꼴). 줄바꿈이 있거나 CR로 끝나는 이름은 표준 입력(줄 단위,
# 줄 끝 CR을 지움)으로 줄 수 없다.
QUOTE_NAME = 'q"\\x.py'   # " 와 \ 가 있다
TAB_NAME = "t\tab.py"
NEWLINE_NAME = "nl\nx.py"
CR_NAME = "cr.py\r"       # 확장자가 '.py\r'라 코드 파일이 아니다(blame하지 않음, 2단계와 같음)


class PartialIndexTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="lv-s2-partial-")
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def has(self, clone, text):
        p = subprocess.run(["git", "-C", clone, "cat-file", "-e", blob_id(text)],
                           env=dict(self.env, GIT_NO_LAZY_FETCH="1"), capture_output=True, timeout=60)
        return p.returncode == 0

    def have(self, clone, versions, paths):
        """{경로: [판마다 clone에 blob이 있는지]}"""
        return {p: [self.has(clone, t) for t in versions[p]] for p in paths}

    def clone_of(self, src, env, versions, *args, filt="blob:none", name="clone", mark=True):
        """부분 clone(self.tmp/<name>)을 받고 .git/lv-partial을 만든다(mark). 원격의 blob이 clone에 하나도 없는지 먼저 확인한다."""
        self.env = env
        clone = os.path.join(self.tmp, name)
        git_run(["clone", "-q", "--filter=" + filt, "--no-checkout", *args, "file://" + src, clone], env)
        if mark:
            open(os.path.join(clone, ".git", "lv-partial"), "w").close()
        got = {p: v for p, v in self.have(clone, versions, versions).items() if any(v)}
        self.assertEqual(got, {}, "부분 clone이 아니다(원격의 blob이 이미 있음)")
        return clone

    def prepare(self, commits=BASE):
        src, env, versions = make_remote(self.tmp, commits)
        return src, self.clone_of(src, env, versions), versions

    def run_index(self, clone, repo=None, path_front=(), run="run", **env_extra):
        """people.json(레포 하나)을 쓰고 LV_GITHUB_OFFLINE=1로 s2_index.py P01을 돌린다. path_front = PATH 맨 앞에 더할 폴더.
        run = 이 부름의 폴더 이름(작업 폴더·가짜 gh. 한 시험에서 여러 번 부를 때 다르게). -> (person.json, 레포 색인)"""
        root = os.path.join(self.tmp, run)
        home = os.path.join(root, "home")
        os.makedirs(home)
        r = {"key": "tester__big", "full_name": "tester/big", "dir": clone, "default_branch": "main", "prs": False}
        r.update(repo or {})
        with open(os.path.join(home, "people.json"), "w", encoding="utf-8") as f:
            json.dump([{"pid": "P01", "login": "tester", "role": None, "level": None, "repos": [r]}], f)
        bin_dir, gh_mark = fake_gh(root)
        env = base_env(LV_S2_HOME=home, LV_GITHUB_OFFLINE="1", **env_extra)
        env["PATH"] = os.pathsep.join([*path_front, bin_dir, env["PATH"]])
        before = code_tree()
        p = subprocess.run([sys.executable, "-I", "-B", os.path.join(CODE, "s2_index.py"), "P01"],
                           env=env, capture_output=True, timeout=300)
        self.assertEqual(code_tree(), before, "s2 코드 폴더에 파일이 생기면 안 된다")
        self.assertFalse(os.path.exists(gh_mark), "gh를 부르면 안 된다")
        self.assertEqual(p.returncode, 0, p.stderr.decode("utf-8", "replace"))
        idx = os.path.join(home, "index", "P01")
        with open(os.path.join(idx, "person.json"), encoding="utf-8") as f:
            person = json.load(f)
        with open(os.path.join(idx, "tester__big.json"), encoding="utf-8") as f:
            data = json.load(f)
        return person, data

    # ---------------- 계획(Task 2b)에 적힌 시험
    def test_partial_fetches_only_my_paths(self):
        _, clone, versions = self.prepare()
        _, data = self.run_index(clone)
        self.assertEqual(self.have(clone, versions, versions), {
            "a.py": [True] * 3, "x.py": [True] * 2, "y.py": [True] * 2,  # 내 경로와 이름 바꾸기 전 경로는 모든 판
            "b.py": [False] * 3, "c.txt": [False] * 2,                    # 남만 고친 경로는 받지 않는다
        })
        self.assertEqual(data["partial"]["paths"], ["a.py", "x.py", "y.py"])
        self.assertEqual(data["partial"]["blobs"], 6)  # a.py 3판 + x.py 2판 + y.py 새 판 1개(첫 판은 x.py 마지막 판)
        self.assertIs(data["partial"]["fetched"], True)

    def test_partial_numstat_mine_exact(self):
        _, clone, _ = self.prepare()
        _, data = self.run_index(clone)
        self.assertEqual([c["subject"] for c in data["commits"]], BASE_LOG)  # 남의 커밋까지 모두 있다
        self.assertEqual(sorted(c["subject"] for c in data["commits"] if c["own"]), MINE)
        files = {c["subject"]: c["files"] for c in data["commits"]}
        self.assertEqual(files["mine 1"], [numstat("a.py", 1, 0)])
        self.assertEqual(files["mine 2"], [numstat("a.py", 2, 1)])
        self.assertEqual(files["mine 3"], [numstat("y.py", 1, 1)])
        # b.py·c.txt만 건드린 남의 커밋은 파일 항목이 없고, 내 경로와 같이 건드린 커밋에도 내 경로만 남는다.
        self.assertEqual(files["edit b"], [])
        self.assertEqual(files["edit b c"], [])
        self.assertEqual(files["add a b c"], [numstat("a.py", 2, 0)])
        self.assertEqual(files["rename x to y"], [numstat("y.py", 0, 0)])  # 옛·새 경로가 다 내 경로인 이름 바꿈은 새 경로(2단계와 같음)
        self.assertIs(data["partial"]["numstat_ok"], True)

    def test_partial_blame_my_lines(self):
        _, clone, versions = self.prepare()
        _, data = self.run_index(clone)
        got = {f["path"]: (f["my_lines"], f["lines"], f["my_ranges"]) for f in data["files"]}
        self.assertEqual(got["a.py"], (3, 4, [[1, 1], [3, 4]]))  # a = 10·c = 3·d = 4가 내 줄, b = 2는 남의 줄
        self.assertEqual(got["y.py"], (1, 3, [[2, 2]]))          # x.py 때의 판까지 따라가 남의 두 줄을 가린다
        self.assertEqual(got["b.py"], (0, None, []))
        # 위 결과는 남의 내용 없이 나왔다(받으러 가서 다 받았으면 b.py도 있다)
        self.assertEqual(self.have(clone, versions, ["b.py", "c.txt"]), {"b.py": [False] * 3, "c.txt": [False] * 2})
        self.assertEqual(data["partial"]["blame_failed"], {"count": 0, "paths": [], "omitted": 0})  # blame은 다 되었다

    def test_partial_one_fetch_no_lazy(self):
        _, clone, _ = self.prepare()
        trace = os.path.join(self.tmp, "trace2.json")
        self.run_index(clone, GIT_TRACE2_EVENT=trace)
        names = trace_names(trace)
        # 내 경로를 받는 한 번뿐이다. lazy fetch가 있으면 git이 fetch를 더 띄운다.
        self.assertEqual(names.count("fetch"), 1, names)
        self.assertEqual([n for n in names if n in ("maintenance", "gc")], [], names)  # 받은 뒤 자동 정리를 돌리지 않는다

    def test_partial_fetch_failure_continues(self):
        src, clone, _ = self.prepare()
        shutil.rmtree(src)  # clone 뒤 원격이 없어짐 → 받기 실패
        person, data = self.run_index(clone)
        self.assertEqual(person["repo_keys"], ["tester__big"])
        self.assertNotIn("error", data)
        self.assertEqual(data["partial"]["paths"], ["a.py", "x.py", "y.py"])
        self.assertIs(data["partial"]["fetched"], False)
        self.assertEqual([c["subject"] for c in data["commits"]], BASE_LOG)
        self.assertEqual(sorted(c["subject"] for c in data["commits"] if c["own"]), MINE)
        # 내용이 없어 내 경로의 numstat도 실패한다 → 파일 항목은 모두 비운다(일부만 남기지 않음).
        self.assertIs(data["partial"]["numstat_ok"], False)
        self.assertEqual([c["files"] for c in data["commits"]], [[]] * len(BASE))
        # 내가 건드린 파일을 모르니 blame도 하지 않는다(받기 실패는 fetched로만 보인다).
        self.assertEqual(data["partial"]["blame_failed"], {"count": 0, "paths": [], "omitted": 0})

    # ---------------- 실제 이력에서 생기는 경우
    def test_partial_raw_pass_reads_no_contents(self):
        # 남이 한 커밋에서 파일을 지우고 다른 내용의 파일을 만들었다. 비슷한 파일로 이름 바꿈을 찾으면(-M) git이 두 파일의
        # 내용을 읽어야 해서, lazy fetch를 막은 부분 clone에서는 그 커밋에서 멈춘다(rc 128). 트리만 읽어야 내 경로를 다 찾는다.
        commits = BASE + [
            (OTHER_EMAIL, "add d", {"d.py": "d = 1\n"}),
            (OTHER_EMAIL, "replace d with e", {"d.py": None, "e.py": "e = 1\ne = 2\n"}),
        ]
        _, clone, versions = self.prepare(commits)
        _, data = self.run_index(clone)
        self.assertEqual(data["partial"]["paths"], ["a.py", "x.py", "y.py"])
        self.assertIs(data["partial"]["fetched"], True)
        self.assertEqual(self.have(clone, versions, ["a.py", "d.py", "e.py"]),
                         {"a.py": [True] * 3, "d.py": [False], "e.py": [False]})

    def test_partial_blame_reads_files_removed_where_my_path_began(self):
        # 내 경로 n.py를 만든 남의 커밋이 다른 파일을 지우고(old.py) 다른 파일을 그대로 옮겼다(r.py → s.py).
        # blame은 그 커밋에서 n.py의 옛 이름을 찾으려고 그 커밋이 없앤 파일의 내용을 모두 읽는다. 그 판만 더 받는다.
        commits = BASE + [
            (OTHER_EMAIL, "add old r", {"old.py": "o = 1\n", "r.py": "r = 1\nr = 2\n"}),
            (OTHER_EMAIL, "edit old", {"old.py": "o = 2\n"}),
            (OTHER_EMAIL, "start n", {"old.py": None, "s.py": (MV, "r.py"), "n.py": "n = 1\nn = 2\n"}),
            (OWN_EMAIL, "mine n", {"n.py": "n = 1\nn = 20\n"}),
        ]
        _, clone, versions = self.prepare(commits)
        _, data = self.run_index(clone)
        got = {f["path"]: (f["my_lines"], f["lines"], f["my_ranges"]) for f in data["files"]}
        self.assertEqual(got["n.py"], (1, 2, [[2, 2]]))
        self.assertEqual(data["partial"]["paths"], ["a.py", "n.py", "x.py", "y.py"])
        self.assertEqual(self.have(clone, versions, ["old.py", "r.py"]), {"old.py": [False, True], "r.py": [True]})
        self.assertEqual(data["partial"]["blobs"], 10)  # 기본 6 + n.py 2판 + 지운 old.py 판 + 옮긴 r.py 판

    def test_partial_numstat_keeps_my_side_branch_commits(self):
        # 곁가지에서 내가 a.py를 고치고 되돌린 뒤 합쳤다(합친 뒤 a.py는 첫 부모와 같다). 경로를 주면 git은 기본으로 이력을
        # 줄여 곁가지 커밋을 보이지 않는다. 표시 없는 레포의 numstat처럼 내 커밋의 파일 항목이 남아야 한다.
        src, env, versions = make_remote(self.tmp, [(OTHER_EMAIL, "add a b", {"a.py": "a1\na2\n", "b.py": "b1\n"})])
        git_run(["-C", src, "checkout", "-q", "-b", "side"], env)
        commit_all(src, env, [(OWN_EMAIL, "mine on side", {"a.py": "a1\nmine\na2\n"}),
                              (OWN_EMAIL, "revert mine", {"a.py": "a1\na2\n"})], versions, 2)
        git_run(["-C", src, "checkout", "-q", "main"], env)
        commit_all(src, env, [(OTHER_EMAIL, "edit b", {"b.py": "b2\n"})], versions, 4)
        merge_in(src, env, "side", "merge side", 5)
        clone = self.clone_of(src, env, versions)
        _, data = self.run_index(clone)
        files = {c["subject"]: c["files"] for c in data["commits"]}
        self.assertEqual(files, {"mine on side": [numstat("a.py", 1, 0)], "revert mine": [numstat("a.py", 0, 1)],
                                 "edit b": [], "add a b": [numstat("a.py", 2, 0)]})
        self.assertEqual(data["partial"]["paths"], ["a.py"])

    def merged_side_repo(self):
        """곁가지에서 내가 m.py 2번 줄을, main에서 남이 9번 줄을 고친 뒤 충돌 없이 합쳤다(끝 = 합친 커밋).
        남만 고친 o.py도 양쪽에서 고쳐 합친 판이 생긴다. 합친 판은 versions 끝에 더한다. -> (clone, versions)"""
        src, env, versions = make_remote(self.tmp, [(OTHER_EMAIL, "add m o", {"m.py": lines10(), "o.py": "o1\no2\no3\n"})])
        git_run(["-C", src, "checkout", "-q", "-b", "side"], env)
        commit_all(src, env, [(OWN_EMAIL, "mine on side", {"m.py": lines10(l2="mine")}),
                              (OTHER_EMAIL, "other on side", {"o.py": "o1\no2\nside\n"})], versions, 2)
        git_run(["-C", src, "checkout", "-q", "main"], env)
        commit_all(src, env, [(OTHER_EMAIL, "other on main", {"m.py": lines10(l9="o9"), "o.py": "main\no2\no3\n"})], versions, 4)
        merge_in(src, env, "side", "merge side", 5)
        versions["m.py"].append(lines10(l2="mine", l9="o9"))  # 합친 커밋에서만 생긴 판
        versions["o.py"].append("main\no2\nside\n")
        return self.clone_of(src, env, versions), versions

    def test_partial_fetches_version_made_by_merge_at_tip(self):
        # 양쪽이 고친 파일을 합치면(충돌이 없어도) 합친 커밋에서만 생긴 판이 남는다. 그 판은 머지 아닌 커밋의 raw에 없다.
        # 그 판(여기서는 끝의 판)이 없으면 blame이 실패하고(my_lines 0) 추출기도 m.py를 읽지 못한다(크기 None).
        clone, versions = self.merged_side_repo()
        _, data = self.run_index(clone)
        got = {f["path"]: (f["my_lines"], f["lines"], f["my_ranges"], f["size"]) for f in data["files"]}
        self.assertEqual(got["m.py"], (1, 10, [[2, 2]], len(versions["m.py"][-1])))
        # 내 경로는 합친 판까지 모든 판을 받고, 남의 경로(o.py)는 합친 판도 받지 않는다.
        self.assertEqual(self.have(clone, versions, ["m.py", "o.py"]), {"m.py": [True] * 4, "o.py": [False] * 4})
        self.assertEqual(data["partial"]["paths"], ["m.py"])
        self.assertEqual(data["partial"]["blobs"], 4)
        self.assertIs(data["partial"]["fetched"], True)

    def test_partial_fetches_versions_made_by_inner_merges(self):
        # 합친 커밋 두 개가 이어지고, 그 뒤 남이 머지 아닌 커밋으로 고쳤다(끝의 판과 그 옛 판은 머지 아닌 커밋의 raw에 있다).
        # 첫 합친 커밋의 판은 어느 머지 아닌 커밋의 raw에도 없다. 끝의 판만 더 받아서는 blame이 그 판에서 실패한다.
        src, env, versions = make_remote(self.tmp, [(OTHER_EMAIL, "add m", {"m.py": lines10()})])
        git_run(["-C", src, "checkout", "-q", "-b", "side1"], env)
        commit_all(src, env, [(OWN_EMAIL, "mine on side1", {"m.py": lines10(l2="mine")})], versions, 2)
        git_run(["-C", src, "checkout", "-q", "main"], env)
        commit_all(src, env, [(OTHER_EMAIL, "other on main", {"m.py": lines10(l9="o9")})], versions, 3)
        git_run(["-C", src, "checkout", "-q", "-b", "side2"], env)
        commit_all(src, env, [(OTHER_EMAIL, "other on side2", {"m.py": lines10(l5="o5", l9="o9")})], versions, 4)
        git_run(["-C", src, "checkout", "-q", "main"], env)
        merge_in(src, env, "side1", "merge 1", 5)  # 판: 2·9번 줄(이 합친 커밋에서만 생김)
        merge_in(src, env, "side2", "merge 2", 6)  # 판: 2·5·9번 줄(다음 커밋의 옛 판)
        commit_all(src, env, [(OTHER_EMAIL, "other after", {"m.py": lines10(l2="mine", l5="o5", l7="o7", l9="o9")})], versions, 7)
        versions["m.py"] += [lines10(l2="mine", l9="o9"), lines10(l2="mine", l5="o5", l9="o9")]
        clone = self.clone_of(src, env, versions)
        _, data = self.run_index(clone)
        got = {f["path"]: (f["my_lines"], f["lines"], f["my_ranges"]) for f in data["files"]}
        self.assertEqual(got["m.py"], (1, 10, [[2, 2]]))
        self.assertEqual(self.have(clone, versions, ["m.py"]), {"m.py": [True] * 7})
        self.assertEqual(data["partial"]["blobs"], 7)
        self.assertIs(data["partial"]["fetched"], True)

    def test_partial_merge_pass_takes_only_my_exact_paths(self):
        # 내가 고친 파일 tool을 남이 지우고 같은 이름의 폴더(tool/x.py)를 만든 뒤, 양쪽에서 tool/x.py를 고쳐 합쳤다.
        # git 경로 조건 'tool'은 폴더 아래 파일도 고르므로, 합친 커밋을 읽는 단계는 내 경로와 글자가 같은 항목만 받는다.
        # (이 모양에서는 내 경로 numstat이 폴더 아래 파일 내용이 없어 실패한다. 이 시험은 받는 범위만 본다.)
        src, env, versions = make_remote(self.tmp, [(OTHER_EMAIL, "add tool", {"tool": "t1\n"})])
        commit_all(src, env, [(OWN_EMAIL, "mine tool", {"tool": "t1\nmine\n"}),
                              (OTHER_EMAIL, "tool becomes a folder", {"tool": None}),
                              (OTHER_EMAIL, "add tool/x.py", {"tool/x.py": "x1\nx2\nx3\n"})], versions, 2)
        git_run(["-C", src, "checkout", "-q", "-b", "side"], env)
        commit_all(src, env, [(OTHER_EMAIL, "other on side", {"tool/x.py": "x1\nx2\nside\n"})], versions, 5)
        git_run(["-C", src, "checkout", "-q", "main"], env)
        commit_all(src, env, [(OTHER_EMAIL, "other on main", {"tool/x.py": "main\nx2\nx3\n"})], versions, 6)
        merge_in(src, env, "side", "merge side", 7)
        versions["tool/x.py"].append("main\nx2\nside\n")  # 합친 커밋에서만 생긴 판
        clone = self.clone_of(src, env, versions)
        _, data = self.run_index(clone)
        self.assertEqual(data["partial"]["paths"], ["tool"])
        self.assertEqual(self.have(clone, versions, ["tool", "tool/x.py"]), {"tool": [True] * 2, "tool/x.py": [False] * 4})
        self.assertEqual(data["partial"]["blobs"], 2)

    def test_partial_no_commits_of_mine_reads_and_fetches_nothing(self):
        # 이 큰 레포의 분석 브랜치에 내 커밋이 없다. 내 경로가 없으니 합친 커밋을 읽지 않고(경로 없이 부르면 모든 합친 커밋의
        # 모든 경로를 비교한다) 받지도 않는다.
        src, env, versions = make_remote(self.tmp, [(OTHER_EMAIL, "add m", {"m.py": lines10()})])
        git_run(["-C", src, "checkout", "-q", "-b", "side"], env)
        commit_all(src, env, [(OTHER_EMAIL, "other on side", {"m.py": lines10(l2="side")})], versions, 2)
        git_run(["-C", src, "checkout", "-q", "main"], env)
        commit_all(src, env, [(OTHER_EMAIL, "other on main", {"m.py": lines10(l9="o9")})], versions, 3)
        merge_in(src, env, "side", "merge side", 4)
        clone = self.clone_of(src, env, versions)
        trace = os.path.join(self.tmp, "trace2.json")
        _, data = self.run_index(clone, GIT_TRACE2_EVENT=trace)
        with open(trace, encoding="utf-8") as f:
            argvs = [ev["argv"] for ev in map(json.loads, f) if ev.get("event") == "start"]
        self.assertEqual([a for a in argvs if "--diff-merges=separate" in a or "fetch" in a], [])
        self.assertEqual(data["partial"], {"paths": [], "blobs": 0, "fetched": True, "numstat_ok": True,
                                           "blame_failed": {"count": 0, "paths": [], "omitted": 0}})
        self.assertEqual([c["own"] for c in data["commits"]], [False] * 3)

    def test_partial_merge_pass_asks_git_for_my_paths_only(self):
        # 합친 커밋을 읽는 단계는 git에 내 경로만 준다(표준 입력, 글자 그대로). 경로 없이 불러도 결과는 내 경로와 글자가 같은
        # 항목만 고르는 거름 때문에 같지만, 모든 합친 커밋의 모든 경로를 부모마다 비교해 큰 레포에서 출력이 커진다.
        # --full-history는 git 2.55에서는 --diff-merges만으로도 이력을 줄이지 않아 결과로 드러나지 않으므로 인자로 확인한다.
        clone, _ = self.merged_side_repo()
        bin_dir, argv_file, stdin_file = spy_git(self.tmp, "--diff-merges=separate")
        _, data = self.run_index(clone, path_front=[bin_dir])
        with open(argv_file, encoding="utf-8") as f:
            argv = f.read().splitlines()
        with open(stdin_file, encoding="utf-8") as f:
            self.assertEqual(f.read(), "--\nm.py\n")
        self.assertEqual([a for a in argv if a in ("--literal-pathspecs", "--merges", "--full-history", "--stdin")],
                         ["--literal-pathspecs", "--merges", "--full-history", "--stdin"])
        self.assertIs(data["partial"]["fetched"], True)

    def test_partial_merge_pass_failure_still_fetches_the_rest(self):
        # 합친 커밋을 읽는 단계가 실패했다(시험용 git이 --diff-merges=separate가 있는 호출만 실패시킨다).
        # 머지 아닌 커밋에서 찾은 내 경로의 판은 그대로 받고(numstat은 됨), 합친 판을 못 받았으니 fetched는 거짓이다.
        clone, versions = self.merged_side_repo()
        bin_dir, argv_file, _ = spy_git(self.tmp, "--diff-merges=separate", fail=True)
        _, data = self.run_index(clone, path_front=[bin_dir])
        self.assertTrue(os.path.exists(argv_file))  # 그 단계를 불렀다(그리고 실패했다)
        self.assertNotIn("error", data)
        self.assertEqual(data["partial"]["paths"], ["m.py"])
        self.assertEqual(data["partial"]["blobs"], 3)
        self.assertIs(data["partial"]["fetched"], False)
        self.assertEqual(self.have(clone, versions, ["m.py", "o.py"]),
                         {"m.py": [True, True, True, False], "o.py": [False] * 4})
        self.assertIs(data["partial"]["numstat_ok"], True)
        self.assertEqual({c["subject"]: c["files"] for c in data["commits"]}["mine on side"], [numstat("m.py", 1, 1)])
        # 합친 판(끝의 판)이 없어 m.py는 blame이 실패한다: 내 줄을 세지 않고(my_ranges None) blame_failed에 남긴다.
        self.assertIsNone({f["path"]: f["my_ranges"] for f in data["files"]}["m.py"])
        self.assertEqual(data["partial"]["blame_failed"], {"count": 1, "paths": ["m.py"], "omitted": 0})

    def test_partial_branch_fetch_brings_no_contents(self):
        # develop은 clone에 없어서(--single-branch) ensure_ref가 받아 온다. 표시한 레포는 내용 없이(blob:none) 받고,
        # 내 경로의 내용만 따로 받는다.
        src, env, versions = make_remote(self.tmp, BASE)
        git_run(["-C", src, "checkout", "-q", "-b", "develop"], env)
        commit_all(src, env, [(OTHER_EMAIL, "dev other", {"dev_other.py": "o = 1\n"}),
                              (OWN_EMAIL, "dev mine", {"dev_mine.py": "m = 1\n"})], versions, len(BASE) + 1)
        git_run(["-C", src, "checkout", "-q", "main"], env)
        clone = self.clone_of(src, env, versions, "--single-branch", "--branch", "main")
        _, data = self.run_index(clone, repo={"has_develop": True})
        self.assertEqual([r["name"] for r in data["refs"]], ["main", "develop"])
        self.assertEqual(self.have(clone, versions, ["dev_other.py", "dev_mine.py"]),
                         {"dev_other.py": [False], "dev_mine.py": [True]})
        self.assertEqual(data["partial"]["paths"], ["a.py", "dev_mine.py", "x.py", "y.py"])

    def test_partial_gitlink_is_not_fetched(self):
        # 내가 하위 모듈 자리(gitlink)를 바꿨다. 그 id는 다른 레포의 커밋이라 받을 수 없고, 하나라도 섞이면 받기 전체가 실패한다.
        commits = BASE + [
            (OTHER_EMAIL, "add sub", {"sub": (LINK, "1" * 40)}),
            (OWN_EMAIL, "bump sub", {"sub": (LINK, "2" * 40)}),
        ]
        _, clone, versions = self.prepare(commits)
        _, data = self.run_index(clone)
        self.assertEqual(data["partial"]["paths"], ["a.py", "sub", "x.py", "y.py"])
        self.assertEqual(data["partial"]["blobs"], 6)
        self.assertIs(data["partial"]["fetched"], True)
        self.assertEqual(self.have(clone, versions, ["a.py"]), {"a.py": [True] * 3})

    def test_partial_tree_read_failure_continues(self):
        # 트리까지 빠진 clone(tree:0)이면 트리를 읽는 첫 단계가 실패한다. 잘린 결과로 일부만 받지 않고 fetched=False로 둔다.
        src, env, versions = make_remote(self.tmp, BASE)
        clone = self.clone_of(src, env, versions, filt="tree:0")
        _, data = self.run_index(clone)
        self.assertEqual(data["partial"]["paths"], [])
        self.assertIs(data["partial"]["fetched"], False)
        self.assertEqual([c["subject"] for c in data["commits"]], BASE_LOG)
        self.assertEqual(sorted(c["subject"] for c in data["commits"] if c["own"]), MINE)

    # ---------------- blame이 받지 않은 판을 읽어 실패하는 경우: 받기를 넓히지 않고(한 번) partial.blame_failed에 남긴다
    def test_partial_blame_failure_after_edited_rename_is_recorded(self):
        # EDITED_RENAME: blame이 받지 않은 q.py의 첫 판을 읽으려다 실패한다. 그 파일은 내 줄을 세지 않은 채(my_ranges None,
        # 2단계 코드가 '세지 않음'으로 읽는 값) 남기고, blame_failed에 수와 경로를 남긴다.
        _, clone, versions = self.prepare(BASE + EDITED_RENAME)
        _, data = self.run_index(clone)
        got = {f["path"]: (f["my_lines"], f["lines"], f["my_ranges"]) for f in data["files"]}
        self.assertEqual(got["p.py"], (0, None, None))
        self.assertEqual(got["a.py"], (3, 4, [[1, 1], [3, 4]]))  # blame이 된 파일은 남기지 않는다
        self.assertEqual(data["partial"]["blame_failed"], {"count": 1, "paths": ["p.py"], "omitted": 0})
        self.assertIs(data["partial"]["fetched"], True)
        self.assertIs(data["partial"]["numstat_ok"], True)
        self.assertEqual({c["subject"]: c["files"] for c in data["commits"]}["mine p"], [numstat("p.py", 1, 1)])
        # 실패한 까닭은 받지 않은 판이다: p.py의 판과 q.py의 옮기기 바로 전 판은 받았고, q.py의 첫 판은 받지 않았다.
        self.assertEqual(self.have(clone, versions, ["p.py", "q.py"]), {"p.py": [True, True], "q.py": [False, True]})

    def test_partial_blame_failure_at_hand_resolved_merge_is_recorded(self):
        # 곁가지에서 내가 f.py를 고치고 남이 d.py를 지웠다. main에서는 남이 f.py를 지웠다. 합칠 때 고침/지움 충돌을 손으로 풀면서
        # f.py를 더 고쳤다. 합친 판은 f.py가 있는 부모(곁가지)와 다르고 다른 부모(main)에는 f.py가 없어서, blame은 main과 비교해
        # 이름 바꿈을 찾으며 합친 커밋이 없앤 남의 d.py 내용을 읽다가 실패한다(전체 clone이면 f.py는 (1, 10, [[2, 2]])).
        src, env, versions = make_remote(self.tmp, [(OTHER_EMAIL, "add f d", {"f.py": lines10(), "d.py": "d1\n"})])
        git_run(["-C", src, "checkout", "-q", "-b", "side"], env)
        commit_all(src, env, [(OWN_EMAIL, "mine on side", {"f.py": lines10(l2="mine")}),
                              (OTHER_EMAIL, "drop d on side", {"d.py": None})], versions, 2)
        git_run(["-C", src, "checkout", "-q", "main"], env)
        commit_all(src, env, [(OTHER_EMAIL, "drop f on main", {"f.py": None})], versions, 4)
        resolved = lines10(l2="mine", l5="fix")
        self.assertEqual(merge_by_hand(src, env, "side", "merge side", 5, {"f.py": resolved}), 1)  # 고침/지움 충돌
        versions["f.py"].append(resolved)
        clone = self.clone_of(src, env, versions)
        _, data = self.run_index(clone)
        got = {f["path"]: (f["my_lines"], f["lines"], f["my_ranges"]) for f in data["files"]}
        self.assertEqual(got, {"f.py": (0, None, None)})
        self.assertEqual(data["partial"]["paths"], ["f.py"])
        self.assertEqual(data["partial"]["blame_failed"], {"count": 1, "paths": ["f.py"], "omitted": 0})
        self.assertIs(data["partial"]["fetched"], True)
        self.assertEqual({c["subject"]: c["files"] for c in data["commits"]}["mine on side"], [numstat("f.py", 1, 1)])
        # f.py는 합친 판까지 모든 판을 받았고, 남의 d.py는 받지 않았다(받는 범위를 넓히지 않음).
        self.assertEqual(self.have(clone, versions, ["f.py", "d.py"]), {"f.py": [True] * 3, "d.py": [False]})

    def test_partial_blame_failed_lists_first_20_paths(self):
        # blame이 실패한 파일이 많으면 경로는 정렬해 앞의 20개만 남기고, 모두의 수와 목록에서 뺀 수를 남긴다(EDITED_RENAME 꼴 22개).
        keys = ["%02d" % i for i in range(22)]

        def text(k, **changed):
            return lines10(l1="q" + k, **changed)  # 파일마다 첫 줄이 달라 blame이 제 짝(q<k>.py)을 찾는다

        commits = [
            (OTHER_EMAIL, "add q", {"q%s.py" % k: text(k) for k in keys}),
            (OTHER_EMAIL, "edit q", {"q%s.py" % k: text(k, l9="o9") for k in keys}),
            (OTHER_EMAIL, "move q to p with edits", dict({"q%s.py" % k: None for k in keys},
                                                         **{"p%s.py" % k: text(k, l9="o9", l10="o10") for k in keys})),
            (OWN_EMAIL, "mine p", {"p%s.py" % k: text(k, l5="mine", l9="o9", l10="o10") for k in keys}),
        ]
        _, clone, _ = self.prepare(commits)
        _, data = self.run_index(clone)
        self.assertEqual(data["partial"]["blame_failed"],
                         {"count": 22, "paths": ["p%s.py" % k for k in keys[:20]], "omitted": 2})
        self.assertEqual({f["path"]: f["my_ranges"] for f in data["files"]}, {"p%s.py" % k: None for k in keys})
        self.assertIs(data["partial"]["fetched"], True)

    def test_partial_blame_failed_paths_sorted_across_branches(self):
        # 분석 브랜치가 둘이면(main·develop) snapshot은 main의 파일 다음에 develop에만 있는 파일을 둔다. blame_failed의 경로는
        # 그 차례와 관계없이 정렬한다(EDITED_RENAME 꼴을 main의 zp.py와 develop의 ap.py에 둠).
        def edited_rename(q, p):
            return [(OTHER_EMAIL, "add " + q, {q: lines10(l1=q)}),
                    (OTHER_EMAIL, "edit " + q, {q: lines10(l1=q, l9="o9")}),
                    (OTHER_EMAIL, "move %s to %s" % (q, p), {q: None, p: lines10(l1=q, l9="o9", l10="o10")}),
                    (OWN_EMAIL, "mine " + p, {p: lines10(l1=q, l5="mine", l9="o9", l10="o10")})]

        src, env, versions = make_remote(self.tmp, edited_rename("zq.py", "zp.py"))
        git_run(["-C", src, "checkout", "-q", "-b", "develop"], env)
        commit_all(src, env, edited_rename("aq.py", "ap.py"), versions, 5)
        git_run(["-C", src, "checkout", "-q", "main"], env)
        clone = self.clone_of(src, env, versions)
        _, data = self.run_index(clone, repo={"has_develop": True})
        self.assertEqual([f["path"] for f in data["files"]], ["zp.py", "ap.py"])  # snapshot 차례: main 먼저
        self.assertEqual(data["partial"]["blame_failed"], {"count": 2, "paths": ["ap.py", "zp.py"], "omitted": 0})

    # ---------------- GIT_NO_LAZY_FETCH를 모르는 옛 git(2.45 전)에서도 받기는 한 번뿐이다
    def test_partial_stays_lazy_free_on_old_git(self):
        # 스테이징 EC2의 git은 Ubuntu 2.34·2.43일 수 있다. 그런 git에서 부분 clone은 빠진 내용을 보는 git마다 받으러 간다:
        # snapshot의 cat-file --batch-check는 끝의 빠진 파일(b.py·c.txt)마다, blame은 q.py의 첫 판(EDITED_RENAME)을.
        # prefetch_mine이 받은 뒤 부분 clone 설정(promisor)을 지우므로, 옛 git에서도 받기는 한 번이고 색인은 보통 git과 같다.
        src, env, versions = make_remote(self.tmp, BASE + EDITED_RENAME)
        normal = self.clone_of(src, env, versions, name="normal")
        old = self.clone_of(src, env, versions, name="old")
        probe = self.clone_of(src, env, versions, name="probe", mark=False)
        bin_dir, old_git_path = old_git(self.tmp)
        # 시험용 옛 git은 GIT_NO_LAZY_FETCH=1을 받아도 정말 받으러 간다(흉내가 듣지 않으면 아래 비교는 아무것도 보지 않는다).
        p = subprocess.run([old_git_path, "-C", probe, "cat-file", "-e", blob_id(versions["b.py"][-1])],
                           env=dict(env, GIT_NO_LAZY_FETCH="1"), capture_output=True, timeout=60)
        self.assertEqual(p.returncode, 0, "시험용 옛 git이 빠진 내용을 받으러 가지 않았다")
        _, want = self.run_index(normal, run="normal")
        trace = os.path.join(self.tmp, "trace2.json")
        _, got = self.run_index(old, run="old", path_front=[bin_dir], GIT_TRACE2_EVENT=trace)
        names = trace_names(trace)
        self.assertEqual(names.count("fetch"), 1, names)
        for rec in (want, got):
            del rec["dir"], rec["index_s"]
        self.assertEqual(got, want)
        self.assertEqual(got["partial"]["blame_failed"], {"count": 1, "paths": ["p.py"], "omitted": 0})
        # 끝난 뒤 두 clone 모두 부분 clone 설정이 없다(이 레포에서 뒤에 도는 추출기도 받으러 가지 않는다).
        self.assertEqual((promisor_config(normal, env), promisor_config(old, env)), ([], []))

    def test_partial_tree_read_failure_stays_lazy_free_on_old_git(self):
        # 트리까지 빠진 clone(tree:0)에서 옛 git은 1단계(log --raw)부터 빠진 트리를 받으러 간다. 부분 clone 설정을 1단계 전에도
        # 지우므로, 옛 git에서도 1단계는 보통 git처럼 실패하고(paths []·fetched 거짓) 아무것도 받지 않는다.
        src, env, versions = make_remote(self.tmp, BASE)
        normal = self.clone_of(src, env, versions, filt="tree:0", name="normal")
        old = self.clone_of(src, env, versions, filt="tree:0", name="old")
        bin_dir, _ = old_git(self.tmp)
        _, want = self.run_index(normal, run="normal")
        trace = os.path.join(self.tmp, "trace2.json")
        _, got = self.run_index(old, run="old", path_front=[bin_dir], GIT_TRACE2_EVENT=trace)
        names = trace_names(trace)
        self.assertEqual(names.count("fetch"), 0, names)
        for rec in (want, got):
            del rec["dir"], rec["index_s"]
        self.assertEqual(got, want)
        self.assertEqual((got["partial"]["paths"], got["partial"]["fetched"]), ([], False))

    def test_partial_old_clone_format_is_closed_too(self):
        # 옛 git이 만든 부분 clone은 받으러 갈 곳을 extensions.partialClone으로도 적는다. 그 설정도 지우므로 옛 git에서도 받기는 한
        # 번이고, 끝난 뒤 설정이 남지 않는다.
        _, clone, _ = self.prepare()
        git_run(["-C", clone, "config", "extensions.partialClone", "origin"], self.env)
        bin_dir, _ = old_git(self.tmp)
        trace = os.path.join(self.tmp, "trace2.json")
        _, data = self.run_index(clone, path_front=[bin_dir], GIT_TRACE2_EVENT=trace)
        self.assertNotIn("error", data)
        self.assertEqual(trace_names(trace).count("fetch"), 1)
        self.assertIs(data["partial"]["fetched"], True)
        self.assertEqual(promisor_config(clone, self.env), [])

    def test_partial_promisor_left_behind_fails_closed(self):
        # 지우지 않는 받으러 갈 곳이 남았다(여기서는 다른 remote의 부분 clone 설정). 받으러 갈 수 있는 채로 색인하지 않고 그 레포를
        # error로 남긴다(Task 4는 '레포 n개는 색인하지 못함'). 색인 파일과 person.json은 생긴다.
        _, clone, _ = self.prepare()
        git_run(["-C", clone, "config", "remote.mirror.url", "file://" + os.path.join(self.tmp, "nowhere")], self.env)
        git_run(["-C", clone, "config", "remote.mirror.promisor", "true"], self.env)
        person, data = self.run_index(clone)
        self.assertEqual(person["repo_keys"], ["tester__big"])
        self.assertRegex(data.get("error", ""), r"^RuntimeError\('부분 clone 설정\(promisor\)을 지우지 못함 \(rc 0\)'\)$")
        self.assertEqual((data["commits"], data["files"]), ([], []))

    def test_unmarked_partial_clone_keeps_lazy_fallback(self):
        # 표시 없는 레포는 2단계 그대로다: 부분 clone이어도 부분 clone 설정을 지우지 않고, 빠진 내용 때문에 numstat이 실패하면
        # git_lazy가 받으러 가서 다시 부른다(남의 커밋도 파일 항목이 모두 있다). 받은 뒤 설정을 지우는 것은 표시한 레포뿐이다.
        src, env, versions = make_remote(self.tmp, BASE)
        clone = self.clone_of(src, env, versions, filt="blob:limit=1", mark=False)
        _, data = self.run_index(clone)
        self.assertNotIn("partial", data)
        files = {c["subject"]: c["files"] for c in data["commits"]}
        self.assertEqual(files["edit b c"], [numstat("b.py", 1, 1), numstat("c.txt", 1, 1)])
        self.assertNotEqual(promisor_config(clone, env), [])

    # ---------------- 이름에 드문 글자가 있는 내 경로도 글자 그대로 맞춘다
    def test_partial_unusual_path_names_match_exactly(self):
        # 내가 고친 파일의 이름에 " · \ · 탭 · 줄바꿈이 있거나 이름이 CR로 끝난다. -z 없는 raw 출력은 이런 이름을 따옴표로 감싸서
        # 내 경로가 표준 입력 경로와 맞지 않았다(numstat이 빠지고 blame도 하지 않음). 줄바꿈이 있거나 CR로 끝나는 이름은
        # 표준 입력으로 줄 수 없어 명령 줄로 준다.
        odd = [QUOTE_NAME, TAB_NAME, NEWLINE_NAME, CR_NAME]
        commits = BASE + [
            (OTHER_EMAIL, "add odd", {QUOTE_NAME: "q1\nq2\n", TAB_NAME: "t1\n", NEWLINE_NAME: "n1\n", CR_NAME: "r1\n"}),
            (OWN_EMAIL, "mine odd", {QUOTE_NAME: "q1\nmine\nq2\n", TAB_NAME: "t1\nmine\n", NEWLINE_NAME: "mine\n",
                                     CR_NAME: "r1\nmine\n"}),
        ]
        _, clone, versions = self.prepare(commits)
        _, data = self.run_index(clone)
        self.assertEqual(data["partial"]["paths"], sorted(["a.py", "x.py", "y.py", *odd]))
        self.assertEqual(self.have(clone, versions, odd), {p: [True, True] for p in odd})
        mine = {f["path"]: (f["add"], f["dele"]) for c in data["commits"] if c["subject"] == "mine odd" for f in c["files"]}
        self.assertEqual(mine, {QUOTE_NAME: (1, 0), TAB_NAME: (1, 0), NEWLINE_NAME: (1, 1), CR_NAME: (1, 0)})
        got = {f["path"]: (f["my_lines"], f["lines"], f["my_ranges"]) for f in data["files"]}
        self.assertEqual(got[QUOTE_NAME], (1, 3, [[2, 2]]))
        self.assertEqual(got[TAB_NAME], (1, 2, [[2, 2]]))
        self.assertEqual(got[NEWLINE_NAME], (1, 1, [[1, 1]]))
        self.assertEqual(data["partial"]["blame_failed"], {"count": 0, "paths": [], "omitted": 0})

    def test_partial_merge_pass_takes_unusual_names(self):
        # 합친 커밋에서만 생긴 판(merged_side_repo 꼴)도, 이름에 " · \ 가 있거나(표준 입력으로 줌) 줄바꿈이 있는(명령 줄로 줌) 내 경로를
        # 글자 그대로 찾아 받는다. 파일마다 내용이 달라 한 파일의 판을 받아 다른 파일의 판이 우연히 생기지 않는다.
        names = [QUOTE_NAME, NEWLINE_NAME]

        def text(n, **changed):
            return lines10(l1=n[:1], **changed)

        src, env, versions = make_remote(self.tmp, [(OTHER_EMAIL, "add odd", {n: text(n) for n in names})])
        git_run(["-C", src, "checkout", "-q", "-b", "side"], env)
        commit_all(src, env, [(OWN_EMAIL, "mine on side", {n: text(n, l2="mine") for n in names})], versions, 2)
        git_run(["-C", src, "checkout", "-q", "main"], env)
        commit_all(src, env, [(OTHER_EMAIL, "other on main", {n: text(n, l9="o9") for n in names})], versions, 3)
        merge_in(src, env, "side", "merge side", 4)
        for n in names:
            versions[n].append(text(n, l2="mine", l9="o9"))  # 합친 커밋에서만 생긴 판
        clone = self.clone_of(src, env, versions)
        _, data = self.run_index(clone)
        self.assertEqual(self.have(clone, versions, names), {n: [True] * 4 for n in names})
        got = {f["path"]: (f["my_lines"], f["lines"], f["my_ranges"]) for f in data["files"]}
        self.assertEqual(got, {n: (1, 10, [[2, 2]]) for n in names})
        self.assertEqual((data["partial"]["blobs"], data["partial"]["fetched"]), (8, True))

    def test_partial_non_utf8_path_keeps_numstat(self):
        # 내가 고친 파일의 이름이 UTF-8로 읽을 수 없는 바이트다(옛 Windows에서 올린 파일 등). 내 경로는 git이 준 바이트 그대로
        # git에 돌려줘야 맞는다. 파일 항목·색인의 글자는 snapshot과 같이 읽는다(못 읽는 바이트는 U+FFFD). blame은 snapshot의
        # 글자로 부르므로 이 파일은 2단계처럼 blame이 실패하고 blame_failed에 남는다.
        raw, shown = b"caf\xe9.py", "caf�.py"
        src, env, versions = make_remote(self.tmp, BASE)
        commit_to_index(src, env, raw, "c1\n", OTHER_EMAIL, "add cafe", 10, versions)
        commit_to_index(src, env, raw, "c1\nmine\n", OWN_EMAIL, "mine cafe", 11, versions)
        clone = self.clone_of(src, env, versions)
        _, data = self.run_index(clone)
        self.assertEqual(data["partial"]["paths"], ["a.py", shown, "x.py", "y.py"])
        self.assertEqual(self.have(clone, versions, [raw]), {raw: [True, True]})
        self.assertEqual({c["subject"]: c["files"] for c in data["commits"]}["mine cafe"], [numstat(shown, 1, 0)])
        self.assertEqual(data["partial"]["blame_failed"], {"count": 1, "paths": [shown], "omitted": 0})


if __name__ == "__main__":
    unittest.main()
