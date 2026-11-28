"""worker.py(요청 파일을 하나씩 처리하는 작업자) 시험.

- analyze는 가짜(analyze_fn 자리, main은 worker.A.analyze를 바꿈)만 쓴다. GitHub·git clone·네트워크는 쓰지 않는다.
  자체 점검과 작업자 시작 로그만 이 컴퓨터의 `git --version`을 부른다(또는 가짜로 바꾼다).
- main을 끝없이 돌리는 시험은 가짜 sleep이 StopLoop를 던져 멈춘다.
- 데이터 폴더는 시험마다 새 임시 폴더다. 요청·프로필은 합성 값이고, 토큰은 시험용 가짜 값이다.
- 자체 점검의 문법 오류·Linguist 자료 시험은 서비스 폴더의 임시 사본을 고친다(진짜 코드 폴더는 건드리지 않는다).
"""
import contextlib
import fcntl
import io
import json
import logging
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
import uuid
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
SERVICE = os.path.realpath(os.path.join(HERE, ".."))
sys.path.insert(0, SERVICE)

import worker  # noqa: E402
import ghapi  # noqa: E402  worker가 불러온 analyze가 s2 폴더를 sys.path에 넣는다(같은 RateLimited 클래스)

WORKER = os.path.join(SERVICE, "worker.py")
RESTART = "작업자가 다시 시작되어 중단됐습니다. 다시 요청해 주세요."
GENERIC = "분석 중 오류가 났습니다. 잠시 뒤 다시 시도해 주세요."
RATE_MESSAGE = r"^GitHub 호출 한도에 걸렸습니다\(\d+분 뒤 다시 시도\)$"
ISO_Z = r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ$"
FAKE_TOKEN = "ghp_" + "Fake0Worker1Token2For3Tests4Only"   # 시험용 가짜 값
SECRET_ENV = ("LV_GITHUB_TOKEN", "GH_TOKEN", "GITHUB_TOKEN", "ANTHROPIC_API_KEY")
# profileKey = sha256("staging:user-1")의 16진수 앞 32자(셸 `printf 'staging:user-1' | shasum -a 256`로 따로 구한 값)
KEY_USER_1 = "25fe06252fe0c17000ef04955a49a533"
KEY_KOREAN = "8a55dd4c3b626699afcdcc41d6678601"   # sha256("staging:사용자 1"), UTF-8
OLD_GIT = "git version 2.39.5 (Apple Git-154)\n"   # GIT_WANT(2.45)보다 옛 판
NEW_GIT = "git version 2.45.0\n"


def git_says(text):
    """`git --version`이 text를 내놓는 것처럼 subprocess.run 자리에 넣는 가짜 결과."""
    return subprocess.CompletedProcess(["git", "--version"], 0, stdout=text, stderr="")


class StopLoop(Exception):
    """끝없이 도는 main을 시험에서 멈춘다(가짜 sleep이 던짐)."""


def new_job(created="2026-11-28T00:00:00.000Z", status="queued", **extra):
    """웹이 만드는 요청(CONTRACT.md). id는 uuid v4."""
    job = {"id": str(uuid.uuid4()), "namespace": "staging", "subjectId": "user-1", "login": "tester",
           "input": "https://github.com/tester", "status": status, "createdAt": created}
    job.update(extra)
    return job


def fake_profile(request):
    """analyze가 돌려주는 profile과 같은 모양(합성 값)."""
    names = {"L": "프로그래밍 활용", "O": "운영 배포", "B": "백엔드 개발", "E": "데이터 엔지니어", "D": "데이터베이스",
             "F": "프론트엔드 앱", "A": "AI 기술"}
    cats = {code: {"name": name, "lv": 0.0, "unknown": 0} for code, name in names.items()}
    cats["L"].update(lv=1.3, languages={"Python": 1.3}, best="Python")
    return {"schema": "lv-stat-profile/1", "method": "lv-stat-s2-20261127",
            "labels": ["2단계 규칙", "LLM 보충 끔", "제안 기준", "본인 확인 안 됨"],
            "namespace": request["namespace"], "subjectId": request["subjectId"], "login": request["login"],
            "jobId": request["id"], "analyzedAt": "2026-11-28T00:05:00Z",
            "repos": {"found": 1, "analyzed": 1, "failed": 0, "notes": []}, "categories": cats}


def never_called(*args, **kwargs):
    raise AssertionError("analyze를 부르면 안 됨")


def snapshot(root):
    """폴더 아래 모든 경로 → 파일 내용(폴더는 None)."""
    out = {}
    for dirpath, dirnames, filenames in os.walk(root):
        for d in dirnames:
            out[os.path.relpath(os.path.join(dirpath, d), root)] = None
        for f in filenames:
            p = os.path.join(dirpath, f)
            with open(p, "rb") as fh:
                out[os.path.relpath(p, root)] = fh.read()
    return out


