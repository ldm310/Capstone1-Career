-- 채용공고 역량 추출 DB (PostgreSQL 17)
-- 논리 설계: docs/erd.png · 물리 설계 설명: docs/physical-design.md
-- 표·칸의 한글 이름은 COMMENT 로 DB 안에도 남긴다.
--
-- 구역
--   ① 수집        company, posting, posting_image
--   ② 추출 결과    extraction_run, recruit_unit, unit_item, requirement, requirement_tech
--   ③ 표준화 사전  capability, tech, tech_capability, dictionary_version

BEGIN;

-- ============================================================ ③ 표준화 사전
-- 결과가 사전을 가리키므로 사전부터 만든다. 원본은 capabilities.json, DB 는 한 방향 복사본.

CREATE TABLE capability (
    id           bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name         text    NOT NULL UNIQUE,
    group_name   text,
    parent_id    bigint  REFERENCES capability (id) ON DELETE RESTRICT,
    aliases      text[]  NOT NULL DEFAULT '{}',
    is_active    boolean NOT NULL DEFAULT true,
    CHECK (parent_id IS NULL OR parent_id <> id)
);
COMMENT ON TABLE  capability            IS '능력';
COMMENT ON COLUMN capability.id         IS '능력ID';
COMMENT ON COLUMN capability.name       IS '이름 (예: 관계형 DB, 기타)';
COMMENT ON COLUMN capability.group_name IS '묶음 (예: 데이터)';
COMMENT ON COLUMN capability.parent_id  IS '상위 능력ID (예: 관계형 DB -> 데이터베이스)';
COMMENT ON COLUMN capability.aliases    IS '별칭 목록 (예: RDBMS, RDB)';
COMMENT ON COLUMN capability.is_active  IS '사용 여부 (사전에서 빠지면 false, 지우지 않음)';

CREATE TABLE tech (
    id           bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name         text    NOT NULL UNIQUE,
    parent_id    bigint  REFERENCES tech (id) ON DELETE RESTRICT,
    aliases      text[]  NOT NULL DEFAULT '{}',
    is_active    boolean NOT NULL DEFAULT true,
    CHECK (parent_id IS NULL OR parent_id <> id)
);
COMMENT ON TABLE  tech           IS '기술';
COMMENT ON COLUMN tech.id        IS '기술ID';
COMMENT ON COLUMN tech.name      IS '이름 (예: Spring Boot)';
COMMENT ON COLUMN tech.parent_id IS '상위 기술ID (예: EC2 -> AWS)';
COMMENT ON COLUMN tech.aliases   IS '별칭 목록 (예: 스프링 부트)';
COMMENT ON COLUMN tech.is_active IS '사용 여부 (사전에서 빠지면 false, 지우지 않음)';

CREATE TABLE tech_capability (
    tech_id       bigint NOT NULL REFERENCES tech (id) ON DELETE CASCADE,
    capability_id bigint NOT NULL REFERENCES capability (id) ON DELETE CASCADE,
    PRIMARY KEY (tech_id, capability_id)
);
COMMENT ON TABLE  tech_capability               IS '기술-능력 (MySQL -> 관계형 DB)';
COMMENT ON COLUMN tech_capability.tech_id       IS '기술ID';
COMMENT ON COLUMN tech_capability.capability_id IS '능력ID';

CREATE TABLE dictionary_version (
    version    text        PRIMARY KEY,
    synced_at  timestamptz NOT NULL DEFAULT now()
);
COMMENT ON TABLE  dictionary_version           IS '사전 버전 (JSON -> DB 동기화 기록, 최근 것이 현재 버전)';
COMMENT ON COLUMN dictionary_version.version   IS '사전 버전 (capabilities.json 의 version)';
COMMENT ON COLUMN dictionary_version.synced_at IS '동기화 시각';

-- ============================================================ ① 수집

CREATE TABLE company (
    id    bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name  text NOT NULL UNIQUE
);
COMMENT ON TABLE  company      IS '회사';
COMMENT ON COLUMN company.id   IS '회사ID';
COMMENT ON COLUMN company.name IS '회사 이름 (사람인 표기 그대로)';

