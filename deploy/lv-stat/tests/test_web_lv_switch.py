"""deploy/web/deploy.sh 시험: 웹 서비스 파일이 스테이징에만 CAREER_LV_STAT=on 을 주는지(운영은 off) 본다.

웹의 LV 분석 칸·분석 API·공고 화면의 분석 결과 읽기는 이 값이 정확히 on 일 때만 켜진다(lv-stat/service/CONTRACT.md).
작업자는 스테이징에만 있으므로 운영 웹은 꺼야 한다(꺼 두지 않으면 요청이 '대기'로 영영 남음).

스크립트를 가짜 HOME·가짜 명령으로 실제로 돌린다. 웹 코드는 합성 git 레포(frontend/package.json 하나)이고 REPO 로
넘긴다(GitHub 에 가지 않음). npm·node·curl 은 아무것도 하지 않는 가짜이고, sudo 는 서비스 파일(tee)을 시험 폴더에만
쓰고 systemctl 은 기록만 한다. mv -Tf(GNU)는 macOS 에서도 돌게 rename 으로 바꾼다. 실제 빌드·서비스·EC2 는 건드리지 않는다.
"""
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[2] / 'web' / 'deploy.sh'
PATH0 = os.environ['PATH']
BASH = shutil.which('bash', path=PATH0)
GIT = shutil.which('git', path=PATH0)
MV = shutil.which('mv', path=PATH0)

STUBS = {
    # 서비스 파일은 STUB_DIR 에만 쓰고, systemctl 은 기록만 한다. 옛 서비스 파일 읽기(sed)만 그대로 돌린다(없으면 실패).
    'sudo': ('case "$1" in\n'
             '  tee) cat > "$STUB_DIR/$(basename "$2")" ;;\n'
             '  systemctl) shift; printf "%s\\n" "$*" >> "$STUB_DIR/systemctl.log" ;;\n'
             '  sed) exec "$@" ;;\n'
             '  cp) case "$3" in "$HOME"/*) exec cp "$2" "$3" ;; esac; echo "sudo $*" >> "$STUB_DIR/refused.log"; exit 1 ;;\n'
             '  *) echo "sudo $*" >> "$STUB_DIR/refused.log"; exit 1 ;;\n'
             'esac\n'),
    'systemctl': 'printf "%s\\n" "$*" >> "$STUB_DIR/systemctl.log"\n',
    'npm': 'printf "%s\\n" "npm $*" >> "$STUB_DIR/calls.log"\n',
    'node': 'printf "%s\\n" "node $*" >> "$STUB_DIR/calls.log"\n',
    'curl': 'exit 0\n',
    'mv': (f'if [ "$1" = -Tf ]; then exec "{sys.executable}" -I -c '
           '\'import os, sys; os.replace(sys.argv[1], sys.argv[2])\' "$2" "$3"; fi\n'
           f'exec "{MV}" "$@"\n'),
}


def git(*args, cwd=None, env=None):
    subprocess.run([GIT, *args], cwd=cwd, env=env, check=True, capture_output=True, text=True, timeout=60)


@unittest.skipUnless(BASH and GIT, 'bash 와 git 이 있어야 한다')
class WebLvSwitchTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name).resolve()
        self.home, self.bin, self.stub = root / 'home', root / 'bin', root / 'stub'
        for d in (self.home, self.bin, self.stub):
            d.mkdir()
        for name, body in STUBS.items():
            path = self.bin / name
            path.write_text('#!/bin/sh\n' + body)
            path.chmod(0o755)
        # 합성 웹 코드 레포(커밋 하나)
        self.repo = root / 'repo'
        (self.repo / 'frontend').mkdir(parents=True)
        (self.repo / 'frontend' / 'package.json').write_text('{"name": "synthetic-web"}\n')
        genv = dict(os.environ, HOME=str(root), GIT_CONFIG_NOSYSTEM='1', GIT_AUTHOR_NAME='Synthetic',
                    GIT_AUTHOR_EMAIL='synthetic@example.com', GIT_COMMITTER_NAME='Synthetic',
                    GIT_COMMITTER_EMAIL='synthetic@example.com')
        git('init', '-q', str(self.repo), env=genv)
        git('-C', str(self.repo), 'add', '-A', env=genv)
        git('-C', str(self.repo), '-c', 'commit.gpgsign=false', 'commit', '-q', '-m', 'synthetic web', env=genv)
        self.sha = subprocess.run([GIT, '-C', str(self.repo), 'rev-parse', 'HEAD'], env=genv, check=True,
                                  capture_output=True, text=True).stdout.strip()

    def deploy(self, env_name):
        """deploy.sh <env_name> <커밋> 을 돌린다. -> 가짜 sudo 가 받은 서비스 파일의 줄"""
        env = {k: v for k, v in os.environ.items() if k != 'CAREER_LV_STAT'}
        env.update(HOME=str(self.home), PATH=f'{self.bin}:{PATH0}', STUB_DIR=str(self.stub), REPO=str(self.repo),
                   GIT_TERMINAL_PROMPT='0')
        r = subprocess.run([BASH, str(SCRIPT), env_name, self.sha], env=env, capture_output=True, text=True,
                           timeout=120)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertFalse((self.stub / 'refused.log').exists(), (self.stub / 'refused.log').read_text()
                         if (self.stub / 'refused.log').exists() else '')
        svc = 'career-web-staging' if env_name == 'staging' else 'career-web'
        return (self.stub / f'{svc}.service').read_text().splitlines()

    def test_staging_web_unit_turns_the_lv_switch_on(self):
        lines = self.deploy('staging')
        self.assertIn(f'Environment=CAREER_DATA_DIR={self.home}/career-data-staging', lines)   # 스테이징 판을 배포함
        self.assertEqual([l for l in lines if 'CAREER_LV_STAT' in l], ['Environment=CAREER_LV_STAT=on'])
        self.assertGreater(lines.index('Environment=CAREER_LV_STAT=on'), lines.index('[Service]'))

    def test_production_web_unit_turns_the_lv_switch_off(self):
        lines = self.deploy('production')
        self.assertIn(f'Environment=CAREER_DATA_DIR={self.home}/career-data', lines)           # 운영 판을 배포함
        self.assertEqual([l for l in lines if 'CAREER_LV_STAT' in l], ['Environment=CAREER_LV_STAT=off'])
        self.assertGreater(lines.index('Environment=CAREER_LV_STAT=off'), lines.index('[Service]'))


if __name__ == '__main__':
    unittest.main()
