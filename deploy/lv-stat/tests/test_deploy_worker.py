"""deploy_worker.sh 시험: 가짜 HOME·가짜 sudo/systemctl 로만 돈다(실제 서비스·EC2·GitHub 는 안 건드림).

스크립트가 PATH 로 찾아 부르는 외부 명령(TRACED·STUBS)은 기록용 껍데기를 거친다. 껍데기는 인자를 argv.log 에
적고, 자기 환경에 시험용 토큰 값이 있으면 ENV-LEAK 를 적은 뒤 진짜 명령(또는 가짜 동작)을 부른다. run_script 는
돌릴 때마다 토큰 값이 출력·외부 명령의 인자·외부 명령의 환경에 없는지 본다. 목록에 없는 명령과 절대 경로로
부르는 명령(/usr/bin/printf 등)은 이 방법으로 보지 못한다.
가짜 journalctl·systemctl status 는 합성 작업자 로그를 내놓는다. 출력은 공개 CI 로그가 되므로 run_script 는
그 로그가 출력에 나오지 않는지도 본다.
가짜 systemctl 은 systemd 처럼 서비스 파일을 daemon-reload 때 읽고, restart 때 current 가 가리키는 판을 켠다.
그 판에 CRASH_LOOP 표시가 있으면 물을 때마다 active 라고 답하지만 NRestarts 가 는다(확인하는 사이 죽었다가 다시 켜짐).
"""
import os
from pathlib import Path
import shutil
import stat
import subprocess
import tempfile
import time
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / 'deploy_worker.sh'
SVC = 'career-lv-worker-staging'
TOKEN = 'ghp_' + 'Fake0Token1Value2For3Tests4Only5xyz'   # 시험용 가짜 값
FAILED_TOKEN = 'ghp_' + 'Second0Fake1Token2' * 2        # 시험용 가짜 값(실패해 되돌린 배포가 가져온 토큰)
ROTATED_TOKEN = 'ghp_' + 'Third0Fake1Token3' * 2        # 시험용 가짜 값(바꾼 토큰)
SECRETS = (TOKEN, FAILED_TOKEN, ROTATED_TOKEN)
# 작업자 로그(journal)의 합성 예: 지난 작업자가 분석한 계정·레포 이름이 남는다. 공개 CI 로그에 옮기면 안 된다
WORKER_LOG_LOGIN = 'synthetic-login-q7z'
WORKER_LOG = (f'lv-worker[4242]: job 7f3c failed: {WORKER_LOG_LOGIN}/synthetic-repo-q7z\n'
              f'lv-worker[4242]: Traceback: work/7f3c/{WORKER_LOG_LOGIN}/synthetic-repo-q7z/README.md\n')
FAKE_GIT_VERSION = '2.99.0.synthetic'   # 가짜 git 이 알려 주는 판
PATH0 = os.environ['PATH']
BASH = shutil.which('bash', path=PATH0)
GIT = shutil.which('git', path=PATH0)
# 기록용 껍데기를 씌울 외부 명령: 스크립트가 쓰는 것과, 고치다가 토큰을 인자로 넘기기 쉬운 것
TRACED = ('awk', 'basename', 'bash', 'cat', 'chmod', 'cmp', 'cp', 'curl', 'cut', 'date', 'dd', 'df', 'dirname',
          'env', 'expr', 'find', 'free', 'grep', 'head', 'id', 'install', 'ln', 'ls', 'mkdir', 'mktemp', 'mv',
          'printf', 'python3', 'readlink', 'realpath', 'rm', 'sed', 'seq', 'sh', 'sort', 'stat', 'tail', 'tee',
          'timeout', 'touch', 'tr', 'wc', 'xargs')


def traced(name):
    """기록 줄(sh). 찾을 토큰 값은 needles 파일에서 읽는다(이 프로세스의 인자·환경에 올리지 않음)."""
    return ('#!/bin/sh\n'
            f'printf "%s\\n" "{name} $*" >> "$STUB_DIR/argv.log"\n'
            'exported=$(export -p)\n'
            'while IFS= read -r needle; do\n'
            f'  case "$exported" in *"$needle"*) printf "%s\\n" "ENV-LEAK {name}" >> "$STUB_DIR/argv.log" ;; esac\n'
            'done < "$STUB_DIR/needles"\n')