CREATE TABLE posting (
    id                bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    company_id        bigint      NOT NULL REFERENCES company (id) ON DELETE RESTRICT,
    site              text        NOT NULL DEFAULT '사람인',
    site_posting_no   text        NOT NULL,
    title             text        NOT NULL,
    site_job_category text,
    career_condition  text,
    min_years         smallint    CHECK (min_years BETWEEN 0 AND 50),
    employment_type   text,
    kind              text        NOT NULL CHECK (kind IN ('글', '이미지', '섞임')),
    status            text        NOT NULL DEFAULT '진행' CHECK (status IN ('진행', '마감')),
    deadline          date,
    raw_path          text        NOT NULL,
    raw_hash          char(64)    NOT NULL,
    collected_at      timestamptz NOT NULL DEFAULT now(),
    last_checked_at   timestamptz NOT NULL DEFAULT now(),
    UNIQUE (site, site_posting_no)
);
COMMENT ON TABLE  posting                   IS '공고';
COMMENT ON COLUMN posting.id                IS '공고ID';
COMMENT ON COLUMN posting.company_id        IS '회사ID';
COMMENT ON COLUMN posting.site              IS '사이트 (사람인)';
COMMENT ON COLUMN posting.site_posting_no   IS '사이트 공고번호 (사람인 rec_idx)';
COMMENT ON COLUMN posting.title             IS '제목';
COMMENT ON COLUMN posting.site_job_category IS '사람인 직무 분류 (예: 백엔드)';
COMMENT ON COLUMN posting.career_condition  IS '경력 조건 (사람인 요약 칸 그대로, 예: 신입 · 경력)';
COMMENT ON COLUMN posting.min_years         IS '최소 요구 연수 (0~3만 수집, 모르면 비움)';
COMMENT ON COLUMN posting.employment_type   IS '고용 형태 (예: 정규직)';
COMMENT ON COLUMN posting.kind              IS '공고 형태 (글/이미지/섞임)';
COMMENT ON COLUMN posting.status            IS '상태 (진행/마감)';
COMMENT ON COLUMN posting.deadline          IS '마감일 (상시채용이면 비움)';
COMMENT ON COLUMN posting.raw_path          IS '원본 위치 (본문 HTML 파일 경로)';
COMMENT ON COLUMN posting.raw_hash          IS '원본 해시 (보이는 글에서 띄어쓰기·줄바꿈을 지우고 만든 SHA-256)';
COMMENT ON COLUMN posting.collected_at      IS '수집 시각';
COMMENT ON COLUMN posting.last_checked_at   IS '마지막 확인 시각 (3일마다 수정 확인)';

CREATE TABLE posting_image (
    id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    posting_id  bigint   NOT NULL REFERENCES posting (id) ON DELETE CASCADE,
    seq         smallint NOT NULL CHECK (seq >= 1),
    url         text     NOT NULL,
    file_path   text     NOT NULL,
    kept        boolean,
    ocr_path    text,
    UNIQUE (posting_id, seq)
);
COMMENT ON TABLE  posting_image            IS '공고 이미지';
COMMENT ON COLUMN posting_image.id         IS '이미지ID';
COMMENT ON COLUMN posting_image.posting_id IS '공고ID';
COMMENT ON COLUMN posting_image.seq        IS '순서 (1, 2, 3…)';
COMMENT ON COLUMN posting_image.url        IS '이미지 주소';
COMMENT ON COLUMN posting_image.file_path  IS '파일 위치';
COMMENT ON COLUMN posting_image.kept       IS '남김 여부 (rule base 결과, 판정 전이면 비움)';
COMMENT ON COLUMN posting_image.ocr_path   IS 'OCR 결과 위치 (글자 + 좌표 JSON)';

-- ============================================================ ② 추출 결과
-- 추출 실행을 지우면 그 아래(모집 단위·항목·요건·요건 기술)도 함께 지워진다.

