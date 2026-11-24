#!/usr/bin/env python3
"""역량 키 목록: 추출기(GitHub 근거)와 매칭기(공고 줄)가 함께 쓰는 이름.
- TOOL_ALIASES: 공고 글에 나오는 표기 -> 추출기가 쓰는 도구 이름
- ACTIVITIES: 활동 키, 그 활동이 GitHub에서 인정되는 LV, 공고 글에서 찾는 표현
- SCALE: 규모·운영을 요구하는 표현(코드로는 확인 못 함)
"""
import re

# (공고 표기 정규식, 도구 이름). 위에서부터 순서대로 전부 적용. 영문은 대소문자 무시
_T = [
 (r'spring\s*boot|스프링\s*부트|springboot|spring|스프링', 'Spring'), (r'(?<![a-z])java(?!\s*script)(?![a-z])|자바(?!스크립트)', 'Java'), (r'kotlin|코틀린', 'Kotlin'),
 (r'python|파이썬', 'Python'), (r'typescript|타입스크립트|(?<![a-z])ts(?![a-z])', 'TypeScript'), (r'javascript|자바스크립트|(?<![a-z.])js(?![a-z])', 'JavaScript'),
 (r'node\.?js|노드(?:js)?(?![가-힣])|(?<![a-z])node(?![a-z])', 'Node.js'), (r'nest\.?js|네스트', 'NestJS'), (r'(?<![a-z])express(\.js)?(?![a-z])', 'Express'), (r'django|장고', 'Django'), (r'fastapi', 'FastAPI'), (r'flask', 'Flask'),
 (r'react\s*native|리액트\s*네이티브', 'React Native'), (r'react(?!\s*native)|리액트(?!\s*네이티브)', 'React'), (r'next\.?js', 'Next.js'), (r'vue(\.js)?|뷰js', 'Vue'), (r'angular', 'Angular'),
 (r'jpa|hibernate', 'JPA'), (r'querydsl', 'QueryDSL'), (r'mybatis|마이바티스', 'MyBatis'), (r'spring\s*security|스프링\s*시큐리티', 'Spring Security'), (r'spring\s*batch|스프링\s*배치', 'Spring Batch'),
 (r'spring\s*cloud', 'Spring Cloud'), (r'mysql', 'MySQL'), (r'mariadb', 'MariaDB'), (r'postgres(ql)?|포스트그레', 'PostgreSQL'), (r'oracle|오라클', 'Oracle'), (r'ms-?sql|sql\s*server', 'SQL Server'),
 (r'mongo\s*db|몽고', 'MongoDB'), (r'redis|레디스', 'Redis'), (r'elastic\s*search|엘라스틱\s*서치|opensearch|(?<![a-z])elk(?![a-z])', 'Elasticsearch'), (r'kafka|카프카', 'Kafka'), (r'rabbit\s*mq', 'RabbitMQ'),
 (r'(?<![a-z])sqs(?![a-z])', 'AWS SQS'), (r'docker|도커', 'Docker'), (r'kubernetes|k8s|쿠버네티스', 'Kubernetes'), (r'github\s*actions?', 'GitHub Actions'), (r'jenkins|젠킨스', 'Jenkins'),
 (r'argo\s*cd', 'ArgoCD'), (r'terraform|테라폼', 'Terraform'), (r'ansible', 'Ansible'), (r'nginx', 'Nginx'), (r'(?<![a-z])aws(?![a-z])|아마존\s*웹', 'AWS'), (r'(?<![a-z])gcp(?![a-z])|google\s*cloud', 'Google Cloud'),
 (r'azure|애저', 'Azure'), (r'linux|리눅스', 'Linux'), (r'(?<![a-z])git(?!hub|lab)(?![a-z])|깃(?!허브|랩)|형상\s*관리|버전\s*관리', 'Git'), (r'github(?!\s*(actions?|copilot))|깃허브', 'GitHub'),
 (r'graphql', 'GraphQL'), (r'grpc', 'gRPC'), (r'websocket|웹\s*소켓|socket\.io', 'WebSocket'), (r'(?<![a-z])jwt(?![a-z])', 'JWT'), (r'prometheus|프로메테우스', 'Prometheus'), (r'grafana|그라파나', 'Grafana'),
 (r'datadog', 'Datadog'), (r'sentry', 'Sentry'), (r'swagger|open\s*api', 'Swagger/OpenAPI'), (r'junit', 'JUnit'), (r'(?<![a-z])jsp(?![a-z])|servlet|서블릿', 'Servlet'), (r'pytest', 'pytest'), (r'(?<![a-z])jest(?![a-z])', 'Jest'),
 (r'prisma', 'Prisma'), (r'typeorm', 'TypeORM'), (r'sqlalchemy', 'SQLAlchemy'), (r'langchain|랭체인', 'LangChain'), (r'langgraph', 'LangGraph'), (r'pytorch|파이토치', 'PyTorch'), (r'tensorflow|텐서플로', 'TensorFlow'),
 (r'openai|gpt[\s-]*(api|\d)', 'OpenAI API'), (r'(?<![a-z])mcp(?![a-z])', 'MCP SDK'), (r'stripe', 'Stripe'), (r'(?<![a-z0-9])(s3|ec2|ecs|eks|rds)(?![a-z0-9])', 'AWS'), (r'anthropic|claude\s*api', 'Anthropic API'), (r'celery', 'Celery'), (r'airflow', 'Airflow'), (r'spark', 'Spark'), (r'hadoop', 'Hadoop'), (r'flink', 'Flink'),
 (r'(?<![a-z])go(lang)?(?![a-z])(?=\s*(언어|,|/|·|\)|개발|기반|$))|golang', 'Go'), (r'c\+\+', 'C++'), (r'c#|\.net|닷넷', 'C#/.NET'), (r'(?<![a-z])php(?![a-z])', 'PHP'), (r'flutter|플러터', 'Flutter'),
 (r'swift', 'Swift'), (r'android|안드로이드', 'Android'), (r'(?<![a-z])ios(?![a-z])', 'iOS'), (r'tailwind', 'Tailwind CSS'), (r'html', 'HTML'), (r'(?<![a-z])css(?![a-z])', 'CSS'),
 (r'(?<![a-z])sql(?![a-z])', 'SQL'), (r'cursor|copilot|chatgpt|claude(?!\s*api)|codex|ai\s*(코딩|개발)\s*(도구|툴|어시스턴트|에이전트)|ai\s*(도구|툴)|코딩\s*(에이전트|어시스턴트)|바이브\s*코딩|vibe\s*coding', 'AI 코딩 도구'), (r'vector\s*db|벡터\s*(db|데이터베이스)|pinecone|milvus|qdrant|chroma|weaviate|pgvector', '벡터 DB'),
 (r'supabase', 'Supabase'), (r'firebase|파이어베이스', 'Firebase'), (r'rest\s*assured', 'REST Assured'), (r'opentelemetry', 'OpenTelemetry'), (r'jira|지라', 'Jira'), (r'toss\s*payments|토스\s*페이먼츠', 'Toss Payments'),
]
TOOL_ALIASES = [(re.compile(rx, re.I), name) for rx, name in _T]

