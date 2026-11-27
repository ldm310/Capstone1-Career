"""큰 레포 부분 받기(.git/lv-partial을 표시한 레포의 s2_index) 시험.

- 합성 원격(uploadpack.allowFilter·uploadpack.allowAnySHA1InWant)을 file://로 --filter=blob:none --no-checkout
  clone하고 .git/lv-partial을 만든다. 시험 준비에서 clone이 정말 부분 clone인지(원격의 blob이 하나도 없는지) 먼저 본다.
- 내 커밋은 noreply 이메일이고 LV_GITHUB_OFFLINE=1이다(GitHub API는 빈 목록). gh는 불리면 실패한다(test_s2_port 도구).
- blob이 있는지는 GIT_NO_LAZY_FETCH=1 git cat-file -e로 본다(확인하는 쪽이 받으러 가지 않게). 기대 blob id는 내용에서 직접 셈한다.
- git 한 단계의 인자·표준 입력 확인과 실패는 PATH 맨 앞의 시험용 git(spy_git)으로 한다. 정한 인자가 있는 호출만 기록하고
  (실패시키거나 진짜 git에 넘김), 나머지는 진짜 git이다.
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
                git_run(["-C", src, "rm", "-q", path], env)
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
                git_run(["-C", src, "add", "--", path], env)
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


class PartialIndexTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="lv-s2-partial-")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.home = os.path.join(self.tmp, "home")

    def has(self, clone, text):
        p = subprocess.run(["git", "-C", clone, "cat-file", "-e", blob_id(text)],
                           env=dict(self.env, GIT_NO_LAZY_FETCH="1"), capture_output=True, timeout=60)
        return p.returncode == 0

    def have(self, clone, versions, paths):
        """{경로: [판마다 clone에 blob이 있는지]}"""
        return {p: [self.has(clone, t) for t in versions[p]] for p in paths}

    def clone_of(self, src, env, versions, *args, filt="blob:none"):
        """부분 clone을 받고 .git/lv-partial을 만든다. 원격의 blob이 clone에 하나도 없는지 먼저 확인한다."""
        self.env = env
        clone = os.path.join(self.tmp, "clone")
        git_run(["clone", "-q", "--filter=" + filt, "--no-checkout", *args, "file://" + src, clone], env)
        open(os.path.join(clone, ".git", "lv-partial"), "w").close()
        got = {p: v for p, v in self.have(clone, versions, versions).items() if any(v)}
        self.assertEqual(got, {}, "부분 clone이 아니다(원격의 blob이 이미 있음)")
        return clone

    def prepare(self, commits=BASE):
        src, env, versions = make_remote(self.tmp, commits)
        return src, self.clone_of(src, env, versions), versions

    def run_index(self, clone, repo=None, path_front=(), **env_extra):
        """people.json(레포 하나)을 쓰고 LV_GITHUB_OFFLINE=1로 s2_index.py P01을 돌린다. path_front = PATH 맨 앞에 더할 폴더.
        -> (person.json, 레포 색인)"""
        os.makedirs(self.home, exist_ok=True)
        r = {"key": "tester__big", "full_name": "tester/big", "dir": clone, "default_branch": "main", "prs": False}
        r.update(repo or {})
        with open(os.path.join(self.home, "people.json"), "w", encoding="utf-8") as f:
            json.dump([{"pid": "P01", "login": "tester", "role": None, "level": None, "repos": [r]}], f)
        bin_dir, gh_mark = fake_gh(self.tmp)
        env = base_env(LV_S2_HOME=self.home, LV_GITHUB_OFFLINE="1", **env_extra)
        env["PATH"] = os.pathsep.join([*path_front, bin_dir, env["PATH"]])
        before = code_tree()
        p = subprocess.run([sys.executable, "-I", "-B", os.path.join(CODE, "s2_index.py"), "P01"],
                           env=env, capture_output=True, timeout=300)
        self.assertEqual(code_tree(), before, "s2 코드 폴더에 파일이 생기면 안 된다")
        self.assertFalse(os.path.exists(gh_mark), "gh를 부르면 안 된다")
        self.assertEqual(p.returncode, 0, p.stderr.decode("utf-8", "replace"))
        idx = os.path.join(self.home, "index", "P01")
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

    def test_partial_one_fetch_no_lazy(self):
        _, clone, _ = self.prepare()
        trace = os.path.join(self.tmp, "trace2.json")
        self.run_index(clone, GIT_TRACE2_EVENT=trace)
        names = []
        with open(trace, encoding="utf-8") as f:
            for line in f:
                ev = json.loads(line)
                if ev.get("event") == "cmd_name":
                    names.append(ev["name"])
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
        self.assertEqual(data["partial"], {"paths": [], "blobs": 0, "fetched": True, "numstat_ok": True})
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


if __name__ == "__main__":
    unittest.main()