STUBS = {
    'sudo': '[ "$1" = -n ] && shift\nexec "$@"\n',
    'systemctl': 'flag=no; [ -n "${LV_GITHUB_TOKEN+x}" ] && flag=yes\n'
                 'echo "$* token-env=$flag" >> "$STUB_DIR/systemctl.log"\n'
                 # NRestarts: systemd 가 서비스를 스스로 다시 켠 횟수
                 'n=0; [ -f "$STUB_DIR/nrestarts" ] && read -r n < "$STUB_DIR/nrestarts"\n'
                 'case "$1" in\n'
                 # 계속 죽는 판: 물을 때마다 active 지만, 지난번 물은 뒤로 죽었다가 한 번 더 다시 켜져 있다
                 '  is-active) loop=no; [ -f "$STUB_DIR/crash-loop" ] && read -r loop < "$STUB_DIR/crash-loop"\n'
                 '    [ "$loop" = yes ] && echo $((n + 1)) > "$STUB_DIR/nrestarts"\n'
                 '    [ "$(cat "$STUB_DIR/active")" = yes ] && exit 0; exit 3 ;;\n'
                 # show -p … --value 은 NRestarts 숫자, 그 밖은 멈춘 서비스의 상태 줄
                 '  show) case " $* " in *" --value "*) echo "$n" ;;\n'
                 '    *) printf "ActiveState=failed\\nSubState=failed\\nResult=exit-code\\nExecMainStatus=1\\nNRestarts=%s\\n" "$n" ;; esac ;;\n'
                 # 진짜 systemctl status 처럼 -n 0 이 아니면 작업자 로그 끝부분도 보여 준다
                 '  status) case " $* " in *" -n 0 "*|*" -n0 "*|*" --lines=0 "*) ;; *) cat "$STUB_DIR/journal" ;; esac ;;\n'
                 # systemd 처럼: 서비스 파일은 daemon-reload 때 읽고, restart 는 그때 읽어 둔 설정으로 켠다
                 f'  daemon-reload) mm=none; u="$LV_UNIT_DIR/{SVC}.service"\n'
                 '    if [ -f "$u" ]; then while IFS= read -r l; do case "$l" in MemoryMax=*) mm=$l ;; esac; done < "$u"; fi\n'
                 '    echo "$mm" > "$STUB_DIR/loaded" ;;\n'
                 '  restart) mm=none; [ -f "$STUB_DIR/loaded" ] && read -r mm < "$STUB_DIR/loaded"\n'
                 '    echo "$mm" >> "$STUB_DIR/restarts.log"\n'
                 # ExecStart 처럼 current 가 가리키는 판을 켠다. 그 판이 계속 죽는 판(CRASH_LOOP)인지 적어 둔다
                 '    loop=no; [ -f "$HOME/lv-stat/staging/current/service/CRASH_LOOP" ] && loop=yes\n'
                 '    echo "$loop" > "$STUB_DIR/crash-loop" ;;\n'
                 'esac\nexit 0\n',
    'journalctl': 'cat "$STUB_DIR/journal"\n',
    'sleep': 'exit 0\n',
    'git': f'[ "$1" = --version ] && {{ echo "git version {FAKE_GIT_VERSION}"; exit 0; }}\n'
           + (f'exec "{GIT}" "$@"\n' if GIT else 'exit 127\n'),
}

# 가짜 작업자: 자체 점검이면 진짜처럼 결과(OK·실패 이유)는 stdout에, 로그는 stderr에 쓴다. 로그에 git 판을 넣어
# 스크립트가 stderr를 CI 로그에 옮기면 test_server_summary_leaves_out_git_version 이 잡게 한다
SELF_CHECK_LOG = f'INFO worker: 자체 점검(가짜): git version {FAKE_GIT_VERSION}'
FAKE_WORKER = f'''import os, sys
here = os.path.dirname(os.path.abspath(__file__))
if '--self-check' in sys.argv:
    data = sys.argv[sys.argv.index('--data-dir') + 1]
    os.makedirs(data, exist_ok=True)
    with open(os.path.join(data, 'selfcheck-env.txt'), 'w') as f:
        f.write('token-present' if 'LV_GITHUB_TOKEN' in os.environ else 'token-absent')
    sys.stderr.write({SELF_CHECK_LOG!r} + '\\n')
    if os.path.exists(os.path.join(here, 'FAIL_SELF_CHECK')):
        print('자체 점검 실패: 가짜 이유'); sys.exit(1)
    print('OK'); sys.exit(0)
'''