def setUpModule():
    # 실패 경로의 경고·오류 로그가 시험 출력에 섞이지 않게 한다(assertLogs는 그대로 잡는다)
    logging.getLogger("worker").addHandler(logging.NullHandler())


def clean_env(**extra):
    env = {k: v for k, v in os.environ.items() if k not in SECRET_ENV}
    env.update(extra)
    return env


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="lv-worker-test-")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.root = os.path.join(self.tmp, "lv-stat")
        self.dirs = worker.Dirs(self.root)

    def put(self, job, name=None):
        """요청 파일을 웹처럼 쓴다(worker.write_json을 쓰지 않음). -> 파일 이름"""
        name = name or job["id"] + ".json"
        with open(os.path.join(self.dirs.jobs, name), "w", encoding="utf-8") as f:
            json.dump(job, f, ensure_ascii=False)
        return name

    def read(self, *parts):
        with open(os.path.join(*parts), encoding="utf-8") as f:
            return json.load(f)

    def job_file(self, name):
        return self.read(self.dirs.jobs, name)


class FilesTest(Base):
    def test_profile_key_matches_contract(self):
        self.assertEqual(worker.profile_key("staging", "user-1"), KEY_USER_1)
        self.assertEqual(worker.profile_key("staging", "사용자 1"), KEY_KOREAN)

    def test_dirs_creates_jobs_profiles_work(self):
        root = os.path.join(self.tmp, "new", "lv-stat")
        d = worker.Dirs(root)
        self.assertEqual((d.jobs, d.profiles, d.work),
                         tuple(os.path.join(root, sub) for sub in ("jobs", "profiles", "work")))
        for sub in ("jobs", "profiles", "work"):
            self.assertTrue(os.path.isdir(os.path.join(root, sub)))

    def test_write_json_replaces_whole_file_and_leaves_no_temp(self):
        path = os.path.join(self.dirs.profiles, "p.json")
        worker.write_json(path, {"a": "한글", "n": 1})
        worker.write_json(path, {"b": 2})
        self.assertEqual(self.read(path), {"b": 2})
        self.assertEqual(os.listdir(self.dirs.profiles), ["p.json"])
        with open(path, encoding="utf-8") as f:
            self.assertNotIn("\\u", f.read())                 # 한글은 그대로(웹이 UTF-8로 읽음)
        worker.write_json(path, {"a": "한글"})
        with open(path, encoding="utf-8") as f:
            self.assertIn("한글", f.read())

    def test_write_json_failure_keeps_old_file(self):
        path = os.path.join(self.dirs.jobs, "x.json")
        worker.write_json(path, {"old": True})
        with self.assertRaises(TypeError):
            worker.write_json(path, {"bad": object()})        # JSON으로 못 바꿈(쓰다 실패)
        self.assertEqual(self.read(path), {"old": True})
        self.assertEqual(os.listdir(self.dirs.jobs), ["x.json"])   # 임시 파일이 남지 않음

    def test_read_json_missing_or_broken_is_none(self):
        broken = os.path.join(self.dirs.jobs, "broken.json")
        with open(broken, "w") as f:
            f.write('{"id": ')
        self.assertIsNone(worker.read_json(broken))
        self.assertIsNone(worker.read_json(os.path.join(self.dirs.jobs, "none.json")))


