#!/usr/bin/env python3
"""lv-stat 2단계 백엔드 추출기 A: 게이트 + 로그인·보안(SEC1~7, 상한 C1~C3) + WAS(WAS1~5, 상한 WAS-C1).
버림용 스파이크(2026-11-26, 제품 코드 아님). 규칙만 쓴다(LLM·네트워크 없음). S5 대상만 표시한다.

usage: python3 -I cat_backend_a.py P01 P02 ...  → out/<pid>/vars-backend_a.json
- 「문서」 백엔드 v5 §1·§2·규칙 1~17, 부록 A-2.1~A-2.5·A-2.9, 「사용자 결정」 lv-stat/CLAUDE.md.
- 파서: Python 표준 ast, Java·Kotlin·JS·TS는 주석·문자열을 가린 정규식(tree-sitter 없음). backend_gate.PARSER에 남긴다.
- 받은 레포는 읽기만 한다. 근거는 위치만 남긴다. 비밀값 후보는 (파일, 커밋, 종류)만 남기고 S5로 보내지 않는다(「제안」 [B-08]).
"""
import hashlib
import json
import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.setrecursionlimit(10000)
import s2lib as L  # noqa: E402
import backend_gate as G  # noqa: E402
import cat_backend_a_oc as oc  # noqa: E402

KEY = 'backend_a'
LOGIN_ITEMS = [('SEC1', '기본', 1), ('SEC2', '접근 막기', 1), ('SEC3', '권한 나누기', 1), ('SEC4', '본인 확인 [AI 확인]', 2),
               ('SEC5', '토큰·세션 수명', 1), ('SEC6', '비밀값 숨기기', 1), ('SEC7', '보안 테스트', 2)]
WAS_ITEMS = [('WAS1', '기본', 1), ('WAS2', '설정 나누기', 1), ('WAS3', '운영 실행', 1), ('WAS4', '백그라운드 작업(가점형)', 1), ('WAS5', '공통 처리', 2)]
CAPS = {'SEC-C1': ('login', 'SQL에 사용자 입력을 문자열로 이어 붙임', 1), 'SEC-C2': ('login', '비밀번호를 평문으로 저장', 1),
        'SEC-C3': ('login', '쿠키로 인증하면서 CORS 자격 증명 허용 + 모든 출처', 2), 'WAS-C1': ('was', '운영 설정에서 DEBUG 켬·오류 응답에 스택 노출·개발 서버로 실행', 2)}
ONE_POINT = {'SEC1', 'SEC2', 'SEC3', 'SEC5', 'SEC6', 'WAS1', 'WAS2', 'WAS3', 'WAS4'}
MAX_INST = 300

# ---------------------------------------------------------------- S5 질문 틀(판정 기준은 문서 문구·사용자 결정을 그대로)
_COMMON = ("너는 신입 백엔드 개발자의 공개 레포 코드를 판정하는 검토자다. 보여 준 코드만 보고 판정한다. "
           "「문서」 백엔드 v5 규칙 6: 선언만 있고 연결이 없으면 인정하지 않는다(활성화 설정 없는 어노테이션, verify 없는 JWT, 등록 안 된 필터 등). "
           "규칙 11: README·문서 주장은 근거가 아니다(코드·설정·배포 스크립트만).")
S5_TEMPLATES = {
    'gate_db': dict(system=_COMMON + " 「문서」 백엔드 v5 규칙 1: 백엔드 레포 = 서버 프레임워크로 만든 API 1개 이상이 DB까지 이어짐 + 내 백엔드 코드 50줄 이상. "
                    "DB는 ORM 저장소·쿼리 실행·모델 저장 같은 실제 DB 접근이다. 메모리 자료 구조(Map·list·dict)로 만든 저장소는 DB가 아니다.",
                    question="보여 준 API 핸들러에서 호출을 따라가면 실제 DB 접근(ORM·쿼리 실행·모델 저장)에 닿는가? yes = 닿음(근거: DB 접근 줄), no = 닿지 않음(메모리 저장·외부 API만 등). "
                             "value에는 닿은 DB 종류(예: 'JPA', 'Mongoose', 'Django ORM', 'SQLite', 'Firebase')를 적는다."),
    'gate_other_stack': dict(system=_COMMON + " 「문서」 백엔드 v5 규칙 1: 백엔드 레포 = 서버 프레임워크로 만든 API 1개 이상이 DB까지 이어짐 + 내 백엔드 코드 50줄 이상. "
                             "이 레포는 규칙이 없는 서버 프레임워크를 쓴다(규칙 12: 규칙 없는 스택은 0이 아니라 모름).",
                             question="이 레포에 그 서버 프레임워크로 만든 API가 1개 이상 있고, 그중 하나가 실제 DB 접근에 닿는가? yes·no. value에는 프레임워크 이름을 적는다."),
    'sec1_flow': dict(system=_COMMON + " 「문서」 로그인·보안 '기본'(1점): 회원가입·로그인 + 가입 때 비밀번호를 느린 해시(BCrypt·Argon2·PBKDF2)로 저장. "
                      "소셜 로그인만이면 서버가 제공자 토큰을 확인하고 자체 토큰·세션을 발급해야 한다. 레포 단위 항목이다(누가 썼든 레포에 있으면 됨, 규칙 9).",
                      question="이 레포의 가입 흐름이 요청의 비밀번호를 느린 해시(BCrypt·Argon2·PBKDF2, Django make_password·create_user 포함)로 바꿔 저장하고 로그인 기능이 있는가? "
                               "(소셜 로그인만이면: 서버가 제공자 토큰·코드를 확인하고 자체 토큰·세션을 발급하는가?) yes·no. 근거는 해시 호출 줄과 저장 줄."),
    'sec2_routes': dict(system=_COMMON + " 「문서」 로그인·보안 '접근 막기'(1점): 쓰기 API 전부(가입·로그인 제외)에 인증 확인(서명 검증 포함). 하나라도 빠지면 0점. "
                        "인증 확인은 보안 설정(매처·permitAll 순서), 가드·미들웨어 등록, 권한 클래스, 의존성 주입으로 연결돼 있어야 한다. JWT는 서명 검증(verify)까지 해야 한다.",
                        question="규칙 결과의 '빠진 쓰기 API' 목록이 실제로 인증 없이 열려 있는가? yes = 보여 준 쓰기 API 전부가 인증 확인(서명 검증 포함)으로 막혀 있음, "
                                 "no = 인증 없이 열린 쓰기 API가 하나 이상 있음(근거: 그 API 줄). value에는 열려 있는 API 수를 적는다."),
    'sec3_role': dict(system=_COMMON + " 「문서」 로그인·보안 '권한 나누기'(1점): 역할(관리자·일반)별 접근 제한이 작동하게 연결.",
                      question="이 레포에 역할(관리자·일반 등)에 따라 API 접근을 막는 코드가 있고 실제로 API에 연결돼 있는가(서비스 안 if 검사 포함)? yes·no. 근거는 역할 검사 줄과 연결 줄."),
    'sec4_api': dict(system=_COMMON + " 「문서」 로그인·보안 '본인 확인'(2점, [AI 확인]): 수정·삭제 API의 절반 이상에서 작성자 = 로그인 사용자 확인. "
                     "「사용자 결정(2026-11-25)」 ① 로그인 사용자와 비교한 것만 센다. ② 로그인 없이 글 비밀번호로만 막는 것은 세지 않는다(로그인이 필수). "
                     "③ 요청에 대상 번호(URL·본문·쿼리)가 없고 서버가 로그인 사용자의 것만 찾아 고치는 API(예: 내 알림 모두 읽음, 내 오늘 목록 저장)는 분자·분모 모두에서 뺀다. "
                     "인정 모양: 작성자 비교, 소유자 조건으로 조회·수정(남의 것은 찾아지지 않음), 소유자를 확인하는 권한 클래스·가드·미들웨어(본문까지 확인), @PreAuthorize 같은 식. "
                     "역할만 확인·글 비밀번호만 확인·확인 코드가 그 API에 연결되지 않음은 인정하지 않는다.",
                     question="이 수정·삭제 API 하나를 판정한다. decision: yes = 작성자·소유자 = 로그인 사용자 확인이 이 API에 실제로 걸림, no = 그런 확인이 없음(남의 자원을 고칠 수 있음, 글 비밀번호만 확인하는 경우 포함), "
                              "unknown = 자료가 모자람. value에는 {\"kind\": \"owned|self|admin|none|unclear\", \"target_in\": \"path|query|body|none\", \"owner_check\": \"yes|no|unclear\", "
                              "\"shape\": \"compare|owner_query|guard|preauthorize|password_only|other|none\"}를 적는다. kind: owned = 작성자·소유자가 있는 자원, self = 로그인 사용자 자신의 것만 다룸, "
                              "admin = 관리자 전용, none = 작성자 개념이 없는 자원."),
    'sec5_life': dict(system=_COMMON + " 「문서」 로그인·보안 '토큰·세션 수명'(1점): 만료 + 재발급(또는 세션 만료)과 로그아웃 무효화 둘 다.",
                      question="이 레포에서 (1) 토큰 만료 시간 + 재발급 API, 또는 세션 만료 설정이 있고 (2) 로그아웃 때 서버 쪽에서 토큰·세션을 무효화(refresh 토큰 삭제·블랙리스트·세션 무효화)하는가? "
                               "둘 다면 yes, 하나라도 없으면 no. value에는 {\"expiry\": true|false, \"reissue_or_session\": true|false, \"logout_invalidate\": true|false}."),
    'sec7_other_user': dict(system=_COMMON + " 「문서」 로그인·보안 '보안 테스트'(2점): 401·403·남의 글 수정 거부를 각각 단언(일부만이면 1점). "
                            "결과를 단언하는 내 테스트만 센다(자동 생성 테스트 제외, 규칙 8).",
                            question="보여 준 테스트 중에 '다른 사용자가 남의 글(자원)을 수정·삭제하려 하면 거부된다'를 준비 코드(다른 사용자로 요청)와 단언(403·404·예외)으로 확인하는 테스트가 있는가? yes·no. "
                                     "value에는 단언한 결과(예: '403', '404', 'exception')를 적는다."),
    'was5_purpose': dict(system=_COMMON + " 「문서」 WAS '공통 처리'(2점): 요청 흐름에 끼우는 직접 만든 코드 중 서로 다른 목적 2종, 각각 API 3개 이상에 적용. "
                         "제외: 인증·인가·로그인 사용자 주입·입력 검사·요청 로그·추적 ID·전역 예외·DB 세션 주입·CORS·프레임워크 내장 기능.",
                         question="보여 준 요청 흐름 코드(필터·인터셉터·AOP·미들웨어·데코레이터·Depends·Pipe) 하나가 제외 목록에 들지 않는 목적의 직접 만든 코드인가? "
                                  "yes = 제외 목록 밖의 목적(근거: 그 코드 줄), no = 제외 목록에 듦 또는 직접 만든 코드가 아님. value에는 {\"purpose\": \"한두 낱말 목적\", \"excluded_as\": \"제외 항목 이름 또는 null\"}."),
    'cap_sql': dict(system=_COMMON + " 「문서」 로그인·보안 상한: SQL에 사용자 입력을 문자열로 이어 붙임 → 최대 1. 확실할 때만 건다(부록 A-2.3).",
                    question="보여 준 SQL·JPQL 문자열 이어 붙이기(또는 ${}·f-string·Unsafe raw 쿼리)에 요청 값(경로·쿼리·본문 매개변수)이 걸러지지 않고 들어가 실행되는가? "
                             "yes = 사용자 입력이 그대로 SQL 문자열에 들어감, no = 상수·허용 목록으로 거른 값이거나 매개변수 바인딩임."),
    'cap_plain': dict(system=_COMMON + " 「문서」 로그인·보안 상한: 비밀번호를 평문으로 저장 → 최대 1. 확실할 때만 건다.",
                      question="가입·비밀번호 변경 경로에서 요청의 비밀번호 값이 해시 호출 없이 DB 저장 호출의 비밀번호 칸에 닿는가? yes = 평문 저장, no = 저장 전에 해시함."),
    'cap_cors': dict(system=_COMMON + " 「문서」 로그인·보안 상한: 쿠키로 인증하면서 CORS 자격 증명 허용 + 모든 출처 → 최대 2. 확실할 때만 건다.",
                     question="이 레포가 (1) 쿠키·세션으로 인증하고 (2) CORS에서 자격 증명을 허용하며 (3) 모든 출처(* 또는 요청 출처를 그대로 돌려줌)를 허용하는가? 셋 다면 yes."),
    'cap_was': dict(system=_COMMON + " 「문서」 WAS 상한: 운영 설정에서 DEBUG 켬·오류 응답에 스택 노출·개발 서버로 실행 → 최대 2. 운영 설정 = 배포 근거(Dockerfile CMD·compose·배포 스크립트·prod 프로필)가 실제로 읽는 설정과 실행 명령(규칙 10).",
                    question="배포 근거의 실행 명령이 실제로 읽는 운영 설정에서 DEBUG가 켜져 있거나, 오류 응답에 스택을 내보내거나, 개발 서버(runserver·--reload·nodemon·npm run dev)로 띄우는가? yes·no."),
}

# ---------------------------------------------------------------- 공통 도구
WRITE = ('POST', 'PUT', 'PATCH', 'DELETE')
AUTH_PATH = re.compile(r'(?i)(log[-_]?out|sign[-_]?out|sign[-_]?up|signin|sign[-_]?in|log[-_]?in|login|register|join|auth/(?:token|kakao|google|naver|github|oauth|callback|social)|oauth|token(?:/refresh)?$|refresh|reissue|password/(?:reset|forgot|find)|find-?(?:id|password)|email/(?:verify|send|check)|verify-?email|duplicate|check-?(?:id|email|nickname))')
STRICT_AUTH_PATH = re.compile(r'(?i)(sign[-_]?up|sign[-_]?in|log[-_]?in|register|join)')


class B:
    """게이트를 통과한 (레포, 프레임워크) 하나의 백엔드 보기."""

    def __init__(self, repo, fw, ctx):
        self.repo, self.fw, self.ctx = repo, fw, ctx
        self.oc = ctx['oc']
        self.files = [p for p in ctx['backend_files'][fw] if not re.search(r'(^|/)conftest\.py$', p)]
        self.roots = [r['dir'] for r in ctx['roots'] if fw in r['fw']] or ['']
        self.texts = ctx['texts']
        self._clean = {}
        allp = [f['path'] for f in repo.files if G.kind_of(f) in ('config', 'test', 'other', 'code', 'data', 'migration') and not L.VENDOR.search(f['path'])]
        self.cfg_paths = [p for p in allp if (ANY_CFG.search(p)) or (CFG_FILE.search(p) and any(G.under(p, d) for d in self.roots)
                                                                         and not (G.FRONT_PATH.search(p) and fw in ('nest', 'express')))]
        self.test_paths = [f['path'] for f in repo.files if G.kind_of(f) == 'test' and G.ext_of(f['path']) in G.FW_LANG[fw]
                           and any(G.under(f['path'], d) for d in self.roots)]
        need = [p for p in self.cfg_paths + self.test_paths if p not in self.texts]
        if need:
            self.texts = dict(self.texts)
            self.texts.update(G.batch_read(repo, need))
        self.routes = [e for e in ctx['routes'] if e.get('fw') == fw]

    def clean(self, path):
        if path not in self._clean:
            t = self.texts.get(path)
            if t is None:
                self._clean[path] = None
            elif path.endswith('.py'):
                self._clean[path] = oc.strip_py(t)
            elif G.ext_of(path) in ('.java', '.kt', '.js', '.ts', '.mjs', '.cjs', '.gradle', '.kts'):
                self._clean[path] = oc.strip_c(t)[0]
            elif G.ext_of(path) in ('.yml', '.yaml', '.properties', '.toml', '.cfg', '.ini', '.conf', '.sh', '') or 'Dockerfile' in path or 'Procfile' in path:
                self._clean[path] = '\n'.join(re.sub(r'(^|\s)#.*$', r'\1', ln) if not path.endswith('.json') else ln for ln in t.split('\n'))
            else:
                self._clean[path] = t
        return self._clean[path]

    def own(self, path):
        return G.own_set(self.repo, path)

    def mine(self, path, line):
        s = self.own(path)
        return bool(s) and line in s

    def share(self, path):
        """그 파일의 줄(빈 줄·주석 뺌) 중 내 줄 비율(공용 설정 과반 판정, 규칙 9)."""
        t = self.texts.get(path)
        if t is None:
            return None
        lines = (self.clean(path) or '').split('\n')
        s = self.own(path)
        if s is None:
            return None
        tot = [i for i, ln in enumerate(lines, 1) if ln.strip()]
        if not tot:
            return 0.0
        return sum(1 for i in tot if i in s) / len(tot)

    def scan(self, rx, paths=None, flags=0):
        """-> [(path, line, mine, match_text_len)]. 주석을 뺀 글에서 찾는다."""
        out = []
        for p in (paths if paths is not None else self.files):
            c = self.clean(p)
            if not c:
                continue
            for mo in rx.finditer(c):
                ln = c.count('\n', 0, mo.start()) + 1
                out.append((p, ln, self.mine(p, ln), mo))
        return out

    def ev(self, path, line, rule, note=None):
        return L.evidence(self.repo, path=path, line=line, rule=rule, note=note)


CFG_FILE = re.compile(r'(?i)(^|/)(application[^/]*\.(ya?ml|properties)|bootstrap[^/]*\.ya?ml|settings[^/]*\.py|[^/]*settings\.py|config/[^/]*\.(js|ts|json|py)|'
                      r'Dockerfile[^/]*|docker-compose[^/]*\.ya?ml|compose[^/]*\.ya?ml|\.github/workflows/[^/]+\.ya?ml|Procfile|[^/]*\.sh|package\.json|'
                      r'ecosystem\.config\.[cm]?js|nginx[^/]*\.conf|\.env[^/]*|appspec\.ya?ml|render\.yaml|fly\.toml|railway\.json|app\.yaml|gunicorn[^/]*\.py|'
                      r'logback[^/]*\.xml|log4j2?[^/]*\.xml|\.gitignore|main\.(ts|js)|app\.module\.ts|server\.(ts|js)|app\.(ts|js)|index\.(ts|js)|asgi\.py|wsgi\.py|main\.py)$')
ANY_CFG = re.compile(r'(?i)(^|/)(Dockerfile[^/]*|docker-compose[^/]*\.ya?ml|compose[^/]*\.ya?ml|\.github/workflows/[^/]+\.ya?ml|Procfile|[^/]*\.sh|\.gitignore|nginx[^/]*\.conf|'
                     r'appspec\.ya?ml|render\.yaml|fly\.toml|railway\.json|app\.yaml)$')
RUN_FILE = re.compile(r'(?i)(^|/)(Dockerfile[^/]*|docker-compose[^/]*\.ya?ml|compose[^/]*\.ya?ml|\.github/workflows/[^/]+\.ya?ml|Procfile|[^/]*\.sh|ecosystem\.config\.[cm]?js|appspec\.ya?ml|render\.yaml|fly\.toml|railway\.json|app\.yaml)$')


def stable_tid(pid, var, repo_key, tmpl, files, key):
    h = hashlib.sha1(json.dumps([repo_key, tmpl, [list(x) for x in files][:4], key], ensure_ascii=False, default=str).encode()).hexdigest()[:6]
    return f'{pid}.{KEY}.{var}.{h}'


def target(pid, var, n, repo, template, files=(), commits=(), text=None, rule_result=None, trace='has_trace', priority=5, group=None, stop_rule=None):
    t = dict(target_id=f'{pid}.{KEY}.{var}.{n:03d}', var=var, repo=repo.key, template=template,
             material=dict(files=[dict(path=p, start=a, end=b) for p, a, b in files][:8], commits=list(commits)[:5]),
             rule_result=rule_result, trace=trace, priority=priority)
    if text:
        t['material']['text'] = text[:1500]
    if group:
        t['group'] = group
    if stop_rule:
        t['stop_rule'] = stop_rule
    return t