CREATE TABLE extraction_run (
    id               bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    posting_id       bigint        NOT NULL REFERENCES posting (id) ON DELETE CASCADE,
    model            text          NOT NULL,
    prompt_version   text          NOT NULL,
    dict_version     text          NOT NULL,
    input_hash       char(64)      NOT NULL,
    input_tokens     integer       NOT NULL CHECK (input_tokens >= 0),
    output_tokens    integer       NOT NULL CHECK (output_tokens >= 0),
    cost_usd         numeric(10,6) NOT NULL CHECK (cost_usd >= 0),
    retried          boolean       NOT NULL DEFAULT false,
    review_reasons   jsonb         NOT NULL DEFAULT '[]' CHECK (jsonb_typeof(review_reasons) = 'array'),
    review_result    text          CHECK (review_result IN ('문제없음', '고침')),
    reviewed_at      timestamptz,
    llm_output_raw   jsonb,
    is_current       boolean       NOT NULL DEFAULT false,
    run_at           timestamptz   NOT NULL DEFAULT now(),
    CHECK ((review_result IS NULL) = (reviewed_at IS NULL))
);
COMMENT ON TABLE  extraction_run                IS '추출 실행';
COMMENT ON COLUMN extraction_run.id             IS '실행ID';
COMMENT ON COLUMN extraction_run.posting_id     IS '공고ID';
COMMENT ON COLUMN extraction_run.model          IS '모델 (예: gpt-5.6-luna)';
COMMENT ON COLUMN extraction_run.prompt_version IS '프롬프트 버전';
COMMENT ON COLUMN extraction_run.dict_version   IS '사전 버전 (예: 0.1.1)';
COMMENT ON COLUMN extraction_run.input_hash     IS '입력 해시 (같은 입력이면 다시 부르지 않음)';
COMMENT ON COLUMN extraction_run.input_tokens   IS '입력 토큰 (다시 부름 포함 합계)';
COMMENT ON COLUMN extraction_run.output_tokens  IS '출력 토큰 (다시 부름 포함 합계)';
COMMENT ON COLUMN extraction_run.cost_usd       IS '비용 (달러, 실행 당시 가격)';
COMMENT ON COLUMN extraction_run.retried        IS '다시 부름 (모집 단위 검사에 걸려 한 번 더 불렀나)';
COMMENT ON COLUMN extraction_run.review_reasons IS '확인 필요 사유 (예: [{"검사":1,"내용":"..."}], 비면 확인 불필요)';
COMMENT ON COLUMN extraction_run.review_result  IS '확인 결과 (문제없음/고침, 확인 전이면 비움)';
COMMENT ON COLUMN extraction_run.reviewed_at    IS '확인 시각';
COMMENT ON COLUMN extraction_run.llm_output_raw IS '표준화 전 답 (LLM 이 준 JSON 그대로, 2026-10-27 이전 결과는 비어 있음)';
COMMENT ON COLUMN extraction_run.is_current     IS '현재 사용 (공고마다 최대 하나)';
COMMENT ON COLUMN extraction_run.run_at         IS '실행 시각';

CREATE TABLE recruit_unit (
    id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    run_id      bigint   NOT NULL REFERENCES extraction_run (id) ON DELETE CASCADE,
    seq         smallint NOT NULL CHECK (seq >= 1),
    name        text     NOT NULL,
    is_it       boolean  NOT NULL,
    career      text     NOT NULL CHECK (career IN ('신입', '경력', '신입·경력', '언급없음')),
    years_text  text     NOT NULL DEFAULT '',
    min_years   smallint CHECK (min_years BETWEEN 0 AND 50),
    max_years   smallint CHECK (max_years BETWEEN 0 AND 50),
    UNIQUE (run_id, seq),
    CHECK (min_years IS NULL OR max_years IS NULL OR min_years <= max_years)
);
COMMENT ON TABLE  recruit_unit            IS '모집 단위 (공고 안에서 따로 뽑는 자리)';
COMMENT ON COLUMN recruit_unit.id         IS '단위ID';
COMMENT ON COLUMN recruit_unit.run_id     IS '실행ID';
COMMENT ON COLUMN recruit_unit.seq        IS '순서 (LLM 답의 순서)';
COMMENT ON COLUMN recruit_unit.name       IS '이름 (예: 서버 개발자 (경력))';
COMMENT ON COLUMN recruit_unit.is_it      IS 'IT 직무 (false 면 이름·경력만, 항목 없음)';
COMMENT ON COLUMN recruit_unit.career     IS '경력 구분 (신입/경력/신입·경력/언급없음)';
COMMENT ON COLUMN recruit_unit.years_text IS '연수 (공고에 적힌 글 그대로, 예: 3년 이상)';
COMMENT ON COLUMN recruit_unit.min_years  IS '최소 연수 (매칭용 숫자, 없으면 비움)';
COMMENT ON COLUMN recruit_unit.max_years  IS '최대 연수 (매칭용 숫자, 없으면 비움)';