# 활동 키: (이름, GitHub에서 인정되는 LV, 공고 글 표현). 추출기의 판정 이름과 같아야 함
_A = [
 ('API 개발', 2, r'(rest(ful)?\s*)?api.{0,6}(설계|개발|구현|서버)|백엔드|back-?end|서버\s*(개발|api|사이드)|server[\s-]*side|웹\s*(서비스|애플리케이션|어플리케이션|서버)\s*(개발|구축)'),
 ('외부 API 연동', 2, r'(외부|서드\s*파티|3rd|third).{0,12}(api|서비스|시스템).{0,8}연동|api\s*연동|연동\s*개발|오픈\s*api'),
 ('테스트 코드', 2, r'테스트\s*코드|단위\s*테스트|통합\s*테스트|unit\s*test|(?<![a-z])tdd(?![a-z])|테스트\s*(자동화|주도)'),
 ('SQL', 1, r'sql\s*(작성|활용|사용|쿼리)|쿼리\s*작성'),
 ('인증·인가 구현', 2, r'인증|인가|로그인|권한\s*(관리|처리|제어)|authentication|authorization|(?<![a-z])rbac(?![a-z])'),
 ('LLM 기능 개발', 2, r'(?<![a-z])llm(?![a-z])|생성형|gen\s*ai|프롬프트|prompt|ai\s*에이전트|(?<![a-z])agent(?![a-z])|챗봇|chatbot|ai\s*(서비스|기능|모델|api)\s*(개발|연동|적용|활용)'),
 ('RAG 구축', 3, r'(?<![a-z])rag(?![a-z])|검색\s*증강|임베딩|embedding'),
 ('DB 설계', 3, r'(db|데이터베이스|database|스키마|schema|테이블)\s*(설계|모델링)|데이터\s*모델링|erd'),
 ('쿼리 튜닝', 3, r'(쿼리|query|sql|db|데이터베이스).{0,10}(튜닝|최적화|성능|개선)|인덱스|느린\s*쿼리|slow\s*query|실행\s*계획'),
 ('캐시 도입', 3, r'캐시|캐싱|cache|caching'),
 ('메시지 큐', 3, r'메시지\s*(큐|브로커|시스템)|message\s*(queue|broker)|(?<![a-z])mq(?![a-z])|비동기\s*메시징|이벤트\s*(스트리밍|스트림)|작업\s*큐|워커\s*큐'),
 ('OAuth 연동', 3, r'oauth|소셜\s*로그인|(?<![a-z])sso(?![a-z])|oidc|간편\s*로그인'),
 ('결제 연동', 3, r'결제\s*(연동|시스템|모듈|서비스|api|\()|웹\s*결제|(?<![a-z])pg(?![a-z])\s*(연동|사)|payment'),
 ('모니터링 설정', 3, r'모니터링|monitoring|observability|관측|로그\s*(수집|분석)|apm'),
 ('CI/CD 구축', 3, r'ci\s*/?\s*cd|배포\s*(자동화|파이프라인)|빌드\s*(자동화|파이프라인)|devops|데브옵스'),
 ('IaC', 3, r'(?<![a-z])iac(?![a-z])|infrastructure\s*as\s*code|인프라\s*(코드|자동화)'),
 ('배치 처리', 3, r'배치|batch|스케줄러|scheduler'),
 ('검색 기능 구축', 3, r'검색\s*(엔진|시스템|기능|서비스)'),
 ('동시성 제어', 4, r'동시성|concurrency|정합성|트랜잭션\s*(관리|처리|설계)|락\b|lock'),
 ('MSA·서비스 분리', 4, r'(?<![a-z])msa(?![a-z])|마이크로\s*서비스|micro\s*service|서비스\s*분리'),
 ('이벤트 기반 아키텍처', 4, r'이벤트\s*(기반|드리븐)|event[\s-]*driven|(?<![a-z])eda(?![a-z])'),
 ('Kubernetes 운영 설정', 4, r'(kubernetes|k8s|쿠버네티스).{0,20}(운영|구축|관리)|컨테이너\s*오케스트레이션'),
 ('아키텍처 패턴 적용', 4, r'헥사고날|hexagonal|클린\s*아키텍처|clean\s*architecture|(?<![a-z])ddd(?![a-z])|도메인\s*주도'),
 ('장애 격리', 4, r'서킷\s*브레이커|circuit\s*breaker|장애\s*(격리|전파)|resilien'),
 ('운영 대응 이력', 4, r'장애\s*(대응|처리|분석|해결)|트러블\s*슈팅|trouble\s*shooting|이슈\s*(분석|대응)'),
 ('부하 테스트', 5, r'부하\s*테스트|성능\s*테스트|load\s*test|stress\s*test|ngrinder|jmeter|(?<![a-z])k6(?![a-z])|locust|gatling'),
 ('무중단 배포', 5, r'무중단|zero[\s-]*downtime|blue[\s/-]*green|블루\s*그린|canary|카나리|롤링\s*(배포|업데이트)|rolling\s*update'),
 ('분산 락·분산 트랜잭션', 5, r'분산\s*(락|트랜잭션|환경|시스템|처리)|distributed|saga|outbox|아웃박스'),
 ('DB 복제·파티셔닝', 5, r'샤딩|sharding|파티셔닝|partitioning|레플리카|replica|이중화|복제|failover|장애\s*전환|고가용성|(?<![a-z])ha(?![a-z])\s*구성'),
]
ACTIVITIES = [(name, lv, re.compile(rx, re.I)) for name, lv, rx in _A]
ACTIVITY_LV = {name: lv for name, lv, _ in _A}