class QueueTest(Base):
    def test_next_job_takes_oldest_queued(self):
        later = new_job(created="2026-11-28T01:00:00.000Z")
        first = new_job(created="2026-11-28T09:30:00+09:00")      # = 00:30Z. 글자 순서로는 later보다 뒤
        running = new_job(created="2026-11-27T00:00:00Z", status="running")
        done = new_job(created="2026-11-26T00:00:00Z", status="done", profileKey=KEY_USER_1)
        undated = new_job(created="언제인지 모름")
        names = {k: self.put(j) for k, j in dict(later=later, first=first, running=running, done=done,
                                                    undated=undated).items()}
        self.assertEqual(worker.next_job(self.dirs), (names["first"], first))
        self.put(dict(first, status="done"))
        self.assertEqual(worker.next_job(self.dirs), (names["later"], later))
        self.put(dict(later, status="failed", error="x"))
        self.assertEqual(worker.next_job(self.dirs), (names["undated"], undated))   # 날짜를 못 읽으면 맨 뒤
        self.put(dict(undated, status="done"))
        self.assertIsNone(worker.next_job(self.dirs))

    def test_ignores_non_uuid_names(self):
        good = new_job(created="2026-11-28T05:00:00Z")
        good_name = self.put(good)
        early = "2026-11-01T00:00:00Z"
        v4 = lambda: str(uuid.uuid4())  # noqa: E731
        for name in ("not-a-uuid.json", str(uuid.uuid1()) + ".json", v4().upper() + ".json", v4() + ".json.tmp",
                     "." + v4() + ".json.abc123.tmp", v4() + ".txt", v4()):
            self.put(new_job(created=early), name=name)
        with open(os.path.join(self.dirs.jobs, v4() + ".json"), "w") as f:
            f.write('{"status": "queued", ')                     # 반쯤 쓴 파일
        self.put(["queued"], name=v4() + ".json")                # dict가 아님
        os.mkdir(os.path.join(self.dirs.jobs, v4() + ".json"))   # 폴더
        outside = os.path.join(self.tmp, "outside.json")
        with open(outside, "w") as f:
            json.dump(new_job(created=early), f)
        os.symlink(outside, os.path.join(self.dirs.jobs, v4() + ".json"))   # 링크는 읽지 않는다
        self.assertEqual(worker.list_jobs(self.dirs), [(good_name, good)])
        self.assertEqual(worker.next_job(self.dirs), (good_name, good))

    def test_recover_closes_running(self):
        running = new_job(status="running", stage="색인", progress={"done": 1, "total": 3},
                          startedAt="2026-11-28T00:01:00Z")
        queued = new_job(created="2026-11-28T00:02:00Z")
        done = new_job(status="done", stage="끝", profileKey=KEY_USER_1, finishedAt="2026-11-28T00:03:00Z")
        names = [self.put(j) for j in (running, queued, done)]
        os.makedirs(os.path.join(self.dirs.work, running["id"], "repos", "01-x"))
        with open(os.path.join(self.dirs.work, running["id"], "repos", "01-x", "a.py"), "w") as f:
            f.write("x = 1\n")
        with open(os.path.join(self.dirs.work, "stray.txt"), "w") as f:
            f.write("x")
        worker.recover(self.dirs)
        closed = self.job_file(names[0])
        self.assertEqual(closed["status"], "failed")
        self.assertEqual(closed["stage"], "실패")
        self.assertEqual(closed["error"], RESTART)
        self.assertIsNone(closed["progress"])
        self.assertRegex(closed["finishedAt"], ISO_Z)
        self.assertEqual(closed["startedAt"], "2026-11-28T00:01:00Z")
        self.assertEqual(self.job_file(names[1]), queued)       # 대기 중인 요청은 그대로(다음에 집음)
        self.assertEqual(self.job_file(names[2]), done)
        self.assertTrue(os.path.isdir(self.dirs.work))
        self.assertEqual(os.listdir(self.dirs.work), [])
        self.assertEqual(worker.next_job(self.dirs), (names[1], queued))


