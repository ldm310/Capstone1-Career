#!/usr/bin/env python3
"""근거 뽑기 v4 (LV1~5, 2026-11-12). v3 최종 + 도구-활동 연결 + LV4~5 기법 근거.
(v3 설명) 근거 뽑기 v3 최종 (LV1~3 중심, 2026-11-11). 공개 레포 98개(8묶음)에서 나온 오류 원인을 고친 버전.
측정 결과와 남은 한계: lv1-3-accuracy-v3-final-2026-11-11.md
- 주석·문자열을 구분해서 읽음(코드, 문자열, 주석을 따로 봄)
- SQL은 .sql 파일의 문장과, 코드 문자열 중 SQL 문장 모양인 것만(JPQL 제외)
- 생성기 기본 파일은 내용 지문으로 제외, 같은 사람의 여러 이름은 이메일·계정으로 묶음, AI가 쓴 커밋은 올린 사람 몫 + "AI 작성"
- 도구·기능 사전(lv_dict)으로 도구와 활동(테스트, 캐시, 큐, OAuth, 결제, 모니터링, 외부 API)을 판정
- DB 설계·인덱스 추가는 SQL / JPA / Alembic / SQLAlchemy / Django / Prisma / TypeORM을 같은 모양으로 뽑아 판정
- CI/CD는 workflow 줄을 빌드·테스트 / 배포로 분류(명령어와 액션 모두)
Usage: python3 lv_rules_v3.py <repo>
"""
import collections, os, re, subprocess, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import lv1_rules as b
import lv_dict as D


def toks(eco, mod):
    r = D.lookup(eco, mod)
    return tuple(x for x in (r[0], 'cap:' + r[1] if r[1] else None) if x) if r else ()


b.java_tech = lambda m: toks('java', m); b.js_tech = lambda m: toks('js', m); b.py_tech = lambda m: toks('py', m)
LANG = dict(b.LANG, **{'.kt': 'Kotlin'})
JS = ('.js', '.jsx', '.ts', '.tsx')
PRACTICE = re.compile(r'(^|[/_.-])(til|study|studies|tutorials?|practice|examples?|samples?|playground|boj|baekjoon|leetcode|algorithms?|codingtest)([/_.-]|$)', re.I)
TESTPATH = re.compile(r'(^|/)(tests?|__tests__|specs?|e2e)/|Tests?\.(java|kt)$|\.(test|spec)\.[jt]sx?$|(^|/)test_[^/]+\.py$|_test\.py$|(^|/)conftest\.py$')
TESTDECL = re.compile(r'@(Test|ParameterizedTest|RepeatedTest)\b|\bdef test_\w+|\b(it|test)\(')
API = {'java': re.compile(r'@(Get|Post|Put|Delete|Patch|Request)Mapping\b'),
       'py': re.compile(r'@\w*(app|router|bp|blueprint|api)\w*\.(get|post|put|delete|patch|route|websocket)\('),
       'js': re.compile(r'@(Get|Post|Put|Delete|Patch)\(|\b(app|router|server|\w+[rR]outer)\.(get|post|put|delete|patch)\(\s*(?P<q>[\'"`])(?P=q)\s*,')}
# ---- v4: 활동 키와 LV4~5 근거
ACT_KEYS = {'API 개발', '외부 API 연동', '테스트 코드', '인증·인가 구현', 'LLM 기능 개발', 'RAG 구축', '배치 처리', '검색 기능 구축', 'DB 설계', '쿼리 튜닝', '캐시 도입', '메시지 큐', 'OAuth 연동', '결제 연동',
            '모니터링 설정', 'CI/CD 구축', 'IaC', '동시성 제어', 'MSA·서비스 분리', '이벤트 기반 아키텍처', 'Kubernetes 운영 설정', '아키텍처 패턴 적용', '장애 격리', '운영 대응 이력',
            '부하 테스트', '무중단 배포', '분산 락·분산 트랜잭션', 'DB 복제·파티셔닝'}
LIFT_CAP_FILE = 3      # 활동이 일어난 파일의 언어·프레임워크가 그 활동으로 올라갈 수 있는 최고 LV
FRAMEWORKS = {'Spring', 'NestJS', 'Express', 'Django', 'Django REST framework', 'FastAPI', 'Flask', 'Fastify', 'Koa', 'Hono', 'Next.js', 'Ktor'}
LLM_TOOLS = {'OpenAI API', 'Anthropic API', 'Gemini API', 'Groq', 'Ollama', 'LangChain', 'LangChain4j', 'LangGraph', 'LlamaIndex', 'Spring AI', 'MCP SDK'}
VECTOR_TOOLS = {'벡터 DB', 'pgvector'}
BROKERS = {'Kafka', 'RabbitMQ', 'AWS SQS', 'Google Pub/Sub', 'NATS', 'Pulsar', 'Spring Cloud Stream', 'RocketMQ', 'ActiveMQ', 'JMS', 'MQTT', 'NestJS Microservices', 'FastStream'}
SVC_COMM = {'Spring Cloud Gateway', 'Eureka', 'gRPC', 'NestJS Microservices', 'OpenFeign'}
PRODUCE = re.compile(r'\.(send|convertAndSend|publish|emit|sendMessage|produce|sendToQueue|basic_publish|send_message|send_and_wait)\(')
CONSUME = re.compile(r'@(KafkaListener|RabbitListener|SqsListener|JmsListener|EventPattern|MessagePattern|StreamListener|KafkaHandler)\b|\.(subscribe|consume|basic_consume|receiveMessage|receive_message)\(|\.subscriber\(|\bgetmany\(')
DLOCK = re.compile(r'\bRedissonClient\b|\bRLock\s+\w+\s*=|\.getLock\(|[rR]edlock|@SchedulerLock\b|\bLockProvider\b')
NXSET = re.compile(r'\bnx\s*=\s*True|\bsetnx\(|\bSETNX\b|setIfAbsent\(')
DLOCK_STR = re.compile(r'pg_(try_)?advisory(_xact)?_lock|\bGET_LOCK\(', re.I)
CIRCUIT = re.compile(r'@CircuitBreaker\b|\bCircuitBreaker(Registry|Config|Factory)?\b|\bopossum\b|\bpybreaker\b|\bcircuitbreaker\b|\bcircuit_breaker\b')
REPL = re.compile(r'\bAbstractRoutingDataSource\b|\bLazyConnectionDataSourceProxy\b|\bReplicationRoutingDataSource\b|\bShardingSphere')
REPL_TOK = {'shard', 'sharding', 'shards', 'replica', 'replication'}
REPL_SQL = re.compile(r'PARTITION\s+BY\s+(RANGE|LIST|HASH)\b|\bPARTITION\s+OF\b|\bPARTITIONS\s+\d+', re.I)
REPL_CFG = re.compile(r'--replSet|replicaSet|redis-sentinel|sentinel\s+monitor|sentinel\.conf|cluster-enabled|MYSQL_REPLICATION|REPLICATION_MODE|primary_conninfo|--replicaof|\bslaveof\b', re.I)
ZERODOWN = re.compile(r'blue[-_ ]?green|bluegreen|canary[-_ ]?(weight|deploy|release|rollout)|(deploy|release|rollout|traffic)[-_ \w]{0,12}canary|argo-?rollouts|kind:\s*Rollout\b|maxUnavailable:\s*0\b|zero[-_ ]?downtime|무중단|switch[-_ ]?(port|upstream|color)|\b(blue|green)[-_](port|container|upstream|app|server|up|down)\b|BLUE_GREEN', re.I)
OPS_MSG = re.compile(r'\bhot-?fix|핫픽스|장애\s*(대응|수정|복구|해결|조치|원인)|\bincident\b|긴급\s*(수정|패치|배포|대응)|post-?mortem|운영\s*(이슈|장애|버그|오류)', re.I)
AUX_PATH = re.compile(r'(^|/)[\w.-]*(seed|demo|sample|example|fixture|playground)[\w.-]*(/|\.\w+$)', re.I)
is_aux = lambda p: bool(AUX_PATH.search(re.sub(r'(^|/)(com|org|io|net|kr)/example(/demo)?/', '/', p)))     # com.example.demo 같은 기본 패키지 이름은 제외
K8S_PROBE = re.compile(r'^\s*(livenessProbe|readinessProbe|startupProbe):')
K8S_OPS = re.compile(r'HorizontalPodAutoscaler|PodDisruptionBudget|maxUnavailable|maxSurge|^\s*limits:|autoscaling/', re.M)
LAYERS = {'port': 'port', 'ports': 'port', 'adapter': 'adapter', 'adapters': 'adapter', 'domain': 'domain', 'application': 'application', 'usecase': 'application', 'usecases': 'application',
          'use_case': 'application', 'use_cases': 'application', 'infrastructure': 'infrastructure', 'infra': 'infrastructure'}