# 규모·운영 표현: GitHub 코드로는 확인할 수 없는 요구
SCALE = re.compile(r'대규모|대용량|대형|대량|트래픽|고가용|(\d+\s*만|\d{2,}\s*k|million).{0,6}(명|건|사용자|유저|tps|rps|트래픽)|(?<![a-z])tps(?![a-z])|24\s*/?\s*(7|365)|실\s*서비스|상용\s*(서비스|화)|프로덕션|production|운영\s*(중|환경|경험)|서비스\s*운영|라이브\s*서비스', re.I)


def tag_line(text):
    """공고 줄 원문 -> dict(tools=[...], activities=[...], scale=bool)"""
    tools, acts = [], []
    for rx, name in TOOL_ALIASES:
        if rx.search(text) and name not in tools: tools.append(name)
    for name, lv, rx in ACTIVITIES:
        if rx.search(text): acts.append(name)
    return dict(tools=tools, activities=acts, scale=bool(SCALE.search(text)))


# 공고가 묶음 이름으로 적은 것: 묶음에 속한 도구 중 하나라도 있으면 그 LV로 봄
GROUPS = {
 'RDB': ['MySQL', 'PostgreSQL', 'MariaDB', 'Oracle', 'SQL Server', 'JPA', 'MyBatis'],
 'NoSQL': ['MongoDB', 'Redis', 'Elasticsearch'],
 '클라우드': ['AWS', 'Google Cloud', 'Azure'],
 '컨테이너': ['Docker', 'Kubernetes'],
 'ORM': ['JPA', 'Prisma', 'TypeORM', 'SQLAlchemy', 'Sequelize', 'Drizzle', 'Django', 'Exposed'],
 'LLM API': ['OpenAI API', 'Anthropic API', 'Gemini API', 'Groq', 'Ollama', 'LangChain', 'LangChain4j', 'LangGraph', 'LlamaIndex', 'Spring AI'],
 '테스트 도구': ['JUnit', 'pytest', 'Jest', 'Vitest', 'Mockito', 'Kotest'],
}
_G = [(r'(?<![a-z])rdb(ms)?(?![a-z])|관계형\s*(db|데이터베이스)', 'RDB'), (r'nosql', 'NoSQL'), (r'클라우드|cloud', '클라우드'), (r'컨테이너|container', '컨테이너'), (r'(?<![a-z])orm(?![a-z])', 'ORM')]
GROUP_ALIASES = [(re.compile(rx, re.I), name) for rx, name in _G]

