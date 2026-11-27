"""deploy_worker.sh 시험: 가짜 HOME·가짜 sudo/systemctl 로만 돈다(실제 서비스·EC2·GitHub 는 안 건드림)."""
import os
from pathlib import Path
import stat
import subprocess
import tempfile
import time
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / 'deploy_worker.sh'
SVC = 'career-lv-worker-staging'
TOKEN = 'ghp_' + 'Fake0Token1Value2For3Tests4Only5xyz'   # 시험용 가짜 값

STUBS = {
    'sudo': '#!/bin/sh\n[ "$1" = -n ] && shift\nexec "$@"\n',
    'systemctl': '#!/bin/sh\n'
                 'flag=no; [ -n "${LV_GITHUB_TOKEN+x}" ] && flag=yes\n'
                 'echo "$* token-env=$flag" >> "$STUB_DIR/systemctl.log"\n'
                 'case "$1" in\n'
                 '  is-active) [ "$(cat "$STUB_DIR/active")" = yes ] && exit 0; exit 3 ;;\n'
                 '  show) echo 0 ;;\n'
                 'esac\nexit 0\n',
    'journalctl': '#!/bin/sh\nexit 0\n',
    'sleep': '#!/bin/sh\nexit 0\n',
}

FAKE_WORKER = '''import os, sys
here = os.path.dirname(os.path.abspath(__file__))
if '--self-check' in sys.argv:
    data = sys.argv[sys.argv.index('--data-dir') + 1]
    os.makedirs(data, exist_ok=True)
    with open(os.path.join(data, 'selfcheck-env.txt'), 'w') as f:
        f.write('token-present' if 'LV_GITHUB_TOKEN' in os.environ else 'token-absent')
    if os.path.exists(os.path.join(here, 'FAIL_SELF_CHECK')):
        print('자체 점검 실패(가짜)'); sys.exit(1)
    print('OK'); sys.exit(0)
'''


def sha(n):
    return f'{n:040x}'


class DeployWorkerTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name).resolve()
        self.home, self.units, self.stub = root / 'home', root / 'units', root / 'stub'
        for d in (self.home, self.units, self.stub):
            d.mkdir()
        for name, body in STUBS.items():
            p = self.stub / name
            p.write_text(body)
            p.chmod(0o755)
        self.set_active(True)
        self.src = self.make_source(root / 'src')
        self.base = self.home / 'lv-stat' / 'staging'
        self.envfile = self.home / 'career-data-staging' / 'lv-worker.env'
        self.unit = self.units / f'{SVC}.service'

    def tearDown(self):
        self.temp.cleanup()

    def make_source(self, path, fail=False):
        path.mkdir(parents=True)
        (path / 'worker.py').write_text(FAKE_WORKER, encoding='utf-8')
        (path / '__pycache__').mkdir()
        (path / '__pycache__' / 'junk.pyc').write_bytes(b'x')
        if fail:
            (path / 'FAIL_SELF_CHECK').write_text('1')
        return path

    def set_active(self, active):
        (self.stub / 'active').write_text('yes' if active else 'no')

    def log(self):
        p = self.stub / 'systemctl.log'
        return p.read_text() if p.exists() else ''

    def run_script(self, commit, src=None, token=None, **extra):
        env = {k: v for k, v in os.environ.items() if k not in ('LV_GITHUB_TOKEN', 'TARGET', 'DEPLOY_ENV', 'CAREER_ENV')}
        env.update(HOME=str(self.home), PATH=f'{self.stub}:{os.environ["PATH"]}', STUB_DIR=str(self.stub),
                   GITHUB_REF_NAME='develop', LV_UNIT_DIR=str(self.units), LV_CHECK_ROUNDS='2')
        if token is not None:
            env['LV_GITHUB_TOKEN'] = token
        env.update(extra)
        return subprocess.run(['bash', str(SCRIPT), commit, str(src or self.src)], env=env,
                              capture_output=True, text=True, timeout=120)

    def current(self):
        link = self.base / 'current'
        return Path(os.path.realpath(link)).name if link.is_symlink() else None

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
        r = self.run_script(sha(1), token=f'  {TOKEN}\n')
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.envfile.read_text(), f'LV_GITHUB_TOKEN={TOKEN}\n')
        self.assertEqual(stat.S_IMODE(self.envfile.stat().st_mode), 0o600)
        self.assertNotIn(TOKEN, r.stdout + r.stderr)
        self.assertNotIn(TOKEN, self.log())                       # 명령줄에 안 나옴
        self.assertNotIn('token-env=yes', self.log())             # sudo·systemctl 에 안 넘김
        self.assertEqual((self.home / 'career-data-staging/lv-stat/selfcheck-env.txt').read_text(), 'token-absent')
        holders = [p for p in self.home.rglob('*') if p.is_file() and not p.is_symlink() and TOKEN.encode() in p.read_bytes()]
        self.assertEqual(holders, [self.envfile])                 # 사본·임시 파일이 남지 않음
        self.assertNotIn(TOKEN, self.unit.read_text())

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
        for want in ('Restart=on-failure', 'Nice=10', 'IOSchedulingClass=idle', 'CPUQuota=100%', 'MemoryMax=1500M',
                     f'EnvironmentFile=-{self.envfile}'):
            self.assertIn(want, lines)
        self.assertIn('「Claude 임시값」', text)
        self.assertEqual(self.current(), sha(1))
        self.assertFalse((self.base / 'releases' / sha(1) / 'service' / '__pycache__').exists())
        for call in ('daemon-reload', f'enable --quiet {SVC}', f'restart {SVC}'):
            self.assertIn(call, self.log())

    def test_same_commit_twice_changes_nothing_but_restarts(self):
        self.assertEqual(self.run_script(sha(1), token=TOKEN).returncode, 0)
        os.utime(self.unit, (1, 1))
        os.utime(self.envfile, (1, 1))
        unit_before = self.unit.read_text()
        r = self.run_script(sha(1), token=TOKEN)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.unit.stat().st_mtime, 1)          # 서비스 파일을 다시 쓰지 않음
        self.assertEqual(self.envfile.stat().st_mtime, 1)       # 같은 토큰이면 파일을 다시 쓰지 않음
        self.assertEqual(self.unit.read_text(), unit_before)
        self.assertEqual(self.log().count(f'restart {SVC}'), 2)
        self.assertEqual(sorted(p.name for p in (self.base / 'releases').iterdir()), [sha(1)])
        self.assertEqual(self.current(), sha(1))

    # --- 되돌리기 ---------------------------------------------------------------
    def test_rolls_back_release_and_token_when_new_release_is_not_active(self):
        self.assertEqual(self.run_script(sha(1), token=TOKEN).returncode, 0)
        unit_before = self.unit.read_text()
        self.set_active(False)
        new_token = 'ghp_' + 'Second0Fake1Token2' * 2
        r = self.run_script(sha(2), token=new_token)
        self.assertEqual(r.returncode, 1)
        self.assertEqual(self.current(), sha(1))
        self.assertEqual(self.unit.read_text(), unit_before)
        self.assertEqual(self.envfile.read_text(), f'LV_GITHUB_TOKEN={TOKEN}\n')
        self.assertEqual(stat.S_IMODE(self.envfile.stat().st_mode), 0o600)
        self.assertFalse((self.base / 'lv-worker.env.prev').exists())
        self.assertNotIn(new_token, r.stdout + r.stderr)
        self.assertEqual(self.log().count(f'restart {SVC}'), 3)   # 1판, 2판, 되돌린 1판

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
        self.assertIn('자체 점검 실패', r.stderr)
        self.assertEqual(self.current(), sha(1))
        self.assertEqual(self.log(), '')
        self.assertFalse(self.envfile.exists())

    def test_keeps_five_most_recent_releases(self):
        t0 = time.time() - 10_000
        for n in range(1, 8):
            self.assertEqual(self.run_script(sha(n)).returncode, 0)
            marker = self.base / 'releases' / sha(n) / '.ready'
            os.utime(marker, (t0 + n, t0 + n))                    # 같은 초에 돌아도 순서가 정해지게
        left = sorted(p.name for p in (self.base / 'releases').iterdir())
        self.assertEqual(left, [sha(n) for n in range(3, 8)])
        self.assertEqual(self.current(), sha(7))


if __name__ == '__main__':
    unittest.main()