def span(path, line, before=15, after=40):
    return (path, max(1, line - before), line + after)


def ep_span(ep):
    p, a, b = G.ep_lines(ep)
    return (p, max(1, a - 3), min(b, a + 120))


# ---------------------------------------------------------------- SEC1 기본(레포 단위)
SLOW_HASH = re.compile(r'BCryptPasswordEncoder|Argon2PasswordEncoder|Pbkdf2PasswordEncoder|PasswordEncoderFactories|DelegatingPasswordEncoder|passwordEncoder\s*\.\s*encode\s*\(|'
                       r'\bencoder\s*\.\s*encode\s*\(|\bbcrypt\w*\s*\.\s*(?:hash|hashSync|genSalt|hashpw|gensalt)\s*\(|\bargon2\s*\.\s*hash\s*\(|\bhash\s*\(\s*[\w.]*password|'
                       r'\bmake_password\s*\(|\bset_password\s*\(|\bcreate_user\s*\(|\bcreate_superuser\s*\(|UserCreationForm|\bpwd_context\s*\.\s*hash\s*\(|CryptContext\s*\(|'
                       r'\bgenerate_password_hash\s*\(|\bpbkdf2\w*\s*\(|\bhashpw\s*\(|BCrypt\s*\.\s*hashpw\s*\(|\bget_password_hash\s*\(|\bhash_password\s*\(|\bhashPassword\s*\(|'
                       r'pre\s*\(\s*[\'"]save[\'"][\s\S]{0,300}?bcrypt')
OTHER_HASH = re.compile(r'(?i)\bscrypt\w*\s*\(|createHash\s*\(\s*[\'"](?:sha|md5)|MessageDigest\s*\.\s*getInstance|hashlib\s*\.\s*(?:sha\d+|md5)\s*\(|\bsha256\s*\(')
SIGNUP_NAME = re.compile(r'(?i)sign[-_]?up|register|(?:^|/)(?:members?|users?|auth|accounts?)/join(?:$|/)|^/?join/?$|join_?member|member_?join|join_?user|create_?user|createUser|createMember|addUser|addMember|saveUser|saveMember|회원가입')
LOGIN_NAME = re.compile(r'(?i)log[-_]?in|sign[-_]?in|authenticate|obtain_?token|token/?$|TokenObtain|issueToken|createToken')
LOGIN_FW = re.compile(r"include\s*\(\s*['\"](?:allauth\.urls|django\.contrib\.auth\.urls|dj_rest_auth\.urls|djoser\.urls|rest_framework\.urls)|auth_views\.LoginView|"
                      r'\.formLogin\s*\(|formLogin\s*\{|\bLoginView\b|obtain_auth_token|TokenObtainPairView|\bauthenticate\s*\(\s*request|passport\s*\.\s*authenticate\s*\(\s*[\'"]local|'
                      r'\bauthenticationManager\s*\.\s*authenticate\s*\(|OAuth2PasswordRequestForm|\blogin\s*\(\s*request\s*,|signInWithEmailAndPassword|LocalStrategy')
SOCIAL = re.compile(r'(?i)kauth\.kakao\.com|kapi\.kakao\.com|nid\.naver\.com|openapi\.naver\.com|oauth2\.googleapis\.com|www\.googleapis\.com/oauth2|accounts\.google\.com|github\.com/login/oauth|api\.github\.com/user|'
                    r'verify_oauth2_token|verifyIdToken|\.oauth2Login\s*\(|oauth2Login\s*\{|GoogleStrategy|KakaoStrategy|NaverStrategy|GitHubStrategy|allauth\.socialaccount|OAuth2UserService|DefaultOAuth2UserService')
ISSUE_TOKEN = re.compile(r'\bjwt\s*\.\s*sign\s*\(|\bjwtService\s*\.\s*sign\w*\s*\(|Jwts\s*\.\s*builder\s*\(|JWT\s*\.\s*create\s*\(|\bjwt\s*\.\s*encode\s*\(|create_access_token\s*\(|'
                         r'RefreshToken\s*\.\s*for_user\s*\(|AccessToken\s*\.\s*for_user|\.createToken\s*\(|generateToken\s*\(|generateAccessToken\s*\(|createAccessToken\s*\(|'
                         r'\blogin\s*\(\s*request\s*,|req\s*\.\s*session\s*\.\s*\w+\s*=|req\s*\.\s*login\s*\(|session\s*\.\s*setAttribute\s*\(|Token\.objects\.(?:get_or_create|create)')


def sec1(b, cx):
    """레포 단위(규칙 9): 가입 + 느린 해시 저장(흐름), 로그인. 소셜만이면 제공자 확인 + 자체 발급."""
    routes = b.routes
    sign = [e for e in routes if e['verb'] in WRITE + ('ANY',) and (SIGNUP_NAME.search(e['path'] or '') or SIGNUP_NAME.search(e.get('name') or '')
                                                                    or any(SIGNUP_NAME.search(h['name']) for h in e['handlers']))]
    login_r = [e for e in routes if (LOGIN_NAME.search(e['path'] or '') or LOGIN_NAME.search(e.get('name') or '') or any(LOGIN_NAME.search(h['name']) for h in e['handlers']))]
    login_fw = b.scan(LOGIN_FW, b.files + b.cfg_paths)
    hashes = b.scan(SLOW_HASH)
    other_h = b.scan(OTHER_HASH)
    social = b.scan(SOCIAL, b.files + b.cfg_paths)
    issue = b.scan(ISSUE_TOKEN)
    has_login = bool(login_r or login_fw)
    # 흐름: 가입 핸들러에서 느린 해시까지(호출 그래프 4단계)
    res = dict(item='SEC1', unit='repo')
    flow = None
    for e in sign:
        hit = reach(b, e['handlers'], SLOW_HASH)
        if hit:
            flow = (e, hit)
            break
    hook = None
    if sign and not flow:
        # 모델 저장 훅·사용자 매니저에서 해시(모든 저장에 걸림): pre('save')·@BeforeInsert·@PrePersist·BaseUserManager·save() 재정의
        for p, ln, mine, mo in hashes:
            c = b.clean(p) or ''
            before = '\n'.join(c.split('\n')[max(0, ln - 25):ln])
            if re.search(r"pre\s*\(\s*['\"]save['\"]|@BeforeInsert|@BeforeUpdate|@PrePersist|BaseUserManager|def\s+save\s*\(|def\s+create_user\s*\(|beforeCreate|beforeSave|hooks\s*:", before) or mo.group(0).startswith(('create_user', 'UserCreationForm')):
                hook = (p, ln)
                break
    lib_auth = b.scan(re.compile(r"include\s*\(\s*['\"](?:allauth\.urls|dj_rest_auth\.registration\.urls|djoser\.urls|rest_auth\.registration\.urls)"), b.files)
    if lib_auth and not flow:
        res.update(score=1, state='value_rule', ev=[b.ev(lib_auth[0][0], lib_auth[0][1], 'backend.login.SEC1.django-auth-library@1')], note='가입·로그인을 라이브러리 URL로 연결(Django 기본 PBKDF2 해시)')
        return res
    if hook and has_login:
        e = sign[0]
        res.update(score=1, state='value_rule', ev=[b.ev(e['file'], e['line'], 'backend.login.SEC1.signup-route@1'), b.ev(hook[0], hook[1], 'backend.login.SEC1.slow-hash-model-hook@1')],
                   note='가입 저장 경로의 모델 훅·사용자 매니저에서 느린 해시')
        return res
    res = dict(item='SEC1', unit='repo')
    if flow and has_login:
        e, (g, ln) = flow
        res.update(score=1, state='value_rule', ev=[b.ev(e['file'], e['line'], 'backend.login.SEC1.signup-route@1'), b.ev(g['file'], ln, 'backend.login.SEC1.slow-hash-flow@1')])
        return res
    if not sign and social and issue and has_login is False:
        res.update(score=1, state='value_rule', ev=[b.ev(social[0][0], social[0][1], 'backend.login.SEC1.social-provider@1'), b.ev(issue[0][0], issue[0][1], 'backend.login.SEC1.own-token@1')],
                   note='소셜 로그인만: 제공자 확인 + 자체 토큰·세션 발급')
        return res
    if social and issue and not sign:
        res.update(score=1, state='value_rule', ev=[b.ev(social[0][0], social[0][1], 'backend.login.SEC1.social-provider@1'), b.ev(issue[0][0], issue[0][1], 'backend.login.SEC1.own-token@1')],
                   note='가입 API 없음, 소셜 로그인 + 자체 발급')
        return res
    trace = bool(sign or has_login or hashes or social)
    res.update(score=0, state='value_rule' if trace else 'zero_unused', ev=[], trace=trace,
               note=f'가입 {len(sign)} · 로그인 {len(login_r) + len(login_fw)} · 느린 해시 {len(hashes)} · 목록 밖 해시 {len(other_h)} · 소셜 {len(social)}')
    if trace:
        files = []
        if sign:
            files.append(ep_span(sign[0]))
        if hashes:
            files.append(span(hashes[0][0], hashes[0][1]))
        if login_r:
            files.append(ep_span(login_r[0]))
        if social:
            files.append(span(social[0][0], social[0][1]))
        res['s5'] = [dict(template='sec1_flow', files=files, rule_result=dict(signup=len(sign), login=len(login_r) + len(login_fw), slow_hash=len(hashes),
                                                                                    other_hash=len(other_h), social=len(social), flow_connected=False))]
    res['other_hash'] = [(p, ln) for p, ln, m, mo in other_h[:3]]
    return res


def reach(b, handlers, rx, depth=4, limit=60):
    """핸들러에서 호출 그래프를 따라 rx에 맞는 줄: (함수, 파일 줄) 또는 None."""
    work = [(h, 0) for h in handlers]
    seen = set()
    n = 0
    while work and n < limit:
        f, d = work.pop(0)
        k = (f['file'], f.get('cls'), f['name'], f['line'])
        if k in seen:
            continue
        seen.add(k)
        n += 1
        c = f.get('code') or ''
        m = oc.strip_c(c)[0] if f['lang'] != 'py' else c
        mo = rx.search(m)
        if mo:
            return f, G.code_line(f, m.count('\n', 0, mo.start()) + 1)
        if d >= depth:
            continue
        for recv, name, this, args, cline in oc.calls_of(f):
            for g in b.oc.resolve_call(f, recv, name, this):
                work.append((g, d + 1))
    return None


# ---------------------------------------------------------------- SEC2 접근 막기 · SEC3 권한 나누기
SPRING_CHAIN = re.compile(r'\b(?:authorizeHttpRequests|authorizeRequests|authorizeExchange)\b')
SPRING_ANY_AUTH = re.compile(r'\.anyRequest\s*\(\s*\)\s*\.\s*(?:authenticated|hasRole|hasAnyRole|hasAuthority|hasAnyAuthority|access)\s*\(|anyExchange\s*\(\s*\)\s*\.\s*authenticated|anyRequest\s*\(\s*\)\s*\.\s*fullyAuthenticated|authorize\s*\(\s*anyRequest\s*,\s*authenticated')
MATCHER = re.compile(r'\.(?:requestMatchers|antMatchers|mvcMatchers|pathMatchers|regexMatchers)\s*\(([^()]*(?:\([^()]*\)[^()]*)*)\)\s*\.\s*(permitAll|authenticated|hasRole|hasAnyRole|hasAuthority|hasAnyAuthority|denyAll|anonymous|access)\s*\(')
JWT_VERIFY = re.compile(r'parseClaimsJws|parseSignedClaims|verifyWith\s*\(|setSigningKey\s*\(|JWT\s*\.\s*require\s*\(|JWTVerifier|\.verify\s*\(\s*\w*[Tt]oken|\bjwt\s*\.\s*verify\s*\(|jwtService\s*\.\s*verify\w*\s*\(|'
                        r'ExtractJwt|PassportStrategy\s*\(\s*Strategy|passport-jwt|secretOrKey|jwt\s*\.\s*decode\s*\([^)]*(?:SECRET|secret|key|KEY)[^)]*algorithms|JWTAuthentication|JwtDecoder|oauth2ResourceServer|'
                        r'jwtVerify\s*\(|TokenAuthentication|SessionAuthentication|rest_framework_simplejwt|decode_token|verify_token|verifyToken\s*\(|jose\s*\.\s*jwt\s*\.\s*decode\s*\([^)]*key')
JWT_DECODE_ONLY = re.compile(r'\bjwt\s*\.\s*decode\s*\(|jwt_decode\s*\(|jwtDecode\s*\(|verify_signature\s*[\'"]?\s*:\s*False|parseClaimsJwt\s*\(')
AUTH_MW_NAME = re.compile(r'(?i)auth|jwt|token|login|verify|protect|passport|guard|session|ensure|require[A-Z_]?user|isLogged|loggedIn|checkUser|authenticate')
NEST_AUTH_GUARD = re.compile(r'@UseGuards\s*\(([^)]*)\)')
NEST_GLOBAL_GUARD = re.compile(r'APP_GUARD|useGlobalGuards\s*\(')
NEST_PUBLIC = re.compile(r'@Public\s*\(|@SkipAuth\s*\(|@AllowAnonymous\s*\(|IS_PUBLIC_KEY')
DRF_DEFAULT_PERM = re.compile(r'DEFAULT_PERMISSION_CLASSES[\'"]?\s*:\s*[\(\[]([^\]\)]*)[\]\)]', re.S)
PY_AUTH_DEP = re.compile(r'Depends\s*\(\s*[\w.]*(?:current_?(?:active_?)?user|get_user|current_member|auth|verify|token|login|jwt|oauth2_scheme|security)\w*', re.I)
PY_LOGIN_REQ = re.compile(r'@login_required|LoginRequiredMixin|@permission_required|IsAuthenticated|@jwt_required|@token_required|@auth_required|@authentication_classes|IsOwner|Is\w+User\b|permissions?\.\w+')
ROLE_CHECK = re.compile(r'(?i)\.(?:hasRole|hasAnyRole|hasAuthority|hasAnyAuthority)\s*\(|@PreAuthorize\s*\(\s*"[^"]*has(?:Any)?(?:Role|Authority)|@Secured\s*\(|@RolesAllowed\s*\(|@Roles\s*\(|@UseGuards\s*\([^)]*Role|'
                        r'IsAdminUser|is_staff|is_superuser|@staff_member_required|user_passes_test|@permission_required|role\s*(?:!==?|===?|!=|==)\s*[\'"`]?\w*(?:admin|ADMIN|manager|MANAGER|seller|SELLER)|'
                        r'(?:getRole|role|roles)\s*\(\s*\)\s*(?:!=|==|\.equals)|(?:Role|UserRole|MemberRole)\s*\.\s*(?:ADMIN|MANAGER|SELLER|OWNER)\b|isAdmin\s*\(|requireAdmin|adminOnly|checkAdmin|verifyAdmin|hasPermission\s*\(')
ROLE_TRACE = re.compile(r'(?i)\benum\s+\w*Role\b|\brole\s*[:=]|ROLE_ADMIN|is_admin|isAdmin|\bUserRole\b|\badmin\b')
METHOD_SEC_ON = re.compile(r'@EnableMethodSecurity|@EnableGlobalMethodSecurity\s*\([^)]*(?:prePostEnabled|securedEnabled|jsr250Enabled)\s*=\s*true|@EnableReactiveMethodSecurity')


def ant_rx(pat):
    pat = pat.strip().strip('"\'')
    if not pat.startswith('/'):
        pat = '/' + pat
    r = re.escape(pat).replace(r'/\*\*', '(?:/.*)?').replace(r'\*\*', '.*').replace(r'\*', '[^/]*')
    r = re.sub(r'\\\{[^}]*\\\}', '[^/]+', r)
    return re.compile('^' + r + '/?$')


def norm_path(p):
    p = '/' + (p or '').strip().strip('/')
    p = re.sub(r'//+', '/', p)
    return re.sub(r'\{[^}]+\}|:\w+|<[^>]+>', 'X', p)


def spring_rules(b):
    """SecurityFilterChain 매처 목록: [(패턴 rx 목록, 판정, path, line, mine)] + anyRequest 판정."""
    rules, anyreq = [], None
    for p in b.files:
        c = b.clean(p)
        if not c or not SPRING_CHAIN.search(c):
            continue
        for mo in MATCHER.finditer(c):
            pats = re.findall(r'"([^"]*)"', mo.group(1))
            meth = re.search(r'HttpMethod\.(\w+)', mo.group(1))
            ln = c.count('\n', 0, mo.start()) + 1
            rules.append(([ant_rx(x) for x in pats] if pats else [re.compile('.*')], mo.group(2), meth.group(1) if meth else None, p, ln, b.mine(p, ln)))
        m2 = SPRING_ANY_AUTH.search(c)
        if m2:
            anyreq = (p, c.count('\n', 0, m2.start()) + 1)
        elif re.search(r'\.anyRequest\s*\(\s*\)\s*\.\s*permitAll', c) and anyreq is None:
            anyreq = False
    return rules, anyreq


def route_auth(b, e, cx):
    """라우트 하나의 인증 판정: ('yes'|'no'|'unclear', 근거 (path,line) 또는 None, 방법)"""
    h = e['handlers'][0] if e['handlers'] else None
    annos = (h.get('annos') or '') if h else ''
    fw = b.fw
    if fw == 'spring':
        if re.search(r'@PreAuthorize|@Secured|@RolesAllowed', annos) and cx['method_sec']:
            return 'yes', (e['file'], e['line']), 'method-security'
        rules, anyreq = cx['spring_rules']
        path = norm_path(e['path']).replace('X', 'x1')
        for rxs, verdict, meth, p, ln, mine in rules:
            if meth and meth.upper() != e['verb']:
                continue
            if any(rx.match(path) or rx.match(norm_path(e['path'])) for rx in rxs):
                if verdict == 'permitAll' or verdict == 'anonymous':
                    return 'no', (p, ln), 'permitAll-matcher'
                return 'yes', (p, ln), 'matcher-' + verdict
        if anyreq:
            return 'yes', anyreq, 'anyRequest-authenticated'
        if cx['interceptor_auth']:
            return 'unclear', cx['interceptor_auth'][0], 'interceptor'
        if h and re.search(r'@(?:AuthenticationPrincipal|LoginUser|CurrentUser|AuthUser|Login|LoginMember|CurrentMember|AuthMember)\b', ' '.join(p[0] for p in h.get('params', []) if p)):
            return 'unclear', (e['file'], e['line']), 'login-user-param'
        return ('unclear' if cx['auth_trace'] else 'no'), None, 'no-rule'
    if fw == 'nest':
        g = ' '.join(e.get('guard_names') or [])
        if g and AUTH_MW_NAME.search(g):
            return 'yes', (e['file'], e['line']), 'use-guards'
        if cx['nest_global']:
            if NEST_PUBLIC.search(annos):
                return 'no', (e['file'], e['line']), 'public-decorator'
            return 'yes', cx['nest_global'], 'global-guard'
        return ('unclear' if cx['auth_trace'] else 'no'), None, 'no-guard'
    if fw == 'express':
        g = ' '.join(e.get('guard_names') or [])
        if g and AUTH_MW_NAME.search(g):
            return 'yes', (e['file'], e['line']), 'route-middleware'
        if re.search(r'@UseBefore\s*\(\s*\w*(?:auth|Auth|jwt|Jwt|token|Token|check\w*Token)', annos) or re.search(r'@Authorized\s*\(', annos):
            return 'yes', (e['file'], e['line']), 'routing-controllers'
        c = b.clean(e['file']) or ''
        before = c[:sum(len(x) + 1 for x in c.split('\n')[:max(0, e['line'] - 1)])]
        mu = re.search(r'\b(?:router|app|r|api)\s*\.\s*use\s*\(\s*(?:[\'"`][^\'"`]*[\'"`]\s*,\s*)?([\w.]*(?:auth|Auth|jwt|Jwt|token|Token|verify|Verify|protect|Protect|passport)[\w.]*)', before)
        if mu:
            return 'yes', (e['file'], before.count('\n', 0, mu.start()) + 1), 'router-use'
        if cx['express_mount_auth']:
            return 'unclear', cx['express_mount_auth'], 'mount-auth'
        return ('unclear' if cx['auth_trace'] else 'no'), None, 'no-middleware'
    if fw == 'django':
        txt = annos + ' ' + ' '.join((hh.get('annos') or '') for hh in e['handlers'])
        cls_assign = ''
        if h and h.get('cls'):
            for cl in b.oc.classes.get(h['cls'], []):
                cls_assign += ' ' + (cl.get('assigns', {}).get('permission_classes', '')) + ' ' + (cl.get('header') or '')
        if re.search(r'AllowAny', cls_assign + txt):
            return 'no', (e['file'], e['line']), 'allow-any'
        if PY_LOGIN_REQ.search(txt + cls_assign):
            return 'yes', (h['file'], h['line']) if h else (e['file'], e['line']), 'permission'
        if cx['drf_default_auth'] and e['kind'] not in ('django-url', 'py-fview') or (cx['drf_default_auth'] and '@api_view' in txt):
            return 'yes', cx['drf_default_auth'], 'drf-default-permission'
        if h and re.search(r'request\s*\.\s*user\s*\.\s*is_authenticated|if\s+not\s+request\s*\.\s*user', h.get('code') or ''):
            return 'yes', (h['file'], h['line']), 'inline-check'
        return ('unclear' if cx['auth_trace'] else 'no'), None, 'no-permission'
    if fw == 'fastapi':
        params = ' '.join((p[0] or '') + ' ' + (p[1] or '') for p in (h.get('params') or [])) if h else ''
        if PY_AUTH_DEP.search(params) or PY_AUTH_DEP.search(annos):
            return 'yes', (h['file'], h['line']), 'depends-user'
        c = b.clean(e['file']) or ''
        if re.search(r'APIRouter\s*\([^)]*dependencies\s*=\s*\[[^\]]*Depends\s*\(\s*\w*(?:user|auth|token|verify)', c, re.I):
            return 'yes', (e['file'], 1), 'router-dependencies'
        return ('unclear' if cx['auth_trace'] else 'no'), None, 'no-depends'
    return 'unclear', None, 'no-rule'


