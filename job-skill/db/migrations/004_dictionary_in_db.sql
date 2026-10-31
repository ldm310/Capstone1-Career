-- 2026-10-31 사전의 원본을 DB로(사용자 결정). 팀원이 RDS 에서 SQL 로 사전을 고치고, 다음 추출부터 쓰인다.
--   - 스킬이 아닌 낱말 표(exclude_word): capabilities.json 의 exclude 에만 있던 것
--   - 기술의 대표 능력(tech_capability.is_primary): JSON 에서 기술의 첫 번째 능력
--   - 사전 변경 기록(dictionary_change) + 사전 표 4개의 트리거, TRUNCATE 막음
--   - dictionary_version: '동기화 기록' → '추출에 쓰인 사전 판(지문)과 처음 쓴 시각'
-- 이미 사전이 있는 DB 만 데이터를 채운다(빈 DB 는 db/seed_dictionary.sql 이 채움). 여러 번 돌려도 안전.
BEGIN;
SET LOCAL search_path TO public;

ALTER TABLE tech_capability ADD COLUMN IF NOT EXISTS is_primary boolean NOT NULL DEFAULT false;
COMMENT ON COLUMN tech_capability.is_primary IS '대표 능력 (기술마다 최대 하나, LLM 이 ''기타: RDS''처럼 적으면 이 능력으로 잇는다. 없으면 능력ID 가 가장 작은 것)';
CREATE UNIQUE INDEX IF NOT EXISTS tech_capability_one_primary ON tech_capability (tech_id) WHERE is_primary;

CREATE TABLE IF NOT EXISTS exclude_word (
    id    bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    word  text NOT NULL,
    kind  text NOT NULL CHECK (kind IN ('LLM 모델', '기술 아님', '일반 낱말')),
    UNIQUE (kind, word)
);
COMMENT ON TABLE  exclude_word      IS '스킬이 아닌 낱말 (대소문자·공백 무시)';
COMMENT ON COLUMN exclude_word.id   IS '낱말ID';
COMMENT ON COLUMN exclude_word.word IS '낱말 (예: Claude, CTO, AI)';
COMMENT ON COLUMN exclude_word.kind IS '종류 (LLM 모델 = 이름 안에 들어 있으면 뺌 / 기술 아님 = 직무명 등 / 일반 낱말 = 낱말만 빼고 요건은 남김)';

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.columns
               WHERE table_schema = 'public' AND table_name = 'dictionary_version' AND column_name = 'synced_at') THEN
        ALTER TABLE dictionary_version RENAME COLUMN synced_at TO first_used_at;
    END IF;
END $$;
COMMENT ON TABLE  dictionary_version               IS '사전 판 (추출에 쓰인 사전 지문과 처음 쓴 시각)';
COMMENT ON COLUMN dictionary_version.version       IS '사전 판 (사전 내용 지문 12자리, 2026-10-31 전에는 0.1.1 같은 번호)';
COMMENT ON COLUMN dictionary_version.first_used_at IS '처음 쓴 시각';
COMMENT ON COLUMN extraction_run.dict_version      IS '사전 판 (사전 내용 지문, 2026-10-31 전 결과는 0.1.1 같은 번호)';

CREATE TABLE IF NOT EXISTS dictionary_change (
    id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    changed_at  timestamptz NOT NULL DEFAULT now(),
    changed_by  text        NOT NULL,
    table_name  text        NOT NULL CHECK (table_name IN ('capability', 'tech', 'tech_capability', 'exclude_word')),
    action      text        NOT NULL CHECK (action IN ('넣기', '고치기', '지우기')),
    old_row     jsonb,
    new_row     jsonb
);
COMMENT ON TABLE  dictionary_change            IS '사전 변경 기록';
COMMENT ON COLUMN dictionary_change.id         IS '기록ID';
COMMENT ON COLUMN dictionary_change.changed_at IS '바꾼 시각';
COMMENT ON COLUMN dictionary_change.changed_by IS '바꾼 사람 (DB 접속 계정, 예: dongmin / 파이프라인은 career)';
COMMENT ON COLUMN dictionary_change.table_name IS '표';
COMMENT ON COLUMN dictionary_change.action     IS '동작 (넣기/고치기/지우기)';
COMMENT ON COLUMN dictionary_change.old_row    IS '예전 값 (줄 전체, 넣기면 비움)';
COMMENT ON COLUMN dictionary_change.new_row    IS '새 값 (줄 전체, 지우기면 비움)';
CREATE INDEX IF NOT EXISTS dictionary_change_changed_at_idx ON dictionary_change (changed_at);