# 추출기의 도구 이름 -> 함께 인정하는 이름(같은 LV)
IMPLIES = {
 'AWS SDK': ['AWS'], 'AWS SQS': ['AWS'], 'AWS CDK': ['AWS'], 'Google Cloud SDK': ['Google Cloud'], 'Google Pub/Sub': ['Google Cloud'], 'Azure SDK': ['Azure'],
 'Spring Security': ['Spring'], 'Spring Data': ['Spring', 'JPA'], 'Spring JDBC': ['Spring'], 'Spring AOP': ['Spring'], 'Spring Batch': ['Spring'], 'Spring Cloud': ['Spring'], 'Spring Cloud Gateway': ['Spring', 'Spring Cloud'],
 'Eureka': ['Spring', 'Spring Cloud'], 'OpenFeign': ['Spring', 'Spring Cloud'], 'Spring AI': ['Spring'], 'Spring Mail': ['Spring'], 'Spring Retry': ['Spring'], 'Spring Cloud Stream': ['Spring'], 'QueryDSL': ['JPA'],
 'Express': ['Node.js'], 'NestJS': ['Node.js'], 'Fastify': ['Node.js'], 'Koa': ['Node.js'], 'Hono': ['Node.js'], 'NestJS Microservices': ['NestJS', 'Node.js'], 'Next.js': ['React'],
 'Django REST framework': ['Django'], 'OpenSearch': ['Elasticsearch'], 'pgvector': ['벡터 DB', 'PostgreSQL'], 'Terraform': [], 'Pulumi': [], 'TypeScript': ['JavaScript'],
 'Kotest': [], 'Toss Payments': [], 'Micrometer': ['Prometheus'],
}


def tag_line(text):
    """공고 줄 원문 -> dict(tools=[...], activities=[...], scale=bool). 묶음 이름은 tools에 그대로 들어감"""
    tools, acts = [], []
    for rx, name in TOOL_ALIASES + GROUP_ALIASES:
        if rx.search(text) and name not in tools: tools.append(name)
    for name, lv, rx in ACTIVITIES:
        if rx.search(text): acts.append(name)
    return dict(tools=tools, activities=acts, scale=bool(SCALE.search(text)))