def sec_context(b):
    cx = {}
    allp = b.files + b.cfg_paths
    cx['method_sec'] = bool(b.scan(METHOD_SEC_ON, allp))
    cx['spring_rules'] = spring_rules(b) if b.fw == 'spring' else ([], None)
    ia = []
    if b.fw == 'spring':
        for p in b.files:
            c = b.clean(p) or ''
            if re.search(r'implements\s+HandlerInterceptor|extends\s+HandlerInterceptorAdapter', c) and re.search(r'(?i)token|jwt|auth|login|session', c):
                ia.append((p, 1))
    cx['interceptor_auth'] = ia
    ng = b.scan(NEST_GLOBAL_GUARD, allp) if b.fw == 'nest' else []
    cx['nest_global'] = (ng[0][0], ng[0][1]) if ng else None
    dd = []
    if b.fw == 'django':
        for p in allp:
            c = b.clean(p) or ''
            mo = DRF_DEFAULT_PERM.search(c)
            if mo and re.search(r'IsAuthenticated|DjangoModelPermissions', mo.group(1)):
                dd.append((p, c.count('\n', 0, mo.start()) + 1))
    cx['drf_default_auth'] = dd[0] if dd else None
    em = []
    if b.fw == 'express':
        for p in b.files:
            c = b.clean(p) or ''
            mo = re.search(r'\b(?:app|server)\s*\.\s*use\s*\(\s*[\'"`][^\'"`]*[\'"`]\s*,\s*[\w.]*(?:auth|Auth|jwt|Jwt|verify|Verify|protect)[\w.]*\s*,', c)
            if mo:
                em.append((p, c.count('\n', 0, mo.start()) + 1))
    cx['express_mount_auth'] = em[0] if em else None
    cx['jwt_verify'] = b.scan(JWT_VERIFY, allp)
    cx['jwt_decode_only'] = b.scan(JWT_DECODE_ONLY, allp)
    cx['auth_trace'] = bool(cx['jwt_verify'] or cx['spring_rules'][0] or cx['nest_global'] or cx['drf_default_auth'] or ia or
                            b.scan(re.compile(r'(?i)passport|jsonwebtoken|spring-boot-starter-security|SecurityFilterChain|WebSecurityConfigurerAdapter|AuthGuard|login_required|'
                                              r'simplejwt|python-jose|fastapi\.security|OAuth2PasswordBearer|HTTPBearer|express-session|authMiddleware'), allp))
    return cx


def sec2(b, cx, mine_api):
    """분모 = 내 쓰기 API(가입·로그인 제외). 전부 인증이면 1."""
    writes = [e for e in b.routes if (e['verb'] in WRITE or (e['verb'] == 'ANY' and b.fw == 'django')) and mine_api(e)]
    res = dict(item='SEC2', unit='mine')
    alt = {}
    for mode, rx in (('lenient', AUTH_PATH), ('strict', STRICT_AUTH_PATH)):
        den = [e for e in writes if not (rx.search(e['path'] or '') or rx.search(e.get('name') or '') or any(rx.search(h['name']) for h in e['handlers']))]
        verdicts = [(e,) + route_auth(b, e, cx) for e in den]
        alt[mode] = dict(den=len(den), yes=sum(1 for v in verdicts if v[1] == 'yes'), no=sum(1 for v in verdicts if v[1] == 'no'),
                         unclear=sum(1 for v in verdicts if v[1] == 'unclear'), verdicts=verdicts)
    v = alt['lenient']
    verify_ok = (not cx['jwt_decode_only']) or bool(cx['jwt_verify'])
    res['alt'] = {k: dict(den=x['den'], yes=x['yes'], no=x['no'], unclear=x['unclear']) for k, x in alt.items()}
    res['instances'] = [dict(path=e['file'], line=e['line'], what=f"{e['verb']} {e['path'][:60]} 인증:{verdict}({how})",
                             status='counted' if verdict == 'yes' else 's5' if verdict == 'unclear' else 'excluded') for e, verdict, ev, how in v['verdicts']]
    if v['den'] == 0:
        res.update(score=None, state='not_applicable' if not writes else 'not_applicable', note='내 쓰기 API 0개(「미정」 [B-56]: 해당 없음으로 둠)', ev=[])
        return res
    evs = []
    for e, verdict, ev, how in v['verdicts']:
        if verdict == 'yes' and ev:
            evs.append(b.ev(ev[0], ev[1], f'backend.login.SEC2.{b.fw}.{how}@1'))
    if v['no'] == 0 and v['unclear'] == 0:
        res.update(score=1 if verify_ok else 0, state='value_rule', ev=evs[:5], num=v['yes'], den=v['den'],
                   note='JWT 서명 검증 없음(decode만, 규칙 6)' if not verify_ok else None)
        return res
    if v['no'] > 0 and not cx['auth_trace']:
        res.update(score=0, state='value_rule', ev=[], num=v['yes'], den=v['den'], note='인증 흔적 없음: 쓰기 API가 열려 있음')
        return res
    sure_open = [x for x in v['verdicts'] if x[1] == 'no' and x[3] in ('permitAll-matcher', 'public-decorator', 'allow-any')]
    if sure_open and not [x for x in v['verdicts'] if x[1] == 'unclear']:
        res.update(score=0, state='value_rule', ev=[b.ev(x[2][0], x[2][1], f'backend.login.SEC2.{b.fw}.{x[3]}@1') for x in sure_open[:3] if x[2]], num=v['yes'], den=v['den'],
                   note='명시적으로 열어 둔 쓰기 API: ' + ', '.join(f"{x[0]['verb']} {x[0]['path'][:40]}" for x in sure_open[:5]))
        return res
    open_ = [x for x in v['verdicts'] if x[1] != 'yes'][:5]
    files = [ep_span(x[0]) for x in open_]
    cfg = [ev for e, verdict, ev, how in v['verdicts'] if ev][:1] or ([cx['nest_global']] if cx['nest_global'] else [])
    for c in cfg:
        files.append(span(c[0], c[1], 30, 60))
    res.update(score=0, state='value_rule', ev=evs[:5], num=v['yes'], den=v['den'],
               s5=[dict(template='sec2_routes', files=files, rule_result=dict(den=v['den'], yes=v['yes'], no=v['no'], unclear=v['unclear'],
                                                                              open=[f"{x[0]['verb']} {x[0]['path'][:50]}" for x in open_]))])
    return res


def sec3(b, cx):
    allp = b.files + b.cfg_paths
    hits = b.scan(ROLE_CHECK, allp)
    res = dict(item='SEC3', unit='mine')
    good = []
    for p, ln, mine, mo in hits:
        s = mo.group(0)
        okmine = mine or (p in b.cfg_paths and (b.share(p) or 0) > 0.5)
        if not okmine:
            continue
        if re.search(r'@PreAuthorize|@Secured|@RolesAllowed', s) and not cx['method_sec']:
            continue      # 활성화 없는 어노테이션(규칙 6)
        if re.search(r'@Roles\s*\(', s) and not b.scan(re.compile(r'RolesGuard'), allp):
            continue
        good.append((p, ln, s))
    if good:
        res.update(score=1, state='value_rule', ev=[b.ev(p, ln, f'backend.login.SEC3.{b.fw}.role-check@1') for p, ln, s in good[:3]],
                   instances=[dict(path=p, line=ln, what='역할 검사', status='counted') for p, ln, s in good[:50]])
        return res
    tr = b.scan(ROLE_TRACE, allp)
    res.update(score=0, state='value_rule' if tr else 'zero_unused', ev=[], trace=bool(tr),
               instances=[dict(path=p, line=ln, what='역할 흔적(내 줄 아님·활성화 없음 포함)', status='s5') for p, ln, m, mo in hits[:20]])
    if tr:
        files = [span(p, ln) for p, ln, m, mo in (hits or tr)[:4]]
        res['s5'] = [dict(template='sec3_role', files=files, rule_result=dict(role_checks_found=len(hits), role_trace=len(tr), mine_or_enabled=0))]
    return res


# ---------------------------------------------------------------- SEC4 본인 확인
PW_ONLY = re.compile(r'(?i)(?:password|passwd|pwd|비밀번호)\w*\s*(?:\)|\]|\.)?\s*(?:!==?|===?|!=|==|\.equals\s*\()|\.equals\s*\(\s*[\w.()]*(?:password|pwd)|(?:bcrypt|passwordEncoder)\s*\.\s*(?:compare|matches)\s*\([^)]*(?:post|board|article|comment|guestbook|req\.body|dto|request)', re.I)
ID_FROM_BODY = re.compile(r'(?i)req\s*\.\s*(?:body|query)\s*\.\s*\w*id\b|req\s*\.\s*(?:body|query)\s*\[\s*[\'"]\w*id[\'"]|@RequestParam[^,)]*\)\s*\w+\s+\w*[Ii]d\b|'
                          r'@RequestBody|request\s*\.\s*(?:data|POST|GET|query_params)\s*(?:\.\s*get\s*\(|\[)\s*[\'"]\w*id[\'"]|@Query\s*\(\s*[\'"]\w*id|@Body\s*\(\s*[\'"]\w*id|\bdto\s*\.\s*\w*[Ii]d\b|'
                          r'body\s*\.\s*\w*[Ii]d\b|\w+_id\s*:\s*int|\w+Id\s*:\s*(?:number|string)')


def sec4_repo(b, mine_api, cx=None):
    """수정·삭제 API마다 분류. 옛 owncheck_v2(routes·analyze·entity_of)를 옮겨 씀."""
    try:
        eps = oc.routes(b.oc)
    except RecursionError:
        eps = []
    eps = [e for e in eps if G.route_fw(b.oc, e, b.ctx['file_fw']) == b.fw or (b.fw == 'django' and e['kind'].startswith(('drf', 'py-f')))]
    apis = []
    for e in eps:
        if not mine_api(e):
            continue
        try:
            hits, collected = oc.analyze(b.oc, e)
        except RecursionError:
            hits, collected = [], []
        ent, ents = oc.entity_of(b.oc, collected)
        path = e['path'] or ''
        has_pathvar = bool(oc.PATH_VAR.search(path)) or e['kind'] in ('drf-generic', 'drf-action')
        if e['kind'] == 'drf-view' and e['handlers']:
            h0 = e['handlers'][0]
            extra = [p[2] for p in (h0.get('params') or []) if p[2] not in ('self', 'request', 'format', 'args', 'kwargs', 'req')]
            has_pathvar = bool(extra) or bool(re.search(r'self\.kwargs|kwargs\s*\[', h0.get('code') or ''))
        body_ids = any(ID_FROM_BODY.search(f.get('code') or '') for f, _ in collected[:3])
        target_in = 'path' if has_pathvar else ('body' if body_ids else 'none')
        guard_txt = ' '.join(e.get('guard_names', [])) + ' ' + ' '.join(h.get('annos', '') or '' for h in e['handlers'][:1])
        for cl in b.oc.classes.values():
            for cls in cl:
                if e['handlers'] and cls['name'] == e['handlers'][0].get('cls') and cls['file'] == e['file']:
                    guard_txt += ' ' + (cls.get('annos') or '')
        admin_only = bool(re.search(r'(?i)(^|/)admin(/|$)', path)) or bool(re.search(
            r'(?i)hasRole\(\s*[\'"](?:ROLE_)?ADMIN|hasAuthority\(\s*[\'"](?:ROLE_)?ADMIN|@Secured\s*\(\s*\{?\s*"ROLE_ADMIN|@RolesAllowed|@Roles\s*\(\s*[\'"\w.]*admin|\bAdmin\w*Guard\b|\b(?:isAdmin|adminOnly|requireAdmin|checkAdmin|verifyAdmin|IsAdminUser)\b', guard_txt))
        strong = [x for x in hits if not x.startswith('P3(이름만)')]
        # 근거 줄은 내 줄이어야 분자(부록 A-2.5)
        mine_hits = []
        for x in strong:
            mo = re.match(r'^(P\d)@(.+):(\d+)$', x)
            if mo and b.mine(mo.group(2), int(mo.group(3))):
                mine_hits.append((mo.group(1), mo.group(2), int(mo.group(3))))
        pw_only = any(PW_ONLY.search(f.get('code') or '') for f, _ in collected[:4]) and not strong
        rec = dict(file=e['file'], line=e['line'], verb=e['verb'], path=path[:120], kind=e['kind'], target_in=target_in, admin=admin_only,
                   entity=ent, hits=strong[:4], mine_hits=mine_hits[:3], pw_only=pw_only, weak=[x for x in hits if x.startswith('P3(이름만)')][:2],
                   followed=[(f['file'], f['line'], f['line'] + (f.get('code') or '').count('\n')) for f, _ in collected[:6]])
        # 규칙 분류(부록 A-2.5 규칙 4·5)
        if mine_hits:
            cls_ = 'num' if not admin_only and target_in != 'none' else 's5'
        elif strong:
            cls_ = 's5'           # 확인은 있는데 내 줄이 아님 또는 분류 충돌
        elif pw_only:
            cls_ = 'pw_only'
        elif admin_only:
            cls_ = 'ex_admin'
        elif target_in == 'none':
            cls_ = 'ex_self'
        elif ent == 'no':
            cls_ = 'ex_noowner'
        elif ent == 'yes':
            cls_ = 's5'           # 작성자 자원인데 확인을 못 찾음
        else:
            cls_ = 's5'           # 자원 판정 애매
        if cls_ == 's5' and cx is not None and not cx['auth_trace'] and not strong:
            # 로그인 자체가 없는 레포: 로그인 사용자와 비교할 수 없다(사용자 결정 ①) → 작성자 자원이면 분모, 아니면 뺌
            cls_ = 'den' if ent == 'yes' else 'ex_noowner'
            rec['no_auth_repo'] = True
        rec['cls'] = cls_
        apis.append(rec)
    return apis


def sec4_score(all_apis, pw_mode='keep'):
    """모든 백엔드 레포 합계(규칙 3·14). pw_mode: keep = 글 비밀번호 API를 분모에 남김, drop = 분자·분모에서 뺌."""
    num = sum(1 for a in all_apis if a['cls'] in ('num', 'llm_yes'))
    den = num + sum(1 for a in all_apis if a['cls'] in ('den', 'llm_no')) + (sum(1 for a in all_apis if a['cls'] == 'pw_only') if pw_mode == 'keep' else 0)
    pend = sum(1 for a in all_apis if a['cls'] in ('s5', 's5_unsent'))
    unk = sum(1 for a in all_apis if a['cls'] == 'llm_unknown')
    if den == 0 and pend == 0:
        return dict(score=0, num=0, den=0, pending=0, unknown=unk, passed=False, note='대상 0개(「미정」 [B-56]: 규칙 4대로 0점, 해당 없음 안은 alternatives)')
    passed = (den > 0) and ((num == den) if den <= 2 else (num * 2 >= den))
    border = den > 0 and ((num + 1) * 2 >= den) != passed if den > 2 else False
    return dict(score=2 if passed else 0, num=num, den=den, pending=pend, unknown=unk, passed=passed, border=border)


# ---------------------------------------------------------------- SEC5 토큰·세션 수명
EXPIRY = re.compile(r'setExpiration\s*\(|\.expiration\s*\(|expiresIn|expires_?in|expiresAt|ACCESS_TOKEN_LIFETIME|REFRESH_TOKEN_LIFETIME|expires_delta|timedelta\s*\(\s*(?:minutes|hours|days|seconds)|'
                    r'["\']exp["\']\s*:|\bexp\s*:|EXPIRATION|expire(?:-|_)?(?:time|ms|seconds|minutes)|token[-_.]?validity|validity[-_]?(?:in[-_]?)?(?:ms|seconds)|access-token-expire|refresh-token-expire', re.I)
REISSUE = re.compile(r'(?i)refresh|reissue|re-issue|renew|TokenRefreshView|token/refresh')
SESSION_EXP = re.compile(r'(?i)session\.timeout|session-timeout|SESSION_COOKIE_AGE|maxInactiveInterval|setMaxInactiveInterval|cookie\s*:\s*\{[^}]*maxAge|maxAge\s*:|SESSION_EXPIRE_AT_BROWSER_CLOSE|expires\s*:\s*new\s+Date')
LOGOUT_INV = re.compile(r'(?i)\.invalidate\s*\(|session\s*\.\s*destroy\s*\(|req\s*\.\s*logout\s*\(|\blogout\s*\(\s*request|blacklist|denylist|\.blacklist\s*\(|token_blacklist|'
                        r'(?:refresh\w*|token\w*)(?:Repository|Repo|Service|Store|Redis|repo|repository|service)?\s*\.\s*(?:delete\w*|remove\w*|revoke\w*|expire\w*)\s*\(|'
                        r'redis\w*\s*\.\s*(?:del|delete|unlink|expire|set\w*)\s*\([^)]*(?:refresh|token|logout|blacklist)|deleteRefreshToken|revokeToken|invalidateToken|'
                        r'\.logout\s*\(\s*\)|logoutUrl|logoutSuccess|deleteCookies|clearCookie\s*\(|delete_cookie\s*\(|Token\.objects\.filter[^\n]*\.delete\s*\(|auth_token\s*\.\s*delete\s*\(')
LOGOUT_NAME = re.compile(r'(?i)log[-_]?out|sign[-_]?out')