class ProcessTest(Base):
    def run_job(self, job, analyze_fn, max_minutes=20):
        name = self.put(job)
        worker.process(self.dirs, name, job, max_minutes, analyze_fn=analyze_fn)
        return name, self.job_file(name)

    def assert_failed(self, saved, message):
        self.assertEqual(saved["status"], "failed")
        self.assertEqual(saved["stage"], "실패")
        self.assertEqual(saved["error"], message)
        self.assertRegex(saved["finishedAt"], ISO_Z)
        self.assertNotIn("profileKey", saved)
        self.assertEqual(os.listdir(self.dirs.profiles), [])

    def test_invalid_login_fails(self):
        for login in ("", "-tester", "tester-", "te--ster", "a" * 40, "te ster", "../x", "tester\n", "ｔｅｓｔ",
                      "te_ster", "tester/repo"):
            with self.subTest(login=login):
                _, saved = self.run_job(new_job(login=login), never_called)
                self.assertEqual(saved["status"], "failed")
                self.assertEqual(saved["stage"], "실패")
                self.assertIn("GitHub 아이디", saved["error"])
        for login in ("a" * 39, "te-st-er", "A1", "x"):
            with self.subTest(login=login):
                _, saved = self.run_job(new_job(login=login), lambda request, *a: fake_profile(request))
                self.assertEqual(saved["status"], "done")

    def test_malformed_request_fails_without_analyze(self):
        job = new_job()
        for bad, name in ((dict(job, namespace=""), None), (dict(job, subjectId=None), None),
                          (dict(job, login=7), None), (dict(job, id="x"), None),
                          (job, str(uuid.uuid4()) + ".json")):          # 파일 이름과 id가 다름
            with self.subTest(bad=bad, name=name):
                fname = self.put(bad, name=name or job["id"] + ".json")
                worker.process(self.dirs, fname, bad, 20, analyze_fn=never_called)
                saved = self.job_file(fname)
                self.assertEqual(saved["status"], "failed")
                self.assertIn("요청 형식", saved["error"])
        self.assertEqual(os.listdir(self.dirs.profiles), [])

    def test_process_refuses_file_name_outside_jobs(self):
        job = new_job()
        for name in ("../" + job["id"] + ".json", job["id"] + ".json/../../x.json", "x.json"):
            with self.subTest(name=name):
                with self.assertRaises(ValueError):
                    worker.process(self.dirs, name, job, 20, analyze_fn=never_called)
        self.assertEqual(sorted(os.listdir(self.root)), ["jobs", "profiles", "work"])
        self.assertEqual(os.listdir(self.dirs.jobs), [])

    def test_process_success_writes_profile_and_key(self):
        calls = []

        def fake(request, work_root, deadline, progress):
            calls.append((request, work_root, deadline))
            return fake_profile(request)

        job = new_job()
        t = time.time()
        name, saved = self.run_job(job, fake)
        self.assertEqual(os.listdir(self.dirs.profiles), [KEY_USER_1 + ".json"])
        self.assertEqual(self.read(self.dirs.profiles, KEY_USER_1 + ".json"), fake_profile(job))
        self.assertEqual(saved["status"], "done")
        self.assertEqual(saved["stage"], "끝")
        self.assertEqual(saved["profileKey"], KEY_USER_1)
        self.assertRegex(saved["startedAt"], ISO_Z)
        self.assertRegex(saved["finishedAt"], ISO_Z)
        self.assertIsNone(saved["progress"])
        self.assertNotIn("error", saved)                       # error는 실패에만(null로도 쓰지 않음)
        for k in ("id", "namespace", "subjectId", "login", "input", "createdAt"):
            self.assertEqual(saved[k], job[k])
        (request, work_root, deadline), = calls
        self.assertEqual({k: request[k] for k in ("id", "namespace", "subjectId", "login")},
                         {k: job[k] for k in ("id", "namespace", "subjectId", "login")})
        self.assertEqual(work_root, self.dirs.work)
        self.assertAlmostEqual(deadline, t + 20 * 60, delta=5)
        self.assertEqual(sorted(os.listdir(self.dirs.jobs)), [name])   # 임시 파일이 남지 않음

    def test_profile_written_before_job_turns_done(self):
        """웹은 요청이 done이면 묻기를 멈추고 프로필을 읽는다. done이 된 순간 이 요청의 프로필이 이미 있어야 한다
        (같은 사람의 옛 프로필이나 없는 파일을 가리키면 안 됨)."""
        old = fake_profile(new_job())                                # 같은 사람의 지난 분석
        with open(os.path.join(self.dirs.profiles, KEY_USER_1 + ".json"), "w", encoding="utf-8") as f:
            json.dump(old, f, ensure_ascii=False)
        job = new_job()
        name = self.put(job)
        job_path = os.path.join(self.dirs.jobs, name)
        seen = []
        real = worker.write_json

        def spy(path, data):
            if os.path.abspath(path) == job_path and data.get("status") == "done":
                prof = worker.read_json(os.path.join(self.dirs.profiles, KEY_USER_1 + ".json"))
                seen.append(prof and prof.get("jobId"))
            return real(path, data)

        with mock.patch.object(worker, "write_json", side_effect=spy):
            worker.process(self.dirs, name, job, 20, analyze_fn=lambda request, *a: fake_profile(request))
        self.assertEqual(seen, [job["id"]])
        self.assertEqual(self.job_file(name)["status"], "done")

    def test_user_error_message_kept(self):
        msg = "공개 레포에서 이 계정의 커밋을 찾지 못했습니다."

        def fake(*a):
            raise worker.UserError(msg)

        _, saved = self.run_job(new_job(), fake)
        self.assert_failed(saved, msg)

    def test_rate_limited_job_fails_with_message(self):
        def fake(*a):
            raise ghapi.RateLimited(time.time() + 600)

        _, saved = self.run_job(new_job(), fake)
        self.assertRegex(saved["error"], RATE_MESSAGE)
        self.assert_failed(saved, saved["error"])

    def test_unexpected_error_generic_message(self):
        def fake(*a):
            raise RuntimeError("계산 실패: /secret/path detail-xyz")

        with self.assertLogs("worker", "ERROR") as logs:
            _, saved = self.run_job(new_job(), fake)
        self.assert_failed(saved, GENERIC)
        self.assertNotIn("detail-xyz", json.dumps(saved, ensure_ascii=False))
        self.assertIn("detail-xyz", "\n".join(logs.output))     # 자세한 것은 로그에만

    def test_bad_profile_or_profile_write_failure_is_generic(self):
        _, saved = self.run_job(new_job(), lambda *a: None)       # profile이 dict가 아님
        self.assert_failed(saved, GENERIC)
        os.rmdir(self.dirs.profiles)
        with open(self.dirs.profiles, "w") as f:                  # profiles가 폴더가 아니라 쓸 수 없음
            f.write("x")
        with self.assertLogs("worker", "ERROR"):
            _, saved = self.run_job(new_job(), lambda request, *a: fake_profile(request))
        self.assertEqual(saved["status"], "failed")
        self.assertEqual(saved["error"], GENERIC)

    def test_progress_updates_job_file(self):
        seen = []
        job = new_job()
        name = self.put(job)

        def fake(request, work_root, deadline, progress):
            seen.append(self.job_file(name))
            progress("색인", 1, 3)
            seen.append(self.job_file(name))
            progress("계산", None, None)
            seen.append(self.job_file(name))
            return fake_profile(request)

        worker.process(self.dirs, name, job, 20, analyze_fn=fake)
        start, index, calc = seen
        self.assertEqual(start["status"], "running")
        self.assertEqual(start["stage"], "레포 찾기")
        self.assertIsNone(start["progress"])
        self.assertRegex(start["startedAt"], ISO_Z)
        self.assertEqual(index["status"], "running")
        self.assertEqual(index["stage"], "색인")
        self.assertEqual(index["progress"], {"done": 1, "total": 3})
        self.assertEqual(calc["stage"], "계산")
        self.assertIsNone(calc["progress"])
        for saved in seen:
            self.assertNotIn("error", saved)
            self.assertNotIn("finishedAt", saved)
            self.assertNotIn("profileKey", saved)
        self.assertEqual(self.job_file(name)["status"], "done")