CREATE TABLE unit_item (
    id        bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    unit_id   bigint   NOT NULL REFERENCES recruit_unit (id) ON DELETE CASCADE,
    category  text     NOT NULL CHECK (category IN ('필수', '우대', '업무', '기타')),
    seq       smallint NOT NULL CHECK (seq >= 1),
    text      text     NOT NULL,
    quote     text     NOT NULL,
    UNIQUE (unit_id, category, seq)
);
COMMENT ON TABLE  unit_item          IS '항목 (자리에 적힌 한 줄)';
COMMENT ON COLUMN unit_item.id       IS '항목ID';
COMMENT ON COLUMN unit_item.unit_id  IS '단위ID';
COMMENT ON COLUMN unit_item.category IS '칸 (필수/우대/업무/기타)';
COMMENT ON COLUMN unit_item.seq      IS '순서 (칸 안에서)';
COMMENT ON COLUMN unit_item.text     IS '개조식 한 줄';
COMMENT ON COLUMN unit_item.quote    IS '근거 (공고 원문 그대로)';

CREATE TABLE requirement (
    id             bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    item_id        bigint NOT NULL REFERENCES unit_item (id) ON DELETE CASCADE,
    capability_id  bigint NOT NULL REFERENCES capability (id) ON DELETE RESTRICT,
    other_name     text   NOT NULL DEFAULT '',
    relation       text   NOT NULL CHECK (relation IN ('예시', '택1', '모두', '능력만'))
);
COMMENT ON TABLE  requirement               IS '요건 (한 줄이 요구하는 능력 하나)';
COMMENT ON COLUMN requirement.id            IS '요건ID';
COMMENT ON COLUMN requirement.item_id       IS '항목ID';
COMMENT ON COLUMN requirement.capability_id IS '능력ID (맞는 능력이 없으면 ''기타'')';
COMMENT ON COLUMN requirement.other_name    IS '기타 이름 (능력이 ''기타''일 때만)';
COMMENT ON COLUMN requirement.relation      IS '관계 (예시/택1/모두/능력만)';

CREATE TABLE requirement_tech (
    id              bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    requirement_id  bigint NOT NULL REFERENCES requirement (id) ON DELETE CASCADE,
    tech_id         bigint REFERENCES tech (id) ON DELETE RESTRICT,
    written_name    text   NOT NULL
);
COMMENT ON TABLE  requirement_tech                IS '요건 기술';
COMMENT ON COLUMN requirement_tech.id             IS '요건기술ID';
COMMENT ON COLUMN requirement_tech.requirement_id IS '요건ID';
COMMENT ON COLUMN requirement_tech.tech_id        IS '기술ID (사전에 없으면 비움)';
COMMENT ON COLUMN requirement_tech.written_name   IS '적힌 이름 (공고 표기 그대로, 예: 스프링 부트)';

-- ============================================================ 색인
-- PostgreSQL 은 FK 칸에 색인을 자동으로 만들지 않는다. 자주 잇거나 거르는 칸에 만든다.

CREATE INDEX ON posting (company_id);
CREATE INDEX ON posting (status, last_checked_at);              -- 3일마다 수정 확인할 공고 고르기
CREATE INDEX ON posting_image (posting_id);
CREATE INDEX ON extraction_run (posting_id);
CREATE UNIQUE INDEX extraction_run_one_current
    ON extraction_run (posting_id) WHERE is_current;           -- 공고마다 '현재 사용'은 최대 하나
CREATE INDEX extraction_run_review_queue
    ON extraction_run (run_at)
    WHERE review_reasons <> '[]'::jsonb AND review_result IS NULL;  -- 사람이 확인할 목록
CREATE INDEX ON recruit_unit (run_id);
CREATE INDEX ON unit_item (unit_id);
CREATE INDEX ON requirement (item_id);
CREATE INDEX ON requirement (capability_id);                   -- 능력별 통계·매칭
CREATE INDEX ON requirement_tech (requirement_id);
CREATE INDEX ON requirement_tech (tech_id);                    -- 기술별 통계·매칭
CREATE INDEX ON tech_capability (capability_id);
CREATE INDEX ON capability (parent_id);
CREATE INDEX ON tech (parent_id);
CREATE INDEX ON capability USING gin (aliases);                -- 별칭으로 찾기
CREATE INDEX ON tech USING gin (aliases);

COMMIT;