def sec5(b):
    allp = b.files + b.cfg_paths
    tokctx = re.compile(r'(?i)jwt|token|access|refresh|session|cookie|Jwts|sign|auth|SIMPLE_JWT')
    exp = []
    for x in b.scan(EXPIRY, allp):
        if not (x[2] or (x[0] in b.cfg_paths and (b.share(x[0]) or 0) > 0.5)):
            continue
        lines = (b.clean(x[0]) or '').split('\n')
        near = ' '.join(lines[max(0, x[1] - 3):x[1] + 2])
        if tokctx.search(near) and not re.search(r'(?i)rtc|agora|hold|seat|reservation|coupon|otp|verification|email|cache|video|stream', near + ' ' + x[0]):
            exp.append(x)
    reiss = [e for e in b.routes if REISSUE.search(e['path'] or '') or REISSUE.search(e.get('name') or '') or any(REISSUE.search(h['name']) for h in e['handlers'])]
    reiss += [(x) for x in b.scan(re.compile(r'TokenRefreshView'), allp) if x[2]]
    sess = [x for x in b.scan(SESSION_EXP, allp) if x[2] or (x[0] in b.cfg_paths and (b.share(x[0]) or 0) > 0.5)]
    inv = []
    for x in b.scan(LOGOUT_INV, allp):
        if not (x[2] or (x[0] in b.cfg_paths and (b.share(x[0]) or 0) > 0.5)):
            continue
        if not re.search(r'(?i)invalidate|destroy|logout\s*\(\s*request|blacklist|denylist|\.logout\s*\(|logoutUrl|logoutSuccess', x[3].group(0)):
            lines = (b.clean(x[0]) or '').split('\n')
            if not re.search(r'(?i)log[-_]?out|sign[-_]?out|로그아웃|revoke', '\n'.join(lines[max(0, x[1] - 15):x[1] + 3])):
                continue
        inv.append(x)
    # clearCookie·deleteCookies만이면 클라이언트 쪽 지우기에 가깝다(「미정」 [B-46]) → 그것만이면 애매
    inv_server = [x for x in inv if not re.search(r'(?i)clearCookie|delete_cookie|deleteCookies', x[3].group(0))]
    logout_r = [e for e in b.routes if LOGOUT_NAME.search(e['path'] or '') or LOGOUT_NAME.search(e.get('name') or '') or any(LOGOUT_NAME.search(h['name']) for h in e['handlers'])]
    life = bool((exp and reiss) or sess)
    res = dict(item='SEC5', unit='mine', parts=dict(expiry=len(exp), reissue=len(reiss), session_exp=len(sess), logout_routes=len(logout_r), invalidate=len(inv_server), client_only=len(inv) - len(inv_server)))
    evs = []
    if exp:
        evs.append(b.ev(exp[0][0], exp[0][1], 'backend.login.SEC5.expiry@1'))
    if sess:
        evs.append(b.ev(sess[0][0], sess[0][1], 'backend.login.SEC5.session-expiry@1'))
    if inv_server:
        evs.append(b.ev(inv_server[0][0], inv_server[0][1], 'backend.login.SEC5.logout-invalidate@1'))
    if life and inv_server and (logout_r or sess):
        res.update(score=1, state='value_rule', ev=evs)
        return res
    trace = bool(exp or reiss or sess or logout_r or inv)
    res.update(score=0, state='value_rule' if trace else 'zero_unused', ev=evs, trace=trace)
    if trace and (logout_r or inv or (exp and not reiss)):
        files = []
        for e in (logout_r[:2] + [x for x in reiss[:1] if isinstance(x, dict)]):
            files.append(ep_span(e))
        for x in (inv[:1] + exp[:1] + sess[:1]):
            files.append(span(x[0], x[1]))
        res['s5'] = [dict(template='sec5_life', files=files, rule_result=res['parts'])]
    return res


# ---------------------------------------------------------------- SEC6 비밀값 숨기기(레포 전체, 「제안」)
SECRET_SHAPES = [('aws_key', r'AKIA[0-9A-Z]{16}'), ('private_key', r'-----BEGIN [A-Z ]*PRIVATE KEY-----'), ('github_token', r'gh[pousr]_[A-Za-z0-9]{36}'),
                 ('slack_token', r'xox[baprs]-[A-Za-z0-9-]{10,}'), ('google_api_key', r'AIza[0-9A-Za-z_-]{35}'), ('stripe_live', r'sk_live_[0-9a-zA-Z]{16,}'),
                 ('openai_key', r'sk-(?:proj-)?[A-Za-z0-9_-]{32,}'), ('jwt_literal', r'eyJ[A-Za-z0-9_-]{15,}\.eyJ[A-Za-z0-9_-]{15,}\.[A-Za-z0-9_-]{10,}')]
CFG_SECRET = re.compile(r'(?im)^[ \t]*(?:[\w.-]*(?:password|passwd|secret|secret[-_]?key|api[-_]?key|access[-_]?key|private[-_]?key|client[-_]?secret|jwt[-_.]?secret|token[-_]?secret))[ \t]*[:=][ \t]*'
                        r'(?![ \t]*(?:\$\{|\$\(|<|\{\{|%\(|os\.|env|ENV|process\.env|getenv|config\(|\'\'|""|$|null|None|~|\[\]|changeme\b))([\'"]?)([^\s\'"#]{4,})\1')
PY_SECRET = re.compile(r'(?m)^\s*(SECRET_KEY|[A-Z_]*(?:PASSWORD|SECRET|API_KEY|TOKEN))\s*=\s*([\'"])(?!\s*\2)([^\'"]{6,})\2')
JS_SECRET = re.compile(r'(?i)(?:secret|secretOrKey|password|apiKey|api_key|privateKey)\s*:\s*([\'"`])([^\'"`$]{6,})\1')
DEV_DEFAULT = re.compile(r'(?i)^(?:root|admin|password|pass|1234|12345|123456|test|postgres|mysql|example|sample|changeme|secret|dev|local|user)\w{0,4}$')
ENV_READ = re.compile(r'\$\{[A-Z_][A-Z0-9_]*(?::[^}]*)?\}|process\.env\b|os\.environ|os\.getenv|getenv\s*\(|environ\.Env|config\s*\(\s*[\'"][A-Z_]+|\bsecrets\.[A-Z_]+|@Value\s*\(\s*"\$\{|env\s*\(\s*[\'"][A-Z_]+|ConfigService|load_dotenv|dotenv')


def sec6(b):
    repo = b.repo
    found_tree, found_hist, dev_found = [], [], []
    # 분석 브랜치 끝 파일(.env*는 내용 검색에서 뺌, 「제안」 [B-06])
    paths = [f['path'] for f in repo.files if G.kind_of(f) in ('code', 'config', 'data', 'other', 'test') and not re.search(r'(^|/)\.env', f['path'])
             and not L.VENDOR.search(f['path']) and (f.get('size') or 0) < 300_000 and G.ext_of(f['path']) in
             ('.java', '.kt', '.js', '.ts', '.py', '.yml', '.yaml', '.properties', '.json', '.toml', '.xml', '.sh', '.cfg', '.ini', '.conf', '', '.env')]
    tx = {p: b.texts.get(p) for p in paths}
    miss = [p for p, t in tx.items() if t is None]
    if miss:
        tx.update(G.batch_read(repo, miss))
    shape_rx = re.compile('|'.join(f'(?P<{n}>{r})' for n, r in SECRET_SHAPES))
    for p, t in tx.items():
        if not t:
            continue
        test_or_example = bool(re.search(r'(?i)example|sample|template|test|mock|fixture|dummy', p))
        for mo in shape_rx.finditer(t):
            found_tree.append(dict(path=p, line=t.count('\n', 0, mo.start()) + 1, kind=mo.lastgroup, example=test_or_example))
        if G.ext_of(p) in ('.yml', '.yaml', '.properties', '.toml', '.cfg', '.ini', '.conf') or 'compose' in p:
            for mo in CFG_SECRET.finditer(t):
                val = mo.group(2)
                rec = dict(path=p, line=t.count('\n', 0, mo.start()) + 1, kind='config_literal', example=test_or_example, dev_default=bool(DEV_DEFAULT.match(val)) or 'compose' in p)
                (dev_found if rec['dev_default'] else found_tree).append(rec)
        if p.endswith('.py'):
            for mo in PY_SECRET.finditer(t):
                val = mo.group(3)
                if re.search(r'django-insecure', val):
                    rec = dict(path=p, line=t.count('\n', 0, mo.start()) + 1, kind='django_insecure_key', example=test_or_example, dev_default=True)
                    dev_found.append(rec)
                    continue
                found_tree.append(dict(path=p, line=t.count('\n', 0, mo.start()) + 1, kind='py_literal', example=test_or_example))
        if G.ext_of(p) in ('.js', '.ts', '.java', '.kt'):
            for mo in JS_SECRET.finditer(t):
                val = mo.group(2)
                if DEV_DEFAULT.match(val) or re.search(r'\s', val):
                    continue
                found_tree.append(dict(path=p, line=t.count('\n', 0, mo.start()) + 1, kind='code_literal', example=test_or_example))
    found_tree = [x for x in found_tree if not x['example']]
    # .env 파일이 기록에 들어간 적(분석 브랜치, 남의 커밋 포함)
    env_commits = []
    for c in repo.commits:
        for f in c['files']:
            if re.search(r'(^|/)\.env(\.[\w.]+)?$', f['path']) and not re.search(r'(?i)example|sample|template|dist|default', f['path'].rsplit('/', 1)[-1]) and f.get('add', 0) > 0:
                env_commits.append(dict(sha=c['sha'][:12], path=f['path'], own=c['own']))
    # 기록 diff의 비밀값 모양(git log -G, 읽기만)
    refs = [x['ref'] for x in repo.refs]
    if refs:
        pat = '|'.join(r for n, r in SECRET_SHAPES if n not in ('jwt_literal',))
        rc, out = L.git(repo.dir, 'log', '--no-merges', '--format=%H', '-E', '-G', pat, *refs, '--', '.', ':(exclude)*.lock', ':(exclude)*lock.json', ':(exclude)*.min.js', ':(exclude)*.map', ':(exclude)**/dist/**', ':(exclude)**/build/**', ':(exclude)**/node_modules/**', timeout=300)
        if rc == 0:
            for sha in out.decode().split()[:20]:
                own = any(c['sha'] == sha and c['own'] for c in repo.commits)
                found_hist.append(dict(sha=sha[:12], kind='secret_shape_in_diff', own=own))
    gi = b.texts.get('.gitignore') or G.batch_read(repo, ['.gitignore']).get('.gitignore') or ''
    env_ignored = bool(re.search(r'(?m)^\s*/?\*?\.env\b|^\s*\.env\*|^\s*\*\.env', gi))
    env_read = bool(b.scan(ENV_READ, b.files + b.cfg_paths))
    res = dict(item='SEC6', unit='repo(제안)', found_tree=len(found_tree), found_hist=len(found_hist), env_commits=len(env_commits), dev_defaults=len(dev_found),
               env_ignored=env_ignored, env_read=env_read,
               instances=[dict(path=x['path'], line=x['line'], what='비밀값 후보:' + x['kind'], status='excluded') for x in (found_tree + dev_found)[:40]]
               + [dict(path=x['path'], line=None, what=f"커밋 {x['sha']}에 .env 들어감", status='excluded') for x in env_commits[:10]]
               + [dict(path=None, line=None, what=f"커밋 {x['sha']} diff에 비밀값 모양", status='excluded') for x in found_hist[:10]])
    strict_bad = bool(found_tree or found_hist or env_commits or dev_found)
    lenient_bad = bool(found_tree or found_hist or env_commits)
    res['alt'] = dict(strict=0 if strict_bad else 1, lenient_dev_defaults_ok=0 if lenient_bad else 1)
    score = res['alt']['strict']
    ev = []
    for x in (found_tree + dev_found)[:3]:
        ev.append(b.ev(x['path'], x['line'], 'backend.login.SEC6.secret-' + x['kind'] + '@1'))
    for x in env_commits[:2]:
        ev.append(L.evidence(repo, path=x['path'], sha=x['sha'], rule='backend.login.SEC6.env-committed@1'))
    for x in found_hist[:2]:
        ev.append(L.evidence(repo, sha=x['sha'], rule='backend.login.SEC6.secret-in-history@1'))
    if score == 1 and env_read:
        ev.append(b.ev(*next(((p, ln) for p, ln, m, mo in b.scan(ENV_READ, b.files + b.cfg_paths)), (None, None)), 'backend.login.SEC6.env-read@1'))
    res.update(score=score, state='value_rule', ev=ev, note=None if env_read or score == 0 else '비밀값 모양 없음 + 환경 변수 읽기 없음(비밀값을 쓰지 않는 레포일 수 있음)')
    return res


# ---------------------------------------------------------------- SEC7 보안 테스트
T401 = re.compile(r'isUnauthorized\s*\(|HttpStatus\.UNAUTHORIZED|\b401\b|HTTP_401|status\.HTTP_401_UNAUTHORIZED|Unauthorized(?:Exception)?\b')
T403 = re.compile(r'isForbidden\s*\(|HttpStatus\.FORBIDDEN|\b403\b|HTTP_403|status\.HTTP_403_FORBIDDEN|Forbidden(?:Exception)?\b|AccessDenied')
ASSERT = re.compile(r'(?i)expect|assert|andExpect|should|toBe|toEqual|toHaveStatus|status_code\s*==|assertEqual|assertThat|isEqualTo|raises|assertThrows|throws')
LINE_ASSERT = re.compile(r'(?i)\bexpect\s*\(|\.expect\s*\(|\bassert|andExpect|toBe\(|toEqual\(|toHaveStatus|status_code\s*==|assertEqual|assertThat|isEqualTo|\.status\s*\(\s*\)\s*\.\s*is|statusCode\s*\)\s*\.\s*to')
OTHER_USER = re.compile(r'(?i)other|another|different|not_?owner|notowner|stranger|attacker|intruder|hacker|타인|다른\s*(?:사용자|유저|회원)|남의|작성자가\s*아닌|권한\s*없|unauthor|non_?author|wrong_?user|user2|member2|otherUser|anotherUser')
MODIFY_WORD = re.compile(r'(?i)update|edit|modify|delete|remove|patch|put|수정|삭제|destroy')
GEN_TEST = re.compile(r'contextLoads|toBeDefined\s*\(\s*\)')


def test_funcs(b, path):
    """테스트 함수(이름, 시작 줄, 끝 줄, 본문). 간단한 경계: Java·JS는 괄호 짝, Python은 ast."""
    t = b.texts.get(path)
    if not t:
        return []
    out = []
    if path.endswith('.py'):
        import ast
        try:
            tree = ast.parse(t)
        except Exception:
            return []
        for n in ast.walk(tree):
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name.startswith('test'):
                seg = '\n'.join(t.split('\n')[n.lineno - 1:n.end_lineno])
                out.append((n.name, n.lineno, n.end_lineno, seg))
        return out
    c, m = oc.strip_c(t)
    for mo in re.finditer(r'(?:@Test[\s\S]{0,300}?(?:void|fun)\s+(\w+)\s*\(|\b(?:it|test)\s*\(\s*([\'"`][^\'"`]*[\'"`])\s*,)', m):
        st = mo.start()
        b0 = m.find('{', mo.end())
        if b0 < 0:
            continue
        e0 = oc.match(m, b0, '{', '}')
        name = mo.group(1) or c[mo.start(2):mo.end(2)]
        out.append((name, c.count('\n', 0, st) + 1, c.count('\n', 0, e0) + 1, c[st:e0 + 1]))
    return out


def sec7(b):
    flags = {'401': None, '403': None, 'other': None}
    cand_other = []
    n_tests = 0
    for p in b.test_paths:
        for name, a, z, body in test_funcs(b, p):
            if GEN_TEST.search(body) and len(body.split('\n')) < 6:
                continue
            own = b.own(p) or set()
            mine_lines = [i for i in range(a, z + 1) if i in own]
            if not mine_lines:
                continue
            n_tests += 1
            if not ASSERT.search(body):
                continue
            lines = body.split('\n')
            for k, ln in enumerate(lines):
                i = a + k
                if i not in own:
                    continue
                if T401.search(ln) and LINE_ASSERT.search(ln + ' ' + (lines[k - 1] if k else '')) and not re.search(r'\b(?:void|fun|def|it|test|describe)\b\s*[\w(\'"`]', ln) and not flags['401']:
                    flags['401'] = (p, i)
                if T403.search(ln) and LINE_ASSERT.search(ln + ' ' + (lines[k - 1] if k else '')) and not re.search(r'\b(?:void|fun|def|it|test|describe)\b\s*[\w(\'"`]', ln) and not flags['403']:
                    flags['403'] = (p, i)
            if OTHER_USER.search(name + ' ' + body) and MODIFY_WORD.search(name + ' ' + body) and re.search(r'(?i)403|404|forbidden|AccessDenied|NotFound|throws|raises|assertThrows|Unauthorized|권한|Exception', body):
                cand_other.append((p, a, z, name))
    res = dict(item='SEC7', unit='mine', tests=n_tests, cand_other=len(cand_other))
    has = [k for k in ('401', '403') if flags[k]]
    ev = [b.ev(flags[k][0], flags[k][1], f'backend.login.SEC7.assert-{k}@1') for k in has]
    res['flags'] = {k: bool(v) for k, v in flags.items()}
    res['instances'] = [dict(path=flags[k][0], line=flags[k][1], what=f'{k} 단언', status='counted') for k in has] + \
                       [dict(path=p, line=a, what='남의 글 수정 거부 후보 테스트', status='s5') for p, a, z, nm in cand_other[:20]]
    base = len(has)
    res.update(score=(2 if base == 2 else 1) if base else 0, state='value_rule' if (n_tests or cand_other) else 'zero_unused', ev=ev,
               note='남의 글 수정 거부는 S5가 정함(규칙은 후보만)' if cand_other else None)
    if cand_other:
        res['s5'] = [dict(template='sec7_other_user', files=[(p, a, z) for p, a, z, nm in cand_other[:3]], rule_result=dict(asserted_401=bool(flags['401']), asserted_403=bool(flags['403']),
                                                                                                                         candidates=len(cand_other)), group='SEC7other', stop_rule='first_yes')]
    return res


def sec7_points(flags):
    n = sum(1 for k in ('401', '403', 'other') if flags.get(k))
    return 2 if n == 3 else (1 if n else 0)


# ---------------------------------------------------------------- 상한 SEC-C1~C3
SQL_CONCAT = [
    ('spring', re.compile(r'(?:createQuery|createNativeQuery|nativeQuery|jdbcTemplate\s*\.\s*(?:query\w*|update|execute)|executeQuery|executeUpdate|prepareStatement|@Query\s*\()\s*\(?\s*"[^"]*"\s*\+\s*\w')),
    ('spring', re.compile(r'"\s*(?:SELECT|UPDATE|DELETE|INSERT)\b[^"]*"\s*\+\s*\w', re.I)),
    ('js', re.compile(r'\.(?:query|execute|raw|\$queryRawUnsafe|\$executeRawUnsafe)\s*\(\s*`[^`]*\$\{\s*(?:req|request|body|params|query)\b')),
    ('js', re.compile(r'\.(?:query|execute|raw)\s*\(\s*[\'"][^\'"]*[\'"]\s*\+\s*(?:req|request|body|params|query)\b')),
    ('js', re.compile(r'\$(?:queryRawUnsafe|executeRawUnsafe)\s*\(')),
    ('py', re.compile(r'\.(?:execute|raw|extra)\s*\(\s*f[\'"]')),
    ('py', re.compile(r'\.(?:execute|raw)\s*\(\s*[\'"][^\'"]*(?:%s|\{\})[^\'"]*[\'"]\s*(?:%|\.format)')),
    ('py', re.compile(r'\btext\s*\(\s*f[\'"]')),
]
MYBATIS_DOLLAR = re.compile(r'\$\{\s*(\w+)')
REQ_INPUT = {
    'spring': re.compile(r'@RequestParam|@PathVariable|@RequestBody|@ModelAttribute|HttpServletRequest\s+\w+[^\n]*getParameter'),
    'nest': re.compile(r'@Query\s*\(|@Param\s*\(|@Body\s*\(|req\s*\.\s*(?:body|query|params)'),
    'express': re.compile(r'req\s*\.\s*(?:body|query|params)'),
    'django': re.compile(r'request\s*\.\s*(?:GET|POST|data|query_params)'),
    'fastapi': re.compile(r'=\s*(?:Query|Path|Body|Form)\s*\('),
}