class MainTest(Base):
    def main(self, *args, env=None, stop_after_sleeps=None, on_sleep=None):
        """worker.main을 가짜 analyze로 돌린다. -> (종료 코드, analyze 호출 기록, 로그 줄)
        sleep은 가짜다(self.sleeps에 기록하고 on_sleep()을 부름). stop_after_sleeps번째 sleep에서 StopLoop로 멈추고,
        그때 종료 코드는 None."""
        calls = []
        self.sleeps = []

        def fake(request, work_root, deadline, progress):
            calls.append(dict(id=request["id"], deadline=deadline, s2home=os.environ.get("LV_S2_HOME")))
            return fake_profile(request)

        def sleep(seconds):
            self.sleeps.append(seconds)
            if on_sleep:
                on_sleep()
            if stop_after_sleeps is not None and len(self.sleeps) >= stop_after_sleeps:
                raise StopLoop

        with mock.patch.dict(os.environ, env or {}, clear=False), mock.patch.object(worker, "_setup_logging"), \
                mock.patch.object(worker.A, "analyze", fake), mock.patch.object(worker.time, "sleep", sleep), \
                self.assertLogs("worker", "INFO") as logs:
            if env is None:
                for k in SECRET_ENV:
                    os.environ.pop(k, None)
            try:
                rc = worker.main(["--data-dir", self.root, *args])
            except StopLoop:
                rc = None
            logs_out = list(logs.output)
        return rc, calls, logs_out

    def test_once_recovers_then_processes_oldest_queued(self):
        crashed = self.put(new_job(status="running", stage="색인"))
        old = new_job(created="2026-11-28T00:01:00Z")
        new = new_job(created="2026-11-28T00:02:00Z")
        old_name, new_name = self.put(old), self.put(new)
        t = time.time()
        rc, calls, _ = self.main("--once")
        self.assertEqual(rc, 0)
        self.assertEqual(self.job_file(crashed)["error"], RESTART)
        self.assertEqual(self.job_file(old_name)["status"], "done")
        self.assertEqual(self.job_file(new_name)["status"], "queued")    # --once는 하나만
        (call,) = calls
        self.assertEqual(call["id"], old["id"])
        self.assertAlmostEqual(call["deadline"], t + 20 * 60, delta=5)    # 기본 20분
        self.assertEqual(call["s2home"], self.dirs.work)                 # s2lib의 빈 HOME이 코드 폴더에 생기지 않게

    def test_max_minutes_option_sets_deadline(self):
        self.put(new_job())
        t = time.time()
        rc, calls, _ = self.main("--once", "--max-minutes", "1.5")
        self.assertEqual(rc, 0)
        self.assertAlmostEqual(calls[0]["deadline"], t + 90, delta=5)

    def test_once_without_jobs_exits_zero(self):
        rc, calls, _ = self.main("--once")
        self.assertEqual((rc, calls), (0, []))

    def test_start_log_says_token_yes_or_no_only(self):
        _, _, logs = self.main("--once", env={"LV_GITHUB_TOKEN": FAKE_TOKEN})
        text = "\n".join(logs)
        self.assertIn("token yes", text)
        self.assertNotIn(FAKE_TOKEN, text)
        self.assertNotIn(FAKE_TOKEN[4:], text)
        _, _, logs = self.main("--once")
        self.assertIn("token no", "\n".join(logs))

    def test_second_worker_on_same_data_dir_stops(self):
        """같은 데이터 폴더에 작업자가 이미 돌면, 그 작업자의 진행 중 요청을 닫거나 work를 비우지 않고 멈춘다."""
        running = self.put(new_job(status="running", stage="색인"))
        os.makedirs(os.path.join(self.dirs.work, "live"))
        with open(os.path.join(self.root, ".worker.lock"), "a") as held:
            fcntl.flock(held, fcntl.LOCK_EX | fcntl.LOCK_NB)
            rc, calls, _ = self.main("--once")
        self.assertNotEqual(rc, 0)
        self.assertEqual(calls, [])
        self.assertEqual(self.job_file(running)["status"], "running")
        self.assertEqual(os.listdir(self.dirs.work), ["live"])

    # --- git 판은 작업자 시작 로그(journal)에만. 자체 점검은 찍지 않는다(배포가 그 출력을 공개 CI 로그에 남김)
    def test_start_log_has_git_version(self):
        _, _, logs = self.main("--once")
        self.assertRegex("\n".join(logs), r"git version \d+\.\d+")

    def test_start_log_warns_on_old_git(self):
        with mock.patch.object(worker.subprocess, "run", return_value=git_says(OLD_GIT)):
            rc, _, logs = self.main("--once")
        self.assertEqual(rc, 0)                                   # 경고만 하고 돈다
        warnings = [line for line in logs if line.startswith("WARNING:")]
        self.assertTrue(any("2.39.5" in line and "2.45" in line for line in warnings), logs)

    def test_start_log_new_git_does_not_warn(self):
        with mock.patch.object(worker.subprocess, "run", return_value=git_says(NEW_GIT)):
            rc, _, logs = self.main("--once")
        self.assertEqual(rc, 0)
        self.assertIn("git version 2.45.0", "\n".join(logs))
        self.assertEqual([line for line in logs if line.startswith("WARNING:")], [])

    def test_start_log_without_git_says_so_and_keeps_running(self):
        with mock.patch.object(worker.subprocess, "run", side_effect=FileNotFoundError("git")):
            rc, _, logs = self.main("--once")
        self.assertEqual(rc, 0)
        self.assertTrue(any(line.startswith("ERROR:") and "git" in line for line in logs), logs)

    # --- 요청 파일 쓰기가 실패해도 대기열이 막히지 않는다
    def unwritable(self, name):
        """그 요청 파일 쓰기만 PermissionError로 실패하는 write_json. -> (가짜, 그 파일에 쓰려던 status 기록)"""
        path = os.path.join(self.dirs.jobs, name)
        real = worker.write_json
        tried = []

        def flaky(p, data):
            if os.path.abspath(p) == path:
                tried.append(data.get("status"))
                raise PermissionError(13, "Permission denied", path)
            return real(p, data)

        return flaky, tried

    def test_job_file_write_failure_skips_that_job_and_keeps_queue_moving(self):
        """요청 파일을 못 쓰면 그 요청은 queued로 남는다. 작업자가 죽으면 systemd가 다시 켜고 같은 요청을 또 집어
        모든 사람이 막히므로, 그 이름을 이 프로세스가 도는 동안 건너뛰고 --poll 뒤 다음 요청으로 간다."""
        stuck = new_job(created="2026-11-28T00:01:00Z")
        other = new_job(created="2026-11-28T00:02:00Z")
        stuck_name, other_name = self.put(stuck), self.put(other)
        flaky, tried = self.unwritable(stuck_name)
        other_at_sleep = []
        with mock.patch.object(worker, "write_json", side_effect=flaky):
            rc, calls, logs = self.main("--poll", "7", stop_after_sleeps=3, env={"LV_GITHUB_TOKEN": FAKE_TOKEN},
                                        on_sleep=lambda: other_at_sleep.append(self.job_file(other_name)["status"]))
        self.assertIsNone(rc)                                     # 예외로 끝나지 않고 계속 돎(가짜 sleep이 멈춤)
        self.assertEqual(tried, ["running"])                      # 막힌 요청은 한 번만 집음
        self.assertEqual(self.job_file(stuck_name), stuck)        # 그대로 queued
        self.assertEqual(self.job_file(other_name)["status"], "done")
        self.assertEqual([c["id"] for c in calls], [other["id"]])
        self.assertEqual(self.sleeps, [7, 7, 7])
        self.assertEqual(other_at_sleep, ["queued", "done", "done"])   # 실패 뒤 --poll 쉬고 다음 요청으로, 그 뒤 대기
        failed = [line for line in logs if stuck_name in line]
        self.assertTrue(failed and all(line.startswith("ERROR:") for line in failed), logs)
        self.assertIn("PermissionError", "\n".join(failed))
        text = "\n".join(logs)
        self.assertNotIn(self.dirs.jobs, "\n".join(failed))      # 경로는 남기지 않고 파일 이름만
        self.assertNotIn(FAKE_TOKEN, text)
        self.assertNotIn(FAKE_TOKEN[4:], text)

    def test_once_job_file_write_failure_returns_one(self):
        stuck_name = self.put(new_job())
        flaky, tried = self.unwritable(stuck_name)
        with mock.patch.object(worker, "write_json", side_effect=flaky):
            rc, calls, logs = self.main("--once")
        self.assertEqual((rc, calls, tried), (1, [], ["running"]))
        self.assertEqual(self.job_file(stuck_name)["status"], "queued")
        self.assertTrue(any(line.startswith("ERROR:") and stuck_name in line for line in logs), logs)

    def test_recover_write_failure_does_not_stop_worker(self):
        """시작할 때 닫지 못한 진행 중 요청이 있어도 작업자는 멈추지 않는다(멈추면 systemd가 다시 켜도 또 멈춤)."""
        stuck_name = self.put(new_job(status="running", stage="색인", created="2026-11-28T00:00:00Z"))
        crashed_name = self.put(new_job(status="running", stage="색인", created="2026-11-28T00:00:30Z"))
        queued = new_job(created="2026-11-28T00:01:00Z")
        queued_name = self.put(queued)
        flaky, tried = self.unwritable(stuck_name)
        with mock.patch.object(worker, "write_json", side_effect=flaky):
            rc, calls, logs = self.main("--once")
        self.assertEqual(rc, 0)
        self.assertEqual(tried, ["failed"])
        self.assertEqual(self.job_file(stuck_name)["status"], "running")
        self.assertEqual(self.job_file(crashed_name)["error"], RESTART)   # 다른 요청은 닫음
        self.assertEqual(self.job_file(queued_name)["status"], "done")
        self.assertEqual([c["id"] for c in calls], [queued["id"]])
        failed = [line for line in logs if stuck_name in line and line.startswith("ERROR:")]
        self.assertTrue(failed, logs)
        self.assertNotIn(self.dirs.jobs, "\n".join(failed))