MANIFEST = {'build.gradle', 'build.gradle.kts', 'pom.xml', 'package.json', 'pyproject.toml', 'requirements.txt', 'go.mod'}
ENTRY = re.compile(r'(Application\.(java|kt)|(^|/)(main|app|server|manage)\.(py|ts|js))$')
FRONT = re.compile(r'(^|/)(front(end)?|client|web|ui|admin-web|app-web|mobile|www)(-[\w]+)?$', re.I)
RATELIM = re.compile(r'rate.?limit|throttl|bucket|limiter|lock|idempoten|session|blacklist|blocklist|otp|verif', re.I)
FIXTURE_PATH = re.compile(r'(^|/)(tests?|load-?tests?|fixtures?|fail|samples?|examples?|docs?|seeds?)/', re.I)
URLTOOL = [(re.compile(r'\brediss?://'), 'Redis'), (re.compile(r'\bpostgres(ql)?(\+\w+)?://'), 'PostgreSQL'), (re.compile(r'\bmysql(\+\w+)?://'), 'MySQL'), (re.compile(r'\bmongodb(\+srv)?://'), 'MongoDB'), (re.compile(r'\bamqps?://'), 'RabbitMQ'), (re.compile(r'storages\.backends\.s3'), 'AWS SDK')]
IMAGETOOL = [(re.compile(r'^\s*image:\s*["\']?(\S*/)?' + a + r'\b', re.I), t) for a, t in (('redis', 'Redis'), ('postgres', 'PostgreSQL'), ('postgis', 'PostgreSQL'), ('pgvector', 'PostgreSQL'), ('mysql', 'MySQL'), ('mariadb', 'MariaDB'), ('mongo', 'MongoDB'),
             ('rabbitmq', 'RabbitMQ'), ('[\\w-]*kafka', 'Kafka'), ('elasticsearch', 'Elasticsearch'), ('nginx', 'Nginx'), ('prom/prometheus', 'Prometheus'), ('grafana', 'Grafana'), ('minio', 'MinIO'))]
HTTPSURE = re.compile(r'\.(builder|create|exchange|retrieve|getForObject|getForEntity|postForObject|postForEntity|newCall|urlopen)\(|\b(AsyncClient|Client|Session|ClientSession)\(|\bfetch\(')
HTTPRECV = re.compile(r'client|template|session|http|axios|requests|httpx|aiohttp|^got$|^ky$|api|rest|web|feign|retrofit', re.I)
PAY_ID = re.compile(r'toss\s?payments?|iamport|portone|kakaopay|naverpay|nicepay|inicis|mercadopago|razorpay|\bpaymentKey\b', re.I)
HTTPCALL = re.compile(r'\.(builder|create|get|post|put|delete|patch|request|send|exchange|retrieve|getForObject|getForEntity|postForObject|postForEntity|execute|newCall)\(|\b(AsyncClient|Client|Session|ClientSession)\(|\bfetch\(')
CACHE_TTL_TOK = {'ttl', 'expire', 'expires', 'expired', 'expiry', 'expiration', 'setex', 'evict', 'invalidate', 'fresh', 'stale'}
TUNE_MSG = re.compile(r'\bperf|성능|튜닝|인덱스|\b(db|database|query|composite|add(ed|s)?|create[ds]?)\W+(\w+\W+){0,3}ind(ex|exes|ices)\b|\bind(exes|ices)\b|n\+1|optimi[sz]\w*\s+(\w+\s+){0,2}(quer|sql|db|select|fetch|join)|quer\w*\s+optimi|slow\s+quer|느린|쿼리 ?(개선|최적화)', re.I)
SQLSTMT = re.compile(r'^\s*(CREATE|ALTER|INSERT|SELECT|UPDATE|DELETE|DROP|WITH|GRANT)\b', re.I)
SQLSHAPE = re.compile(r'^\s*(select\b[\s\S]{1,400}?\bfrom\s+[\w."`\[]|insert\s+into\s+[\w."`]|update\s+[\w."`]+\s+set\b|delete\s+from\s+[\w."`]|'
                      r'create\s+(table|index|unique\s+index)\b|alter\s+table\b|with\s+\w+\s+as\s*\()', re.I)
PROSE = re.compile(r'\b(a|an|the|your|one|please|to)\b', re.I)
JPQL = re.compile(r'\b(?i:from)\s+[A-Z]\w*\s+(?:(?i:as)\s+)?[a-z]\w*\b|\b(?i:new)\s+[\w.]+\(')
PAY_HOST = re.compile(r'api\.tosspayments\.com|api\.iamport\.kr|api\.portone\.io|api\.stripe\.com|kapi\.kakao\.com/v1/payment|open-api\.kakaopay\.com|api\.paypal\.com|api-m\.paypal\.com')
OAUTH_HOST = re.compile(r'kauth\.kakao\.com|accounts\.google\.com/o/oauth2|oauth2\.googleapis\.com|nid\.naver\.com/oauth2|github\.com/login/oauth|appleid\.apple\.com/auth')
OAUTH_CFG = re.compile(r'client-id\s*[:=]|authorization-grant-type|redirect-uri\s*[:=]|oauth2\.client\.registration')
NPLUS1 = re.compile(r'join\s+fetch|@EntityGraph\b|\.select_related\(|\.prefetch_related\(|\bjoinedload\(|\bselectinload\(|@BatchSize\b', re.I)
LOCK = re.compile(r'@Lock\(|PESSIMISTIC_(WRITE|READ)|OPTIMISTIC(_FORCE_INCREMENT)?\b|@Version\b|select_for_update\(|\.tryLock\(\s*[^)\s]|with_for_update\(|isolation\s*=\s*Isolation\.|isolationLevel\s*:')
LOCKSTR = re.compile(r'\bFOR UPDATE\b', re.I)
BUILD = re.compile(r'gradlew|\bgradle\s|\bmvnw?\s|\b(npm|pnpm|yarn|bun)\s+(ci|test|run\s+(build|test|lint)|build|install)|pytest|\btox\b|go\s+(build|test)|cargo\s+(build|test)|docker\s+build\b|\bbuild[\w-]*\.sh\b|^\s*-?\s*name:.*\b(build|test|lint|빌드|테스트)\b|\b(turbo|nx|lerna)\s+(run\s+)?(build|test)|\buv\s+(run|sync)|pip\s+install|make\s+(build|test)')
DEPLOY = re.compile(r'appleboy/(ssh|scp)-action|\bssh\s+-|\bssh\s+\S+@|\bscp\s|rsync\s|kubectl\s+(?:-\S+\s+\S+\s+)*(apply|rollout|set\s+image|replace|patch)|helm\s+(upgrade|install)|'
                    r'aws\s+(ecs|s3\s+(sync|cp)\s+(?!\S*s3://)\S+\s+\S*s3://|deploy|lambda|elasticbeanstalk|ssm\s+send-command)|send-ssm-command|\bdeploy[\w-]*\.sh\b|aws-actions/amazon-ecs|eb\s+deploy|azure/webapps-deploy|einaregilsson/beanstalk-deploy|'
                    r'google-github-actions/deploy|gcloud\s+(run|app)\s+deploy|peaceiris/actions-gh-pages|JamesIves/github-pages-deploy|actions/deploy-pages|flyctl|superfly/|'
                    r'vercel\s+(deploy|--prod|pull|build)|vercel-action|netlify\s+deploy|netlify/actions|actions-netlify|railway\s+up|deploy-hook|deploy_hook|render\.com/deploy')
PUBLISH = re.compile(r'docker\s+(compose\s+)?push|push:\s*true')
AI_FILES = re.compile(r'(^|/)(CLAUDE\.md|AGENTS\.md|\.cursorrules|copilot-instructions\.md)$|^\.cursor/|^\.claude/')
AI_NAMES = {'claude', 'claude code', 'copilot', 'github copilot', 'cursor', 'cursor agent', 'cursoragent', 'devin', 'codex', 'openai codex', 'jules', 'gemini', 'aider'}
GEN_PATH = re.compile(r'(^|/)prisma/migrations/|(^|/)drizzle/|(^|/)migrations/\d{4}_\w+\.py$|(^|/)migrations?/\d{10,}[-_]\w+\.(ts|js)$')
GEN_NAME = re.compile(r'(^|/)(gradlew(\.bat)?|mvnw(\.cmd)?|reportWebVitals\.[jt]s|setupTests\.[jt]s|react-app-env\.d\.ts|vite-env\.d\.ts|next-env\.d\.ts|App\.test\.[jt]sx?|manage\.py|asgi\.py|wsgi\.py)$')