def caps_login(b, sec1r):
    out = {}
    hits = []
    for kind, rx in SQL_CONCAT:
        if (kind == 'spring' and b.fw != 'spring') or (kind == 'js' and b.fw not in ('nest', 'express')) or (kind == 'py' and b.fw not in ('django', 'fastapi')):
            continue
        for p, ln, mine, mo in b.scan(rx):
            if mine:
                hits.append((p, ln))
    for p in [x for x in b.oc.files if x.endswith('.xml')]:
        t = b.oc.files[p][1]
        for mo in MYBATIS_DOLLAR.finditer(t):
            ln = t.count('\n', 0, mo.start()) + 1
            if b.mine(p, ln):
                hits.append((p, ln))
    certain, unclear = [], []
    for p, ln in hits:
        # 같은 함수 안에서 요청 값이 들어오는지(앞 40줄 안에 요청 매개변수)
        c = b.clean(p) or ''
        lines = c.split('\n')
        win = '\n'.join(lines[max(0, ln - 40):ln])
        if REQ_INPUT[b.fw].search(win) and not re.search(r'(?i)order\s*by|sort|column|allowed|whitelist|allowList|includes\s*\(|in\s*\(\s*\[', win):
            certain.append((p, ln))
        else:
            unclear.append((p, ln))
    out['SEC-C1'] = dict(certain=certain[:5], unclear=unclear[:5], hit=bool(certain))
    # SEC-C2 평문 저장: 가입이 있는데 레포 어디에도 해시가 없을 때만 '확실'
    sign_any = sec1r.get('note', '') and not sec1r.get('score')
    hashes = b.scan(SLOW_HASH) + b.scan(OTHER_HASH)
    pw_store = b.scan(re.compile(r'(?i)setPassword\s*\(\s*[\w.]*(?:get)?[Pp]assword|password\s*[:=]\s*(?:req\.body\.|body\.|dto\.|request\.data|data\[[\'"]password|form\.|\w+\.password\b)|password\s*=\s*(?:request|form|data|serializer)\.'))
    pw_store = [x for x in pw_store if x[2]]
    signup = [e for e in b.routes if e['verb'] in WRITE + ('ANY',) and (SIGNUP_NAME.search(e['path'] or '') or any(SIGNUP_NAME.search(h['name']) for h in e['handlers']))]
    if signup and pw_store and not hashes and b.fw != 'django':
        out['SEC-C2'] = dict(certain=[(p, ln) for p, ln, m, mo in pw_store[:3]], unclear=[], hit=True)
    elif signup and pw_store and not sec1r.get('score'):
        out['SEC-C2'] = dict(certain=[], unclear=[(p, ln) for p, ln, m, mo in pw_store[:3]], hit=False)
    else:
        out['SEC-C2'] = dict(certain=[], unclear=[], hit=False)
    # SEC-C3 쿠키 인증 + 자격 증명 허용 + 모든 출처
    allp = b.files + b.cfg_paths
    cred = b.scan(re.compile(r'allowCredentials\s*\(\s*true|setAllowCredentials\s*\(\s*true|credentials\s*:\s*true|CORS_ALLOW_CREDENTIALS\s*=\s*True|allow_credentials\s*=\s*True|allow-credentials\s*:\s*true'), allp)
    star = b.scan(re.compile(r'allowedOrigins\s*\(\s*"\*"|allowedOriginPatterns\s*\(\s*"\*"|addAllowedOrigin\s*\(\s*"\*"|addAllowedOriginPattern\s*\(\s*"\*"|setAllowedOrigins\s*\([^)]*"\*"|'
                             r'origin\s*:\s*[\'"]\*[\'"]|CORS_ALLOW_ALL_ORIGINS\s*=\s*True|CORS_ORIGIN_ALLOW_ALL\s*=\s*True|allow_origins\s*=\s*\[\s*[\'"]\*[\'"]|allowed-origins\s*:\s*[\'"]?\*'), allp)
    echo = b.scan(re.compile(r'origin\s*:\s*true\b|origin\s*:\s*\(\s*origin\s*,\s*callback\s*\)\s*=>\s*callback\s*\(\s*null\s*,\s*true'), allp)
    cookie = b.scan(re.compile(r'(?i)res\s*\.\s*cookie\s*\(\s*[\'"`]\w*(?:token|session|auth|jwt)|ResponseCookie\s*\.\s*from\s*\(\s*"\w*(?:token|session|auth|jwt)|new\s+Cookie\s*\(\s*"\w*(?:token|refresh|auth|jwt)|'
                               r'set_cookie\s*\(\s*[\'"]?\w*(?:token|session|auth|jwt)|express-session|session\s*\(\s*\{|\.formLogin\s*\(|SessionAuthentication|cookies\s*\.\s*get\s*\(\s*[\'"]\w*(?:token|jwt)|req\s*\.\s*cookies\s*\.\s*\w*(?:token|jwt)|httpOnly\s*:\s*true|HttpOnly'), allp)
    mine_ok = lambda xs: [x for x in xs if x[2] or (x[0] in b.cfg_paths and (b.share(x[0]) or 0) > 0.5)]
    if mine_ok(cred) and mine_ok(star) and cookie:
        out['SEC-C3'] = dict(certain=[(x[0], x[1]) for x in mine_ok(star)[:2]], unclear=[], hit=True)
    elif mine_ok(cred) and (mine_ok(echo) or (mine_ok(star) and not cookie)):
        out['SEC-C3'] = dict(certain=[], unclear=[(x[0], x[1]) for x in (mine_ok(echo) or mine_ok(star))[:2]], hit=False, note='요청 출처를 돌려줌(「미정」 [B-52]) 또는 쿠키 인증 불명')
    else:
        out['SEC-C3'] = dict(certain=[], unclear=[], hit=False)
    return out


# ---------------------------------------------------------------- WAS2 설정 나누기 · WAS3 운영 실행 · WAS-C1
def env_files(b):
    """환경별 설정 파일·클래스: [(path, env, line)]"""
    out = []
    names = [f['path'] for f in b.repo.files if any(G.under(f['path'], d) for d in b.roots + [''])]
    for p in names:
        base = p.rsplit('/', 1)[-1]
        mo = re.match(r'(?i)application-(\w+)\.(ya?ml|properties)$', base)
        if mo:
            out.append((p, mo.group(1).lower(), 1))
            continue
        mo = re.match(r'(?i)\.env\.(\w+)$', base)
        if mo and mo.group(1).lower() not in ('example', 'sample', 'template', 'dist', 'defaults'):
            out.append((p, mo.group(1).lower(), 1))
            continue
        mo = re.match(r'(?i)(?:settings[_-]?(\w+)|(\w+)[_-]settings)\.py$', base)
        if mo and (mo.group(1) or mo.group(2) or '').lower() not in ('', 'base', 'common', 'test', 'tests'):
            out.append((p, (mo.group(1) or mo.group(2)).lower(), 1))
            continue
        if re.search(r'(?i)(^|/)settings/(dev|development|local|prod|production|staging|deploy)\w*\.py$', p):
            out.append((p, re.search(r'(?i)settings/(\w+)\.py$', p).group(1).lower(), 1))
            continue
        if re.search(r'(?i)(^|/)config/(development|production|dev|prod|staging|local)\.(js|ts|json|ya?ml)$', p):
            out.append((p, re.search(r'(?i)config/(\w+)\.', p).group(1).lower(), 1))
    # 한 파일 안 여러 프로필(spring.config.activate.on-profile / spring.profiles)
    for p in b.cfg_paths:
        c = b.clean(p) or ''
        for mo in re.finditer(r'(?m)^\s*(?:on-profile|profiles)\s*:\s*(\w+)|spring\.config\.activate\.on-profile\s*=\s*(\w+)', c):
            if re.search(r'application[^/]*\.(ya?ml|properties)$', p):
                out.append((p, (mo.group(1) or mo.group(2)).lower(), c.count('\n', 0, mo.start()) + 1))
    # 환경별 설정 클래스·읽기(NestJS ConfigModule envFilePath, BaseSettings env_file, django-environ)
    for p, ln, mine, mo in b.scan(re.compile(r'envFilePath\s*:\s*[^\n]*NODE_ENV|env_file\s*=\s*[^\n]*(?:ENV|env)|environ\.Env\s*\(|`\.env\.\$\{process\.env\.NODE_ENV|\.env\.\$\{'), b.files + b.cfg_paths):
        out.append((p, 'by-env', ln))
    return out


PROD = re.compile(r'(?i)^(prod|production|real|release|deploy|live|operation|ops|prd)')
DEV = re.compile(r'(?i)^(dev|develop|development|local|test|default|staging|stage|qa|by-env)')


def was2(b):
    ef = env_files(b)
    envs = {e for p, e, ln in ef}
    prod = [x for x in ef if PROD.match(x[1])]
    dev = [x for x in ef if DEV.match(x[1])]
    # 기본 설정(application.yml·settings.py)이 개발 쪽이고 prod 파일이 따로 있으면 둘로 본다
    base = [p for p in b.cfg_paths if re.search(r'(?i)(^|/)(application\.(ya?ml|properties)|settings\.py)$', p)]
    ok = bool(prod and (dev or base)) or any(e == 'by-env' for e in envs)

    def is_mine(p):
        if re.search(r'(^|/)\.env', p):        # .env* 는 이름만 본다 → 그 파일을 더한 커밋이 내 것인지
            return any(c['own'] and any(f['path'] == p for f in c['files']) for c in b.repo.commits)
        s = b.share(p)
        return s is not None and s > 0.5
    mine_prod = [x for x in prod if is_mine(x[0])] or [x for x in ef if x[1] == 'by-env' and b.mine(x[0], x[2])]
    res = dict(item='WAS2', unit='mine', envs=sorted(envs), instances=[dict(path=p, line=ln, what=f'환경별 설정:{e}', status='counted' if is_mine(p) else 'excluded') for p, e, ln in ef[:40]])
    if ok and mine_prod:
        res.update(score=1, state='value_rule', ev=[b.ev(mine_prod[0][0], mine_prod[0][2], f'backend.was.WAS2.{b.fw}.env-config@1')])
    elif ok:
        res.update(score=0, state='value_rule', ev=[], note='환경별 설정은 있으나 내 줄 과반이 아님(규칙 9)')
    else:
        res.update(score=0, state='value_rule' if ef or base else 'zero_unused', ev=[], note='개발·운영 설정 분리 없음' + (' (기본 설정 하나뿐, 「미정」 [B-48]·[B-58])' if base else ''))
    return res


RUN_CMD = {
    'spring': re.compile(r'java\s+[^\n]*-jar|ENTRYPOINT\s*\[\s*"java"|CMD\s*\[\s*"java"|bootRun|gradlew\s+bootRun|(?:ENTRYPOINT|CMD)[^\n]*\.jar\b'),
    'nest': re.compile(r'node\s+[\w./-]*(?:dist|build)/|pm2(?:-runtime)?\s+(?:start\s+)?|npm\s+(?:run\s+)?start(?::prod)?\b|yarn\s+start|"start:prod"|CMD\s*\[\s*"node"|CMD\s*\[\s*"npm"|ENTRYPOINT\s*\[\s*"node"'),
    'express': re.compile(r'node\s+[\w./-]+\.(?:js|mjs|cjs)|node\s+[\w./-]*(?:dist|build|src)?/?|pm2(?:-runtime)?\s+(?:start\s+)?|npm\s+(?:run\s+)?start\b|yarn\s+start|CMD\s*\[\s*"node"|CMD\s*\[\s*"npm"|ENTRYPOINT\s*\[\s*"node"'),
    'django': re.compile(r'gunicorn|uwsgi|daphne|uvicorn|runserver|hypercorn'),
    'fastapi': re.compile(r'gunicorn|uvicorn|hypercorn|fastapi\s+run'),
}
PROD_MODE = {
    'spring': re.compile(r'(?i)spring[._]profiles[._]active\s*[=:]\s*["\']?(?:prod|production|real|deploy|release|prd)|-Dspring\.profiles\.active=(?:prod|production|real|deploy|prd)|--spring\.profiles\.active=(?:prod|production|real|deploy|prd)|SPRING_PROFILES_ACTIVE'),
    'nest': re.compile(r'NODE_ENV\s*[=:]\s*["\']?production|start:prod|--env\s+production|NODE_ENV'),
    'express': re.compile(r'NODE_ENV\s*[=:]\s*["\']?production|--env\s+production|NODE_ENV'),
    'django': re.compile(r'(?i)DJANGO_SETTINGS_MODULE\s*[=:]\s*["\']?[\w.]*(?:prod|production|deploy|real)|--settings\s*[= ]\s*[\w.]*(?:prod|production|deploy)|gunicorn|uwsgi|daphne'),
    'fastapi': re.compile(r'(?i)gunicorn|uvicorn(?![^\n]*--reload)|ENV\s*[=:]\s*["\']?prod'),
}
PROD_EXPLICIT = {
    'spring': re.compile(r'(?i)(?:spring[._]profiles[._]active|SPRING_PROFILES_ACTIVE)\s*[=:]\s*["\']?(?:prod|production|real|deploy|release|prd|live|server|ec2|aws)\w*|-Dspring\.profiles\.active=(?:prod|production|real|deploy|prd)|--spring\.profiles\.active=(?:prod|production|real|deploy|prd)'),
    'nest': re.compile(r'NODE_ENV\s*[=:]\s*["\']?production|start:prod|--env\s+production'),
    'express': re.compile(r'NODE_ENV\s*[=:]\s*["\']?production|--env\s+production'),
    'django': re.compile(r'(?i)DJANGO_SETTINGS_MODULE\s*[=:]\s*["\']?[\w.]*(?:prod|production|deploy|real)|--settings\s*[= ]\s*[\w.]*(?:prod|production|deploy)'),
    'fastapi': re.compile(r'(?i)(?:ENV|ENVIRONMENT|APP_ENV)\s*[=:]\s*["\']?prod'),
}
DEV_RUN = re.compile(r'runserver|--reload\b|nodemon|npm\s+run\s+dev\b|yarn\s+dev\b|start:dev|ts-node(?:-dev)?\s|bootRun|flask\s+run|fastapi\s+dev')


def was3_c1(b):
    runs = [p for p in b.repo.files if RUN_FILE.search(p['path']) and not L.VENDOR.search(p['path'])]
    paths = [f['path'] for f in runs]
    miss = [p for p in paths if p not in b.texts]
    if miss:
        b.texts = dict(b.texts)
        b.texts.update(G.batch_read(b.repo, miss))
    cmd_hits = []
    prod_hits, dev_hits = [], []
    for p in paths:
        c = b.clean(p) or ''
        for mo in RUN_CMD[b.fw].finditer(c):
            ln = c.count('\n', 0, mo.start()) + 1
            line_txt = c.split('\n')[ln - 1]
            if DEV_RUN.search(line_txt):
                dev_hits.append((p, ln))
            else:
                cmd_hits.append((p, ln))
        for mo in PROD_MODE[b.fw].finditer(c):
            prod_hits.append((p, c.count('\n', 0, mo.start()) + 1))
        for mo in DEV_RUN.finditer(c):
            dev_hits.append((p, c.count('\n', 0, mo.start()) + 1))
    # package.json scripts.start(Node): 실행 근거가 'npm start'면 그 스크립트 본문을 본다
    pj = [x for x in b.cfg_paths if x.endswith('package.json')]
    start_script = None
    for p in pj:
        try:
            j = json.loads(b.texts.get(p) or '{}')
            s = (j.get('scripts') or {})
            start_script = s.get('start:prod') or s.get('start')
        except Exception:
            pass
    profiles = {e for p, e, ln in env_files(b)}
    single_profile = len([e for e in profiles if e != 'by-env']) == 0
    mine_file = lambda p: (b.share(p) or 0) > 0.5
    good = []
    any_prod = any(PROD_EXPLICIT[b.fw].search(b.clean(p) or '') for p in paths)
    for p, ln in cmd_hits:
        ctxt = b.clean(p) or ''
        has_prod = bool(PROD_EXPLICIT[b.fw].search(ctxt)) or any_prod
        if b.fw == 'spring' and (has_prod or single_profile):
            good.append((p, ln, 'prod-profile' if has_prod else 'single-profile'))
        elif b.fw in ('nest', 'express') and (has_prod or (start_script and not DEV_RUN.search(start_script) and re.search(r'NODE_ENV=production', start_script))):
            good.append((p, ln, 'node-production' if has_prod else 'start-script-production'))
        elif b.fw in ('django', 'fastapi') and re.search(r'gunicorn|uwsgi|daphne|uvicorn|hypercorn', (ctxt.split('\n')[ln - 1])):
            good.append((p, ln, 'wsgi-server'))
    good_mine = [x for x in good if mine_file(x[0]) or b.mine(x[0], x[1])]
    paas = [f['path'] for f in b.repo.files if re.search(r'(?i)(^|/)(vercel\.json|netlify\.toml|render\.yaml|fly\.toml|railway\.json|app\.yaml|Procfile|\.platform|\.ebextensions)', f['path'])]
    r3 = dict(item='WAS3', unit='mine', run_files=len(paths), cmds=len(cmd_hits), prod_mode=len(prod_hits), single_profile=single_profile,
              instances=[dict(path=p, line=ln, what='실행 명령:' + how, status='counted' if (p, ln, how) in good_mine else 'excluded') for p, ln, how in good[:30]])
    if good_mine:
        r3.update(score=1, state='value_rule', ev=[b.ev(good_mine[0][0], good_mine[0][1], f'backend.was.WAS3.{b.fw}.{good_mine[0][2]}@1')])
    elif good:
        r3.update(score=0, state='value_rule', ev=[], note='운영 실행 근거가 있으나 내 줄 과반 아님(「미정」 [B-48])')
    elif not paths:
        r3.update(score=0, state='paas' if paas else 'zero_unused', ev=[], note='실행 근거 없음' + (' (PaaS 설정만)' if paas else ''))
    else:
        r3.update(score=0, state='value_rule', ev=[], note='실행 근거는 있으나 운영 설정·모드로 띄우는 명령 없음')
    # WAS-C1: 실행 근거가 있을 때만(규칙 10)
    c1 = dict(certain=[], unclear=[], hit=False)
    if paths:
        dev_cmd = [x for x in dev_hits if mine_file(x[0]) or b.mine(x[0], x[1])]
        stack = []
        for p in b.cfg_paths:
            c = b.clean(p) or ''
            for mo in re.finditer(r'include-stacktrace\s*:\s*always|include_stacktrace\s*=\s*always|server\.error\.include-stacktrace\s*=\s*always', c):
                ln = c.count('\n', 0, mo.start()) + 1
                if b.mine(p, ln):
                    stack.append((p, ln, re.search(r'(?i)application-(prod|production)', p) is not None or single_profile))
        debug = []
        if b.fw in ('django', 'fastapi'):
            for p in b.cfg_paths + b.files:
                c = b.clean(p) or ''
                for mo in re.finditer(r'(?m)^\s*DEBUG\s*=\s*True\b|FastAPI\s*\([^)]*debug\s*=\s*True', c):
                    ln = c.count('\n', 0, mo.start()) + 1
                    if b.mine(p, ln):
                        debug.append((p, ln))
        prod_files = [x for x in profiles if PROD.match(x)]
        dev_named = [x for x in dev_cmd if re.search(r'(?i)(^|[/._-])(dev|develop|development|local|test)([._-]|$)', x[0].rsplit('/', 1)[-1])]
        dev_cmd_ops = [x for x in dev_cmd if x not in dev_named]
        if dev_cmd_ops and not good:
            c1 = dict(certain=dev_cmd_ops[:3], unclear=dev_named[:2], hit=True, note='실행 근거가 개발 서버로 띄움')
        elif dev_named and not good:
            c1 = dict(certain=[], unclear=dev_named[:3], hit=False, note='개발용 이름의 compose·스크립트만 개발 서버로 띄움(「미정」 [B-48])')
        elif dev_cmd:
            c1 = dict(certain=[], unclear=dev_cmd[:3], hit=False, note='운영·개발 실행이 같이 있음(개발용 compose 구분 「미정」 [B-48])')
        if any(x[2] for x in stack):
            c1['certain'] = c1.get('certain', []) + [(p, ln) for p, ln, prod in stack if prod][:2]
            c1['hit'] = True
        if debug and not prod_files and b.fw == 'django':
            c1['certain'] = c1.get('certain', []) + debug[:2]
            c1['hit'] = True
        elif debug:
            c1['unclear'] = c1.get('unclear', []) + debug[:2]
    return r3, c1