-- 함수·트리거 설명은 db/schema.sql 참고(같은 내용)
CREATE OR REPLACE FUNCTION log_dictionary_change() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $f$
BEGIN
    IF TG_OP = 'UPDATE' AND to_jsonb(OLD) = to_jsonb(NEW) THEN
        RETURN NULL;   -- 값이 그대로인 고치기는 남기지 않는다
    END IF;
    INSERT INTO public.dictionary_change (changed_by, table_name, action, old_row, new_row)
    VALUES (session_user, TG_TABLE_NAME,
            CASE TG_OP WHEN 'INSERT' THEN '넣기' WHEN 'UPDATE' THEN '고치기' ELSE '지우기' END,
            CASE WHEN TG_OP <> 'INSERT' THEN to_jsonb(OLD) END,
            CASE WHEN TG_OP <> 'DELETE' THEN to_jsonb(NEW) END);
    RETURN NULL;
END $f$;

CREATE OR REPLACE FUNCTION block_dictionary_truncate() RETURNS trigger
LANGUAGE plpgsql SET search_path = pg_catalog, pg_temp AS $f$
BEGIN
    RAISE EXCEPTION '사전 표는 TRUNCATE 할 수 없습니다(변경 기록이 남지 않음). DELETE 를 쓰세요.';
END $f$;

CREATE OR REPLACE TRIGGER dictionary_change_log AFTER INSERT OR UPDATE OR DELETE ON capability
    FOR EACH ROW EXECUTE FUNCTION log_dictionary_change();
CREATE OR REPLACE TRIGGER dictionary_change_log AFTER INSERT OR UPDATE OR DELETE ON tech
    FOR EACH ROW EXECUTE FUNCTION log_dictionary_change();
CREATE OR REPLACE TRIGGER dictionary_change_log AFTER INSERT OR UPDATE OR DELETE ON tech_capability
    FOR EACH ROW EXECUTE FUNCTION log_dictionary_change();
CREATE OR REPLACE TRIGGER dictionary_change_log AFTER INSERT OR UPDATE OR DELETE ON exclude_word
    FOR EACH ROW EXECUTE FUNCTION log_dictionary_change();
CREATE OR REPLACE TRIGGER dictionary_no_truncate BEFORE TRUNCATE ON capability
    FOR EACH STATEMENT EXECUTE FUNCTION block_dictionary_truncate();
CREATE OR REPLACE TRIGGER dictionary_no_truncate BEFORE TRUNCATE ON tech
    FOR EACH STATEMENT EXECUTE FUNCTION block_dictionary_truncate();
CREATE OR REPLACE TRIGGER dictionary_no_truncate BEFORE TRUNCATE ON tech_capability
    FOR EACH STATEMENT EXECUTE FUNCTION block_dictionary_truncate();
CREATE OR REPLACE TRIGGER dictionary_no_truncate BEFORE TRUNCATE ON exclude_word
    FOR EACH STATEMENT EXECUTE FUNCTION block_dictionary_truncate();