# ------------------------------------------------------------------ 주석·문자열 구분
def mask_code(ext, text):
    """-> (줄별 코드: 주석 제거·문자열 내용 비움, [(시작 줄, 문자열 내용)])"""
    slash, hashc, dash = ext not in ('.py', '.sql'), ext == '.py', ext == '.sql'
    tick, triple = ext in JS, ext in ('.py', '.java', '.kt')
    out, strs, buf, i, n, line = [], [], [], 0, len(text), 0
    while i < n:
        c, two = text[i], text[i:i + 2]
        if c == '\n':
            out.append(''.join(buf)); buf = []; line += 1; i += 1; continue
        if (slash and two == '//') or (hashc and c == '#') or (dash and two == '--'):
            j = text.find('\n', i); i = n if j < 0 else j; continue
        if (slash or dash) and two == '/*':
            j = text.find('*/', i + 2); j = n if j < 0 else j + 2
            for _ in range(text.count('\n', i, j)): out.append(''.join(buf)); buf = []; line += 1
            i = j; continue
        if (c == "'" or (c == '"' and not dash)) or (tick and c == '`'):
            q = c * 3 if triple and text[i:i + 3] == c * 3 else c
            j, content, start = i + len(q), [], line
            while j < n and not text.startswith(q, j):
                if text[j] == '\\': content.append(text[j:j + 2]); j += 2; continue
                if text[j] == '\n' and len(q) == 1 and q != '`': break
                content.append(text[j]); j += 1
            s = ''.join(content); strs.append((start, s)); buf.append(q[0] * 2)
            for _ in range(s.count('\n')): out.append(''.join(buf)); buf = []; line += 1
            i = j + len(q) if text.startswith(q, j) else j
            continue
        buf.append(c); i += 1
    out.append(''.join(buf))
    return out, strs


def mask_hash(line):
    for m in re.finditer(r'(^|\s)#', line):
        head = line[:m.start()]
        if head.count('"') % 2 == 0 and head.count("'") % 2 == 0: return head
    return line


GEN_DIR = re.compile(r'(^|/)(generated|__generated__|gen|out|target|coverage|\.next|\.nuxt|\.output|storybook-static)/', re.I)
SQL_GEN = re.compile(r'--> statement-breakpoint|^-- (MySQL dump|PostgreSQL database dump|phpMyAdmin SQL Dump|Dumped (from|by))|^/\*!40\d{3} SET|\b[a-z]\w{0,3}\d_\d\.\w+', re.M)


COOKIECUTTER = re.compile(r'class TestUserAdmin\b|class TestUserUpdateView\b|class TestUserAdminCreationForm\b|def test_user_get_absolute_url\b|def test_swagger_accessible_by_admin\b|def test_user_count\(settings\)|'
                          r'def is_open_for_signup\b|def merge_production_dotenvs|class TestUserViewSet\b|def test_user_detail\(\)|def test_update_site_forward|Set site domain and name')


TESTSEG = re.compile(r'(^|[-_.])(tests?|testing|e2e|specs?|mocks?|fixtures?|stubs?|fakes?)($|[-_.])', re.I)
TOPIC = {'java', 'spring', 'springboot', 'boot', 'kotlin', 'python', 'py', 'js', 'javascript', 'ts', 'typescript', 'react', 'vue', 'node', 'nodejs', 'nest', 'nestjs', 'express', 'django', 'fastapi', 'flask',
         'algorithm', 'algorithms', 'cs', 'sql', 'db', 'database', 'backend', 'frontend', 'web', 'basic', 'basics', 'note', 'notes', 'til', 'log', 'my', 'jpa', 'docker', 'aws', 'go', 'rust', 'c', 'cpp', 'coding', 'code', 'dev', 'repo'}


def is_test_path(p):
    if TESTPATH.search(p): return True
    if re.search(r'^mock|[-_.]mock|Mock[A-Z]|[a-z]Mock\b', os.path.basename(p)): return True
    return any(TESTSEG.search(seg) or re.search(r'[a-z]Tests?($|[A-Z])|^tests?[A-Z]', seg) for seg in p.split('/')[:-1])


def is_practice(name):
    """이름 기준 연습·학습 레포. 'study'는 나머지 낱말이 전부 기술·주제 낱말일 때만(예: spring-study). study-editor 같은 제품 이름은 제외"""
    m = PRACTICE.search(name)
    if not m: return False
    if m.group(2).lower() in ('study', 'studies'):
        rest = [t for t in re.split(r'[/_.\-]+', name.lower()) if t and t not in ('study', 'studies') and not t.isdigit()]
        return all(t in TOPIC for t in rest)
    return True


def tokens(line):
    """식별자를 camelCase·snake_case 조각으로 쪼갠 소문자 집합"""
    return {t.lower() for w in re.findall(r'[A-Za-z]+', line) for t in re.findall(r'[A-Z]+(?![a-z])|[A-Z]?[a-z]+', w)}


def generated(p, text):
    if GEN_NAME.search(p) or GEN_PATH.search(p) or GEN_DIR.search(p) or p.endswith('.d.ts'): return True
    if p.endswith('.py') and COOKIECUTTER.search(text): return True                                # cookiecutter-django 기본 파일
    if any(len(x) > 1500 for x in text.split('\n')): return True                               # 압축·번들 결과물
    if p.endswith(('.js', '.jsx', '.cjs', '.mjs')) and re.search(r'Object\.defineProperty\(exports, "__esModule"|__importDefault|tslib_1\b|__createBinding', text): return True   # tsc 결과물
    if re.search(r'(^|/)app\.controller\.ts$', p) and 'getHello' in text and len(re.findall(r'@(Get|Post|Put|Delete|Patch)\(', text)) <= 1: return True
    if re.search(r'(^|/)app\.service\.ts$', p) and 'getHello' in text and text.count('(') <= 3: return True
    if len(re.findall(r'@Test\b', text)) == 1 and 'contextLoads' in text: return True          # Spring Initializr 기본 테스트
    if re.search(r'(^|/)app\.(controller|service|controller\.spec|e2e-spec)\.ts$', p) and 'Hello World!' in text: return True   # Nest CLI 기본 파일
    t = re.sub(r'\s+', ' ', re.sub(r'^\s*(package|import)\b.*$', '', text, flags=re.M)).strip()
    return bool(re.fullmatch(r'@SpringBootTest (public )?class \w+ \{ @Test (public )?void contextLoads\(\) (throws Exception )?\{ \} \}', t)
                or re.fullmatch(r'@SpringBootApplication public class \w+ \{ public static void main\(String\[\] args\) \{ SpringApplication\.run\(\w+\.class, args\); \} \}', t))


def fkind(p):
    base, low = os.path.basename(p), p.lower()
    if b.EXCL.search(p): return None
    if base == 'Dockerfile' or base.startswith('Dockerfile.') or low.endswith('.dockerfile') or re.fullmatch(r'(docker-)?compose[\w.-]*\.ya?ml', base): return 'docker'
    if low.startswith('.github/workflows/') and low.endswith(('.yml', '.yaml')): return 'workflow'
    if low.endswith('.tf'): return 'iac'
    if low.endswith('.jmx'): return 'loadtest'
    if low.endswith('.sh') or base in ('appspec.yml', 'appspec.yaml'): return 'script'
    if re.search(r'prometheus|grafana', low) and low.endswith(('.yml', '.yaml', '.ini', '.json')): return 'monitoring'
    if 'nginx' in low and low.endswith('.conf'): return 'nginx'
    if low.endswith('.sql'): return 'sql'
    if low.endswith('.prisma'): return 'prisma'
    if re.fullmatch(r'application(-[\w.]+)?\.(ya?ml|properties)', base): return 'appcfg'
    if base in ('build.gradle', 'build.gradle.kts', 'package.json', 'requirements.txt', 'pyproject.toml', 'pom.xml'): return 'manifest'
    if AI_FILES.search(p): return 'ai'
    if low.endswith(('.yml', '.yaml')): return 'yaml'
    return 'code' if os.path.splitext(base)[1] in LANG else None


# ------------------------------------------------------------------ 사람 묶기
def is_ai(name, email):
    n, e = name.lower().strip(), email.lower()
    return n in AI_NAMES or e.endswith('@anthropic.com') or ('[bot]' in n and any(x in n for x in ('copilot', 'claude', 'cursor', 'codex', 'devin', 'jules')))


def is_bot(name, email):
    return '[bot]' in name or (name == 'GitHub' and email == 'noreply@github.com')