# ---------------------------------------------------------------- WAS4 백그라운드(가점형)
BG = {
    'spring': (re.compile(r'@Scheduled\s*\(|@Async\b|TaskScheduler|@KafkaListener|@RabbitListener|@SqsListener|@JmsListener'), re.compile(r'@EnableScheduling|@EnableAsync|@EnableKafka|@EnableRabbit|@EnableJms|ThreadPoolTaskScheduler|SchedulingConfigurer')),
    'nest': (re.compile(r'@Cron\s*\(|@Interval\s*\(|@Timeout\s*\(|@Process\s*\(|@Processor\s*\(|new\s+Worker\s*\(|cron\s*\.\s*schedule\s*\(|new\s+CronJob\s*\(|@OnQueue'), re.compile(r'ScheduleModule\s*\.\s*forRoot|BullModule\s*\.\s*(?:forRoot|registerQueue)|new\s+Queue\s*\(|cron\s*\.\s*schedule|CronJob|new\s+Worker')),
    'express': (re.compile(r'cron\s*\.\s*schedule\s*\(|new\s+CronJob\s*\(|schedule\s*\.\s*scheduleJob\s*\(|new\s+Worker\s*\(|\.process\s*\(\s*(?:[\'"`]\w+[\'"`]\s*,\s*)?(?:async\s*)?(?:function|\(|\w+\s*=>)|agenda\s*\.\s*define\s*\(|setInterval\s*\('), re.compile(r'cron\s*\.\s*schedule|CronJob|scheduleJob|new\s+Worker|new\s+Queue|agenda\s*\.\s*(?:start|every)|setInterval\s*\(')),
    'django': (re.compile(r'@shared_task|@app\.task|@celery_app\.task|@\w+\.task\s*\(|\.delay\s*\(|\.apply_async\s*\(|BackgroundScheduler|BlockingScheduler|add_job\s*\(|@periodic_task|CELERY_BEAT_SCHEDULE|beat_schedule'), re.compile(r'Celery\s*\(|CELERY_|beat_schedule|scheduler\s*\.\s*start\s*\(|\.delay\s*\(|\.apply_async\s*\(')),
    'fastapi': (re.compile(r'BackgroundTasks|\.add_task\s*\(|@shared_task|@\w+\.task\s*\(|\.delay\s*\(|AsyncIOScheduler|BackgroundScheduler|add_job\s*\(|@repeat_every'), re.compile(r'\.add_task\s*\(|Celery\s*\(|scheduler\s*\.\s*start\s*\(|\.delay\s*\(|@repeat_every|BackgroundTasks')),
}
FAIL_HANDLE = re.compile(r'(?i)\bcatch\s*\(|\bexcept\b|\.catch\s*\(|@Retryable|autoretry_for|max_retries|retry_backoff|self\.retry\s*\(|attempts\s*:|backoff\s*:|retry\s*=|onFailure|on_failure|\.on\s*\(\s*[\'"]failed')


def was4(b):
    reg_rx, act_rx = BG[b.fw]
    allp = b.files + b.cfg_paths
    regs = [x for x in b.scan(reg_rx) if x[2]]
    acts = b.scan(act_rx, allp)
    res = dict(item='WAS4', unit='mine', bonus=True, jobs=len(regs), activation=len(acts))
    good = []
    for p, ln, mine, mo in regs:
        c = b.clean(p) or ''
        lines = c.split('\n')
        body = '\n'.join(lines[ln - 1:ln + 40])
        own = b.own(p) or set()
        fh = [k for k, x in enumerate(lines[ln - 1:ln + 40]) if FAIL_HANDLE.search(x) and (ln + k) in own]
        if fh:
            good.append((p, ln, ln + fh[0]))
    res['instances'] = [dict(path=p, line=ln, what='백그라운드 작업 등록', status='counted' if any(g[0] == p and g[1] == ln for g in good) else 'excluded') for p, ln, m, mo in regs[:50]]
    if regs and acts and good:
        res.update(score=1, state='value_rule', ev=[b.ev(good[0][0], good[0][1], f'backend.was.WAS4.{b.fw}.job@1'), b.ev(acts[0][0], acts[0][1], f'backend.was.WAS4.{b.fw}.enable@1'),
                                                   b.ev(good[0][0], good[0][2], f'backend.was.WAS4.{b.fw}.failure-handling@1')])
    else:
        res.update(score=0, state='value_rule' if regs else 'zero_unused', ev=[],
                   note=('작업은 있으나 ' + ('활성화 없음' if not acts else '실패 처리가 내 코드에 없음')) if regs else None)
    return res


# ---------------------------------------------------------------- WAS5 공통 처리
EXCLUDE_PURPOSE = re.compile(r'(?i)auth|jwt|token|security|login|session|guard|permission|role|principal|currentuser|loginuser|argumentresolver|user(?:id)?resolver|trac(?:e|ing)|'
                             r'valid|pipe(?:validation)?|sanitiz|log|logging|mdc|trace|request[-_]?id|correlation|exception|error|advice|cors|db|database|transaction|session[-_]?scope|'
                             r'helmet|morgan|bodyparser|body[-_]?parser|cookieparser|multer|compression|static')
PURPOSE_WORDS = [('rate-limit', r'(?i)rate|limit|throttl|bucket'), ('timing', r'(?i)time|timer|elapsed|duration|perf|stopwatch|latency|metric'),
                 ('cache', r'(?i)cache|etag'), ('response-wrap', r'(?i)response|wrap|envelope|transform|serializ|format|result'),
                 ('idempotency', r'(?i)idempot|duplicate|dedup'), ('locale', r'(?i)locale|i18n|lang'), ('encoding', r'(?i)encod|charset|utf'),
                 ('lock', r'(?i)lock|redisson|mutex'), ('audit', r'(?i)audit|history|track'), ('xss', r'(?i)xss|escape|filter(?:ing)?html'),
                 ('retry', r'(?i)retry'), ('maintenance', r'(?i)maintenance|maint'), ('timeout', r'(?i)timeout'), ('tenant', r'(?i)tenant'),
                 ('version', r'(?i)version'), ('view-count', r'(?i)view|count|hit')]


def purpose_of(name, body):
    for nm, rx in PURPOSE_WORDS:
        if re.search(rx, name):
            return nm
    for nm, rx in PURPOSE_WORDS:
        if len(re.findall(rx, body or '')) >= 2:
            return nm
    return None


def was5(b, n_api):
    """직접 만든 요청 흐름 코드 → (목적, 적용 API 수). 전역 등록 = 전체 API."""
    comps = []
    oc_ = b.oc
    for cname, cl in oc_.classes.items():
        for cls in cl:
            if cls['file'] not in b.files:
                continue
            hdr = (cls.get('header') or '') + ' ' + (cls.get('annos') or '')
            kind = None
            if b.fw == 'spring' and re.search(r'implements\s+[^{]*\b(?:Filter|HandlerInterceptor|HandlerMethodArgumentResolver|ResponseBodyAdvice)\b|extends\s+(?:OncePerRequestFilter|GenericFilterBean|HandlerInterceptorAdapter)|@Aspect\b', hdr):
                kind = 'aspect' if '@Aspect' in hdr else 'filter/interceptor'
            elif b.fw == 'nest' and re.search(r'implements\s+[^{]*\b(?:NestInterceptor|PipeTransform|NestMiddleware|CanActivate|ExceptionFilter)\b', hdr):
                kind = re.search(r'(NestInterceptor|PipeTransform|NestMiddleware|CanActivate|ExceptionFilter)', hdr).group(1)
            elif b.fw == 'django' and cls['lang'] == 'py' and (re.search(r'MiddlewareMixin', hdr) or ('__call__' in cls['methods'] and re.search(r'get_response', cls.get('code') or ''))):
                kind = 'django-middleware'
            elif b.fw == 'fastapi' and cls['lang'] == 'py' and re.search(r'BaseHTTPMiddleware', hdr):
                kind = 'starlette-middleware'
            if not kind:
                continue
            line = cls.get('line') or (b.texts.get(cls['file']) or '')[:cls.get('start', 0)].count('\n') + 1
            comps.append(dict(name=cname, file=cls['file'], line=line, kind=kind, body=(cls.get('code') or '')[:3000] if cls['lang'] == 'py' else (b.oc.files[cls['file']][1][cls.get('start', 0):cls.get('end', 0)])[:3000]))
    if b.fw in ('express', 'fastapi'):
        for p in b.files:
            c = b.clean(p) or ''
            if b.fw == 'fastapi':
                for mo in re.finditer(r'@\w+\s*\.\s*middleware\s*\(\s*[\'"]http[\'"]\s*\)\s*\n\s*(?:async\s+)?def\s+(\w+)', c):
                    comps.append(dict(name=mo.group(1), file=p, line=c.count('\n', 0, mo.start()) + 1, kind='fastapi-http-middleware', body=c[mo.start():mo.start() + 1500], scope='global'))
            else:
                for mo in re.finditer(r'(?:function\s+(\w+)\s*\(\s*req\s*,\s*res\s*,\s*next\s*\)|(?:const|let|var|exports\.)\s*(\w+)\s*=\s*(?:async\s*)?(?:function\s*\w*)?\s*\(\s*req\s*,\s*res\s*,\s*next\s*\)\s*(?:=>)?)', c):
                    nm = mo.group(1) or mo.group(2)
                    comps.append(dict(name=nm, file=p, line=c.count('\n', 0, mo.start()) + 1, kind='express-middleware', body=c[mo.start():mo.start() + 1500]))
    # 적용 범위: 이름이 쓰인 라우트 수(가드·미들웨어 이름·데코레이터·어노테이션) 또는 전역 등록
    allp = b.files + b.cfg_paths
    alltext = {p: b.clean(p) or '' for p in allp}
    out = []
    for cmp_ in comps:
        nm = cmp_['name']
        own_line = b.mine(cmp_['file'], cmp_['line'])
        own_s = b.own(cmp_['file']) or set()
        body_lines = (cmp_['body'] or '').count('\n') + 1
        mine_share = sum(1 for i in range(cmp_['line'], cmp_['line'] + body_lines) if i in own_s) / max(1, body_lines)
        glob = False
        for p, c in alltext.items():
            if p == cmp_['file'] and cmp_['kind'] not in ('fastapi-http-middleware',):
                pass
            if re.search(r'(?:addFilter\w*|registerFilter|FilterRegistrationBean|addInterceptor|useGlobal\w+|APP_INTERCEPTOR|APP_PIPE|APP_GUARD|app\s*\.\s*use|add_middleware|MIDDLEWARE\s*=)[^\n]{0,200}\b' + re.escape(nm) + r'\b', c, re.S):
                glob = True
                break
        if cmp_['kind'] in ('fastapi-http-middleware',) or (b.fw == 'spring' and cmp_['kind'] == 'filter/interceptor' and re.search(r'@Component|@WebFilter', b.texts.get(cmp_['file']) or '') and 'Filter' in cmp_['body'][:400]):
            glob = True
        if b.fw == 'django' and any(re.search(r'MIDDLEWARE[\s\S]{0,3000}' + re.escape(nm), c) for c in alltext.values()):
            glob = True
        uses = 0
        if not glob:
            for e in b.routes:
                txt = ' '.join(e.get('guard_names') or []) + ' ' + ' '.join((h.get('annos') or '') for h in e['handlers'])
                if re.search(r'\b' + re.escape(nm) + r'\b', txt):
                    uses += 1
            if cmp_['kind'] == 'aspect':
                pc = re.findall(r'@annotation\s*\(\s*([\w.]+)\s*\)', cmp_['body'])
                for a in pc:
                    an = a.split('.')[-1]
                    uses += sum(1 for e in b.routes if re.search(r'@' + re.escape(an) + r'\b', ' '.join((h.get('annos') or '') for h in e['handlers'])))
                if re.search(r'execution\s*\(\s*\*\s+[\w.]*(?:controller|Controller)', cmp_['body']):
                    uses = n_api
        applied = n_api if glob else uses
        excluded = bool(EXCLUDE_PURPOSE.search(nm)) or cmp_['kind'] in ('CanActivate', 'ExceptionFilter')
        purpose = None if excluded else purpose_of(nm, cmp_['body'])
        out.append(dict(name=nm, file=cmp_['file'], line=cmp_['line'], kind=cmp_['kind'], applied=applied, global_=glob, mine=mine_share > 0.5,
                        excluded=excluded, purpose=purpose, span=(cmp_['file'], cmp_['line'], cmp_['line'] + min(body_lines, 120))))
    good = [c for c in out if c['mine'] and not c['excluded'] and c['purpose'] and c['applied'] >= 3]
    purposes = {c['purpose'] for c in good}
    unclear = [c for c in out if c['mine'] and not c['excluded'] and not c['purpose'] and c['applied'] >= 3]
    res = dict(item='WAS5', unit='mine', components=len(out), candidates=len(good) + len(unclear), purposes=sorted(purposes),
               instances=[dict(path=c['file'], line=c['line'], what=f"{c['kind']} 적용 {c['applied']} 목적 {c['purpose'] or ('제외' if c['excluded'] else '모름')}",
                               status='counted' if c in good else 's5' if c in unclear else 'excluded') for c in out[:60]])
    if len(purposes) >= 2:
        res.update(score=2, state='value_rule', ev=[b.ev(c['file'], c['line'], f'backend.was.WAS5.{b.fw}.{c["purpose"]}@1') for c in good[:4]])
    else:
        res.update(score=0, state='value_rule' if out else 'zero_unused', ev=[b.ev(c['file'], c['line'], f'backend.was.WAS5.{b.fw}.{c["purpose"]}@1') for c in good[:2]],
                   note=f'목적 {len(purposes)}종(2종 필요). 목적 1종이면 0점인지 「미정」 [B-48]')
        if unclear and len(purposes) + len(unclear) >= 2:
            res['s5'] = [dict(template='was5_purpose', files=[c['span']], rule_result=dict(name=c['name'], kind=c['kind'], applied=c['applied'], known_purposes=sorted(purposes)),
                              key=c['name']) for c in unclear[:6]]
    res['comp'] = [dict((k, v) for k, v in c.items() if k != 'span') for c in out[:60]]
    return res


# ---------------------------------------------------------------- 레포 하나
def mine_api_fn(b):
    cache = {}

    def f(e):
        k = (e['file'], e['line'], e['verb'])
        if k not in cache:
            cache[k] = bool(G.is_my_api(b.repo, b.ctx, e))
        return cache[k]
    return f


def repo_items(repo, fw, ctx):
    b = B(repo, fw, ctx)
    mine_api = mine_api_fn(b)
    my_routes = [e for e in b.routes if mine_api(e)]
    cx = sec_context(b)
    r = {}
    r['SEC1'] = sec1(b, cx)
    r['SEC2'] = sec2(b, cx, mine_api)
    r['SEC3'] = sec3(b, cx)
    apis = sec4_repo(b, mine_api, cx)
    r['SEC4'] = dict(item='SEC4', unit='mine', apis=apis)
    r['SEC5'] = sec5(b)
    r['SEC6'] = sec6(b)
    r['SEC7'] = sec7(b)
    caps = caps_login(b, r['SEC1'])
    r['WAS1'] = dict(item='WAS1', unit='mine(게이트)', score=1, state='value_rule', ev=[])
    r['WAS2'] = was2(b)
    r['WAS3'], caps['WAS-C1'] = was3_c1(b)
    r['WAS4'] = was4(b)
    r['WAS5'] = was5(b, len(my_routes) or len(b.routes))
    r['_caps'] = caps
    tops = sorted(b.files, key=lambda p: -len(b.own(p) or ()))[:4]
    r['_meta'] = dict(fw=fw, routes=len(b.routes), my_routes=len(my_routes), files=len(b.files), tests=len(b.test_paths), cfg=len(b.cfg_paths),
                      top_files=[(p, 1, 200) for p in tops])
    return r


# ---------------------------------------------------------------- 합치기·점수(규칙 2·3·4·5·9·14, 부록 A-2.4 항목 상태)
def combine(pid, raw, answers, pw_mode='keep', ai_plan='B'):
    """raw: {repo_key: items}. answers: S5 답. → (variables, s5_targets)"""
    targets, n = [], [0]
    T = {}

    def add_t(var, repo_key, tmpl, files, rule_result, trace='has_trace', priority=5, group=None, stop_rule=None, key=None):
        n[0] += 1
        tid = stable_tid(pid, var, repo_key, tmpl, files, key)
        t = dict(target_id=tid, var=var, repo=repo_key, template=tmpl, material=dict(files=[dict(path=p, start=a, end=b_) for p, a, b_ in files][:8], commits=[]),
                 rule_result=rule_result, trace=trace, priority=priority)
        if group:
            t['group'], t['stop_rule'] = group, stop_rule
        targets.append(t)
        T[(var, repo_key, key)] = tid
        return tid

    def ans(tid):
        a = answers.get(tid)
        return a if a and a.get('decision') in ('yes', 'no', 'unknown') else None

    # SEC4: S5 답이 어떻게 나와도 '절반 이상' 판정이 같으면 보내지 않는다(비용 절약, 생략 수는 남김)
    allap = [a for r in raw.values() for a in (r.get('SEC4') or {}).get('apis', [])]
    def _pass(nm_, dn_):
        return dn_ > 0 and ((nm_ == dn_) if dn_ <= 2 else nm_ * 2 >= dn_)
    n_, d_ = sum(1 for a in allap if a['cls'] == 'num'), sum(1 for a in allap if a['cls'] in ('num', 'den', 'pw_only'))
    p_ = sum(1 for a in allap if a['cls'] == 's5')
    sec4_needed = p_ > 0 and len({_pass(n_, d_), _pass(n_, d_ + p_), _pass(n_ + p_, d_ + p_)}) > 1
    sec4_cap = 60
    sec4_sent = [0]
    items = {}
    for iid, nm, pts in LOGIN_ITEMS + WAS_ITEMS:
        per = {}
        for rk, r in raw.items():
            it = r.get(iid)
            if it is None:
                continue
            x = dict(it)
            if iid == 'SEC4':
                apis = []
                for a in it['apis']:
                    a = dict(a)
                    if a['cls'] == 's5' and not sec4_needed:
                        a['cls'] = 'skip_decided'
                    elif a['cls'] == 's5' and sec4_sent[0] >= sec4_cap:
                        a['cls'] = 's5_unsent'
                    if a['cls'] == 's5':
                        sec4_sent[0] += 1
                        p0, a0, b0 = a['followed'][0] if a['followed'] else (a['file'], a['line'], a['line'] + 40)
                        files = [(a['file'], max(1, a['line'] - 5), a['line'] + 60)] + [(p, max(1, s - 2), min(e, s + 120)) for p, s, e in a['followed'][1:5]]
                        tid = add_t('backend.login.SEC4', rk, 'sec4_api', files, dict(verb=a['verb'], path=a['path'], target_in=a['target_in'], entity_has_owner=a['entity'],
                                                                                          rule_hits=a['hits'], mine_hits=bool(a['mine_hits']), admin=a['admin']), priority=3)
                        an = ans(tid)
                        if an:
                            v = an.get('value') if isinstance(an.get('value'), dict) else {}
                            if v.get('kind') in ('admin', 'none') or (v.get('kind') == 'self' and v.get('target_in') == 'none'):
                                a['cls'] = 'llm_ex'
                            elif an['decision'] == 'yes':
                                a['cls'] = 'llm_yes'
                            elif an['decision'] == 'no':
                                a['cls'] = 'llm_pw' if v.get('shape') == 'password_only' else 'llm_no'
                            else:
                                a['cls'] = 'llm_unknown'
                        a['tid'] = tid
                    elif a['cls'] in ('num',):
                        pass
                    apis.append(a)
                x['apis'] = apis
            elif it.get('s5'):
                tids = []
                for s in it['s5']:
                    tid = add_t(f"backend.{'login' if iid.startswith('SEC') else 'was'}.{iid}", rk, s['template'], s['files'], s['rule_result'],
                                priority=4, group=(s.get('group') and f"{s['group']}.{rk}"), stop_rule=s.get('stop_rule'), key=s.get('key'))
                    tids.append(tid)
                    an = ans(tid)
                    if an:
                        x.setdefault('llm', []).append(dict(tid=tid, decision=an['decision'], value=an.get('value'), evidence=an.get('evidence')))
                x['tids'] = tids
            per[rk] = x
        items[iid] = per
    # 흔적이 전혀 없는 0(zero_unused): 레포마다 (변수, 레포) 최대 3개를 no_trace 표본 후보로(사용자 결정 2026-11-26)
    NT = {'SEC1': 'sec1_flow', 'SEC3': 'sec3_role', 'SEC5': 'sec5_life', 'SEC7': 'sec7_other_user'}
    for rk, r in raw.items():
        k = 0
        top = (r.get('_meta') or {}).get('top_files') or []
        for iid in ('SEC1', 'SEC3', 'SEC5', 'SEC7'):
            it = r.get(iid) or {}
            if it.get('state') == 'zero_unused' and k < 3 and top:
                k += 1
                add_t(f"backend.login.{iid}", rk, NT[iid], [tuple(x) for x in top[:4]], dict(rule='흔적 없음(0, 안 씀)'), trace='no_trace', priority=9)
    return items, targets, T


