"""LLM 없는 마무리(s2_final)와 확정 사다리 계산(calc) 시험.

- s2 모듈은 불러올 때 작업 폴더(LV_S2_HOME)를 정한다. 그래서 test_s2_port처럼 언제나 새 하위 프로세스(-I -B)에서
  부르고, 환경은 PATH와 임시 LV_S2_HOME만 준다. 부를 때마다 코드 폴더(s2)에 아무것도 안 생겼는지 확인한다.
- 계산 시험은 합성 final-*.json만 쓴다(사람·레포·공고 자료 없음). 기대값은 손으로 셈한 값이다.
- 네트워크는 쓰지 않는다.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
CODE = os.path.realpath(os.path.join(HERE, "..", "s2"))
PID = "P01"
REPO = "tester__demo"  # 합성 레포 키

# 2026-11-26 사용자 확정 고정 사다리(1~5단계 시작값)와 「문서」 lv-calc AI 기술 시작값
LADDERS = {
    "prog.commits": [1, 7, 30, 180, 365], "prog.lines": [1, 200, 1000, 5000, 25000], "prog.period": [1, 7, 30, 150, 300],
    "deploy.repos": [1, 2, 3, 5, 8], "deploy.period": [1, 7, 50, 150, 250],
    "dataeng.dags": [1, 2, 5, 10, 20], "dataeng.period": [1, 7, 30, 100, 250],
    "database.tables": [1, 3, 8, 20, 50], "database.period": [1, 7, 30, 120, 250],
    "api_calls": [1, 3, 10, 30, 100], "data_io": [1, 3, 10, 30, 100], "events": [1, 10, 30, 100, 300],
}
AI_LADDERS = {"ai.integrations": [1, 2, 4, 8, 15], "ai.features": [1, 2, 3, 5, 8],
              "ai.techniques.llm": [1, 2, 3, 5, 7], "ai.techniques.ml": [1, 2, 3, 4, 6]}

# 하위 프로세스: argv[1] = 코드 폴더, argv[2] = pid. calc_person 결과를 JSON 한 줄로 찍는다.
PROBE_CALC = """
import json, sys
sys.path.insert(0, sys.argv[1])
import calc
print(json.dumps(calc.calc_person(sys.argv[2]), ensure_ascii=False))
"""

# argv[2] = {"FIXED": {키: [값...]}, "SPEC": {...}} → 같은 모양으로 단계를 찍는다.
PROBE_STAGES = """
import json, sys
sys.path.insert(0, sys.argv[1])
import calc
table = json.loads(sys.argv[2])
ladders = {'FIXED': calc.FIXED, 'SPEC': calc.SPEC}
print(json.dumps({name: {k: [calc.stage(v, ladders[name][k]) for v in vs] for k, vs in t.items()} for name, t in table.items()}))
"""

# argv[1] = 코드 폴더, argv[2] = pid. backend_a 마무리 모듈(cat_backend_a) 자리에 고장 난 가짜를 두고
# s2_final.py를 명령행처럼(__main__) 돌린다. 가짜는 받은 데이터를 고치다가 터지고, 받은 답·대상을 오류 글에 남긴다.
PROBE_FINAL_BROKEN = """
import runpy, sys, types
code, pid = sys.argv[1], sys.argv[2]

def finalize(person, data, answers):
    data['variables']['backend.gate']['value'] = 99
    raise RuntimeError('boom answers=%r targets=%r' % (answers, [t['target_id'] for t in data['s5_targets']]))

