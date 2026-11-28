"""deploy/web/deploy.sh 시험: 웹 서비스 파일이 스테이징에만 CAREER_LV_STAT=on 을 주는지(운영은 off) 스크립트 글로 본다.

웹의 LV 분석 칸·분석 API·공고 화면의 분석 결과 읽기는 이 값이 정확히 on 일 때만 켜진다(lv-stat/service/CONTRACT.md).
작업자는 스테이징에만 있으므로 운영 웹은 꺼야 한다(꺼 두지 않으면 요청이 '대기'로 영영 남음).

deploy.sh 는 팀 웹 배포 스크립트다. 가짜 명령으로 통째로 돌리면 팀이 다른 단계(빌드·DB 준비 등)를 고칠 때마다 이 시험이
깨지므로, LV 스위치에 닿는 곳만 글로 읽는다: 환경별 case 갈래(staging → on, production → off)와, 서비스 파일 글(want="…")의
Environment=CAREER_LV_STAT= 줄이 그 갈래가 정한 변수를 쓰는지. CI 는 deploy/web/deploy.sh 가 바뀌어도 이 시험을 돌린다
(.github/workflows/ci.yml 의 lv-stat 경로).
"""
from pathlib import Path
import re
import unittest

SCRIPT = Path(__file__).resolve().parents[2] / 'web' / 'deploy.sh'


def unit_lines(text):
    """서비스 파일 글(want="…" 에 담아 sudo tee 로 쓰는 것)의 줄."""
    m = re.search(r'^want="(.*?)"[ \t]*$', text, re.S | re.M)
    if not m:
        raise AssertionError(f'{SCRIPT} 에 서비스 파일 글(want="…")이 없다')
    return m.group(1).splitlines()


def arm(text, env):
    """`case "$env" in` 의 그 환경 갈래(`<env>)` 부터 `;;` 까지)에서 변수 = 값."""
    m = re.search(r'^[ \t]*' + re.escape(env) + r'\)(.*?);;', text, re.S | re.M)
    if not m:
        raise AssertionError(f'{SCRIPT} 에 {env}) 갈래가 없다')
    return dict(re.findall(r'(?:^|[\s;])(\w+)=([^\s;]*)', m.group(1)))


class WebLvSwitchTest(unittest.TestCase):
    def setUp(self):
        self.text = SCRIPT.read_text(encoding='utf-8')
        self.unit = unit_lines(self.text)
        switch = [line for line in self.unit if 'CAREER_LV_STAT' in line]
        self.assertEqual(len(switch), 1, switch)                       # 같은 이름이 또 있으면 systemd 는 뒤의 값을 쓴다
        m = re.fullmatch(r'Environment=CAREER_LV_STAT=\$\{?(\w+)\}?', switch[0])
        self.assertIsNotNone(m, f'스위치 값은 환경별 갈래가 정한 변수여야 한다: {switch[0]}')
        self.line, self.var = switch[0], m.group(1)

    def test_staging_arm_turns_the_lv_switch_on(self):
        self.assertEqual(arm(self.text, 'staging').get(self.var), 'on')

    def test_production_arm_turns_the_lv_switch_off(self):
        self.assertEqual(arm(self.text, 'production').get(self.var), 'off')

    def test_web_unit_sets_the_switch_from_that_variable_only(self):
        """스위치 줄은 [Service] 안에 있고, 그 변수는 두 갈래 밖에서 다시 정하지 않는다(뒤에서 바꾸면 갈래의 값이 안 쓰임)."""
        self.assertLess(self.unit.index('[Service]'), self.unit.index(self.line))
        self.assertLess(self.unit.index(self.line), self.unit.index('[Install]'))
        assigned = re.findall(r'(?:^|[\s;])' + re.escape(self.var) + r'=', self.text, re.M)
        self.assertEqual(len(assigned), 2, f'{self.var} 를 정하는 곳은 staging·production 갈래뿐이어야 한다')


if __name__ == '__main__':
    unittest.main()