def item_final(iid, per, answers_by_tid):
    """레포별 → 사람 하나의 항목 결과(규칙 14 가장 좋은 결과). -> dict(points, state, best_repo, by_repo, pending)"""
    by = {}
    pend = 0
    for rk, x in per.items():
        sc, st = x.get('score'), x.get('state')
        for l in x.get('llm', []):
            if l['decision'] == 'yes':
                if iid == 'SEC7':
                    fl = dict(x.get('flags') or {})
                    fl['other'] = True
                    sc = sec7_points(fl)
                elif iid in ('SEC1', 'SEC2', 'SEC3', 'SEC5'):
                    sc = 1
                elif iid == 'WAS5':
                    pass
                st = 'value_llm'
            elif l['decision'] == 'unknown' and (sc or 0) == 0:
                st = 'unknown_failed'
        if iid == 'WAS5' and x.get('llm'):
            ok = {l['value'].get('purpose') if isinstance(l.get('value'), dict) else 'llm' for l in x['llm'] if l['decision'] == 'yes'}
            purposes = set(x.get('purposes') or []) | {p for p in ok if p}
            if len(purposes) >= 2:
                sc, st = 2, 'value_llm'
        if x.get('tids') and not x.get('llm') and (sc or 0) < (1 if iid in ONE_POINT else 2):
            pend += 1
        by[rk] = dict(score=sc, state=st)
    vals = [v for v in by.values() if v['score'] is not None]
    if not vals:
        sts = {v['state'] for v in by.values()}
        state = 'not_applicable' if 'not_applicable' in sts else ('unknown_failed' if 'unknown_failed' in sts else (next(iter(sts)) if sts else 'zero_unused'))
        return dict(points=None, state=state, by_repo=by, pending=pend)
    best_rk = max(by, key=lambda k: (by[k]['score'] if by[k]['score'] is not None else -1))
    best = by[best_rk]
    state = best['state']
    if (best['score'] or 0) == 0:
        sts = {v['state'] for v in by.values()}
        state = 'value_rule' if 'value_rule' in sts else ('paas' if 'paas' in sts else ('readme_only' if 'readme_only' in sts else 'zero_unused'))
        if pend:
            state = state + '+대기'
    return dict(points=best['score'], state=state, best_repo=best_rk, by_repo=by, pending=pend)


def var_score(items_final, ids, caps, mine_item_ids, bonus_ids=(), ai_items=(), ai_plan='B', unknown_items=()):
    """변수 점수 = 점수 ÷ 만점 × 5(규칙 2), 상한(규칙 2·14). 해당 없음(1점 항목만)·모름은 만점에서 뺌(「제안」 [B-55]). 가점형은 1점일 때만(규칙 5)."""
    got = mx = 0
    parts = {}
    for iid, nm, pts in ids:
        f = items_final.get(iid)
        if f is None:
            continue
        st = f['state']
        if iid in bonus_ids:
            if (f['points'] or 0) >= pts:
                got += pts
                mx += pts
                parts[iid] = 'bonus+1'
            else:
                parts[iid] = 'bonus-excluded'
            continue
        if ai_plan == 'A' and iid in ai_items:
            parts[iid] = 'A안: 만점에서 뺌'
            continue
        if st == 'not_applicable':
            if pts == 1:
                parts[iid] = '해당 없음'
                continue
            got += 0
            mx += pts
            parts[iid] = '대상 0 → 0점(2점 항목)'
            continue
        if st.startswith('unknown'):
            parts[iid] = '모름 → 만점에서 뺌(「제안」 [B-55])'
            continue
        got += f['points'] or 0
        mx += pts
        parts[iid] = f"{f['points'] or 0}/{pts}"
    if mx == 0:
        return dict(score=None, got=got, max=mx, lv=None, parts=parts, cap=None)
    lv = got / mx * 5
    mine_pts = sum((items_final[i]['points'] or 0) for i in mine_item_ids if i in items_final and not (ai_plan == 'A' and i in ai_items))
    zero_rule = mine_pts == 0
    if zero_rule:
        lv = 0.0
    cap = None
    for cid, c in caps.items():
        if c.get('apply'):
            cap = min(cap, c['max']) if cap is not None else c['max']
    if cap is not None:
        lv = min(lv, cap)
    return dict(score=round(lv, 1), raw=lv, got=got, max=mx, lv=round(lv, 1), parts=parts, cap=cap, mine_points_zero=zero_rule)


# ---------------------------------------------------------------- extract · finalize
def _gate_target_material(repo, ctx, gv):
    files = []
    for fw, x in (gv.get('frameworks') or {}).items():
        eps = [e for e in ctx['routes'] if e.get('fw') == fw][:3]
        for e in eps:
            files.append(ep_span(e))
            for h in e['handlers'][:1]:
                for recv, name, this, args, cline in oc.calls_of(h)[:30]:
                    for g in ctx['oc'].resolve_call(h, recv, name, this)[:1]:
                        files.append((g['file'], max(1, g['line'] - 2), g['line'] + (g.get('code') or '').count('\n') + 2))
    return files[:8]


def extract(person):
    t0 = time.time()
    pid = person.pid
    gate = G.gate(person)
    raw, info, gate_targets = {}, {}, []
    db_trace_rx = re.compile(r'(?i)spring-boot-starter-data|mybatis|jdbc|mongoose|typeorm|sequelize|prisma|knex|"pg"|mysql|sqlite|mongodb|sqlalchemy|psycopg|pymysql|motor|DATABASES|tortoise|peewee|firebase|supabase')
    for r in person.repos:
        gv = gate[r.key]
        info[r.key] = gv
        if gv['pass']:
            ctx = G.context(r)
            fw = gv['framework']
            try:
                raw[r.key] = repo_items(r, fw, ctx)
            except Exception as e:      # 레포 하나가 실패해도 계속(그 레포 항목은 모름)
                raw[r.key] = {'_error': repr(e)[:200]}
                print(pid, r.key, '항목 실패', repr(e)[:200], file=sys.stderr)
            continue
        # 게이트 S5: DB까지 안 이어짐 + DB 흔적 / 규칙 없는 스택 흔적(「제안」 [B-54])
        if gv.get('fail_reason') == 'DB까지 안 이어짐' and gv['my_backend_lines'] >= 50:
            ctx = G.context(r)
            bt = ' '.join((t or '') for t in ctx['build_texts'].values())
            cfgs = [f['path'] for f in r.files if L.CONFIG_NAME.search(f['path'])]
            trace = bool(db_trace_rx.search(bt))
            if trace:
                gate_targets.append((r, dict(template='gate_db', files=_gate_target_material(r, ctx, gv), rule_result=dict(fail_reason=gv['fail_reason'], my_backend_lines=gv['my_backend_lines'],
                                                                                                                              frameworks={k: dict(routes=v['routes']) for k, v in gv['frameworks'].items()}))))
                # 게이트가 S5에서 통과로 바뀔 때를 위해 항목을 미리 잰다(tentative)
                fw = max(gv['frameworks'], key=lambda k: gv['frameworks'][k]['my_backend_lines'])
                try:
                    raw[r.key] = repo_items(r, fw, ctx)
                    raw[r.key]['_tentative'] = True
                except Exception as e:
                    print(pid, r.key, '항목 실패(tentative)', repr(e)[:200], file=sys.stderr)
        elif gv.get('fail_reason') == 'API 없음' and gv['my_backend_lines'] >= 50:
            # 라우트를 못 찾음(파서 한계일 수 있음, 부록 A-2.1) → 그 프레임워크 파일 중 내 줄이 많은 것을 보낸다
            ctx = G.context(r)
            fw = max(gv['frameworks'], key=lambda k: gv['frameworks'][k]['my_backend_lines'])
            fl = sorted(ctx['backend_files'][fw], key=lambda p: -len(G.own_set(r, p) or ()))
            gate_targets.append((r, dict(template='gate_other_stack', files=[(p, 1, 150) for p in fl[:4]],
                                         rule_result=dict(fail_reason='API 없음(규칙 라우트 0개)', framework=fw, my_backend_lines=gv['my_backend_lines']))))
        elif gv.get('state') == 'unknown_no_rule' and (gv.get('other_stack_my_lines') or 0) >= 50:
            ctx = G.context(r)
            fl = [f for f in r.files if G.kind_of(f) == 'code' and (f.get('my_lines') or 0) > 0]
            fl.sort(key=lambda f: -(f.get('my_lines') or 0))
            files = [(f['path'], 1, 150) for f in fl[:4]]
            gate_targets.append((r, dict(template='gate_other_stack', files=files, rule_result=dict(other_fw=gv.get('other_fw'), my_code_lines=gv.get('other_stack_my_lines')))))
    data = build(person, raw, info, gate_targets, {})
    data['stats']['seconds'] = round(time.time() - t0, 1)
    return data