-- 데이터: 이미 사전이 있는 DB(sync-dict 로 채운 RDS·로컬)만. 값은 2026-10-31 capabilities.json(0.1.1)에서 뽑았다.
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM capability) THEN
        IF NOT EXISTS (SELECT 1 FROM exclude_word) THEN
            INSERT INTO exclude_word (kind, word) VALUES
            ('LLM 모델', 'claude'),
            ('LLM 모델', '클로드'),
            ('LLM 모델', 'gemini'),
            ('LLM 모델', '제미나이'),
            ('LLM 모델', 'chatgpt'),
            ('LLM 모델', '챗gpt'),
            ('LLM 모델', 'gpt'),
            ('LLM 모델', 'llama'),
            ('LLM 모델', 'mistral'),
            ('LLM 모델', 'grok'),
            ('LLM 모델', 'deepseek'),
            ('LLM 모델', 'qwen'),
            ('LLM 모델', 'hyperclova'),
            ('LLM 모델', '하이퍼클로바'),
            ('LLM 모델', 'exaone'),
            ('LLM 모델', '엑사원'),
            ('기술 아님', 'AI Engineer'),
            ('기술 아님', 'Data Engineer'),
            ('기술 아님', 'Data Scientist'),
            ('기술 아님', 'DBA'),
            ('기술 아님', 'CTO'),
            ('기술 아님', 'BPO'),
            ('기술 아님', 'MRO'),
            ('기술 아님', 'ICT'),
            ('기술 아님', 'IT'),
            ('기술 아님', 'B2B'),
            ('기술 아님', 'RFP'),
            ('기술 아님', 'PRD'),
            ('기술 아님', 'PoC'),
            ('기술 아님', 'SI'),
            ('기술 아님', 'AX'),
            ('기술 아님', 'LMS'),
            ('기술 아님', 'MALL'),
            ('기술 아님', 'EPMS 3.0'),
            ('기술 아님', 'FBW'),
            ('기술 아님', 'LEVER Xpert'),
            ('기술 아님', 'Push-To-Talk'),
            ('기술 아님', '5G'),
            ('기술 아님', 'Silver'),
            ('기술 아님', 'Gold'),
            ('기술 아님', 'DMP'),
            ('기술 아님', 'AICC'),
            ('기술 아님', 'UI.UX'),
            ('기술 아님', 'AI Native'),
            ('기술 아님', 'Core API'),
            ('기술 아님', 'GPU'),
            ('기술 아님', '3D'),
            ('기술 아님', '모션'),
            ('기술 아님', 'DL'),
            ('기술 아님', 'DM'),
            ('일반 낱말', 'AI'),
            ('일반 낱말', 'ML'),
            ('일반 낱말', 'Data'),
            ('일반 낱말', 'Database'),
            ('일반 낱말', '튜닝'),
            ('일반 낱말', '성능 튜닝'),
            ('일반 낱말', '최적화'),
            ('일반 낱말', 'Lifecycle'),
            ('일반 낱말', '파이프라인'),
            ('일반 낱말', 'Embedding'),
            ('일반 낱말', 'AP');
        END IF;
        IF NOT EXISTS (SELECT 1 FROM tech_capability WHERE is_primary) THEN
            UPDATE tech_capability tc SET is_primary = true
            FROM (VALUES
                    ('Java', '프로그래밍 언어'),
                    ('Python', '프로그래밍 언어'),
                    ('JavaScript', '프로그래밍 언어'),
                    ('TypeScript', '프로그래밍 언어'),
                    ('C', '프로그래밍 언어'),
                    ('C++', '프로그래밍 언어'),
                    ('C#', '프로그래밍 언어'),
                    ('Go', '프로그래밍 언어'),
                    ('Kotlin', '프로그래밍 언어'),
                    ('PHP', '프로그래밍 언어'),
                    ('Rust', '프로그래밍 언어'),
                    ('Swift', '프로그래밍 언어'),
                    ('SQL', 'SQL'),
                    ('Spring', '백엔드 프레임워크'),
                    ('Spring Boot', '백엔드 프레임워크'),
                    ('Spring Framework', '백엔드 프레임워크'),
                    ('Spring Security', '보안·인증'),
                    ('Node.js', '백엔드 프레임워크'),
                    ('NestJS', '백엔드 프레임워크'),
                    ('FastAPI', '백엔드 프레임워크'),
                    ('Django', '백엔드 프레임워크'),
                    ('Flask', '백엔드 프레임워크'),
                    ('Express', '백엔드 프레임워크'),
                    ('전자정부프레임워크', '백엔드 프레임워크'),
                    ('JPA', 'ORM·데이터 접근'),
                    ('MyBatis', 'ORM·데이터 접근'),
                    ('QueryDSL', 'ORM·데이터 접근'),
                    ('Hibernate', 'ORM·데이터 접근'),
                    ('REST API', 'API 설계'),
                    ('GraphQL', 'API 설계'),
                    ('gRPC', 'API 설계'),
                    ('HashiCorp Vault', '보안·인증'),
                    ('Boundary', '보안·인증'),
                    ('React', '프론트엔드 프레임워크'),
                    ('Next.js', '프론트엔드 프레임워크'),
                    ('Vue', '프론트엔드 프레임워크'),
                    ('Angular', '프론트엔드 프레임워크'),
                    ('Tanstack Query', '프론트엔드 프레임워크'),
                    ('Jest', '테스트 자동화'),
                    ('Storybook', '테스트 자동화'),
                    ('Webpack', '빌드·모노레포'),
                    ('React Native', '모바일 앱'),
                    ('Flutter', '모바일 앱'),
                    ('FCM', '모바일 앱'),
                    ('MySQL', '관계형 DB'),
                    ('PostgreSQL', '관계형 DB'),
                    ('MariaDB', '관계형 DB'),
                    ('Oracle', '관계형 DB'),
                    ('MS-SQL', '관계형 DB'),
                    ('Tibero', '관계형 DB'),
                    ('SQLite', '관계형 DB'),
                    ('MongoDB', 'NoSQL DB'),
                    ('Redis', 'NoSQL DB'),
                    ('Cassandra', 'NoSQL DB'),
                    ('Elasticsearch', 'NoSQL DB'),
                    ('Apache Airflow', '데이터 파이프라인'),
                    ('Spark', '데이터 파이프라인'),
                    ('Databricks', '데이터 플랫폼'),
                    ('Unity Catalog', '데이터 플랫폼'),
                    ('SQL Warehouse', '데이터 플랫폼'),
                    ('Lakeview', '데이터 플랫폼'),
                    ('Iceberg', '데이터 플랫폼'),
                    ('Snowflake', '데이터 플랫폼'),
                    ('BigQuery', '데이터 플랫폼'),
                    ('Power BI', 'BI·시각화'),
                    ('Tableau', 'BI·시각화'),
                    ('Superset', 'BI·시각화'),
                    ('FHIR', '의료정보 표준'),
                    ('SNOMED CT', '의료정보 표준'),
                    ('ATC', '의료정보 표준'),
                    ('EDI', '의료정보 표준'),
                    ('KR CDI', '의료정보 표준'),
                    ('KR Core', '의료정보 표준'),
                    ('EMR', '의료정보 표준'),
                    ('Kafka', '메시지 브로커'),
                    ('RabbitMQ', '메시지 브로커'),
                    ('NATS', '메시지 브로커'),
                    ('AWS', '클라우드'),
                    ('GCP', '클라우드'),
                    ('Azure', '클라우드'),
                    ('NCP', '클라우드'),
                    ('Cloudflare', '클라우드'),
                    ('EC2', '클라우드'),
                    ('S3', '클라우드'),
                    ('Lambda', '클라우드'),
                    ('ECS', '클라우드'),
                    ('EKS', '클라우드'),
                    ('RDS', '클라우드'),
                    ('Aurora', '클라우드'),
                    ('DynamoDB', '클라우드'),
                    ('ElastiCache', '클라우드'),
                    ('SQS', '클라우드'),
                    ('API Gateway', '클라우드'),
                    ('Athena', '클라우드'),
                    ('DMS', '클라우드'),
                    ('CloudFormation', 'IaC'),
                    ('Docker', '컨테이너'),
                    ('Kubernetes', '컨테이너 오케스트레이션'),
                    ('Serverless Framework', '서버리스·호스팅'),
                    ('Vercel', '서버리스·호스팅'),
                    ('Supabase', '서버리스·호스팅'),
                    ('Firebase', '서버리스·호스팅'),
                    ('Terraform', 'IaC'),
                    ('Ansible', 'IaC'),
                    ('Jenkins', 'CI/CD'),
                    ('GitHub Actions', 'CI/CD'),
                    ('ArgoCD', 'CI/CD'),
                    ('Tekton', 'CI/CD'),
                    ('Git', '버전 관리'),
                    ('GitHub', '버전 관리'),
                    ('GitLab', '버전 관리'),
                    ('SVN', '버전 관리'),
                    ('Linux', '운영체제'),
                    ('Windows', '운영체제'),
                    ('Unix', '운영체제'),
                    ('Apache', '웹·WAS 서버'),
                    ('Nginx', '웹·WAS 서버'),
                    ('Tomcat', '웹·WAS 서버'),
                    ('WebLogic', '웹·WAS 서버'),
                    ('Lena', '웹·WAS 서버'),
                    ('JEUS', '웹·WAS 서버'),
                    ('Datadog', '모니터링·관측'),
                    ('Grafana', '모니터링·관측'),
                    ('Prometheus', '모니터링·관측'),
                    ('Sentry', '모니터링·관측'),
                    ('Loki', '모니터링·관측'),
                    ('TCP', '네트워크'),
                    ('UDP', '네트워크'),
                    ('DNS', '네트워크'),
                    ('DDNS', '네트워크'),
                    ('P2P', '네트워크'),
                    ('PyTorch', '딥러닝 프레임워크'),
                    ('Torch', '딥러닝 프레임워크'),
                    ('TensorFlow', '딥러닝 프레임워크'),
                    ('Keras', '딥러닝 프레임워크'),
                    ('Deeplearning4j', '딥러닝 프레임워크'),
                    ('RAG', 'LLM 응용'),
                    ('LangChain', 'LLM 응용'),
                    ('LangGraph', 'LLM 응용'),
                    ('LlamaIndex', 'LLM 응용'),
                    ('vLLM', 'LLM 파인튜닝·서빙'),
                    ('SGLang', 'LLM 파인튜닝·서빙'),
                    ('Quantization', '모델 경량화·최적화'),
                    ('Pruning', '모델 경량화·최적화'),
                    ('Distillation', '모델 경량화·최적화'),
                    ('Eclipse', '개발 도구'),
                    ('IntelliJ', '개발 도구'),
                    ('Toad', '개발 도구'),
                    ('SSMS', '개발 도구'),
                    ('VS Code', '개발 도구'),
                    ('Cursor', 'AI 코딩 도구'),
                    ('CodeRabbit', 'AI 코딩 도구'),
                    ('Figma', '디자인 협업'),
                    ('그누보드', 'CMS'),
                    ('워드프레스', 'CMS'),
                    ('Agile', '개발 방법론'),
                    ('Scrum', '개발 방법론'),
                    ('Hadoop', '데이터 플랫폼'),
                    ('DataStage', '데이터 파이프라인'),
                    ('TeraStream', '데이터 파이프라인'),
                    ('SQLAlchemy', 'ORM·데이터 접근'),
                    ('PL/SQL', 'SQL'),
                    ('Pandas', '데이터 처리·분석'),
                    ('OAuth', '보안·인증'),
                    ('OpenTelemetry', '모니터링·관측'),
                    ('HTML', '프론트엔드 프레임워크'),
                    ('CSS', '프론트엔드 프레임워크'),
                    ('Phaser', '프론트엔드 프레임워크'),
                    ('WebSocket', '실시간 처리'),
                    ('Webhook', '실시간 처리'),
                    ('Colyseus', '실시간 처리'),
                    ('YouTube API', '외부 플랫폼 연동'),
                    ('OBS', '방송·스트리밍 도구'),
                    ('Milvus', '벡터 DB'),
                    ('Pinecone', '벡터 DB'),
                    ('Qdrant', '벡터 DB'),
                    ('Weaviate', '벡터 DB'),
                    ('Chroma', '벡터 DB'),
                    ('ArcGIS', 'GIS·공간 데이터'),
                    ('QGIS', 'GIS·공간 데이터'),
                    ('WMS', '물류 시스템'),
                    ('OMS', '물류 시스템'),
                    ('TMS', '물류 시스템'),
                    ('Lean Startup', '개발 방법론')
                 ) AS v (tech, cap), tech t, capability c
            WHERE t.name = v.tech AND c.name = v.cap AND tc.tech_id = t.id AND tc.capability_id = c.id;
        END IF;
    END IF;
END $$;

COMMIT;