def people(repo):
    fmt = '%H%x1f%an%x1f%ae%x1f%cn%x1f%ce%x1f%s%x1f%(trailers:key=Co-authored-by,valueonly=true,separator=%x3B)'
    rows = [l.split('\x1f') for l in b.git(repo, 'log', '--reverse', f'--format={fmt}', 'HEAD').splitlines() if l.count('\x1f') >= 6]
    par = {}

    def find(x):
        par.setdefault(x, x)
        while par[x] != x: par[x] = par[par[x]]; x = par[x]
        return x

    pair = collections.Counter()
    for sha, an, ae, cn, ce, subj, tr in rows:
        if not is_ai(an, ae) and not is_bot(an, ae): pair[(re.sub(r'\s+', '', an.lower()), ae.lower())] += 1
    top_email, top_name = {}, {}
    for (nm, em), c in pair.items():
        if c > pair.get((nm, top_email.get(nm)), 0): top_email[nm] = em
        if c > pair.get((top_name.get(em), em), 0): top_name[em] = nm
    for (nm, em), c in pair.items():   # 이름-이메일은 서로에게 가장 흔한 짝일 때만 묶음(남의 컴퓨터로 올린 커밋 때문에 두 사람이 합쳐지지 않게)
        if top_email[nm] == em or top_name[em] == nm: par[find('n:' + nm)] = find('e:' + em)
        m = re.match(r'(?:\d+\+)?([\w-]+)@users\.noreply\.github\.com$', em)
        if m: par[find('e:' + em)] = find('n:' + m.group(1).lower())

    def ident(name, email):
        return 'e:' + email.lower()

    names = collections.defaultdict(collections.Counter)
    for sha, an, ae, cn, ce, subj, tr in rows:
        if not is_ai(an, ae) and not is_bot(an, ae): names[find(ident(an, ae))][an] += 1
    disp = {g: c.most_common(1)[0][0] for g, c in names.items()}
    humans = set(disp.values())
    who, ai_n, order, subj_of, unassigned = {}, collections.Counter(), {}, {}, 0
    for i, (sha, an, ae, cn, ce, subj, tr) in enumerate(rows):
        order[sha] = i; subj_of[sha] = subj
        if is_ai(an, ae):
            p = disp.get(find(ident(cn, ce))) if not is_ai(cn, ce) and not is_bot(cn, ce) else None
            if p is None and len(humans) == 1: p = next(iter(humans))
            who[sha] = p
            if p: ai_n[p] += 1
            else: unassigned += 1
        elif is_bot(an, ae): who[sha] = None
        else:
            who[sha] = disp[find(ident(an, ae))]
            if re.search(r'claude|copilot|cursor|codex|devin|anthropic', tr, re.I): ai_n[who[sha]] += 1
    merged = {d: sorted(c) for g, c in names.items() for d in [disp[g]] if len(c) > 1}
    return dict(who=who, order=order, subj=subj_of, ai=ai_n, merged=merged, ai_unassigned=unassigned, humans=sorted(humans))


def kt_aliases(lines, sym):
    al = dict(sym)
    for line in lines:
        for m in re.finditer(r'\b(\w+)\s*:\s*([A-Z]\w*)', line):
            if m.group(2) in al: al.setdefault(m.group(1), al[m.group(2)])
        m = re.match(r'\s*(?:private\s+|lateinit\s+)*(?:val|var)\s+(\w+)\s*=\s*([A-Z]\w*)', line)
        if m and m.group(2) in al: al.setdefault(m.group(1), al[m.group(2)])
    return al


def aliases1(ext, lines, sym):
    """import한 이름으로 직접 만든 변수만 별칭으로 인정(별칭의 별칭은 인정 안 함)"""
    al = dict(sym)
    for line in lines:
        if ext == '.java':
            for m in re.finditer(r'\b([A-Z]\w*)\s*(?:<[^;=(){}]*>)?\s+([a-z]\w*)\s*(?=[;=,)])', line):
                if m.group(1) in sym: al.setdefault(m.group(2), sym[m.group(1)])
        elif ext == '.py':
            m = re.match(r'\s*(?:self\.)?(\w+)\s*(?::\s*[\w.\[\], |]+)?\s*=\s*(?:await\s+)?(\w+)((?:\.\w+)*)\(', line)
            if m and m.group(2) in sym:      # 객체를 만드는 호출만(대문자로 시작하는 이름, 알려진 생성 함수). 함수 결과값은 별칭 아님
                last = (m.group(3) or m.group(2)).split('.')[-1]
                if last[:1].isupper() or last in ('create_engine', 'create_async_engine', 'sessionmaker', 'async_sessionmaker', 'from_url', 'connect'):
                    al.setdefault(m.group(1), sym[m.group(2)])
            for m in re.finditer(r'\b(\w+)\s*:\s*(\w+)\b', line):
                if m.group(2) in sym: al.setdefault(m.group(1), sym[m.group(2)])
            m = re.search(r'\bwith\s+(\w+)[.(].*\bas\s+(\w+)\s*:', line)
            if m and m.group(1) in sym and re.search(r'\b[A-Z]\w*\([^()]*\)?[^()]*\bas\s+\w+\s*:', line): al.setdefault(m.group(2), sym[m.group(1)])
        else:
            m = re.match(r'\s*(?:export\s+)?(?:const|let|var)\s+([\w$]+)\s*(?::\s*[\w$<>\[\]. |]+)?=\s*(?:await\s+)?(new\s+)?([\w$]+)((?:\.[\w$]+)*)\s*[(<]', line)
            if m and m.group(3) in sym:
                last = (m.group(4) or m.group(3)).split('.')[-1]
                if 'await' not in line and ').' not in line and (m.group(2) or not m.group(4) or last[:1].isupper() or last.startswith('create')): al.setdefault(m.group(1), sym[m.group(3)])
    return al


def used(c, al, sym):
    t = set()
    for m in b.IDENT.finditer(c):
        tok = m.group(0)
        if tok not in al: continue
        if tok not in sym:
            head, tail = c[:m.start()], c[m.end():]
            if tail.lstrip().startswith('(') or (head.endswith('.') and not re.search(r'\b(self|this|cls)\.$', head)): continue
        t.update(al[tok])
    for fq in re.findall(r'\b((?:org|jakarta|javax|lombok)\.[a-z][\w.]*)', c): t.update(b.java_tech(fq))
    return t


def parse_imports(ext, lines):
    if ext == '.kt':
        out = {}
        for i, raw in enumerate(lines):
            m = re.match(r'\s*import\s+([\w.]+?)(\.\*)?(?:\s+as\s+(\w+))?\s*$', raw.replace('`', ''))
            if m: out[i] = [(None if m.group(2) else (m.group(3) or m.group(1).rsplit('.', 1)[-1]), toks('java', m.group(1)))]
        return out
    cont = set()
    if ext in JS or ext == '.py':            # 여러 줄에 걸친 import를 한 줄로 이어 붙임
        lines = list(lines); i = 0
        while i < len(lines):
            t = lines[i].strip()
            if ext == '.py':
                opened = re.match(r'from\s+[\w.]+\s+import\s*\(', t) and ')' not in t
                end = lambda x: ')' in x
            else:
                opened = re.match(r'(import|export)\s+(type\s+)?(\{|[\w$]+\s*,\s*\{|\*)', t) and not re.search(r"""from\s+['"]""", t)
                end = lambda x: re.search(r"""from\s+['"]""", x)
            if opened:
                buf, k = [t], i + 1
                while k < len(lines) and k - i < 120:
                    buf.append(re.sub(r'\s+#.*$|\s+//.*$', '', lines[k].strip()))
                    if end(lines[k]): break
                    k += 1
                if k < len(lines) and k - i < 120:
                    lines[i] = ' '.join(buf)
                    for q in range(i + 1, k + 1): lines[q] = ''; cont.add(q)
                    i = k
            i += 1
    out = b.parse_imports(ext, lines)
    if ext in JS:
        out = {i: [((n[5:].strip() if n and n.startswith('type ') else n), tt) for n, tt in lst] for i, lst in out.items()}
    for q in cont: out.setdefault(q, [])
    return out