def build(person, raw, info, gate_targets, answers):
    pid = person.pid
    active = {k: v for k, v in raw.items() if not v.get('_tentative') and not v.get('_error')}
    # 게이트 S5 답 → tentative 레포를 넣음
    gtids = {}
    for i, (r, g) in enumerate(gate_targets, 1):
        tid = stable_tid(pid, 'backend.gate', r.key, g['template'], g['files'], None)
        gtids[r.key] = tid
        a = answers.get(tid)
        if a and a.get('decision') == 'yes' and raw.get(r.key, {}).get('_tentative'):
            active[r.key] = raw[r.key]
    items, targets, T = combine(pid, active, answers)
    # 게이트 대상 + tentative 레포의 S5 대상은 게이트 답을 기다린다(게이트 대상만 먼저 낸다)
    gts = []
    for i, (r, g) in enumerate(gate_targets, 1):
        t = dict(target_id=gtids[r.key], var='backend.gate', repo=r.key, template=g['template'],
                 material=dict(files=[dict(path=p, start=a, end=b_) for p, a, b_ in g['files']][:8], commits=[]), rule_result=g['rule_result'], trace='has_trace', priority=1)
        gts.append(t)
    targets = gts + targets
    finals = {iid: item_final(iid, per, answers) for iid, per in items.items()}
    # SEC4: 모든 레포 합계
    all_apis = [a for rk, per in items['SEC4'].items() for a in per.get('apis', [])] if items.get('SEC4') else []
    s4k = sec4_score(all_apis, 'keep')
    s4d = sec4_score(all_apis, 'drop')
    if items.get('SEC4'):
        st = 'value_llm' if any(a['cls'].startswith('llm_') for a in all_apis) else 'value_rule'
        if s4k['den'] == 0 and s4k['pending'] == 0:
            st = 'value_rule'
        if s4k['pending']:
            st += '+대기'
        finals['SEC4'] = dict(points=s4k['score'], state=st, by_repo={rk: dict(num=sum(1 for a in per['apis'] if a['cls'] in ('num', 'llm_yes')),
                                                                                den=sum(1 for a in per['apis'] if a['cls'] in ('num', 'llm_yes', 'den', 'llm_no', 'pw_only')),
                                                                                s5=sum(1 for a in per['apis'] if a['cls'] == 's5'))
                                                                      for rk, per in items['SEC4'].items()}, pending=s4k['pending'], sec4=s4k, sec4_drop=s4d)
    # 상한(규칙 14: 실수 레포는 그 변수에서 빼고, 모든 레포에 있으면 상한)
    caps = {}
    for cid, (var, nm, cmax) in CAPS.items():
        repos_with = [rk for rk, r in active.items() if r.get('_caps', {}).get(cid, {}).get('hit')]
        unclear = [rk for rk, r in active.items() if r.get('_caps', {}).get(cid, {}).get('unclear')]
        apply = bool(active) and len(repos_with) == len(active)
        caps[cid] = dict(apply=apply, repos_with=repos_with, unclear_repos=unclear, max=cmax, name=nm)
        for rk in unclear:
            r = active[rk]
            c = r['_caps'][cid]
            tmpl = {'SEC-C1': 'cap_sql', 'SEC-C2': 'cap_plain', 'SEC-C3': 'cap_cors', 'WAS-C1': 'cap_was'}[cid]
            tid = stable_tid(pid, f'backend.{var}.{cid}', rk, tmpl, c['unclear'][:4], None)
            targets.append(dict(target_id=tid, var=f'backend.{var}.{cid}', repo=rk, template=tmpl,
                                material=dict(files=[dict(path=p, start=max(1, ln - 25), end=ln + 25) for p, ln in c['unclear'][:4]], commits=[]),
                                rule_result=dict(certain=len(c.get('certain', [])), unclear=len(c['unclear']), note=c.get('note')), trace='has_trace', priority=6))
            a = answers.get(tid)
            if a and a.get('decision') == 'yes':
                caps[cid].setdefault('llm_repos', []).append(rk)
        if caps[cid].get('llm_repos'):
            hit_all = set(repos_with) | set(caps[cid]['llm_repos'])
            caps[cid]['apply'] = len(hit_all) == len(active)
    # 상한 실수 레포를 그 변수에서 뺀 계산(규칙 14)
    def var_calc(var, ids, mine_ids, bonus=(), ai=(), plan='B', s4mode='keep'):
        cs = {c: v for c, v in caps.items() if CAPS[c][0] == var}
        bad = {rk for c in cs.values() for rk in c['repos_with'] + c.get('llm_repos', [])}
        use = finals
        if s4mode == 'drop' and 'SEC4' in finals:
            use = dict(finals)
            use['SEC4'] = dict(finals['SEC4'], points=s4d['score'])
        if bad and len(bad) < len(active):
            sub = {iid: {rk: x for rk, x in per.items() if rk not in bad} for iid, per in items.items()}
            use = {iid: item_final(iid, per, answers) for iid, per in sub.items()}
            if 'SEC4' in use and var == 'login':
                apis2 = [a for rk, per in sub['SEC4'].items() for a in per.get('apis', [])]
                s = sec4_score(apis2, s4mode)
                use['SEC4'] = dict(points=s['score'], state='value_rule', by_repo={}, pending=s['pending'])
        return var_score(use, ids, cs, mine_ids, bonus, ai, plan)
    login_ids = LOGIN_ITEMS
    was_ids = WAS_ITEMS
    login_mine = ['SEC2', 'SEC3', 'SEC4', 'SEC5', 'SEC7']
    was_mine = ['WAS1', 'WAS2', 'WAS3', 'WAS4', 'WAS5']
    if not active:
        login_B = login_A = was_v = None
    else:
        login_B = var_calc('login', login_ids, login_mine, ai=('SEC4',), plan='B')
        login_A = var_calc('login', login_ids, login_mine, ai=('SEC4',), plan='A')
        was_v = var_calc('was', was_ids, was_mine, bonus=('WAS4',))
    # SEC4 대안: 글 비밀번호 API를 뺀 분모
    login_B_drop = None
    if active and items.get('SEC4'):
        login_B_drop = var_calc('login', login_ids, login_mine, ai=('SEC4',), plan='B', s4mode='drop')
    # ---------------- 변수 레코드
    V = {}
    passed = [rk for rk, v in info.items() if v['pass']]
    V['backend.gate'] = dict(name='백엔드 레포(게이트, 규칙 1)', role='gate', value=len(passed), state='value_rule' if passed else ('zero_unused' if not gate_targets else 'value_rule+대기'), unit='레포',
                             by_repo={rk: dict(pass_=v['pass'], framework=v.get('framework'), my_backend_lines=v['my_backend_lines'], fail_reason=v.get('fail_reason'), state=v.get('state'),
                                               frameworks={fw: dict(pass_=x['pass'], pass_my_api=x['pass_my_api'], routes=x['routes'], my_routes=x['my_routes'], my_lines=x['my_backend_lines'],
                                                                    my_lines_with_test_config=x['my_lines_with_test_config'], reason=x['fail_reason']) for fw, x in (v.get('frameworks') or {}).items()},
                                               other_fw=v.get('other_fw')) for rk, v in info.items() if v.get('frameworks') or v.get('other_fw') or v['pass']},
                             instances=[dict(repo=rk, path=None, line=None, what=f"게이트 {'통과' if v['pass'] else '실패'}: {v.get('framework') or ''} 내 백엔드 {v['my_backend_lines']}줄 {v.get('fail_reason') or ''}",
                                             status='counted' if v['pass'] else ('s5' if rk in gtids else 'excluded')) for rk, v in info.items() if v.get('frameworks') or v.get('other_fw')][:MAX_INST],
                             evidence=[e for rk in passed for e in info[rk]['evidence']][:20],
                             definition='「문서」 백엔드 v5 규칙 1: 서버 프레임워크(Spring Boot·NestJS·Express·Django·FastAPI)로 만든 API 1개 이상이 DB까지 이어짐(핸들러→호출 그래프 4단계→DB 접근) + 내 백엔드 코드(규칙 프레임워크 언어의 code 파일, 빈 줄·주석·생성 파일 제외) 50줄 이상. (레포, 프레임워크)마다 판정',
                             notes='DB 연결 API가 내 API여야 하는지 「미정」 [B-43] → definition_choices. 테스트·설정 줄 포함 여부 「미정」 [B-44] → definition_choices. 규칙 없는 스택은 모름(규칙 없음) + S5(gate_other_stack)')
    def item_rec(var, iid, nm, pts, f):
        per = items.get(iid, {})
        inst, evs = [], []
        for rk, x in per.items():
            for i in (x.get('instances') or [])[:100]:
                inst.append(dict(repo=rk, **i))
            for e in (x.get('ev') or [])[:5]:
                evs.append(e)
            if iid == 'SEC4':
                for a in x.get('apis', [])[:150]:
                    inst.append(dict(repo=rk, path=a['file'], line=a['line'], what=f"{a['verb']} {a['path'][:50]} 분류:{a['cls']} 대상번호:{a['target_in']} 작성자칸:{a['entity']}",
                                     status='counted' if a['cls'] in ('num', 'llm_yes') else 's5' if a['cls'] == 's5' else 'excluded'))
                    for h in a['mine_hits'][:1]:
                        evs.append(L.evidence(next(r for r in person.repos if r.key == rk), path=h[1], line=h[2], rule=f'backend.login.SEC4.{h[0]}@1'))
        rec = dict(name=f"{'로그인·보안' if var == 'login' else 'WAS'} / {nm}", role='item', value=f['points'] if f else None, state=(f or {}).get('state'), unit=f'점(최대 {pts})',
                   by_repo={rk: dict(score=v.get('score'), state=v.get('state'), **({k: v[k] for k in ('num', 'den', 's5') if k in v})) for rk, v in ((f or {}).get('by_repo') or {}).items()},
                   instances=inst[:MAX_INST], evidence=evs[:20], definition=DEFS.get(iid, ''), notes=NOTES.get(iid))
        extra = {}
        for rk, x in per.items():
            for k in ('alt', 'parts', 'flags', 'found_tree', 'found_hist', 'env_commits', 'dev_defaults', 'env_ignored', 'env_read', 'purposes', 'components', 'candidates', 'jobs', 'activation', 'envs',
                      'note', 'num', 'den', 'tests', 'cand_other', 'run_files', 'cmds', 'prod_mode', 'single_profile', 'trace'):
                if k in x and x[k] not in (None, [], {}):
                    extra.setdefault(rk, {})[k] = x[k]
        if extra:
            rec['detail_by_repo'] = extra
        if iid == 'SEC4' and f:
            rec['sec4'] = dict(keep=f.get('sec4'), drop=f.get('sec4_drop'))
        return rec
    for iid, nm, pts in LOGIN_ITEMS:
        V[f'backend.login.{iid}'] = item_rec('login', iid, nm, pts, finals.get(iid))
    for iid, nm, pts in WAS_ITEMS:
        V[f'backend.was.{iid}'] = item_rec('was', iid, nm, pts, finals.get(iid))
    for cid, c in caps.items():
        var = CAPS[cid][0]
        inst = []
        for rk, r in active.items():
            cc = r.get('_caps', {}).get(cid, {})
            for p, ln in cc.get('certain', [])[:10]:
                inst.append(dict(repo=rk, path=p, line=ln, what='상한 실수(확실)', status='counted'))
            for p, ln in cc.get('unclear', [])[:10]:
                inst.append(dict(repo=rk, path=p, line=ln, what='상한 후보(애매)', status='s5'))
        V[f'backend.{var}.{cid}'] = dict(name=f"{'로그인·보안' if var == 'login' else 'WAS'} 상한 / {c['name']}", role='cap', value=c['max'] if c['apply'] else None,
                                          state='value_llm' if c.get('llm_repos') else 'value_rule', unit='변수 LV 최댓값', by_repo={rk: True for rk in c['repos_with']},
                                          instances=inst[:MAX_INST], evidence=[], definition=DEFS.get(cid, ''),
                                          notes=f"걸린 레포 {len(c['repos_with'])}/{len(active)} (모든 레포에 있을 때만 상한, 규칙 14). 애매 {len(c['unclear_repos'])}개 레포 → S5")
    def var_rec(name, v, alt=None, note=None):
        if v is None:
            return dict(name=name, role='backend_var', value=0 if not passed and not gate_targets else None, state='value_rule' if not passed else None, unit='LV 0~5',
                        by_repo={}, instances=[], evidence=[], definition='게이트 통과 레포가 없으면 백엔드 LV 0(규칙 1)', notes=note)
        return dict(name=name, role='backend_var', value=v['score'], state='value_rule', unit='LV 0~5(점수 ÷ 만점 × 5, 상한 적용)', by_repo={}, instances=[], evidence=[],
                    definition='「문서」 규칙 2: 받은 점수(기본 포함) ÷ 만점 × 5, 소수 첫째 자리. 상한 = 변수 LV 최댓값. 해당 없음(1점 항목)·모름(「제안」 [B-55])은 만점에서 뺌. 내 줄 점수 0이면 0(규칙 9)',
                    notes=note, got=v['got'], max=v['max'], parts=v['parts'], cap=v['cap'], mine_points_zero=v.get('mine_points_zero'), alternatives=alt)
    V['backend.login'] = var_rec('로그인·보안(만점 9)', login_B, alt=dict(A안_규칙13=login_A and dict(lv=login_A['score'], got=login_A['got'], max=login_A['max']),
                                                                       B안_LLM값처음부터=login_B and dict(lv=login_B['score'], got=login_B['got'], max=login_B['max']),
                                                                       SEC4_글비밀번호_분모에서뺌=login_B_drop and dict(lv=login_B_drop['score'], got=login_B_drop['got'], max=login_B_drop['max'])),
                                 note='value는 B안(사용자 결정 2026-11-25: LLM 값 처음부터 LV에). A안(규칙 13: SEC4 만점에서 뺌)은 alternatives. 「미정」 [B-14]')
    V['backend.was'] = var_rec('WAS(만점 5, 백그라운드 제대로 하면 6)', was_v, note='WAS5 공통 처리 LLM 거절은 승인된 검증기만(A-2.9) → 이번엔 거절을 넣지 않음')
    # ---------------- 정의 고른 것
    def gate_alt(key):
        return {rk: v['frameworks'][v['framework'] or max(v['frameworks'], key=lambda k: v['frameworks'][k]['my_backend_lines'])][key] if v.get('frameworks') else False
                for rk, v in info.items() if v.get('frameworks')}
    n_any = sum(1 for v in info.values() if v['pass'])
    n_my = sum(1 for v in info.values() if any(x['pass_my_api'] for x in (v.get('frameworks') or {}).values()))
    n_tc = sum(1 for v in info.values() if any(x['pass_with_test_config'] for x in (v.get('frameworks') or {}).values()))
    s4a = finals.get('SEC4', {}) if finals.get('SEC4') else {}
    choices = [
        dict(item='B-43 게이트: DB까지 이어지는 API가 내 API여야 하는지', choice='아니오(레포의 API 아무거나, 50줄은 내 줄)',
             why='문서 규칙 1은 \'API 1개 이상이 DB까지\'만 적고 내 API를 요구하지 않는다. 내 줄 50줄 조건이 이미 본인 몫을 거른다. 대안과 통과 레포 수 차이를 같이 낸다.',
             alternatives={'레포 API 아무거나': n_any, '내 API만': n_my}),
        dict(item='B-44 게이트: 내 백엔드 코드에 테스트·설정 줄을 넣는지', choice='아니오(code 파일만)',
             why='문서가 \'내 백엔드 코드\'라 부르고 생성 파일을 빼라고만 했다. 테스트·설정을 넣으면 설정 파일이 많은 스택이 유리해진다(문서가 경계한 스택 차이).',
             alternatives={'code만': n_any, 'code+test+config': n_tc}),
        dict(item='SEC4 글 비밀번호로만 막는 API(사용자 결정 2026-11-26: 두 방식 다 계산)', choice='분모에 남김(keep)을 value로, 뺀 값(drop)은 alternatives',
             why='사용자 결정 ②가 \'세지 않는다\'(분자 아님)까지만 정했고, 로그인 없이 남의 글을 고칠 수 있는 API라 분모에 남기는 쪽이 문서 취지(남의 자원 보호)에 가깝다. 확정은 사용자.',
             alternatives={'keep': dict(points=(s4a.get('sec4') or {}).get('score'), num=(s4a.get('sec4') or {}).get('num'), den=(s4a.get('sec4') or {}).get('den')),
                           'drop': dict(points=(s4a.get('sec4_drop') or {}).get('score'), num=(s4a.get('sec4_drop') or {}).get('num'), den=(s4a.get('sec4_drop') or {}).get('den'))}),
        dict(item='B-56 SEC4 대상 0개', choice='규칙 4대로 0점(2점 항목은 해당 없음 없음)', why='문서 규칙 4가 2점 항목은 해당 없음 없이 0점이라고 적었다.',
             alternatives={'0점': (s4a.get('sec4') or {}).get('den') == 0, '해당 없음(만점 9→7)': (s4a.get('sec4') or {}).get('den') == 0}),
        dict(item='B-46 SEC2 공개 쓰기 API(토큰 재발급·비밀번호 찾기·중복 확인 등)', choice='가입·로그인과 함께 분모에서 뺌(lenient)',
             why='토큰 재발급·비밀번호 찾기는 로그인 전에 불러야 하는 API라 인증을 걸 수 없다. 문서 괄호(가입·로그인 제외)를 \'로그인 전 API\'로 넓게 읽었다.',
             alternatives={rk: x.get('alt') for rk, x in (items.get('SEC2') or {}).items() if x.get('alt')}),
        dict(item='B-46 SEC6 로컬 개발용 기본 비밀번호(compose DB 비밀번호·django-insecure 키 등)', choice='엄격(있으면 0점)',
             why='문서 문구가 \'비밀번호·키가 코드·커밋 기록에 없음\'이라 예외를 두지 않았다. 너그러운 값을 같이 낸다.',
             alternatives={rk: x.get('alt') for rk, x in (items.get('SEC6') or {}).items() if x.get('alt')}),
        dict(item='A-2.9 [AI 확인] SEC4: A안(규칙 13, 만점 9→7) vs B안(처음부터 LV에)', choice='B안을 value로, A안은 alternatives',
             why='CLAUDE.md 사용자 결정(2026-11-25) \'LLM이 뽑은 값은 처음부터 LV에\'를 따랐다. 「미정」 [B-14]라 둘 다 낸다.',
             alternatives=V['backend.login'].get('alternatives') or {}),
        dict(item='B-55 모름(3번 실패) 항목', choice='그 항목을 만점에서 빼고 \'일부 모름\'', why='부록 A-2.4 「제안」 그대로.', alternatives={}),
    ]
    stats = dict(passed_repos=len(passed), active_repos=len(active), tentative_repos=[rk for rk, v in raw.items() if v.get('_tentative')],
                 repo_meta={rk: r.get('_meta') for rk, r in active.items()}, s5_targets=len(targets),
                 s5_by_template={}, parser=G.PARSER,
                 raw=_slim_raw(raw), gate_targets=[dict(repo=r.key, **{k: v for k, v in g.items() if k != 'files'}, files=g['files']) for r, g in gate_targets])
    for t in targets:
        stats['s5_by_template'][t['template']] = stats['s5_by_template'].get(t['template'], 0) + 1
    return dict(category='backend_a', pid=pid, variables=V, s5_targets=targets, definition_choices=choices, stats=stats)


def _slim_raw(raw):
    """finalize가 다시 계산할 수 있게 레포별 항목 결과를 남긴다(코드 내용 없음)."""
    out = {}
    for rk, r in raw.items():
        d = {}
        for k, v in r.items():
            if k == '_meta' or k == '_tentative' or k == '_error':
                d[k] = v
            elif isinstance(v, dict):
                d[k] = json.loads(json.dumps(v, default=lambda o: None))
        out[rk] = d
    return out


def finalize(person, data, answers):
    """S5 답을 반영해 다시 계산한다. 답이 없는 대상은 대기로 남는다."""
    raw = data['stats']['raw']
    for rk, r in raw.items():
        for k, v in r.items():
            if isinstance(v, dict) and 'certain' not in v and k.startswith('_caps'):
                pass
        # JSON으로 돌아오며 tuple → list
        caps = r.get('_caps') or {}
        for cid, c in caps.items():
            c['certain'] = [tuple(x) for x in c.get('certain', [])]
            c['unclear'] = [tuple(x) for x in c.get('unclear', [])]
        for iid in ('SEC1', 'SEC2', 'SEC3', 'SEC5', 'SEC7', 'WAS5'):
            it = r.get(iid)
            if it and it.get('s5'):
                for s in it['s5']:
                    s['files'] = [tuple(x) for x in s['files']]
    info = {}
    for rk, v in data['variables']['backend.gate']['by_repo'].items():
        info[rk] = dict(**{'pass': v['pass_']}, framework=v['framework'], my_backend_lines=v['my_backend_lines'], fail_reason=v['fail_reason'], state=v['state'],
                        frameworks={fw: dict(**{'pass': x['pass_']}, pass_my_api=x['pass_my_api'], routes=x['routes'], my_routes=x['my_routes'], my_backend_lines=x['my_lines'],
                                             my_lines_with_test_config=x['my_lines_with_test_config'], pass_with_test_config=x['my_lines_with_test_config'] >= 50, fail_reason=x['reason'])
                                    for fw, x in v['frameworks'].items()}, other_fw=v.get('other_fw'), evidence=[])
    for r in person.repos:
        info.setdefault(r.key, dict(**{'pass': False}, framework=None, my_backend_lines=0, fail_reason=None, state=None, frameworks={}, other_fw=[], evidence=[]))
    for e in data['variables']['backend.gate']['evidence']:
        if e['repo'] in info:
            info[e['repo']]['evidence'].append(e)
    gts = []
    for g in data['stats'].get('gate_targets', []):
        r = next(x for x in person.repos if x.key == g['repo'])
        gts.append((r, dict(template=g['template'], files=[tuple(x) for x in g['files']], rule_result=g['rule_result'])))
    out = build(person, raw, info, gts, answers or {})
    # 답이 없는 대상은 대기
    waiting = [t['target_id'] for t in out['s5_targets'] if t['target_id'] not in (answers or {})]
    out['stats']['s5_waiting'] = len(waiting)
    out['stats']['complete'] = not waiting
    out['stats']['seconds'] = data['stats'].get('seconds')
    return out


# ---------------------------------------------------------------- 정의 글(결과에 남김)
DEFS = {
    'SEC1': '레포 단위(규칙 9). 가입 API(경로·핸들러 이름) → 호출 그래프 4단계 안에 느린 해시(BCrypt·Argon2·PBKDF2, Django make_password·create_user·set_password, passlib) + 로그인(API 또는 formLogin·LoginView·TokenObtainPairView 등). 소셜만이면 제공자 확인 호출 + 자체 토큰·세션 발급. 흐름이 끊기면 S5',
    'SEC2': '분모 = 내 쓰기 API(POST·PUT·PATCH·DELETE, Django 함수 뷰는 ANY) − 가입·로그인·재발급·비밀번호 찾기 등 로그인 전 API(「제안」 lenient). 라우트마다 보안 설정 매처·anyRequest·메서드 보안·가드·미들웨어·permission_classes·Depends로 인증 판정. 전부 인증 + JWT 서명 검증(decode만이면 0) → 1. 애매하면 S5',
    'SEC3': '역할 검사(hasRole·@PreAuthorize+활성화·@Secured·RolesGuard+@Roles·IsAdminUser·is_staff·role 비교 등)가 내 줄 1곳 이상(공용 설정은 내 줄 과반). 활성화 없는 어노테이션은 0(규칙 6). 역할 흔적만 있으면 S5',
    'SEC4': '옛 owncheck_v2: 수정·삭제 API(PUT·PATCH·DELETE + 수정하는 POST) 중 내 API. 인정 모양 P1 작성자 비교·P2 소유자 조건 조회·P3 소유자 가드·P4 @PreAuthorize 식, 근거 줄이 내 줄. 대상 번호(경로·본문·쿼리) 없음·관리자 전용·작성자 칸 없음 → 분모에서 뺌. 글 비밀번호만 → 분자 아님(분모 keep/drop 두 값). 애매·충돌 → S5. 모든 백엔드 레포 합계: 분모 1~2면 전부, 3 이상이면 분자×2 ≥ 분모 → 2점',
    'SEC5': '(토큰 만료 설정 + 재발급 API) 또는 세션 만료 설정, 그리고 로그아웃 서버 쪽 무효화(refresh 삭제·블랙리스트·session.invalidate·destroy). 근거는 내 줄(공용 설정은 과반). clearCookie만이면 무효화로 안 셈(「미정」 [B-46]) → S5',
    'SEC6': '레포 전체(「제안」, 남의 커밋 포함): 분석 브랜치 파일의 비밀값 모양·설정 비밀값 글자·.env가 커밋에 들어감·기록 diff의 비밀값 모양(git log -G)이 하나도 없으면 1. .env* 내용은 읽지 않음. 값은 남기지 않음. S5 없음',
    'SEC7': '내 테스트 줄에서 401 단언·403 단언·남의 글 수정 거부(다른 사용자 + 수정·삭제 + 거부 단언)를 각각 찾음. 셋 다 2, 일부 1. 남의 글 수정 거부는 규칙이 후보만 고르고 S5가 정함. contextLoads 등 자동 생성 제외',
    'WAS1': '게이트 통과(내 백엔드 코드 50줄 포함) 레포면 1',
    'WAS2': '환경별 설정 파일(application-{prod..}·.env.{env}(이름만)·settings 분리·config/{env}) 또는 환경별 설정 읽기(envFilePath NODE_ENV·env_file·django-environ). prod 쪽 + (dev 쪽 또는 기본 설정). 내 줄 과반(.env*는 그 파일을 더한 커밋이 내 것)',
    'WAS3': '「실행 근거」(Dockerfile·compose·워크플로·배포 스크립트·Procfile 등)의 실행 명령이 운영 설정·모드로 서버를 띄움: Spring prod 프로필(프로필 하나면 그 설정), Node NODE_ENV=production 또는 운영 start 스크립트, Django·FastAPI gunicorn·uvicorn(--reload 없이). 실행 근거 파일 내 줄 과반',
    'WAS4': '가점형: 작업 등록(@Scheduled·@Async·@Cron·Celery task·BackgroundTasks 등, 내 줄) + 활성화(@EnableScheduling·ScheduleModule·Celery 앱 등) + 작업 본문 40줄 안의 내 실패 처리(try/catch·except·재시도 설정)',
    'WAS5': '직접 만든 필터·인터셉터·AOP·미들웨어(내 줄 과반) 중 제외 목록(인증·인가·사용자 주입·입력 검사·요청 로그·추적 ID·전역 예외·DB 세션·CORS·내장) 밖 목적을 이름·본문 낱말로 분류, 적용 API 수(전역 등록 = 내 API 전부, 그 밖은 라우트의 가드·데코레이터 이름) ≥ 3. 목적 2종 이상 → 2. 목적을 못 정한 것은 S5',
    'SEC-C1': '내 줄의 SQL·JPQL 문자열 이어 붙이기·${}·f-string·Unsafe raw 쿼리 중 앞 40줄 안에 요청 매개변수가 있고 허용 목록 흔적이 없으면 확실, 아니면 S5',
    'SEC-C2': '가입 API + 비밀번호 칸 저장 줄(내 줄) + 레포 어디에도 해시 호출 없음(Django 제외) → 확실. 해시가 있는데 SEC1 흐름을 못 이으면 S5',
    'SEC-C3': '자격 증명 허용 + 모든 출처(*) + 쿠키·세션 인증이 같은 레포에 다 있고 설정이 내 줄 → 확실. origin:true(요청 출처 돌려줌)는 「미정」 [B-52]라 S5',
    'WAS-C1': '실행 근거가 있을 때만(규칙 10): 실행 명령이 개발 서버(runserver·--reload·nodemon·npm run dev)로만 띄우면 확실, 운영·개발 실행이 같이 있으면 S5. 운영 프로필의 include-stacktrace: always, prod 설정 파일이 없는 Django의 DEBUG=True(내 줄)도 확실',
}
NOTES = {
    'SEC4': '[AI 확인] 항목. A안·B안은 backend.login alternatives',
    'SEC6': '레포 전체로 본 것은 「제안」(확인 전, 「미정」 [B-46])',
    'WAS4': '가점형: 제대로 하면 점수·만점 +1, 아니면 계산에서 뺌',
}


def main():
    for pid in sys.argv[1:]:
        t = time.time()
        P = L.load_person(pid)
        data = extract(P)
        L.write_vars(pid, KEY, data)
        V = data['variables']
        print(pid, f'{time.time() - t:.1f}s', 'gate', V['backend.gate']['value'], 'login', V['backend.login']['value'], 'was', V['backend.was']['value'],
              'S5', len(data['s5_targets']), data['stats']['s5_by_template'], file=sys.stderr, flush=True)


if __name__ == '__main__':
    main()