def sha(n):
    return f'{n:040x}'


def write_exe(path, body):
    path.write_text(body)
    path.chmod(0o755)


class DeployWorkerTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # 껍데기·가짜 명령은 한 번만 만든다(macOS 는 새 실행 파일을 처음 돌릴 때 느림). 기록은 시험마다 따로(STUB_DIR)
        cls.bin_temp = tempfile.TemporaryDirectory()
        cls.bin = Path(cls.bin_temp.name).resolve()
        for name in TRACED:
            real = shutil.which(name, path=PATH0)
            if real:   # 이 컴퓨터에 없는 명령(macOS 의 free·timeout 등)은 없는 그대로 둔다
                write_exe(cls.bin / name, traced(name) + f'exec "{real}" "$@"\n')
        for name, body in STUBS.items():
            write_exe(cls.bin / name, traced(name) + body)

    @classmethod
    def tearDownClass(cls):
        cls.bin_temp.cleanup()

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name).resolve()
        self.home, self.units, self.stub = root / 'home', root / 'units', root / 'stub'
        for d in (self.home, self.units, self.stub):
            d.mkdir()
        (self.stub / 'needles').write_text(''.join(s + '\n' for s in SECRETS))
        (self.stub / 'journal').write_text(WORKER_LOG)
        self.set_active(True)
        self.src = self.make_source(root / 'src')
        self.base = self.home / 'lv-stat' / 'staging'
        self.envfile = self.home / 'career-data-staging' / 'lv-worker.env'
        self.unit = self.units / f'{SVC}.service'

    def tearDown(self):
        self.temp.cleanup()

    def make_source(self, path, fail=False, crash_loop=False):
        path.mkdir(parents=True)
        (path / 'worker.py').write_text(FAKE_WORKER, encoding='utf-8')
        (path / '__pycache__').mkdir()
        (path / '__pycache__' / 'junk.pyc').write_bytes(b'x')
        if fail:
            (path / 'FAIL_SELF_CHECK').write_text('1')
        if crash_loop:   # 자체 점검은 통과하지만, 켜 두면 계속 죽고 systemd 가 다시 켜는 판(가짜 systemctl 이 봄)
            (path / 'CRASH_LOOP').write_text('1')
        return path

    def set_active(self, active):
        (self.stub / 'active').write_text('yes' if active else 'no')

    def read_stub(self, name):
        p = self.stub / name
        return p.read_text() if p.exists() else ''

    def log(self):
        return self.read_stub('systemctl.log')

    def loaded_at_restart(self):
        """restart 할 때마다 systemd(가짜)가 읽어 두었던 서비스 설정의 MemoryMax 줄"""
        return self.read_stub('restarts.log').splitlines()

    def holders(self, secret):
        """HOME 아래에서 그 값을 담은 파일(링크 제외)"""
        return [p for p in self.home.rglob('*') if p.is_file() and not p.is_symlink() and secret.encode() in p.read_bytes()]

    def run_script(self, commit, src=None, token=None, **extra):
        env = {k: v for k, v in os.environ.items() if k not in ('LV_GITHUB_TOKEN', 'TARGET', 'DEPLOY_ENV', 'CAREER_ENV')}
        env.update(HOME=str(self.home), PATH=f'{self.bin}:{PATH0}', STUB_DIR=str(self.stub),
                   GITHUB_REF_NAME='develop', LV_UNIT_DIR=str(self.units), LV_CHECK_ROUNDS='2')
        if token is not None:
            env['LV_GITHUB_TOKEN'] = token
        env.update(extra)
        r = subprocess.run([BASH, str(SCRIPT), commit, str(src or self.src)], env=env,
                           capture_output=True, text=True, timeout=120)
        self.assert_nothing_leaks(r)
        return r

    def assert_nothing_leaks(self, r):
        """토큰 값은 셸 변수로만 든다: 출력·외부 명령의 인자·외부 명령의 환경 어디에도 없다.
        출력(CI 로그, 공개)에는 작업자 로그도 옮기지 않는다. 실패하면 걸린 줄만 보여 준다."""
        out, argv = (r.stdout + r.stderr).splitlines(), self.read_stub('argv.log').splitlines()
        self.assertEqual([l for l in out if any(s in l for s in SECRETS)], [], '토큰 값이 출력에 나옴')
        self.assertEqual([l for l in argv if any(s in l for s in SECRETS)], [], '토큰 값이 외부 명령의 인자에 나옴')
        self.assertEqual([l for l in argv if l.startswith('ENV-LEAK')], [], '토큰 값이 외부 명령의 환경에 나옴')
        self.assertEqual([l for l in out if WORKER_LOG_LOGIN in l], [], '작업자 로그가 CI 로그에 나옴')

    def current(self):
        link = self.base / 'current'
        return Path(os.path.realpath(link)).name if link.is_symlink() else None

    def switch_current(self, commit):
        """README '되돌리기' 처럼 손으로 current 를 그 판으로 바꾼다(ln -sfn … current.new && mv -Tf current.new current)"""
        new = self.base / 'current.new'
        os.symlink(self.base / 'releases' / commit, new)
        os.replace(new, self.base / 'current')

    def releases(self):
        return sorted(p.name for p in (self.base / 'releases').iterdir())

    def assert_untouched(self, result):
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertFalse((self.home / 'lv-stat').exists())
        self.assertFalse((self.home / 'career-data-staging').exists())
        self.assertEqual(list(self.units.iterdir()), [])
        self.assertEqual(self.log(), '')

    # --- 운영 거부 --------------------------------------------------------------
    def test_refuses_anything_but_develop(self):
        for ref in ('main', '', 'feature/lv-stat'):
            with self.subTest(ref=ref):
                self.assert_untouched(self.run_script(sha(1), GITHUB_REF_NAME=ref))

    def test_refuses_production_target_even_on_develop(self):
        for key in ('TARGET', 'DEPLOY_ENV', 'CAREER_ENV'):
            with self.subTest(key=key):
                self.assert_untouched(self.run_script(sha(1), **{key: 'production'}))

    def test_refuses_malformed_commit(self):
        self.assert_untouched(self.run_script('production'))
        self.assert_untouched(self.run_script('abc123'))

    # --- 토큰 파일 --------------------------------------------------------------
    def test_token_file_is_owner_only_and_value_never_printed_or_inherited(self):
        r = self.run_script(sha(1), token=f'  {TOKEN}\n')        # 출력·인자·자식 환경은 run_script 가 본다
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.envfile.read_text(), f'LV_GITHUB_TOKEN={TOKEN}\n')
        self.assertEqual(stat.S_IMODE(self.envfile.stat().st_mode), 0o600)
        self.assertNotIn('token-env=yes', self.log())             # sudo·systemctl 에 안 넘김
        self.assertEqual((self.home / 'career-data-staging/lv-stat/selfcheck-env.txt').read_text(), 'token-absent')
        self.assertEqual(self.holders(TOKEN), [self.envfile])     # 사본·임시 파일이 남지 않음
        self.assertNotIn(TOKEN, self.unit.read_text())

    def test_new_token_replaces_old_and_leaves_no_copy_of_old(self):
        self.assertEqual(self.run_script(sha(1), token=TOKEN).returncode, 0)
        r = self.run_script(sha(2), token=ROTATED_TOKEN)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.current(), sha(2))
        self.assertEqual(self.envfile.read_text(), f'LV_GITHUB_TOKEN={ROTATED_TOKEN}\n')
        self.assertEqual(stat.S_IMODE(self.envfile.stat().st_mode), 0o600)
        self.assertEqual(self.holders(ROTATED_TOKEN), [self.envfile])
        self.assertEqual(self.holders(TOKEN), [])                 # 옛 토큰의 사본(되돌리기용)도 남지 않음
        self.assertFalse((self.base / 'lv-worker.env.prev').exists())

    def test_empty_secret_keeps_existing_token_file(self):
        self.envfile.parent.mkdir(parents=True)
        self.envfile.write_text('LV_GITHUB_TOKEN=kept\n')
        self.envfile.chmod(0o644)
        r = self.run_script(sha(1), token='')
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.envfile.read_text(), 'LV_GITHUB_TOKEN=kept\n')
        self.assertEqual(stat.S_IMODE(self.envfile.stat().st_mode), 0o600)

    def test_empty_secret_without_file_creates_nothing(self):
        r = self.run_script(sha(1))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertFalse(self.envfile.exists())
        self.assertIn(f'EnvironmentFile=-{self.envfile}', self.unit.read_text())

    def test_malformed_token_is_refused_without_echo(self):
        bad = 'ghp_bad value with spaces'
        r = self.run_script(sha(1), token=bad)
        self.assertEqual(r.returncode, 2)
        self.assertNotIn(bad, r.stdout + r.stderr)
        self.assertNotIn('bad value', r.stdout + r.stderr)
        self.assertFalse(self.envfile.exists())
        self.assertEqual(self.log(), '')

    # --- 서비스 파일·멱등 ----------------------------------------------------------
    def test_unit_file_contents(self):
        r = self.run_script(sha(1))
        self.assertEqual(r.returncode, 0, r.stderr)
        text = self.unit.read_text()
        lines = text.splitlines()
        self.assertIn(f'User={subprocess.check_output(["id", "-un"], text=True).strip()}', lines)
        self.assertIn(f'WorkingDirectory={self.base}/current', lines)
        exec_line = next(l for l in lines if l.startswith('ExecStart='))
        python = exec_line.split('=', 1)[1].split()[0]
        self.assertTrue(os.path.isabs(python), exec_line)
        self.assertTrue(exec_line.endswith(f'-I -u {self.base}/current/service/worker.py --data-dir {self.home}/career-data-staging/lv-stat'), exec_line)
        # OOMPolicy=continue: 메모리 한도(MemoryMax)로 자식(색인 등) 하나가 죽어도 유닛 전체를 멈추지 않는다(그 단계만 실패 메모)
        for want in ('Restart=on-failure', 'Nice=10', 'IOSchedulingClass=idle', 'CPUQuota=100%', 'MemoryHigh=400M',
                     'MemoryMax=512M', 'OOMPolicy=continue', f'EnvironmentFile=-{self.envfile}'):
            self.assertIn(want, lines)
        # 메모리 한도 줄은 이 둘뿐이다(같은 이름이 또 있으면 systemd 는 뒤의 값을 쓴다)
        self.assertEqual([l for l in lines if l.startswith('Memory')], ['MemoryHigh=400M', 'MemoryMax=512M'])
        self.assertIn('「Claude 임시값」', text)
        self.assertEqual(self.current(), sha(1))
        self.assertFalse((self.base / 'releases' / sha(1) / 'service' / '__pycache__').exists())
        for call in ('daemon-reload', f'enable --quiet {SVC}', f'restart {SVC}'):
            self.assertIn(call, self.log())

    def test_same_commit_twice_changes_nothing_but_restarts(self):
        self.assertEqual(self.run_script(sha(1), token=TOKEN).returncode, 0)
        release = self.base / 'releases' / sha(1)
        release_inode = release.stat().st_ino
        os.utime(release / 'service' / 'worker.py', (1, 1))
        os.utime(self.unit, (1, 1))
        os.utime(self.envfile, (1, 1))
        unit_before = self.unit.read_text()
        r = self.run_script(sha(1), token=TOKEN)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(release.stat().st_ino, release_inode)                      # 도는 판의 폴더를 지우고 새로 만들지 않음
        self.assertEqual((release / 'service' / 'worker.py').stat().st_mtime, 1)    # 판을 다시 복사하지 않음
        self.assertEqual(self.unit.stat().st_mtime, 1)          # 서비스 파일을 다시 쓰지 않음
        self.assertEqual(self.envfile.stat().st_mtime, 1)       # 같은 토큰이면 파일을 다시 쓰지 않음
        self.assertEqual(self.unit.read_text(), unit_before)
        self.assertEqual(self.log().count(f'restart {SVC}'), 2)
        self.assertEqual(self.releases(), [sha(1)])
        self.assertEqual(self.current(), sha(1))

    # --- 되돌리기 ---------------------------------------------------------------
    def test_rolls_back_release_unit_and_token_when_new_release_is_not_active(self):
        self.assertEqual(self.run_script(sha(1), token=TOKEN).returncode, 0)
        old_unit = self.unit.read_text().replace('MemoryMax=512M', 'MemoryMax=999M')    # 옛 배포가 쓴 다른 설정
        self.unit.write_text(old_unit)
        self.set_active(False)
        r = self.run_script(sha(2), token=FAILED_TOKEN)
        self.assertEqual(r.returncode, 1)
        self.assertEqual(self.current(), sha(1))
        self.assertEqual(self.unit.read_text(), old_unit)                    # 서비스 설정도 옛 것으로
        # restart 마다 systemd 가 읽어 둔 설정: 1판, 2판(새 설정), 되돌린 1판(옛 설정을 다시 읽은 뒤)
        self.assertEqual(self.loaded_at_restart(), ['MemoryMax=512M', 'MemoryMax=512M', 'MemoryMax=999M'])
        self.assertEqual(self.envfile.read_text(), f'LV_GITHUB_TOKEN={TOKEN}\n')
        self.assertEqual(stat.S_IMODE(self.envfile.stat().st_mode), 0o600)
        self.assertFalse((self.base / 'lv-worker.env.prev').exists())

    def test_rolls_back_when_new_release_restarts_between_checks(self):
        """물을 때마다 active 여도, 확인하는 사이 systemd 가 다시 켠 적(NRestarts 증가)이 있으면 실패로 보고 되돌린다."""
        self.assertEqual(self.run_script(sha(1), token=TOKEN).returncode, 0)   # 다시 켜지지 않는 판은 통과
        looping = self.make_source(Path(self.temp.name).resolve() / 'looping', crash_loop=True)
        r = self.run_script(sha(2), src=looping, token=FAILED_TOKEN)
        self.assertEqual(r.returncode, 1, r.stderr)
        self.assertEqual(self.current(), sha(1))
        self.assertEqual(self.envfile.read_text(), f'LV_GITHUB_TOKEN={TOKEN}\n')

    def test_rollback_reports_systemd_state_not_worker_log(self):
        """CI 로그는 공개된다. 되돌릴 때는 systemd 가 알려 주는 상태만 남기고 작업자 로그(분석한 계정·레포)는 옮기지 않는다."""
        self.assertEqual(self.run_script(sha(1)).returncode, 0)
        self.set_active(False)
        r = self.run_script(sha(2))
        self.assertEqual(r.returncode, 1)
        self.assertNotIn(WORKER_LOG_LOGIN, r.stdout + r.stderr)
        for want in ('Result=exit-code', 'ExecMainStatus=1'):   # 왜 멈췄는지(종료 코드·메모리 초과 등)는 남긴다
            self.assertIn(want, r.stderr)

    def test_server_summary_leaves_out_git_version(self):
        """받은 레포를 여는 git 의 판은 공개 CI 로그에 남기지 않는다(그 판에 맞는 약점을 고르기 쉬움).
        가짜 git 의 판도, 자체 점검이 stderr(로그)에 쓴 git 판도 나오지 않는다. 자체 점검 결과(stdout 의 OK)는 남긴다."""
        r = self.run_script(sha(1))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertNotIn(FAKE_GIT_VERSION, r.stdout + r.stderr)
        self.assertIn('OK', r.stdout.splitlines())

    def test_self_check_log_stays_on_server_owner_only(self):
        """자체 점검의 stderr(로그)는 CI 로그 대신 서버 파일(판 폴더 위, 소유자만 읽음)에 남긴다. 배포마다 새로 쓴다."""
        log_file = self.base / 'self-check.log'
        log_file.parent.mkdir(parents=True)
        log_file.write_text('지난 배포의 로그\n')
        log_file.chmod(0o644)
        r = self.run_script(sha(1))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(log_file.read_text(encoding='utf-8'), SELF_CHECK_LOG + '\n')
        self.assertEqual(stat.S_IMODE(log_file.stat().st_mode), 0o600)
        log_file.unlink()
        self.assertEqual(self.run_script(sha(2)).returncode, 0)   # 없던 파일도 소유자만 읽게 만든다
        self.assertEqual(stat.S_IMODE(log_file.stat().st_mode), 0o600)
        self.assertEqual(log_file.read_text(encoding='utf-8'), SELF_CHECK_LOG + '\n')

    def test_first_deploy_failure_removes_service(self):
        self.set_active(False)
        r = self.run_script(sha(1), token=TOKEN)
        self.assertEqual(r.returncode, 1)
        self.assertFalse(self.unit.exists())
        self.assertIsNone(self.current())
        self.assertFalse(self.envfile.exists())                   # 새로 만든 토큰 파일도 되돌림
        self.assertIn(f'stop {SVC}', self.log())
        self.assertIn(f'disable --quiet {SVC}', self.log())

    def test_self_check_failure_leaves_running_worker_alone(self):
        self.assertEqual(self.run_script(sha(1)).returncode, 0)
        (self.stub / 'systemctl.log').unlink()
        bad = self.make_source(Path(self.temp.name).resolve() / 'bad', fail=True)
        r = self.run_script(sha(2), src=bad, token=TOKEN)
        self.assertEqual(r.returncode, 1)
        self.assertIn('자체 점검 실패: 가짜 이유', r.stderr.splitlines())   # 실패 이유(stdout)는 CI 로그에
        self.assertNotIn(FAKE_GIT_VERSION, r.stdout + r.stderr)            # 로그(stderr)는 서버 파일에만
        self.assertEqual((self.base / 'self-check.log').read_text(encoding='utf-8'), SELF_CHECK_LOG + '\n')
        self.assertEqual(self.current(), sha(1))
        self.assertEqual(self.log(), '')
        self.assertFalse(self.envfile.exists())

    def test_keeps_five_most_recent_releases(self):
        t0 = time.time() - 10_000
        for n in range(1, 8):
            self.assertEqual(self.run_script(sha(n)).returncode, 0)
            marker = self.base / 'releases' / sha(n) / '.ready'
            os.utime(marker, (t0 + n, t0 + n))                    # 같은 초에 돌아도 순서가 정해지게
        self.assertEqual(self.releases(), [sha(n) for n in range(3, 8)])
        self.assertEqual(self.current(), sha(7))

    def test_prune_keeps_previous_release_even_when_it_is_the_oldest(self):
        """손으로 가장 오래된 판으로 되돌린 뒤 새로 배포해도, 그때까지 돌던 그 판(바로 전 판)은 지우지 않는다."""
        t0 = time.time() - 10_000
        for n in range(1, 6):
            self.assertEqual(self.run_script(sha(n)).returncode, 0)
            os.utime(self.base / 'releases' / sha(n) / '.ready', (t0 + n, t0 + n))
        self.switch_current(sha(1))
        self.assertEqual(self.run_script(sha(6)).returncode, 0)
        self.assertEqual(self.current(), sha(6))
        self.assertEqual(self.releases(), [sha(n) for n in range(1, 7)])   # 1판은 최근 순 여섯째(5개 밖)지만 바로 전 판이라 남김

    def test_prune_keeps_current_release_even_when_its_marker_looks_oldest(self):
        """시계가 뒤로 가 방금 배포한 판의 표시가 가장 오래돼 보여도, 지금 도는 판은 지우지 않는다."""
        ahead = time.time() + 10_000                                       # 앞서 가던 시계로 배포한 판들
        for n in range(1, 6):
            self.assertEqual(self.run_script(sha(n)).returncode, 0)
            os.utime(self.base / 'releases' / sha(n) / '.ready', (ahead + n, ahead + n))
        self.assertEqual(self.run_script(sha(6)).returncode, 0)
        self.assertEqual(self.current(), sha(6))
        self.assertEqual(self.releases(), [sha(n) for n in range(1, 7)])
        self.assertTrue((self.base / 'current' / 'service' / 'worker.py').is_file())   # 도는 판의 코드가 남아 있음


if __name__ == '__main__':
    unittest.main()