class SelfCheckTest(Base):
    def check(self, root=None, **kw):
        out = io.StringIO()
        with contextlib.redirect_stdout(out), self.assertLogs("worker", "INFO") as logs:
            rc = worker.self_check(root or self.root, **kw)
        return rc, out.getvalue(), "\n".join(logs.output)

    def copy_service(self):
        dest = os.path.join(self.tmp, "release", "service")
        shutil.copytree(SERVICE, dest, ignore=shutil.ignore_patterns("__pycache__", ".emptyhome"))
        return dest

    def test_self_check_ok(self):
        running = self.put(new_job(status="running", stage="색인"))
        with open(os.path.join(self.dirs.profiles, KEY_USER_1 + ".json"), "w") as f:
            f.write("{}")
        os.makedirs(os.path.join(self.dirs.work, "live"))
        before = snapshot(self.root)
        rc, out, logs = self.check()
        self.assertEqual((rc, out), (0, "OK\n"))
        self.assertEqual(snapshot(self.root), before)           # recover하지 않고 jobs·profiles·work를 건드리지 않음
        self.assertEqual(self.job_file(running)["status"], "running")
        self.assertNotIn("git version", out + logs)              # git 판은 작업자 시작 로그에만

    def test_self_check_cli_prints_ok_and_leaves_code_alone(self):
        """배포 스크립트처럼 python3 -I -u로 부른다. 코드 폴더는 __pycache__가 없는 새 사본이다(남아 있던 컴파일 파일이
        있으면 새로 생겨도 못 본다)."""
        code = self.copy_service()
        before = snapshot(code)
        p = subprocess.run([sys.executable, "-I", "-u", os.path.join(code, "worker.py"), "--data-dir", self.root,
                            "--self-check"], capture_output=True, text=True, timeout=120,
                           env=clean_env(LV_GITHUB_TOKEN=FAKE_TOKEN))
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertEqual(p.stdout, "OK\n")
        self.assertNotIn("git version", p.stderr)
        self.assertNotIn(FAKE_TOKEN, p.stdout + p.stderr)
        self.assertEqual(snapshot(code), before)                # 컴파일 파일(__pycache__)·빈 HOME이 생기지 않음

    def test_self_check_cli_on_this_service_folder(self):
        p = subprocess.run([sys.executable, "-I", "-u", WORKER, "--data-dir", self.root, "--self-check"],
                           capture_output=True, text=True, timeout=120, env=clean_env())
        self.assertEqual((p.returncode, p.stdout), (0, "OK\n"), p.stdout + p.stderr)

    def test_self_check_output_never_has_git_version(self):
        """배포 스크립트는 자체 점검 출력을 공개 CI 로그에 남긴다. 받은 레포를 여는 git의 판은 stdout에도 stderr에도
        찍지 않는다(그 판에 맞는 약점을 고르기 쉬움). 이 컴퓨터의 git과, 2.45보다 옛 판인 가짜 git 둔 다로 본다."""
        real = subprocess.run(["git", "--version"], capture_output=True, text=True, timeout=30, env=clean_env())
        self.assertEqual(real.returncode, 0, real.stderr)
        bin_dir = os.path.join(self.tmp, "bin")
        os.mkdir(bin_dir)
        fake_git = os.path.join(bin_dir, "git")
        with open(fake_git, "w") as f:
            f.write('#!/bin/sh\n[ "$1" = --version ] && { echo "git version 2.39.5.synthetic"; exit 0; }\nexit 1\n')
        os.chmod(fake_git, 0o755)
        real_version = re.search(r"\d+\.\d+(?:\.\d+)?", real.stdout).group(0)
        for label, env, version in (("이 컴퓨터의 git", clean_env(), real_version),
                                    ("옛 판 가짜 git", clean_env(PATH=bin_dir + os.pathsep + os.environ["PATH"]),
                                     "2.39.5.synthetic")):
            with self.subTest(label):
                p = subprocess.run([sys.executable, "-I", "-u", WORKER, "--data-dir", self.root, "--self-check"],
                                   capture_output=True, text=True, timeout=120, env=env)
                self.assertEqual((p.returncode, p.stdout), (0, "OK\n"), p.stdout + p.stderr)
                for stream in (p.stdout, p.stderr):
                    self.assertNotIn("git version", stream)
                    self.assertNotIn(version, stream)

    def test_self_check_reports_bad_syntax(self):
        code = self.copy_service()
        with open(os.path.join(code, "s2", "bad_syntax.py"), "w") as f:
            f.write("def broken(:\n    pass\n")
        p = subprocess.run([sys.executable, "-I", "-u", os.path.join(code, "worker.py"), "--data-dir", self.root,
                            "--self-check"], capture_output=True, text=True, timeout=120, env=clean_env())
        self.assertNotEqual(p.returncode, 0)
        self.assertIn("bad_syntax.py", p.stdout)
        self.assertNotIn("OK", p.stdout.split())
        self.assertFalse(os.path.exists(os.path.join(code, "s2", "__pycache__")))   # 메모리에서만 compile

    def test_self_check_reports_missing_or_empty_linguist_data(self):
        code = self.copy_service()
        self.assertEqual(self.check(code_dir=code)[0], 0)
        ling = os.path.join(code, "s2", "data", "linguist")
        for name in ("languages.yml", "vendor.yml", "documentation.yml"):
            path = os.path.join(ling, name)
            with open(path, "rb") as f:
                saved = f.read()
            for broken in ("empty", "missing"):
                with self.subTest(name=name, broken=broken):
                    if broken == "empty":
                        open(path, "w").close()
                    else:
                        os.remove(path)
                    rc, out, _ = self.check(code_dir=code)
                    self.assertEqual(rc, 1)
                    self.assertIn(name, out)
            with open(path, "wb") as f:
                f.write(saved)

    @unittest.skipIf(os.geteuid() == 0, "root는 폴더 권한을 무시한다")
    def test_self_check_reports_unwritable_or_missing_data_dir(self):
        os.chmod(self.root, 0o500)
        self.addCleanup(os.chmod, self.root, 0o700)
        rc, out, _ = self.check()
        self.assertEqual(rc, 1)
        self.assertIn(self.root, out)
        os.chmod(self.root, 0o700)
        os.chmod(self.dirs.jobs, 0o500)
        self.addCleanup(os.chmod, self.dirs.jobs, 0o700)
        rc, out, _ = self.check()
        self.assertEqual(rc, 1)
        self.assertIn("jobs", out)
        rc, out, _ = self.check(root=os.path.join(self.tmp, "none"))
        self.assertEqual(rc, 1)

    def test_self_check_fails_without_git(self):
        with mock.patch.object(worker.subprocess, "run", side_effect=FileNotFoundError("git")):
            rc, out, _ = self.check()
        self.assertEqual(rc, 1)
        self.assertIn("git", out)

    def test_self_check_old_or_new_git_passes_without_version(self):
        """옛 판 경고는 작업자 시작 로그가 한다(MainTest). 자체 점검은 판도 경고도 남기지 않고 통과한다."""
        for text, version in ((OLD_GIT, "2.39.5"), (NEW_GIT, "2.45.0")):
            with self.subTest(version=version):
                with mock.patch.object(worker.subprocess, "run", return_value=git_says(text)):
                    rc, out, logs = self.check()
                self.assertEqual((rc, out), (0, "OK\n"))
                self.assertNotIn(version, out + logs)
                self.assertNotIn("git version", out + logs)
                self.assertNotIn("WARNING", logs)

    def test_self_check_fails_when_git_does_not_work(self):
        broken = subprocess.CompletedProcess(["git", "--version"], 1, stdout="", stderr="error")
        with mock.patch.object(worker.subprocess, "run", return_value=broken):
            rc, out, _ = self.check()
        self.assertEqual(rc, 1)
        self.assertIn("git", out)

    def test_old_python_fails(self):
        with mock.patch.object(worker, "_py_version", return_value=(3, 9, 18)):
            rc, out, _ = self.check()
        self.assertEqual(rc, 1)
        self.assertIn("3.10", out)


if __name__ == "__main__":
    unittest.main()