broken = types.ModuleType('cat_backend_a')
broken.finalize = finalize
sys.modules['cat_backend_a'] = broken
script = code + '/s2_final.py'
sys.argv = [script, pid]
runpy.run_path(script, run_name='__main__')
"""


def base_env(**extra):
    """하위 프로세스 환경: PATH만 물려받는다(개발자 셸의 토큰·설정이 섞이지 않게)."""
    env = {"PATH": os.environ.get("PATH", os.defpath)}
    env.update(extra)
    return env


def code_tree():
    return sorted(
        os.path.relpath(os.path.join(d, n), CODE)
        for d, dirs, files in os.walk(CODE)
        for n in dirs + files
    )


def rec(value, state="value_rule", **extra):
    """추출기가 쓰는 변수 기록 한 개(이름·역할·값·상태·단위 + 근거 칸)."""
    v = {"name": "합성 변수", "role": "count", "value": value, "state": state, "unit": "개",
         "by_repo": {}, "instances": [], "evidence": []}
    v.update(extra)
    return v


def target(tid, var, template, trace, priority):
    """S5 대상 한 개(추출기가 쓰는 모양)."""
    return {"target_id": tid, "var": var, "repo": REPO, "template": template,
            "material": {"files": [{"path": "app/main.py", "start": 1, "end": 40}], "commits": []},
            "rule_result": {"rule": "합성"}, "trace": trace, "priority": priority}


class CalcTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="lv-calc-")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.home = os.path.join(self.tmp, "home")
        self.out = os.path.join(self.home, "out", PID)
        os.makedirs(self.out)

    def run_py(self, args):
        """s2 모듈을 새 프로세스로 부르고, 코드 폴더에 아무것도 안 생겼는지 확인한다. -> (stdout, stderr)"""
        before = code_tree()
        p = subprocess.run([sys.executable, "-I", "-B", *args], env=base_env(LV_S2_HOME=self.home),
                           capture_output=True, timeout=120)
        self.assertEqual(code_tree(), before, "s2 코드 폴더에 파일이 생기면 안 된다")
        out, err = p.stdout.decode("utf-8", "replace"), p.stderr.decode("utf-8", "replace")
        self.assertEqual(p.returncode, 0, err)
        return out, err

    def write(self, name, data):
        with open(os.path.join(self.out, name), "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)

    def read(self, name):
        with open(os.path.join(self.out, name), encoding="utf-8") as f:
            return json.load(f)

    def final(self, key, variables, **extra):
        """마무리된 카테고리 파일(out/<pid>/final-<key>.json)을 쓴다."""
        data = {"category": key, "pid": PID, "variables": variables, "s5_targets": []}
        data.update(extra)
        self.write("final-%s.json" % key, data)

    def backend(self, gate, login, was, api, log, items=None):
        """백엔드 두 파일: backend_a(게이트·로그인·WAS와 SEC·WAS 항목), backend_b(API·로그와 API·LOG 항목)."""
        def lv(x):
            return rec(x, "value_rule" if x is not None else "unknown_failed", unit="LV(0~5)")
        a = {"backend.gate": rec(gate, "value_rule" if gate else "zero_unused", unit="레포"),
             "backend.login": lv(login), "backend.was": lv(was)}
        b = {"backend.api": lv(api), "backend.log": lv(log)}
        for vid, v in (items or {}).items():
            (a if vid.startswith(("backend.login.", "backend.was.")) else b)[vid] = v
        self.final("backend_a", a)
        self.final("backend_b", b)

    def calc(self):
        out, _ = self.run_py(["-c", PROBE_CALC, CODE, PID])
        return json.loads(out)

    # ---------------- 단계·반올림
    def test_ladder_boundaries(self):
        # 시작값 이상이면 그 단계(바로 아래 값은 한 단계 아래). 확정 사다리 값이 하나라도 다르면 실패한다.
        table, want = {"FIXED": {}, "SPEC": {}}, {"FIXED": {}, "SPEC": {}}
        for name, ladders in (("FIXED", LADDERS), ("SPEC", AI_LADDERS)):
            for key, starts in ladders.items():
                table[name][key] = [x for s in starts for x in (s - 0.5, s)] + [starts[-1] * 10]
                want[name][key] = [x for i in range(1, 6) for x in (i - 1, i)] + [5]
        out, _ = self.run_py(["-c", PROBE_STAGES, CODE, json.dumps(table)])
        self.assertEqual(json.loads(out), want)

    def test_mean_rounds_half_up(self):
        # (로그인 2.5 + WAS 2 + API 2 + 로그 2 + DB 깊이 3 + 운영 배포 2.0) / 6 = 2.25 → ROUND_HALF_UP 2.3
        # (짝수 쪽 반올림이면 2.2). 운영 배포 = (배포 레포 2 → 2단계 + 배포 기간 7일 → 2단계) / 2 = 2.0
        self.backend(gate=1, login=2.5, was=2.0, api=2.0, log=2.0)
        self.final("db", {"database.depth": rec(3)})
        self.final("deploy", {"deploy.repos": rec(2), "deploy.period": rec(7)})
        self.assertEqual(self.calc()["B"]["lv"], 2.3)

    # ---------------- 프로그래밍 활용
    def test_spec_example_programming_33(self):
        # 명세 예시: 커밋 120(3단계)·바꾼 줄 8,000(4단계)·기간 90일(3단계) → (3 + 4 + 3) / 3 = 3.33 → 3.3
        self.final("prog", {"prog.commits:Java": rec(120), "prog.lines:Java": rec(8000), "prog.period:Java": rec(90),
                            "prog.related_code:Java": rec(True, role="tf", unit="T/F")})
        self.assertEqual(self.calc()["L"], {"name": "프로그래밍 활용", "lv": 3.3, "unknown": 0,
                                            "languages": {"Java": 3.3}, "best": "Java"})

    def test_best_language_and_per_language(self):
        # Python이 먼저 나오고 커밋도 더 많지만(180 → 4단계) 줄 150(1단계)·기간 3일(1단계)이라 (4 + 1 + 1) / 3 = 2.0.
        # Java는 3.3 → 가장 높은 언어는 Java. 언어마다 LV가 모두 남는다.
        self.final("prog", {"prog.commits:Python": rec(180), "prog.lines:Python": rec(150), "prog.period:Python": rec(3),
                            "prog.commits:Java": rec(120), "prog.lines:Java": rec(8000), "prog.period:Java": rec(90)})
        got = self.calc()["L"]
        self.assertEqual(got["languages"], {"Python": 2.0, "Java": 3.3})
        self.assertEqual((got["best"], got["lv"]), ("Java", 3.3))

    def test_best_language_tie_keeps_first(self):
        # Kotlin(120·8,000·90 → 3·4·3)과 Java(150·6,000·100 → 3·4·3)가 같은 LV면 먼저 나온 Kotlin
        self.final("prog", {"prog.commits:Kotlin": rec(120), "prog.lines:Kotlin": rec(8000), "prog.period:Kotlin": rec(90),
                            "prog.commits:Java": rec(150), "prog.lines:Java": rec(6000), "prog.period:Java": rec(100)})
        got = self.calc()["L"]
        self.assertEqual(got["languages"], {"Kotlin": 3.3, "Java": 3.3})
        self.assertEqual(got["best"], "Kotlin")

    def test_prog_file_without_languages_is_zero(self):
        # prog 파일은 있는데 언어 변수가 하나도 없음(설정·문서만 고친 사람) → 0.0
        self.final("prog", {}, stats={"languages": {}})
        self.assertEqual(self.calc()["L"], {"name": "프로그래밍 활용", "lv": 0.0, "unknown": 0,
                                            "languages": {}, "best": None})

    # ---------------- 데이터베이스
    def test_db_depth_single_evidence(self):
        # 깊이 4단계 근거가 파일 한 곳뿐이어도 4단계(사용자 결정 2026-11-26: 근거 1곳이면 그 단계).
        # 테이블 8 → 3단계, 기간 30일 → 3단계 → (4 + 3 + 3) / 3 = 3.3.
        # 2단계 계산의 '3~5단계는 파일 2곳' 규칙이면 깊이 1 → (1 + 3 + 3) / 3 = 2.3이 된다.
        depth = rec(4, unit="단계(0~5, 단계가 곧 값)", stages=[1, 4], instances=[
            {"repo": REPO, "path": "app/db.py", "line": 12, "what": "1단계(연결) 근거: SQL DML", "status": "counted"},
            {"repo": REPO, "path": "app/db.py", "line": 30, "what": "4단계(트랜잭션) 근거: 트랜잭션 묶음", "status": "counted"}])
        self.final("db", {"database.depth": depth, "database.tables": rec(8), "database.period": rec(30)})
        self.assertEqual(self.calc()["D"], {"name": "데이터베이스", "lv": 3.3, "unknown": 0})

    # ---------------- 백엔드 개발
    def test_backend_gate_zero_is_zero(self):
        # 게이트를 통과한 레포가 없으면 다른 변수가 있어도 0.0이고 모름도 세지 않는다(대기 항목 LOG6가 있어도)
        self.backend(gate=0, login=3.0, was=2.0, api=4.0, log=1.0, items={"backend.log.LOG6": rec(None, None)})
        self.final("db", {"database.depth": rec(4), "database.tables": rec(8), "database.period": rec(30)})
        self.final("deploy", {"deploy.repos": rec(2), "deploy.period": rec(50)})
        self.assertEqual(self.calc()["B"], {"name": "백엔드 개발", "lv": 0.0, "unknown": 0,
                                            "note": "백엔드 게이트 통과 레포 없음"})

    def test_backend_mean_six(self):
        # 운영 배포 = (배포 레포 2 → 2단계 + 배포 기간 50일 → 3단계) / 2 = 2.5
        # 백엔드 = (로그인 3 + WAS 2 + API 4 + 로그 1 + DB 깊이 4 + 운영 배포 2.5) / 6 = 2.75 → 2.8
        # DB 깊이는 근거 한 곳의 4단계를 그대로 쓴다('파일 2곳' 규칙이면 1 → 2.25 → 2.3).
        # 데이터베이스 LV(3.3: 깊이 4·테이블 8·기간 30)가 아니라 깊이다(LV를 넣으면 2.6).
        self.backend(gate=1, login=3.0, was=2.0, api=4.0, log=1.0)
        self.final("db", {"database.depth": rec(4, instances=[
            {"repo": REPO, "path": "app/db.py", "line": 30, "what": "4단계(트랜잭션) 근거: 트랜잭션 묶음", "status": "counted"}]),
            "database.tables": rec(8), "database.period": rec(30)})
        self.final("deploy", {"deploy.repos": rec(2), "deploy.period": rec(50)})
        got = self.calc()
        self.assertEqual(got["O"], {"name": "운영 배포", "lv": 2.5, "unknown": 0})
        self.assertEqual((got["B"]["lv"], got["B"]["unknown"]), (2.8, 0))

    def test_backend_unknown_counts_pending_items(self):
        # 모름 = 값이 없는 변수(로그) 1 + 대기·모름이고 값이 없는 항목 3(SEC1 모름, WAS4 대기, LOG6 대기) = 4.
        # 값이 있는 대기(SEC4 'value_rule+대기')·상태 없이 값이 있는 항목(API3, 규칙 값)·안 씀·해당 없음·
        # 상한 칸(WAS-C1)은 세지 않는다.
        # LV = (로그인 3 + WAS 2 + API 4 + DB 깊이 4 + 운영 배포 2.5) / 5 = 3.1
        self.backend(gate=1, login=3.0, was=2.0, api=4.0, log=None, items={
            "backend.login.SEC1": rec(None, "unknown_failed"),
            "backend.login.SEC2": rec(None, "zero_unused"),
            "backend.login.SEC4": rec(2, "value_rule+대기"),
            "backend.was.WAS4": rec(None, None),
            "backend.was.WAS-C1": rec(None, None),
            "backend.api.API3": rec(1, None),
            "backend.api.API6": rec(None, "not_applicable"),
            "backend.log.LOG6": rec(None, None),
        })
        self.final("db", {"database.depth": rec(4)})
        self.final("deploy", {"deploy.repos": rec(2), "deploy.period": rec(50)})
        got = self.calc()["B"]
        self.assertEqual((got["lv"], got["unknown"]), (3.1, 4))

    # ---------------- 모름
    def test_unknown_counted_and_excluded(self):
        # 데이터 송수신이 대기(LLM 보충 끔) → 평균에서 빼고 모름 1개:
        # (API 연동 10 → 3단계 + 이벤트 30 → 3단계) / 2 = 3.0 (0으로 넣으면 2.0)
        self.final("fe", {"api_calls": rec(10), "data_io": rec(None, None), "events": rec(30),
                          "ui_tech": rec({"HTML": True, "CSS": True}, role="tf_set", unit="T/F")})
        self.assertEqual(self.calc()["F"], {"name": "프론트엔드 앱", "lv": 3.0, "unknown": 1})

    def test_value_without_state_is_rule_value(self):
        # 모듈이 상태를 비운 채 값을 둔 변수(대기 대상이 있는 API 연동 10)는 규칙 값으로 센다. 0(안 씀)도 값이다:
        # (10 → 3단계 + 송수신 0 → 0단계 + 이벤트 30 → 3단계) / 3 = 2.0
        # (상태 없는 값을 모름으로 빼면 1.5·모름 1, 0을 모름으로 빼면 3.0·모름 1)
        self.final("fe", {"api_calls": rec(10, None), "data_io": rec(0, "zero_unused"), "events": rec(30)})
        self.assertEqual(self.calc()["F"], {"name": "프론트엔드 앱", "lv": 2.0, "unknown": 0})

    def test_no_final_files_all_null(self):
        # 마무리 파일이 하나도 없음(추출기가 모두 실패) → 일곱 칸 모두 판정 불가.
        # 백엔드는 게이트를 몰라 0.0이 아니라 판정 불가다.
        got = self.calc()
        self.assertEqual(list(got), ["L", "O", "B", "E", "D", "F", "A"])
        self.assertEqual(got, {
            "L": {"name": "프로그래밍 활용", "lv": None, "unknown": 0, "languages": {}, "best": None},
            "O": {"name": "운영 배포", "lv": None, "unknown": 2},
            "B": {"name": "백엔드 개발", "lv": None, "unknown": 6, "note": "백엔드 게이트를 판정하지 못함"},
            "E": {"name": "데이터 엔지니어", "lv": None, "unknown": 2},
            "D": {"name": "데이터베이스", "lv": None, "unknown": 3},
            "F": {"name": "프론트엔드 앱", "lv": None, "unknown": 3},
            "A": {"name": "AI 기술", "lv": None, "unknown": 3},
        })

    # ---------------- AI 기술
    def test_ai_techniques_max_of_llm_ml(self):
        # 기법 수는 LLM·ML을 따로 단계로 바꿔 높은 쪽(LLM 1/2/3/5/7, ML 1/2/3/4/6).
        # 연동·기능은 대기(값 없음)로 두어 AI LV가 곧 기법 단계가 되게 한다.
        cases = [
            ("LLM 3 → 3단계, ML 2 → 2단계", 3, 2),  # 합계 5를 LLM 사다리로 매기면 4단계
            ("LLM 2 → 2단계, ML 3 → 3단계", 2, 3),  # LLM만 보면 2단계
        ]
        for label, llm, ml in cases:
            with self.subTest(label):
                parts = {"llm": llm, "ml": ml, "llm_list": ["t%d" % i for i in range(llm)], "ml_list": ["m%d" % i for i in range(ml)]}
                self.final("ai", {"ai.integrations": rec(None, None), "ai.techniques": rec(llm + ml, parts=parts),
                                  "ai.features": rec(None, None)})
                self.assertEqual(self.calc()["A"], {"name": "AI 기술", "lv": 3.0, "unknown": 2})
        with self.subTest("기법이 대기(값 없음)면 모름"):
            # 연동 1 → 1단계만 남는다. 기법을 0단계로 넣으면 0.5·모름 1
            self.final("ai", {"ai.integrations": rec(1),
                              "ai.techniques": rec(None, None, parts={"llm": 0, "ml": 0, "llm_list": [], "ml_list": []}),
                              "ai.features": rec(None, None)})
            self.assertEqual(self.calc()["A"], {"name": "AI 기술", "lv": 1.0, "unknown": 2})

    # ---------------- 마무리(s2_final)
    def test_final_drops_no_trace_and_survives_module_error(self):
        # LLM 보충 끔: 흔적 없는 0(no_trace) 대상은 보내지 않으므로 목록에서 빼고, 흔적 있는 대상은 대기로 남는다.
        # - 진짜 cat_ai: 연동의 대상은 no_trace 하나뿐이라 빠지면 연동은 0(안 씀) 그대로(남기면 대기 → 값 없음).
        #   기능의 흔적 있는 대상은 답이 없어 대기 → 값 없음(모름).
        # - 고장 난 가짜 cat_backend_a: 오류(finalize_error)를 남기고, 그 뒤 카테고리(prog)도 마무리한다.
        idx = os.path.join(self.home, "index", PID)
        os.makedirs(idx)
        with open(os.path.join(idx, "person.json"), "w", encoding="utf-8") as f:
            json.dump({"pid": PID, "login": "tester", "role": None, "level": None, "repo_keys": [], "index_s": 0}, f)
        self.write("vars-ai.json", {
            "category": "ai", "pid": PID, "definition_choices": [], "stats": {},
            "variables": {
                "ai.integrations": rec(0, "zero_unused", parts={"providers": [], "pairs": []}, s5_waiting=1),
                "ai.techniques": rec(0, "zero_unused", parts={"llm": 0, "ml": 0, "llm_list": [], "ml_list": []}, s5_waiting=0),
                "ai.features": rec(None, None, s5_waiting=1),
                "ai.verified_prs": rec(0, "zero_unused", role="bonus_count", s5_waiting=0),
                "ai.tool_trace": rec(False, "zero_unused", role="tf", unit="T/F", s5_waiting=0),
            },
            "s5_targets": [target("P01.ai.integrations.1", "integrations", "ai.integration", "no_trace", 9),
                           target("P01.ai.features.2", "features", "ai.feature", "has_trace", 2)],
        })
        self.write("vars-backend_a.json", {
            "category": "backend_a", "pid": PID, "definition_choices": [], "stats": {},
            "variables": {"backend.gate": rec(1, unit="레포")},
            "s5_targets": [target("P01.backend.login.SEC1.3", "backend.login.SEC1", "sec1_flow", "no_trace", 9),
                           target("P01.backend.gate.4", "backend.gate", "gate_other_stack", "has_trace", 1)],
        })
        self.write("vars-prog.json", {
            "category": "prog", "pid": PID, "definition_choices": [], "stats": {}, "complete": True,
            "variables": {"prog.commits:Python": rec(7), "prog.lines:Python": rec(200), "prog.period:Python": rec(7)},
            "s5_targets": [],
        })
        self.run_py(["-c", PROBE_FINAL_BROKEN, CODE, PID])

        ai = self.read("final-ai.json")
        self.assertEqual([t["target_id"] for t in ai["s5_targets"]], ["P01.ai.features.2"])
        self.assertEqual((ai["s5_policy"]["pending"], ai["s5_policy"]["no_trace_not_sent"]), (1, 1))
        self.assertEqual(ai["variables"]["ai.integrations"]["value"], 0)
        self.assertIsNone(ai["variables"]["ai.features"]["value"])

        bad = self.read("final-backend_a.json")
        self.assertIn("boom", bad["finalize_error"])
        self.assertIn("answers={}", bad["finalize_error"])  # LLM 답 없이 불렀다
        self.assertIn("P01.backend.gate.4", bad["finalize_error"])  # 흔적 있는 대상만 넘겼다
        self.assertNotIn("SEC1.3", bad["finalize_error"])
        self.assertEqual(bad["variables"]["backend.gate"]["value"], 1)  # 모듈이 고치다 만 값이 아니라 규칙 값
        self.assertEqual([t["target_id"] for t in bad["s5_targets"]], ["P01.backend.gate.4"])
        self.assertEqual(bad["s5_policy"]["pending"], 1)

        prog = self.read("final-prog.json")  # 고장 난 모듈 뒤에도 계속했다
        self.assertEqual(prog["s5_applied"], 0)
        self.assertEqual(prog["s5_policy"]["pending"], 0)


if __name__ == "__main__":
    unittest.main()