# ------------------------------------------------------------------ 분석
def analyze(repo):
    P = people(repo); who, order = P['who'], P['order']
    practice_repo = is_practice(os.path.basename(os.path.abspath(repo)).split('__')[-1])
    ev, weak = collections.defaultdict(list), collections.defaultdict(list)

    lift, cv = collections.defaultdict(list), {'via': set(), 'base': set(), 'line': set()}

    def add(p, key, lv, where, test=False, via=None, strong=False):
        if not p: return
        ev[(p, key)].append((lv, where, test, strong))
        if key in ACT_KEYS and lv >= 2 and not test:
            for t in (cv['via'] if via is None else via):
                # 근거 줄에 직접 나온 도구는 활동 LV 그대로, 파일의 언어·프레임워크는 LIFT_CAP_FILE 까지만
                lift[(p, t)].append((min(lv, LIFT_CAP_FILE) if (via is None and t in cv['base'] and t not in cv['line']) else lv, key, where))

    files = [p for p in b.head_files(repo) if fkind(p)]
    lang = collections.Counter(); gen_files = []
    prod, cons, outbox, saga, vec, llm, circuit, bluegreen = (collections.defaultdict(list) for _ in range(8))
    svc_lines, svc_comm, layer_files = collections.defaultdict(collections.Counter), {}, collections.defaultdict(lambda: collections.defaultdict(list))
    all_files = b.head_files(repo)
    svc_roots = sorted({os.path.dirname(q) for q in all_files if os.path.basename(q) in MANIFEST and os.path.dirname(q) and q.count('/') <= 3 and not FRONT.search(os.path.dirname(q)) and not is_test_path(q)}, key=len, reverse=True)
    svc_roots = sorted(set(svc_roots) | {'/'.join(q.split('/')[:2]) for q in all_files if re.match(r'(apps|services|microservices)/[^/]+/', q) and ENTRY.search(q) and not FRONT.search('/'.join(q.split('/')[:2])) and not is_test_path(q)}, key=len, reverse=True)
    svc_roots = [r0 for r0 in svc_roots if any(q.startswith(r0 + '/') and (os.path.basename(q).startswith('Dockerfile') or ENTRY.search(q)) for q in all_files)]
    svc_roots = [r0 for r0 in svc_roots if not any(o != r0 and o.startswith(r0 + '/') for o in svc_roots)] if len(svc_roots) > 1 else svc_roots
    layer_kinds = {LAYERS[seg.lower()] for q in all_files for seg in q.split('/')[:-1] if seg.lower() in LAYERS}
    layered = ({'port', 'adapter'} <= layer_kinds) or ({'domain', 'application', 'infrastructure'} <= layer_kinds)
    deploy_orders, outbox_best, filecols = [], {}, set()
    tables, tab_of, rels, idxs, nplus = {}, collections.defaultdict(set), collections.Counter(), [], []
    newcols = set()

    def table(name, sha, where):
        name = name.split('.')[-1].strip('`"[]').lower(); p = who.get(sha)
        if name not in tables or order.get(sha, 1e9) < order.get(tables[name][0], 1e9): tables[name] = (sha, where)
        if p: tab_of[p].add(name)
        return name

    for p in files:
        k, ext = fkind(p), os.path.splitext(p)[1]
        bl = b.blame(repo, p)
        if not bl: continue
        raw = [x[2] for x in bl]; shas = [x[0] for x in bl]; text = '\n'.join(raw)
        prac = practice_repo or is_practice('/'.join(p.split('/')[:-1][:2]))
        low_lv = 1 if prac else 2
        is_test = is_test_path(p)
        per = collections.Counter(who.get(s) for s, t in zip(shas, raw) if t.strip() and not t.strip().startswith(('#', '//')))
        per.pop(None, None)
        if k == 'code':
            if generated(p, text): gen_files.append(p); continue
            code, strs = mask_code(ext, text)
            if len(code) != len(raw): code = (code + [''] * len(raw))[:len(raw)]
            imps = parse_imports(ext, raw)
            sym = {n: tt for lst in imps.values() for n, tt in lst if n and tt}
            if ext == '.py':
                for n0 in ('WebSocket', 'WebSocketDisconnect'):
                    if n0 in sym and 'FastAPI' in sym[n0]: sym[n0] = list(sym[n0]) + ['WebSocket']
            al = kt_aliases(code, sym) if ext == '.kt' else aliases1(ext, code, sym)
            if ext in ('.ts', '.tsx'):
                for c0 in code:
                    for m0 in re.finditer(r'\b(?:private|public|protected|readonly)\s+(?:readonly\s+)?([\w$]+)\s*[?!]?:\s*([A-Z][\w$]*)', c0):
                        if m0.group(2) in sym: al.setdefault(m0.group(1), sym[m0.group(2)])
            is_entity = '@Entity' in text
            cv['via'], cv['base'], cv['line'] = set(), set(), set()
            file_tools = {x for lst in imps.values() for _, tt in lst for x in tt}
            base_via = {LANG[ext]} | (file_tools & FRAMEWORKS)
            svc = next((r0 for r0 in svc_roots if p.startswith(r0 + '/')), None)
            if svc and not is_test:
                for d0, n0 in per.items(): svc_lines[d0][svc] += n0
            if layered and not is_test and not prac:
                kinds = {LAYERS[seg.lower()] for seg in p.split('/')[:-1] if seg.lower() in LAYERS}
                for d0, n0 in per.items():
                    if n0 >= 10:
                        for kk in kinds: layer_files[d0][kk].append(p)
            if 'cap:loadtest' in file_tools and not prac and 'smoke' not in os.path.basename(p).lower():
                for d0, n0 in per.items():
                    if n0 >= 10: add(d0, '부하 테스트', 5, f'{p} {n0}줄', via={LANG[ext]} | {x for x in file_tools if x in ('k6', 'Locust', 'Gatling', 'nGrinder')})
            client_al = {m.group(2) for c0 in code for m in re.finditer(r'\b([A-Z]\w*(?:Client|Template|Session))\s*(?:<[^;=(){}]*>)?\s+([a-z]\w*)\s*(?=[;=,)])', c0)} | {m.group(1) for c0 in code for m in re.finditer(r'\b(\w+)\s*:\s*[A-Z]\w*(?:Client|Template|Session)\b', c0)}
            declarative_http = ext in ('.java', '.kt') and bool(re.search(r'@FeignClient\b|^import\s+retrofit2\.|@HttpExchange\b', text, re.M))
            sby = collections.defaultdict(list)
            for ln, s in strs: sby[ln].append(s)
            cur = cur_sha = pend = batch = None; pend_idx = []
            cls_sha = next((shas[i] for i, c in enumerate(code) if re.search(r'\b(class|interface)\s+\w+', c)), shas[0])
            for i, c in enumerate(code):
                sha, pr = shas[i], who.get(shas[i]); where = f'{p}:{i + 1}'
                # ---- 스키마 사실(누가 썼든 테이블 등록은 하고, 근거는 쓴 사람에게)
                if ext in JS:
                    m = re.search(r"""\b(?:pg|mysql|sqlite)Table\(\s*['"`](\w+)|\.createTable\(\s*['"`](\w+)|sequelize\.define\(\s*['"`](\w+)""", raw[i]) if '(' in c else None
                    if m: cur = table(next(x for x in m.groups() if x), sha, where)
                    m = re.search(r'\b(?:const|let|var)\s+(\w+?)(?:Schema)?\s*=\s*new\s+(?:mongoose\.)?Schema\b', c)
                    if m: cur = table(m.group(1), sha, where)
                    if pr and (re.search(r'\.references\(|\.(belongsTo|hasMany|hasOne|belongsToMany)\(', c) or re.search(r"""\bref:\s*['"`]""", raw[i])): rels[pr] += 1
                if ext == '.kt':
                    m = re.match(r'\s*(?:internal\s+|private\s+)?object\s+(\w+)\s*:\s*\w*Table\b', c)
                    if m: cur = table(m.group(1), sha, where)
                    if pr and re.search(r'\breference\(|\.references\(', c): rels[pr] += 1
                if ext == '.py':
                    m = re.match(r'class\s+(\w+)\(.*\bSQLModel\b.*\btable\s*=\s*True', c)
                    if m: cur = table(m.group(1), sha, where)
                    if pr and re.search(r'\bforeign_key\s*=', c): rels[pr] += 1
                if ext in ('.java', '.kt', '.ts'):
                    if re.search(r'@Entity\b', c): pend = sha
                    if re.search(r'@Index\b', c):
                        if ext == '.ts' and cur and pend is None: idxs.append((pr, sha, cur, where, 'unique' in raw[i].lower(), None))
                        else: pend_idx.append((pr, sha, where, 'unique' in raw[i].lower()))
                    m = re.search(r'\b(?:class|interface)\s+(\w+)', c)
                    if m:
                        if pend is not None:
                            cur = table(m.group(1), pend, where); pend = None
                            for a, s2, w2, u in pend_idx: idxs.append((a, s2, cur, w2, u, None))
                        pend_idx = []
                    if re.search(r'@(ManyToOne|OneToMany|OneToOne|ManyToMany)\b', c) and pr: rels[pr] += 1
                    elif is_entity and pr and re.search(r'\b(Long|UUID|Integer|String|number|string)\s+\w+Id\s*;|\b\w+Id\s*:\s*(number|string)\s*;', c): rels[pr] += 1
                elif ext == '.py':
                    near = [s for j in range(i, min(i + 5, len(code))) for s in sby.get(j, [])]
                    if re.search(r'\bop\.create_table\(', c) and near: cur = table(near[0], sha, where)
                    m = re.search(r'batch_alter_table\(', c)
                    if m and near: batch = near[0]
                    if re.search(r'\bop\.create_index\(', c) and len(near) >= 2:
                        idxs.append((pr, sha, near[1].lower(), where, 'unique=True' in ''.join(code[i:i + 6]), None))
                    elif re.search(r'\bbatch_op\.create_index\(', c) and batch:
                        idxs.append((pr, sha, batch.lower(), where, 'unique=True' in ''.join(code[i:i + 4]), None))
                    if re.search(r'__tablename__\s*=', c) and sby.get(i): cur = table(sby[i][0], sha, where)
                    m = re.search(r'^class\s+(\w+)\(.*\bmodels\.Model\b', c)
                    if m: cur = table(m.group(1), sha, where)
                    if re.search(r'\bForeignKey(Constraint)?\(', c) and pr: rels[pr] += 1
                    if cur and re.search(r'\b(db_)?index=True|\bIndex\(', c): idxs.append((pr, sha, cur, where, bool(re.search(r'unique=True|primary_key=True|UniqueConstraint', ''.join(code[max(0, i - 3):i + 4]))), None))
                if not pr or not c.strip(): continue
                lang[(pr, LANG[ext])] += 1
                if i in imps:
                    for _, tt in imps[i]:
                        for tech in tt:
                            if not tech.startswith('cap:'): weak[(pr, tech)].append(f'import만 {where}')
                    continue
                u = used(c, al, sym)
                recv = {x for t in al if re.search(r'\b' + re.escape(t) + r'\.\w+\(', c) for x in al[t]}
                tools = {x for x in u if not x.startswith('cap:')}
                direct = {x for t in set(b.IDENT.findall(c)) & sym.keys() for x in sym[t]}
                for tool in tools: add(pr, tool, low_lv, where, is_test or tool not in direct)
                caps = {x[4:] for x in (direct | recv) if x.startswith('cap:')}
                ltools = {x for x in (direct | recv) if not x.startswith('cap:')}
                cv['via'], cv['base'], cv['line'] = base_via | ltools, base_via, ltools
                if 'JWT' in sby.get(i, []) and re.search(r'\btyp\b', c) and not is_test: add(pr, 'JWT', low_lv, where)
                for s in sby.get(i, []):
                    if not is_test:
                        for rx, t0 in URLTOOL:
                            if rx.search(s) and not re.search(r'\s', s.strip()): add(pr, t0, low_lv, where, True)
                    if SQLSHAPE.search(s) and not (ext in ('.java', '.kt') and JPQL.search(s) and 'nativeQuery' not in ''.join(raw[max(0, i - 2):i + 3])):
                        sel = re.match(r'\s*select\b([\s\S]*?)\bfrom\b', s, re.I)
                        if not is_test and not (sel and PROSE.search(sel.group(1))) and not re.search(r'[\uac00-\ud7a3]', s[:60]): add(pr, 'SQL', 1, where)
                    if not prac and not is_test and '\n' not in s and not re.search(r'docs?|example|swagger|openapi|readme', p, re.I):
                        if PAY_HOST.search(s): add(pr, '결제 연동', 3, where)
                        if OAUTH_HOST.search(s): add(pr, 'OAuth 연동', 3, where)
                        if LOCKSTR.search(s) and SQLSHAPE.search(s) and not is_aux(p): add(pr, '동시성 제어', 4, where)
                        if DLOCK_STR.search(s) and not is_aux(p): add(pr, '분산 락·분산 트랜잭션', 5, where)
                if not is_test and (NPLUS1.search(c) or any(NPLUS1.search(s) for s in sby.get(i, []))): nplus.append((pr, sha, cls_sha, where))
                if prac: continue
                if is_test:
                    if TESTDECL.search(c) and not re.search(r'should be defined|should create the app|should be created|should create\b|renders learn react link|should render title|should have (as|the) title', raw[i]) and not p.endswith('conftest.py') and not (i and 'fixture' in raw[i - 1]): add(pr, '테스트 코드', 2, where, True)
                    continue
                if declarative_http:
                    if re.search(r'@(Get|Post|Put|Delete|Patch|Request)Mapping\b|@(GET|POST|PUT|DELETE|PATCH)\(|@(Get|Post|Put|Delete|Patch|Http)Exchange\b|@FeignClient\b', c): add(pr, '외부 API 연동', 2, where)
                elif API['java' if ext in ('.java', '.kt') else 'py' if ext == '.py' else 'js'].search(c): add(pr, 'API 개발', 2, where)
                if ext in JS and re.search(r'(?<![.\w$])fetch\(', c) and not re.search(r'function\s+fetch\b', text): add(pr, '외부 API 연동', 2, where)
                if re.search(r'\bTransport\.(RMQ|KAFKA|NATS|MQTT)\b', c): add(pr, '메시지 큐', 3, where)
                if 'http' in caps and HTTPCALL.search(c) and (HTTPSURE.search(c) or any(HTTPRECV.search(x) or x in client_al for x in re.findall(r'([\w$]+)\s*\.\s*(?:get|post|put|delete|patch|request|send|execute)\(', c))):
                    add(pr, '외부 API 연동', 2, where)
                tk = tokens(c) if 'cach' in c.lower() else set()
                if 'cache' in caps or (tk & {'cache', 'caches', 'caching'} and tk & CACHE_TTL_TOK and '(' in c and not re.search(r'cache-?control', c, re.I)):
                    if not RATELIM.search(p) and not RATELIM.search(c) and not re.match(r'\s*@EnableCaching\s*$', c): add(pr, '캐시 도입', 3, where)
                if 'queue' in caps and not (ltools == {'Celery'} and not re.search(r'@shared_task|@\w+\.task\b|\.delay\(|\.apply_async\(|send_task\(|\bcrontab\(|beat_schedule', c)): add(pr, '메시지 큐', 3, where)
                if 'oauth' in caps or re.search(r'\.oauth2Login\(', c): add(pr, 'OAuth 연동', 3, where)
                if 'payment' in caps or (PAY_ID.search(c) and '(' in c): add(pr, '결제 연동', 3, where)
                if 'monitoring' in caps: add(pr, '모니터링 설정', 3, where)
                if 'iac' in caps and per.get(pr, 0) >= 10: add(pr, 'IaC', 3, where)
                if is_aux(p): continue
                lock_ctx = bool(re.search(r'lock', ' '.join(code[max(0, i - 5):i + 1]) + ' ' + os.path.basename(p), re.I))   # 앞 5줄·파일 이름에 lock이 있어야 잠금 용도로 봄(중복 방지 표시는 제외)
                if DLOCK.search(c) or (lock_ctx and (NXSET.search(c) or re.search(r"""['"]NX['"]""", raw[i]))): add(pr, '분산 락·분산 트랜잭션', 5, where, strong=bool(re.search(r'\.getLock\(|\.tryLock\(|\.acquire\(|setIfAbsent\(|nx\s*=|NX', raw[i])))
                elif LOCK.search(c): add(pr, '동시성 제어', 4, where)
                if 'auth' in caps: add(pr, '인증·인가 구현', 2, where)
                if ltools & LLM_TOOLS: add(pr, 'LLM 기능 개발', 2, where); llm[pr].append(where)
                if ltools & VECTOR_TOOLS: vec[pr].append(where)
                if 'Spring Batch' in ltools: add(pr, '배치 처리', 3, where)
                elif 'scheduler' in caps or re.search(r'@Scheduled\b', c): add(pr, '배치 처리', 2, where)
                if ltools & {'Elasticsearch', 'OpenSearch'}: add(pr, '검색 기능 구축', 3, where)
                if CIRCUIT.search(c) and not re.match(r'\s*package\s', c) and ('Resilience4j' in ltools or re.search(r'@CircuitBreaker\b|opossum|pybreaker|circuit_?breaker', c)): add(pr, '장애 격리', 4, where)
                tk4 = tokens(c) if not re.match(r'\s*package\s', c) else set()
                if {'circuit', 'breaker'} <= tk4 or 'circuitbreaker' in tk4: circuit[pr].append(where)
                if REPL.search(c) or (tk4 & REPL_TOK and not tk4 & {'kafka', 'topic', 'partitions', 'k8s', 'deployment', 'pod', 'pods', 'dto', 'health', 'lag'} and tk4 & {'datasource', 'database', 'db', 'redis', 'mongo', 'mongodb', 'mysql', 'postgres', 'postgresql', 'routing', 'url', 'uri', 'host', 'hosts', 'nodes'}
                                      and not re.match(r'\s*(export\s+)?(abstract\s+)?(class|interface|type|enum)\b|\s*@', c) and not re.search(r'dto|health|swagger|docs?/', p, re.I)):
                    add(pr, 'DB 복제·파티셔닝', 5, where)
                if 'outbox' in tk4:
                    outbox[pr].append(where)
                    if pr not in outbox_best and re.search(r'\b(class|def|function|interface)\s+\w*[Oo]utbox|[Oo]utbox\w*\.(save|publish|insert|create|add|send)\w*\(', c): outbox_best[pr] = where   # 근거로 보여 줄 줄: 정의나 저장·발행 호출
                if {'blue', 'green'} <= tk4 or 'bluegreen' in tk4: bluegreen[pr].append(where)
                if 'saga' in tk4: saga[pr].append(where)
                if ltools & BROKERS:
                    if CONSUME.search(c): cons[pr].append((where, tuple(ltools & BROKERS)))
                    if PRODUCE.search(c): prod[pr].append((where, tuple(ltools & BROKERS)))
                if svc and (ltools & SVC_COMM or (ltools & BROKERS and (CONSUME.search(c) or PRODUCE.search(c))) or (declarative_http and '@FeignClient' in c)): svc_comm.setdefault(pr, where)
        elif k == 'sql' and (GEN_PATH.search(p) or GEN_DIR.search(p) or SQL_GEN.search(text)): gen_files.append(p)
        elif k == 'sql':
            code, _ = mask_code('.sql', text); stmt, start = [], 0
            if len(code) != len(raw): code = (code + [''] * len(raw))[:len(raw)]
            norm = lambda x: x.split('.')[-1].strip('`"[]').lower()
            cols = lambda x: [y for y in (re.sub(r'[`"\[\]]', '', z).strip().split('(')[0].split(' ')[0].lower() for z in x.split(',')) if y]
            for i, c in enumerate(code):
                sha, pr = shas[i], who.get(shas[i]); where = f'{p}:{i + 1}'
                if re.search(r'\bREFERENCES\b|\bFOREIGN\s+KEY\b', c, re.I) and pr: rels[pr] += 1
                if pr and SQLSTMT.search(c): add(pr, 'SQL', 1, where)
                if pr and REPL_SQL.search(c) and not FIXTURE_PATH.search(p): add(pr, 'DB 복제·파티셔닝', 5, where, via={'SQL'})
                if not stmt or not ''.join(stmt).strip(): start = i
                stmt.append(c)
                if ';' not in c and i < len(code) - 1: continue
                st = ' '.join(stmt); stmt = []; sha0, pr0, w0 = shas[start], who.get(shas[start]), f'{p}:{start + 1}'
                m = re.search(r'CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?([\w.`"\[\]]+)\s*\((.*)', st, re.I)
                if m:
                    tb = table(m.group(1), sha0, w0)
                    for col in re.findall(r'(?:^|,)\s*[`"\[]?(\w+)[`"\]]?\s+[A-Za-z]', m.group(2)): newcols.add((sha0, tb, col.lower()))
                m = re.search(r'ALTER\s+TABLE\s+(?:IF\s+EXISTS\s+)?(?:ONLY\s+)?([\w.`"\[\]]+)(.*)', st, re.I)
                if m:
                    tb = norm(m.group(1))
                    for col in re.findall(r'\bADD\s+(?:COLUMN\s+)?(?:IF\s+NOT\s+EXISTS\s+)?[`"\[]?(\w+)', m.group(2), re.I):
                        if col.upper() not in ('CONSTRAINT', 'INDEX', 'KEY', 'PRIMARY', 'UNIQUE', 'FOREIGN', 'CHECK', 'FULLTEXT', 'SPATIAL', 'COLUMN'): newcols.add((sha0, tb, col.lower())); filecols.add((p, tb, col.lower()))
                    mi = re.search(r'\bADD\s+(?:INDEX|KEY)\s+\w*\s*\(([^)]*)\)', m.group(2), re.I)
                    if mi: idxs.append((pr0, sha0, tb, w0, False, cols(mi.group(1))))
                m = re.search(r'CREATE\s+(UNIQUE\s+)?INDEX\s+(?:CONCURRENTLY\s+)?(?:IF\s+NOT\s+EXISTS\s+)?[\w.`"\[\]]+\s+ON\s+(?:ONLY\s+)?([\w.`"\[\]]+)\s*(?:USING\s+\w+\s*)?\(([^;]*)', st, re.I)
                if m and not FIXTURE_PATH.search(p) and not re.search(r'CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?[\w.`"\[\]]*\b' + re.escape(norm(m.group(2))) + r'\b', text, re.I):
                    idxs.append((pr0, sha0, norm(m.group(2)), w0, bool(m.group(1)), cols(m.group(3).rsplit(')', 1)[0])))
        elif k == 'prisma':
            cur = None
            for i, t in enumerate(raw):
                sha, pr = shas[i], who.get(shas[i]); where = f'{p}:{i + 1}'; t = t.split('//')[0]
                m = re.match(r'\s*model\s+(\w+)\s*\{', t)
                if m: cur = table(m.group(1), sha, where)
                if '@relation(' in t and pr: rels[pr] += 1
                if '@@index' in t and cur: idxs.append((pr, sha, cur, where, False, None))
            for d, n in per.items():
                if n >= 3: add(d, 'Prisma', low_lv, f'{p} {n}줄')
        elif k == 'docker':
            for d, n in per.items(): (add(d, 'Docker', low_lv, f'{p} {n}줄') if n >= 3 else weak[(d, 'Docker')].append(p))
            for i, t in enumerate(raw):
                for rx, t0 in IMAGETOOL:
                    if rx.search(t) and who.get(shas[i]): add(who[shas[i]], t0, 1, f'{p}:{i + 1}', True)
                if who.get(shas[i]) and not prac and not is_test and not t.strip().startswith('#'):
                    if REPL_CFG.search(t): add(who[shas[i]], 'DB 복제·파티셔닝', 5, f'{p}:{i + 1}', via={'Docker'})
                    if ZERODOWN.search(mask_hash(t)) and per.get(who[shas[i]], 0) >= 10: add(who[shas[i]], '무중단 배포', 5, f'{p}:{i + 1}', via={'Docker'})
        elif k == 'workflow':
            for d, n in per.items():
                if n >= 3: add(d, 'GitHub Actions', low_lv, f'{p} {n}줄')
            st = {'build': [], 'deploy': [], 'publish': []}
            for i, t in enumerate(raw):
                c = mask_hash(t); a0 = who.get(shas[i]); w0 = f'{p}:{i + 1}'
                if (BUILD.search(c) if 'name:' not in c else (re.match(r'\s+-?\s*name:', c) and re.search(BUILD.pattern, c, re.I) and not re.search(r'push|image|docker|이미지|fail', c, re.I))): st['build'].append((a0, w0))
                if DEPLOY.search(c) and not re.search(r'k3d|\bkind\b|minikube|--dry-run|kubeconform|localhost|git@github\.com', c): st['deploy'].append((a0, w0))
                if PUBLISH.search(c): st['publish'].append((a0, w0))
                if (DEPLOY.search(c) or PUBLISH.search(c)) and shas[i] in order: deploy_orders.append(order[shas[i]])
                if a0 and re.search(r'aws-actions/|\baws\s+[a-z]|amazon-ecr|amazonaws\.com', c): add(a0, 'AWS', low_lv, w0)
                if a0 and not prac and ZERODOWN.search(c) and per.get(a0, 0) >= 10: add(a0, '무중단 배포', 5, w0, via={'GitHub Actions'})
            pages = re.compile(r'gh-pages|github-pages|deploy-pages')
            if all(pages.search(raw[int(w.split(':')[-1]) - 1]) for _, w in st['deploy']): st['deploy'] = []   # Pages 게시만 있으면 서비스 배포가 아님(문서·리포트)
            if (st['deploy'] or (st['build'] and st['publish'])) and not prac:
                total = sum(per.values())
                for d, n in per.items():
                    mine_out = [w for kk in ('deploy', 'publish') for a, w in st[kk] if a == d]
                    mine_any = mine_out or [w for a, w in st['build'] if a == d]
                    if n >= 5 and mine_any and (mine_out or n >= 0.3 * total):     # 배포·게시 줄을 직접 썼거나, workflow의 30% 이상을 썼을 때만
                        desc = '배포 ' + st['deploy'][0][1].split(':')[-1] + '줄' if st['deploy'] else '빌드 ' + st['build'][0][1].split(':')[-1] + '줄 + 이미지 게시 ' + st['publish'][0][1].split(':')[-1] + '줄'
                        add(d, 'CI/CD 구축', 3, f"{mine_any[0]} ({desc}이 있는 workflow에 내 줄 {n}줄)", via={'GitHub Actions'})
        elif k == 'yaml':
            if re.search(r'^apiVersion:', text, re.M) and re.search(r'^kind:\s*(Deployment|StatefulSet|Service|Ingress|HorizontalPodAutoscaler|CronJob)', text, re.M):
                for d, n in per.items():
                    if n >= 3: add(d, 'Kubernetes', low_lv, f'{p} {n}줄')
                    probe = next((i for i, t in enumerate(raw) if who.get(shas[i]) == d and K8S_PROBE.search(t)), None)
                    if n >= 10 and probe is not None and K8S_OPS.search(text) and not prac: add(d, 'Kubernetes 운영 설정', 4, f'{p}:{probe + 1}', via={'Kubernetes'})
                for i, t in enumerate(raw):
                    a0 = who.get(shas[i])
                    if a0 and not prac and ZERODOWN.search(mask_hash(t)) and per.get(a0, 0) >= 10: add(a0, '무중단 배포', 5, f'{p}:{i + 1}', via={'Kubernetes'})
                if not prac and re.search(r'^kind:\s*Deployment', text, re.M) and (re.search(r'canary', os.path.basename(p), re.I) or re.search(r'^\s*name:\s*\S*canary', text, re.M | re.I)):
                    for d, n in per.items():
                        if n >= 5: add(d, '무중단 배포', 5, f'{p} {n}줄 (canary Deployment)', via={'Kubernetes'})
        elif k in ('script', 'loadtest'):
            for i, t in enumerate(raw):
                a0 = who.get(shas[i])
                if k == 'script' and a0 and not prac and not is_test and ZERODOWN.search(mask_hash(t)) and per.get(a0, 0) >= 10: add(a0, '무중단 배포', 5, f'{p}:{i + 1}', via=set())
            if k == 'loadtest' and not prac:
                for d, n in per.items():
                    if n >= 10: add(d, '부하 테스트', 5, f'{p} {n}줄', via={'JMeter'})
        elif k in ('monitoring', 'iac', 'nginx', 'ai'):
            for d, n in per.items():
                if k == 'monitoring' and n >= 3 and not prac: add(d, '모니터링 설정', 3, f'{p} {n}줄')
                elif k == 'iac' and n >= 10 and not prac and any(who.get(s0) == d and re.match(r'\s*(resource|module)\s+"', t0) for s0, t0 in zip(shas, raw)):
                    add(d, 'IaC', 3, f'{p} {n}줄', via={'Terraform'} | ({'AWS'} if re.search(r'"aws_|provider\s+"aws"', text) else set()))
                    z = next((i for i, t in enumerate(raw) if who.get(shas[i]) == d and re.search(r'replication_group|read_replica|replicate_source_db|multi_az\s*=\s*true|num_cache_clusters|replicas_per_node_group', t)), None)
                    if z is not None: add(d, 'DB 복제·파티셔닝', 5, f'{p}:{z + 1}', via={'Terraform'})
                elif k == 'nginx':
                    if n >= 3: add(d, 'Nginx', low_lv, f'{p} {n}줄')
                    z = next((i for i, t in enumerate(raw) if who.get(shas[i]) == d and ZERODOWN.search(mask_hash(t))), None)
                    if z is not None and n >= 10 and not prac: add(d, '무중단 배포', 5, f'{p}:{z + 1}', via={'Nginx'})
                elif k == 'ai': add(d, 'AI 코딩 도구', 1, f'{p} {n}줄')
        elif k == 'appcfg':
            for i, t in enumerate(raw):
                pr = who.get(shas[i]); where = f'{p}:{i + 1}'
                if not pr or t.strip().startswith('#'): continue
                if is_test: continue
                for rx, db in b.DBURL:
                    if rx.search(t): add(pr, db, low_lv, where)
                if not prac and re.search(r'^\s*include:.*\bprometheus\b|management\.endpoints\.web\.exposure\.include\s*=.*prometheus|^\s*(otlp|zipkin)\s*:|management\.(otlp|zipkin|tracing)\.', t): add(pr, '모니터링 설정', 3, where)
                if not prac and (OAUTH_HOST.search(t) or (OAUTH_CFG.search(t) and ('oauth2' in t.lower() or re.search(r'oauth2\s*:', text) and 'registration' in text))): add(pr, 'OAuth 연동', 3, where)
    # ---- 레포 단위 판정
    for (d, l), n in lang.items():
        if n >= 5: add(d, l, 1, f'{l} 내 줄 {n}줄')
    for sha, pr in who.items():
        if pr and (pr, 'Git') not in ev: add(pr, 'Git', 1, f'커밋 {sha[:7]}')
    for d, n in P['ai'].items(): add(d, 'AI 코딩 도구', 1, f'AI가 쓰거나 함께 쓴 커밋 {n}개')
    if not practice_repo:
        for d, ts in tab_of.items():
            if len(ts) >= 3 and rels[d] >= 1: add(d, 'DB 설계', 3, f'테이블 {len(ts)}개, 관계 {rels[d]}개')
        for d, sha, tb, where, uniq, ic in idxs:
            if not d or uniq or tb not in tables or tables[tb][0] == sha or order.get(sha, 0) <= order.get(tables[tb][0], 0): continue
            # SQL: 이미 있던 컬럼에만 건 인덱스(같은 커밋에서 새로 만든 컬럼이면 설계이지 튜닝이 아님). 그 밖의 형식: 커밋 제목이 성능·인덱스를 말할 때만
            ok = (bool(ic) and not any((sha, tb, x) in newcols or (where.split(':')[0], tb, x) in filecols for x in ic)) if ic is not None else bool(TUNE_MSG.search(P['subj'].get(sha, '')))
            if ok: add(d, '쿼리 튜닝', 3, f'{where} (테이블 {tb}을 만든 뒤, 이미 있던 컬럼에 인덱스 추가)')
        for d, sha, cls_sha, where in nplus:
            if d and sha != cls_sha and order.get(sha, 0) > order.get(cls_sha, 0) and TUNE_MSG.search(P['subj'].get(sha, '')): add(d, '쿼리 튜닝', 3, f'{where} (성능 개선 커밋에서 조회 방식 변경)')
    if not practice_repo:
        cv['via'] = set()
        for d in set(prod) & set(cons):
            tl = set(cons[d][0][1]) | set(prod[d][0][1])
            add(d, '이벤트 기반 아키텍처', 4, f'{cons[d][0][0]} (받는 쪽) + {prod[d][0][0]} (보내는 쪽)', via=tl)
        for d, lst in outbox.items():
            if len(lst) >= 3: add(d, '분산 락·분산 트랜잭션', 5, f'{outbox_best.get(d, lst[0])} (outbox 관련 줄 {len(lst)}줄)', via=set())
        for d, lst in circuit.items():
            if len(lst) >= 3 and (d, '장애 격리') not in ev: add(d, '장애 격리', 4, f'{lst[0]} (서킷 브레이커 관련 줄 {len(lst)}줄)', via=set())
        for d, lst in bluegreen.items():
            if len(lst) >= 3 and (d, '무중단 배포') not in ev: add(d, '무중단 배포', 5, f'{lst[0]} (blue-green 전환 코드 {len(lst)}줄)', via=set())
        for d, lst in saga.items():
            if len(lst) >= 3: add(d, '분산 락·분산 트랜잭션', 5, f'{lst[0]} (saga 관련 줄 {len(lst)}줄)', via=set())
        for d in set(llm) & set(vec): add(d, 'RAG 구축', 3, f'{vec[d][0]} (벡터 검색) + {llm[d][0]} (LLM 호출)', via=set())
        if len(svc_roots) >= 2:
            for d, cnt in svc_lines.items():
                mine = [s0 for s0, n0 in cnt.items() if n0 >= 20]
                if len(mine) >= 2 and d in svc_comm: add(d, 'MSA·서비스 분리', 4, f'{svc_comm[d]} (서비스 {len(svc_roots)}개 중 {len(mine)}개에 내 코드, 서비스 간 통신 코드)', via=set())
        if layered:
            need = {'port', 'adapter'} if {'port', 'adapter'} <= layer_kinds else {'domain', 'application', 'infrastructure'}
            for d, kf in layer_files.items():
                mine = {kk: fs for kk, fs in kf.items() if kk in need}
                nfiles = len({f for fs in mine.values() for f in fs})
                if len(mine) >= 2 and nfiles >= 6: add(d, '아키텍처 패턴 적용', 4, f'{sorted(mine.items())[0][1][0]} ({"·".join(sorted(mine))} 계층에 내 파일 {nfiles}개)', via=set())
        if deploy_orders:
            start = min(deploy_orders); hot = collections.defaultdict(list)
            for sha, pr in who.items():
                sj = P['subj'].get(sha, '')
                if pr and order.get(sha, -1) > start and OPS_MSG.search(sj) and not re.match(r'\s*\[?(docs?|test|chore\(docs?\)|문서)\b', sj, re.I): hot[pr].append(sha)
            for d, lst in hot.items():
                if len(lst) >= 2:
                    lst.sort(key=lambda x: order[x])
                    add(d, '운영 대응 이력', 4, f'커밋 {lst[0][:7]} "{P["subj"][lst[0]][:50]}" 외 {len(lst) - 1}개 (배포 설정 이후)', via=set())
    res = {}
    for (d, key), lst in ev.items():
        lv = max(x[0] for x in lst); best = [x for x in lst if x[0] == lv]; pick = next((x for x in best if not x[2] and x[3]), next((x for x in best if not x[2]), best[0]))
        res[(d, key)] = dict(lv=lv, where=pick[1], n=len(lst), kind='activity' if key in ACT_KEYS else 'tool')
    for (d, t), lst in lift.items():          # 도구의 LV = 그 도구로 한 활동의 최고 LV
        lv, key, where = max(lst, key=lambda x: x[0])
        r0 = res.get((d, t))
        if r0 is None: res[(d, t)] = dict(lv=lv, where=where, n=len(lst), kind='tool', lifted_by=key)
        elif lv > r0['lv']: r0.update(own_lv=r0['lv'], lv=lv, lifted_by=key, lifted_where=where)
    weak = {k: v[0] for k, v in weak.items() if k not in res and k[0]}
    return res, weak, dict(people=P['humans'], merged=P['merged'], ai=dict(P['ai']), ai_unassigned=P['ai_unassigned'], generated=gen_files, practice=practice_repo)


if __name__ == '__main__':
    r, w, meta = analyze(sys.argv[1])
    for (d, k), v in sorted(r.items(), key=lambda x: (x[0][0], x[1]['lv'], x[0][1])): print(f"LV{v['lv']} {d:16} {k:16} {v['where']}")
    print(meta)
