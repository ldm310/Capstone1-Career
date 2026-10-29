-- 사용자 역량 평가 DB (PostgreSQL 17) — 제안, 최종 DB 는 미정
-- feature/job-skill 의 공고 DB(스키마 job)와 같은 DB 에 같은 규칙으로 만든다. BE 표(기본 스키마 public)와도 이름이 부딪히지 않는다.
-- 표·칸 이름은 로컬 SQLite(collector/store.py)와 같다. 이 파일에만 있는 칸은 tech_id 하나다(옮길 때 기술 이름으로 job.tech 에서 찾아 채운다).
-- 옮길 때: SQLite 는 나중에 더한 칸이 끝에 붙어 칸 순서가 다를 수 있으니 칸 이름으로 맞춰 넣는다. id 를 그대로 넣으려면 INSERT ... OVERRIDING SYSTEM VALUE 를 쓰고,
-- 넣은 뒤 identity 표(account, collect_run, repo, assessment, stat, gold_label)마다 SELECT setval(pg_get_serial_sequence('eval.<표>', 'id'), max(id)) 를 실행한다.
-- SQLite 쪽은 CHECK 일부(아래 정확한 목록·짝 검사)를 두지 않았다. 옮기기 전에 같은 검사를 돌려 거절될 값이 없는지 본다.
-- 표·칸의 한글 이름은 COMMENT 로 DB 안에도 남긴다. 다른 쪽에서 읽을 때는 eval.assessment 처럼 스키마 이름을 붙인다.
-- 기술은 job 의 표준화 사전(job.tech · job.capability · job.tech_capability)을 그대로 가리킨다.
-- 그래서 내 기술별 LV(eval.stat_tech)와 공고 요건 기술(job.requirement_tech)을 tech_id 로 바로 잇는다.
--
-- 구역
--   ① 계정·수집   account, collect_run, repo, own_commit, eval_commit, evidence_line, external_pr_repo
--   ② 판정        assessment, finding, risk_item
--   ③ 결과        stat, stat_tech
--   ④ 검증        gold_label
--   보기          latest_stat_tech, capability_level

BEGIN;

CREATE SCHEMA IF NOT EXISTS eval;
COMMENT ON SCHEMA eval IS '사용자 역량 평가 (GitHub 수집·조건 판정·기술별 LV·내 STAT·정답 세트)';
SET LOCAL search_path TO eval;   -- 아래 표·색인은 모두 eval 안에 만들어진다. job 의 표는 job. 을 붙여 가리킨다

-- ============================================================ ① 계정·수집

CREATE TABLE account (
    id            bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    login         text        NOT NULL,
    github_id     bigint      UNIQUE,
    relation      text        NOT NULL CHECK (relation IN ('본인', '지인')),
    consent_note  text        NOT NULL,
    consented_at  date        NOT NULL,
    revoked_at    date,
    created_at    timestamptz NOT NULL DEFAULT now()
);
COMMENT ON TABLE  account              IS '계정 (분석하는 GitHub 계정과 동의 기록, 동의 없으면 수집하지 않음)';
COMMENT ON COLUMN account.id           IS '계정ID';
COMMENT ON COLUMN account.login        IS 'GitHub 계정 이름 (대소문자 무시)';
COMMENT ON COLUMN account.github_id    IS 'GitHub 사용자 번호';
COMMENT ON COLUMN account.relation     IS '관계 (본인/지인)';
COMMENT ON COLUMN account.consent_note IS '동의 내용 (받은 방법·범위, 예: 카톡, 공개 레포 분석에 동의)';
COMMENT ON COLUMN account.consented_at IS '동의 날짜';
COMMENT ON COLUMN account.revoked_at   IS '동의 철회 날짜 (철회되면 수집·판정·내보내기를 하지 않음. 기존 기록을 지울지는 미정)';
COMMENT ON COLUMN account.created_at   IS '기록 시각';

CREATE TABLE collect_run (
    id               bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    account_id       bigint      NOT NULL REFERENCES account (id) ON DELETE RESTRICT,
    login            text        NOT NULL,
    github_id        bigint,
    started_at       timestamptz NOT NULL,
    finished_at      timestamptz NOT NULL,
    token_used       boolean     NOT NULL,
    api_calls        integer     NOT NULL CHECK (api_calls >= 0),
    stopped          text,
    identity_emails  jsonb       NOT NULL DEFAULT '[]' CHECK (jsonb_typeof(identity_emails) = 'array')
);
COMMENT ON TABLE  collect_run                 IS '수집 실행 (계정 하나를 한 번 수집)';
COMMENT ON COLUMN collect_run.id              IS '수집ID';
COMMENT ON COLUMN collect_run.account_id      IS '계정ID';
COMMENT ON COLUMN collect_run.login           IS '수집할 때의 계정 이름';
COMMENT ON COLUMN collect_run.github_id       IS 'GitHub 사용자 번호';
COMMENT ON COLUMN collect_run.started_at      IS '시작 시각';
COMMENT ON COLUMN collect_run.finished_at     IS '끝난 시각';
COMMENT ON COLUMN collect_run.token_used      IS 'GitHub 토큰 사용 (없으면 시간당 60회 한도)';
COMMENT ON COLUMN collect_run.api_calls       IS 'API 호출 수';
COMMENT ON COLUMN collect_run.stopped         IS '중단 이유 (끝까지 마쳤으면 비움)';
COMMENT ON COLUMN collect_run.identity_emails IS '본인 commit 판별에 쓴 이메일 (가린 값만, 원래 이메일은 저장하지 않음)';

CREATE TABLE repo (
    id                     bigint  GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    run_id                 bigint  NOT NULL REFERENCES collect_run (id) ON DELETE CASCADE,
    full_name              text    NOT NULL,
    fork                   boolean NOT NULL,
    default_branch         text,
    size_kb                integer,
    default_sha            text,
    develop_sha            text,
    develop_contains_main  boolean,
    reachable_commits      integer,
    pulls                  integer,
    pulls_merged           integer,
    pulls_own              integer,
    issues                 integer,
    deployments            integer,
    actions_all            integer,
    error                  text,
    source                 text    CHECK (source IN ('owner', 'member', 'search')),
    UNIQUE (run_id, full_name)
);
COMMENT ON TABLE  repo                       IS '레포 (공개 레포 하나와 활용 기록 개수, main·develop 만 본다)';
COMMENT ON COLUMN repo.id                    IS '레포ID';
COMMENT ON COLUMN repo.run_id                IS '수집ID';
COMMENT ON COLUMN repo.full_name             IS '레포 이름 (owner/name)';
COMMENT ON COLUMN repo.fork                  IS 'fork 여부';
COMMENT ON COLUMN repo.default_branch        IS '기본 브랜치';
COMMENT ON COLUMN repo.size_kb               IS '크기 (KB)';
COMMENT ON COLUMN repo.default_sha           IS '기본 브랜치 끝 commit';
COMMENT ON COLUMN repo.develop_sha           IS 'develop 끝 commit (없으면 비움)';
COMMENT ON COLUMN repo.develop_contains_main IS 'develop 이 main 을 포함 (거짓이면 갈라짐, 같은 commit 이거나 develop 없으면 비움)';
COMMENT ON COLUMN repo.reachable_commits     IS 'main·develop 에서 닿는 commit 수';
COMMENT ON COLUMN repo.pulls                 IS 'PR 수';
COMMENT ON COLUMN repo.pulls_merged          IS '병합된 PR 수';
COMMENT ON COLUMN repo.pulls_own             IS '본인이 연 PR 수';
COMMENT ON COLUMN repo.issues                IS '이슈 수 (PR 제외)';
COMMENT ON COLUMN repo.deployments           IS '배포 기록 수';
COMMENT ON COLUMN repo.actions_all           IS '레포 전체 GitHub Actions 실행 수';
COMMENT ON COLUMN repo.error                 IS '건너뛴 이유 (예: clone 실패)';
COMMENT ON COLUMN repo.source                IS '찾은 경로 (owner 소유/member 멤버/search commit·PR 검색)';

CREATE TABLE own_commit (
    repo_id      bigint      NOT NULL REFERENCES repo (id) ON DELETE CASCADE,
    sha          text        NOT NULL,
    kind         text        NOT NULL CHECK (kind IN ('api', 'email', 'name_only')),
    authored_at  timestamptz,
    added        integer,
    deleted      integer,
    files        integer,
    is_merge     boolean,
    PRIMARY KEY (repo_id, sha)
);
COMMENT ON TABLE  own_commit             IS '본인 commit (이름만 일치는 추정이라 판정에 쓰지 않음)';
COMMENT ON COLUMN own_commit.repo_id     IS '레포ID';
COMMENT ON COLUMN own_commit.sha         IS 'commit ID';
COMMENT ON COLUMN own_commit.kind        IS '판별 방법 (api 계정 연결/email 이메일/name_only 이름만 일치)';
COMMENT ON COLUMN own_commit.authored_at IS '작성 시각';
COMMENT ON COLUMN own_commit.added       IS '추가 줄 (생성 파일 제외)';
COMMENT ON COLUMN own_commit.deleted     IS '삭제 줄 (생성 파일 제외)';
COMMENT ON COLUMN own_commit.files       IS '바꾼 파일 수';
COMMENT ON COLUMN own_commit.is_merge    IS '병합 commit 여부';

CREATE TABLE eval_commit (
    repo_id          bigint  NOT NULL REFERENCES repo (id) ON DELETE CASCADE,
    sha              text    NOT NULL,
    branches         text    NOT NULL,
    own_lines        integer,
    name_only_lines  integer,
    other_lines      integer,
    files            integer,
    actions          integer,
    check_runs       integer,
    statuses         integer,
    conclusions      jsonb   NOT NULL DEFAULT '[]' CHECK (jsonb_typeof(conclusions) = 'array'),
    run_details      jsonb,
    PRIMARY KEY (repo_id, sha)
);
COMMENT ON TABLE  eval_commit                 IS '평가 commit (본인 줄 요약과 같은 commit 의 실행 기록)';
COMMENT ON COLUMN eval_commit.repo_id         IS '레포ID';
COMMENT ON COLUMN eval_commit.sha             IS 'commit ID';
COMMENT ON COLUMN eval_commit.branches        IS '브랜치 (쉼표로, 예: main,develop)';
COMMENT ON COLUMN eval_commit.own_lines       IS '본인이 마지막으로 쓴 줄 (git blame, 생성 파일 제외)';
COMMENT ON COLUMN eval_commit.name_only_lines IS '이름만 일치하는 줄 (추정이라 본인 줄로 세지 않음)';
COMMENT ON COLUMN eval_commit.other_lines     IS '다른 사람의 줄';
COMMENT ON COLUMN eval_commit.files           IS '파일 수';
COMMENT ON COLUMN eval_commit.actions         IS '같은 commit 의 GitHub Actions 실행 수';
COMMENT ON COLUMN eval_commit.check_runs      IS '같은 commit 의 check run 수';
COMMENT ON COLUMN eval_commit.statuses        IS '같은 commit 의 commit status 수 (실행 기록으로 세지 않음)';
COMMENT ON COLUMN eval_commit.conclusions     IS 'Actions 결과 목록 (예: ["success"])';
COMMENT ON COLUMN eval_commit.run_details     IS 'workflow·check run·status 이름과 결과';

CREATE TABLE evidence_line (
    repo_id     bigint  NOT NULL REFERENCES repo (id) ON DELETE CASCADE,
    sha         text    NOT NULL,
    path        text    NOT NULL,
    line_start  integer NOT NULL CHECK (line_start >= 1),
    line_end    integer NOT NULL CHECK (line_end >= line_start),
    PRIMARY KEY (repo_id, sha, path, line_start)
);
COMMENT ON TABLE  evidence_line            IS '본인 줄 (증거 단위: 레포·commit·파일·줄 범위)';
COMMENT ON COLUMN evidence_line.repo_id    IS '레포ID';
COMMENT ON COLUMN evidence_line.sha        IS 'commit ID';
COMMENT ON COLUMN evidence_line.path       IS '파일 경로';
COMMENT ON COLUMN evidence_line.line_start IS '시작 줄';
COMMENT ON COLUMN evidence_line.line_end   IS '끝 줄';

CREATE TABLE external_pr_repo (
    run_id     bigint NOT NULL REFERENCES collect_run (id) ON DELETE CASCADE,
    full_name  text   NOT NULL,
    PRIMARY KEY (run_id, full_name)
);
COMMENT ON TABLE  external_pr_repo           IS '본인 소유가 아닌 레포 (멤버·검색으로 찾음)';
COMMENT ON COLUMN external_pr_repo.run_id    IS '수집ID';
COMMENT ON COLUMN external_pr_repo.full_name IS '레포 이름';

-- ============================================================ ② 판정
-- 판정 실행 한 줄 = 기술 하나 × 레포 하나 × 평가 commit 하나. job.extraction_run 과 같은 칸(모델·버전·입력 해시·비용·확인 사유·LLM 답·현재 사용)을 둔다.

CREATE TABLE assessment (
    id                  bigint        GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    run_id              bigint        NOT NULL REFERENCES collect_run (id) ON DELETE CASCADE,
    repo                text          NOT NULL,
    sha                 text          NOT NULL,
    tech                text          NOT NULL,
    tech_id             bigint        REFERENCES job.tech (id) ON DELETE RESTRICT,
    created_at          timestamptz   NOT NULL DEFAULT now(),
    model               text,
    effort              text,
    status              text          NOT NULL CHECK (status IN ('ok', 'refusal', 'max_tokens', 'bad_json', 'budget', 'no_material')),
    mode                text          NOT NULL CHECK (mode IN ('llm', 'rule_only', 'shadow')),
    is_current          boolean       NOT NULL DEFAULT false,
    shadow_of           bigint        REFERENCES assessment (id) ON DELETE SET NULL,
    level               smallint      CHECK (level BETWEEN 0 AND 5),
    blocked_at          text          CHECK (blocked_at IN ('0', '1', '2', '3', '4', '5', 'personal_scope', 'risk')),
    retries             smallint      CHECK (retries BETWEEN 0 AND 3),
    input_tokens        integer       CHECK (input_tokens >= 0),
    output_tokens       integer       CHECK (output_tokens >= 0),
    cache_read_tokens   integer       CHECK (cache_read_tokens >= 0),
    cache_write_tokens  integer       CHECK (cache_write_tokens >= 0),
    cost_usd            numeric(10,6) CHECK (cost_usd >= 0),
    shown_files         jsonb         NOT NULL DEFAULT '[]' CHECK (jsonb_typeof(shown_files) = 'array'),
    omitted_files       jsonb         NOT NULL DEFAULT '[]' CHECK (jsonb_typeof(omitted_files) = 'array'),
    reused_from         bigint        REFERENCES assessment (id) ON DELETE SET NULL,
    in_dictionary       boolean,
    prompt_version      text,
    rule_version        text,
    rule_hash           char(64),
    dict_version        text,
    input_hash          char(64),
    review_reasons      jsonb         NOT NULL DEFAULT '[]' CHECK (jsonb_typeof(review_reasons) = 'array'),
    review_result       text          CHECK (review_result IN ('문제없음', '고침')),
    reviewed_at         timestamptz,
    llm_output_raw      jsonb,
    CHECK (mode <> 'shadow' OR NOT is_current),
    CHECK (mode = 'shadow' OR shadow_of IS NULL),
    CHECK ((review_result IS NULL) = (reviewed_at IS NULL)),          -- job-skill 과 같은 업무 규칙: 확인 결과와 시각은 함께
    FOREIGN KEY (run_id, repo) REFERENCES repo (run_id, full_name) ON DELETE CASCADE
);
COMMENT ON TABLE  assessment                    IS '판정 실행 (기술 × 레포 × 평가 commit 하나, job.extraction_run 과 같은 뜻의 칸을 둔다)';
COMMENT ON COLUMN assessment.id                 IS '판정ID';
COMMENT ON COLUMN assessment.run_id             IS '수집ID';
COMMENT ON COLUMN assessment.repo               IS '레포 이름 (owner/name)';
COMMENT ON COLUMN assessment.sha                IS '평가 commit ID';
COMMENT ON COLUMN assessment.tech               IS '기술 이름 (사전 표준 이름, 사전에 없으면 찾은 이름 그대로 — job.requirement_tech.written_name 과 같은 뜻)';
COMMENT ON COLUMN assessment.tech_id            IS '기술ID (job.tech, 사전에 없으면 비움)';
COMMENT ON COLUMN assessment.created_at         IS '판정 시각';
COMMENT ON COLUMN assessment.model              IS '모델 (예: claude-haiku-5-5, LLM 을 부르지 않은 rule_only 판정이면 비움)';
COMMENT ON COLUMN assessment.effort             IS '추론 강도 (예: high, rule_only 면 비움)';
COMMENT ON COLUMN assessment.status             IS '결과 (ok 판정함/refusal·max_tokens·bad_json 응답 실패/budget 예산 한도/no_material 보여 줄 코드 없음)';
COMMENT ON COLUMN assessment.mode               IS '판정 방식 (llm LLM 해석 + 규칙/rule_only 규칙만으로 확정해 LLM 안 부름/shadow 그림자 실행, LV 반영 안 함)';
COMMENT ON COLUMN assessment.is_current         IS '현재 사용 (한 수집 실행 안에서 기술 × 레포마다 최대 하나, 그림자는 늘 거짓. 계정의 최신 판정은 current_assessment 보기)';
COMMENT ON COLUMN assessment.shadow_of          IS '그림자 실행이 비교하는 현재 판정ID';
COMMENT ON COLUMN assessment.level              IS '이 레포에서의 LV (비우면 미확인, LV0 이 아님)';
COMMENT ON COLUMN assessment.blocked_at         IS '막힌 곳 (0~5 그 LV 에서 막힘/personal_scope 개인 기여 미확인/risk 위험 미확인으로 LV2 이상 보류, 비우면 막힘 없음)';
COMMENT ON COLUMN assessment.retries            IS '추가 LLM 재검토 횟수 (최대 3)';
COMMENT ON COLUMN assessment.input_tokens       IS '입력 토큰 (재검토 포함 합계)';
COMMENT ON COLUMN assessment.output_tokens      IS '출력 토큰 (생각 포함, 재검토 포함 합계)';
COMMENT ON COLUMN assessment.cache_read_tokens  IS '캐시 읽기 토큰';
COMMENT ON COLUMN assessment.cache_write_tokens IS '캐시 쓰기 토큰';
COMMENT ON COLUMN assessment.cost_usd           IS '추정 비용 (달러, 판정 당시 단가, 실제 청구액은 Console)';
COMMENT ON COLUMN assessment.shown_files        IS 'LLM 에게 보여 준 파일 목록';
COMMENT ON COLUMN assessment.omitted_files      IS '길이 제한으로 뺀 파일 목록';
COMMENT ON COLUMN assessment.reused_from        IS 'LLM 답을 다시 쓴 판정ID (비용 0)';
COMMENT ON COLUMN assessment.in_dictionary      IS '팀 사전(capabilities.json)에 있는 기술 (거짓이면 공고와 비교 불가)';
COMMENT ON COLUMN assessment.prompt_version     IS '프롬프트 버전 (사람이 붙인 이름)';
COMMENT ON COLUMN assessment.rule_version       IS '규칙 버전 (사람이 붙인 이름, 규칙을 바꾸면 올림)';
COMMENT ON COLUMN assessment.rule_hash          IS '규칙 지문 (규칙 코드·상수의 SHA-256, 지금 값과 다르면 옛 규칙으로 나온 판정)';
COMMENT ON COLUMN assessment.dict_version       IS '사전 버전 (capabilities.json version 의 첫 토큰, 예: 0.1.1 — job-skill 이 넣는 값과 같음)';
COMMENT ON COLUMN assessment.input_hash         IS 'LLM 입력 해시 (같은 입력이면 다시 부르지 않음)';
COMMENT ON COLUMN assessment.review_reasons     IS '확인 필요 사유 (예: [{"항목":"L0-02","사유":"..."}], 비면 확인 불필요. job-skill 은 [{"검사":1,"내용":"..."}] 모양이라 칸의 뜻만 같다)';
COMMENT ON COLUMN assessment.review_result      IS '확인 결과 (문제없음/고침, 확인 전이면 비움)';
COMMENT ON COLUMN assessment.reviewed_at        IS '확인 시각';
COMMENT ON COLUMN assessment.llm_output_raw     IS 'LLM 답 ({answer: 재검토까지 합친 정규화 답, retried, unresolved} — job-skill 의 표준화 전 원답과 모양이 다르다. 규칙이 바뀌면 여기에 새 규칙만 다시 적용, LLM 을 부르지 않았으면 비움)';

CREATE TABLE finding (
    assessment_id  bigint NOT NULL REFERENCES assessment (id) ON DELETE CASCADE,
    cond_id        text   NOT NULL CHECK (cond_id IN ('L0-01', 'L0-02', 'L0-03', 'L0-04', 'L1-01', 'L1-02', 'L1-03', 'L1-04', 'L2-01', 'L2-02', 'L2-03', 'L2-04', 'L2-05', 'L3-01', 'L3-02', 'L3-03', 'L3-04', 'L3-05', 'L4-01', 'L4-02', 'L4-03', 'L4-04', 'L4-05', 'L4-06', 'L5-01', 'L5-02', 'L5-03', 'L5-04', 'L5-05', 'L5-06', 'L5-07', 'personal_scope')),
    kind           text   CHECK (kind IN ('문서형', '코드형', '실행 기록형', '활용 기록형', '혼합', '개인 기여')),
    llm_status     text   CHECK (llm_status IN ('met', 'not_met', 'unknown', 'conflict')),
    final_status   text   NOT NULL CHECK (final_status IN ('met', 'not_met', 'unknown', 'conflict')),
    reason         text,
    rule_note      text,
    evidence       jsonb  NOT NULL DEFAULT '[]' CHECK (jsonb_typeof(evidence) = 'array'),
    PRIMARY KEY (assessment_id, cond_id)
);
COMMENT ON TABLE  finding               IS '조건 판정 (기준표 31개 + 개인 기여)';
COMMENT ON COLUMN finding.assessment_id IS '판정ID';
COMMENT ON COLUMN finding.cond_id       IS '조건ID (L0-01~L5-07, personal_scope)';
COMMENT ON COLUMN finding.kind          IS '조건 유형 (인정 규칙이 다름)';
COMMENT ON COLUMN finding.llm_status    IS 'LLM 판단 (met 충족/not_met 미충족/unknown 근거 부족/conflict 충돌, LLM 을 부르지 않았으면 비움)';
COMMENT ON COLUMN finding.final_status  IS '최종 상태 (규칙 검사 뒤)';
COMMENT ON COLUMN finding.reason        IS 'LLM 이 쓴 이유';
COMMENT ON COLUMN finding.rule_note     IS '규칙 메모 (규칙이 상태를 내린 이유, 예: 같은 commit의 실행 기록 없음)';
COMMENT ON COLUMN finding.evidence      IS '인용 목록 (예: [{"file":"FACTS","quote":"..."}], 원문 그대로)';

CREATE TABLE risk_item (
    assessment_id  bigint NOT NULL REFERENCES assessment (id) ON DELETE CASCADE,
    risk_id        text   NOT NULL CHECK (risk_id IN ('external_input', 'access_control', 'persistent_write', 'harmful_duplicates',
                                                      'external_api', 'analytics', 'model_evaluation', 'production_change')),
    llm_status     text   CHECK (llm_status IN ('yes', 'no', 'unknown')),
    final_status   text   NOT NULL CHECK (final_status IN ('yes', 'no', 'unknown')),
    reason         text,
    rule_note      text,
    evidence       jsonb  NOT NULL DEFAULT '[]' CHECK (jsonb_typeof(evidence) = 'array'),
    PRIMARY KEY (assessment_id, risk_id)
);
COMMENT ON TABLE  risk_item               IS '위험 적용 여부 (위험 8개, 실험 규칙: 하나라도 모르면 LV2 이상 보류)';
COMMENT ON COLUMN risk_item.assessment_id IS '판정ID';
COMMENT ON COLUMN risk_item.risk_id       IS '위험ID';
COMMENT ON COLUMN risk_item.llm_status    IS 'LLM 판단 (yes 해당/no 해당 없음/unknown 모름)';
COMMENT ON COLUMN risk_item.final_status  IS '최종 상태 (규칙 검사 뒤)';
COMMENT ON COLUMN risk_item.reason        IS 'LLM 이 쓴 이유';
COMMENT ON COLUMN risk_item.rule_note     IS '규칙 메모';
COMMENT ON COLUMN risk_item.evidence      IS '인용 목록';

-- ============================================================ ③ 결과

CREATE TABLE stat (
    id            bigint      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    run_id        bigint      NOT NULL REFERENCES collect_run (id) ON DELETE CASCADE,
    created_at    timestamptz NOT NULL DEFAULT now(),
    levels        jsonb       NOT NULL,
    reach         jsonb       NOT NULL,
    blocked_at    smallint    CHECK (blocked_at BETWEEN 0 AND 4),
    type          text,
    note          text,
    threshold     real        CHECK (threshold > 0 AND threshold <= 1),
    rule_version  text,
    rule_hash     char(64),
    dict_version  text
);
COMMENT ON TABLE  stat              IS '내 STAT (단계별 도달률·막힌 단계·지원자 유형, 수치는 규칙이 계산)';
COMMENT ON COLUMN stat.id           IS 'STAT ID';
COMMENT ON COLUMN stat.run_id       IS '수집ID';
COMMENT ON COLUMN stat.created_at   IS '계산 시각';
COMMENT ON COLUMN stat.levels       IS '기술별 LV (예: {"Python": 2, "Docker": null}, null 은 미확인)';
COMMENT ON COLUMN stat.reach        IS '단계별 도달률 (기본 수행·과제 완성·신뢰성 확보·실제 활용·개선·설계)';
COMMENT ON COLUMN stat.blocked_at   IS '막힌 단계 (0~4, 비우면 막힘 없음)';
COMMENT ON COLUMN stat.type         IS '지원자 유형 (제안)';
COMMENT ON COLUMN stat.note         IS '메모 (분모를 어떻게 정했는지 등)';
COMMENT ON COLUMN stat.threshold    IS '막힌 단계 기준값 (제안 0.5)';
COMMENT ON COLUMN stat.rule_version IS '규칙 버전';
COMMENT ON COLUMN stat.rule_hash    IS '규칙 지문';
COMMENT ON COLUMN stat.dict_version IS '사전 버전';

CREATE TABLE stat_tech (
    stat_id         bigint   NOT NULL REFERENCES stat (id) ON DELETE CASCADE,
    tech            text     NOT NULL,
    tech_id         bigint   REFERENCES job.tech (id) ON DELETE RESTRICT,
    in_dictionary   boolean,
    level           smallint CHECK (level BETWEEN 0 AND 5),
    assessment_ids  jsonb    CHECK (assessment_ids IS NULL OR jsonb_typeof(assessment_ids) = 'array'),
    PRIMARY KEY (stat_id, tech)
);
COMMENT ON TABLE  stat_tech                IS 'STAT 기술별 LV (공고 요건 기술과 tech_id 로 잇는다)';
COMMENT ON COLUMN stat_tech.stat_id        IS 'STAT ID';
COMMENT ON COLUMN stat_tech.tech           IS '기술 이름';
COMMENT ON COLUMN stat_tech.tech_id        IS '기술ID (job.tech, 사전에 없으면 비움 → 공고와 비교 불가)';
COMMENT ON COLUMN stat_tech.in_dictionary  IS '팀 사전에 있는 기술';
COMMENT ON COLUMN stat_tech.level          IS '기술 LV (레포별 LV 중 최고, 비우면 미확인)';
COMMENT ON COLUMN stat_tech.assessment_ids IS '이 LV 를 낸 현재 판정ID 목록 ([] 면 판정 못 해 미확인으로 셈, 비우면 옛 기록이라 모름)';

-- ============================================================ ④ 검증
-- 정답 세트: 사람이 시스템 결과를 보기 전에 따로 적은 기대 LV·조건 판정. 시스템 전체(규칙 + LLM)의 결과와 비교한다.

CREATE TABLE gold_label (
    id          bigint      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    account_id  bigint      NOT NULL REFERENCES account (id) ON DELETE CASCADE,
    repo        text        NOT NULL,
    tech        text        NOT NULL,
    tech_id     bigint      REFERENCES job.tech (id) ON DELETE RESTRICT,
    sha         text        NOT NULL,
    cond_id     text        NOT NULL CHECK (cond_id IN ('LV', 'L0-01', 'L0-02', 'L0-03', 'L0-04', 'L1-01', 'L1-02', 'L1-03', 'L1-04', 'L2-01', 'L2-02', 'L2-03', 'L2-04', 'L2-05', 'L3-01', 'L3-02', 'L3-03', 'L3-04', 'L3-05', 'L4-01', 'L4-02', 'L4-03', 'L4-04', 'L4-05', 'L4-06', 'L5-01', 'L5-02', 'L5-03', 'L5-04', 'L5-05', 'L5-06', 'L5-07', 'personal_scope')),
    expected    text        NOT NULL,
    case_tag    text        NOT NULL DEFAULT '',
    note        text        NOT NULL DEFAULT '',
    labeler     text        NOT NULL,
    labeled_at  timestamptz NOT NULL,
    CHECK ((cond_id = 'LV' AND expected IN ('미확인', 'LV0', 'LV1', 'LV2', 'LV3', 'LV4', 'LV5'))
        OR (cond_id <> 'LV' AND expected IN ('충족', '미충족', '근거 부족', '충돌'))),
    UNIQUE (account_id, repo, tech, sha, cond_id, labeler)
);
COMMENT ON TABLE  gold_label            IS '정답 (사람이 시스템과 별개로 적은 기대 LV·조건 판정)';
COMMENT ON COLUMN gold_label.id         IS '정답ID';
COMMENT ON COLUMN gold_label.account_id IS '계정ID';
COMMENT ON COLUMN gold_label.repo       IS '레포 이름';
COMMENT ON COLUMN gold_label.tech       IS '기술 이름';
COMMENT ON COLUMN gold_label.tech_id    IS '기술ID (job.tech, 사전에 없으면 비움)';
COMMENT ON COLUMN gold_label.sha        IS '정답을 매길 때 본 commit (빈 표에 적힌 평가 commit, 다른 commit 의 정답은 따로 남는다)';
COMMENT ON COLUMN gold_label.cond_id    IS '대상 (LV 기술 LV/L0-01~L5-07 조건/personal_scope 개인 기여)';
COMMENT ON COLUMN gold_label.expected   IS '정답 (LV: 미확인·LV0~LV5, 조건: 충족·미충족·근거 부족·충돌)';
COMMENT ON COLUMN gold_label.case_tag   IS '경계 사례 표시 (예: CI 없이 결과 파일만, CI 실패, 다른 commit 의 CI)';
COMMENT ON COLUMN gold_label.note       IS '메모 (그렇게 본 이유)';
COMMENT ON COLUMN gold_label.labeler    IS '정답을 적은 사람';
COMMENT ON COLUMN gold_label.labeled_at IS '처음 넣은 시각 (같은 값을 다시 넣으면 그대로, 판정보다 늦으면 결과를 보고 적었을 수 있음)';

-- ============================================================ 색인
-- PostgreSQL 은 FK 칸에 색인을 자동으로 만들지 않는다. 자주 잇거나 거르는 칸에 만든다.
-- own_commit·eval_commit·evidence_line·external_pr_repo·finding·risk_item·stat_tech 는 job.tech_capability 처럼 복합 PK 가 그 표의 정체라 id 를 따로 두지 않는다(BE 의 JPA 가 이 표를 직접 쓰게 되면 id 를 더할지 정한다 — 미정).

CREATE UNIQUE INDEX account_login_ci ON account (lower(login));        -- 계정 이름은 대소문자를 무시한다
CREATE INDEX ON collect_run (account_id);
CREATE INDEX ON repo (run_id);
CREATE INDEX ON assessment (run_id);
CREATE UNIQUE INDEX assessment_one_current
    ON assessment (run_id, tech, repo) WHERE is_current;               -- 수집 × 기술 × 레포마다 '현재 사용'은 최대 하나
CREATE INDEX ON assessment (input_hash);                               -- 같은 입력이면 저장된 LLM 답을 다시 쓴다
CREATE INDEX ON assessment (shadow_of);
CREATE INDEX ON assessment (reused_from);
CREATE INDEX ON assessment (run_id, repo);                             -- repo 로 잇는 FK
CREATE INDEX assessment_review_queue
    ON assessment (created_at)
    WHERE review_reasons <> '[]'::jsonb AND review_result IS NULL;     -- 사람이 확인할 목록(승급 보류·그림자 실행 불일치 등)
CREATE INDEX ON assessment (tech_id);
CREATE INDEX ON stat (run_id);
CREATE INDEX ON stat_tech (tech_id);                                   -- 기술별 공고 매칭
CREATE INDEX ON gold_label (account_id);
CREATE INDEX ON gold_label (tech_id);

-- ============================================================ 보기 (제안)
-- 공고 적합도는 이 보기를 job.requirement · job.requirement_tech 와 이어 계산한다. 그 계산에 필요한데 아직 없는 것(미정):
-- job 쪽 요구 LV 칸(요건마다 LV0~5), 기술 이름 대신 tech_id 로 잇는 근거(사전에 없는 기술은 비교 불가), 동의를 철회한 계정의 결과를 뺄지.

CREATE VIEW current_assessment AS
SELECT a.*
FROM assessment a
WHERE a.is_current
  AND a.run_id = (SELECT max(r2.id) FROM collect_run r2
                  WHERE r2.account_id = (SELECT r.account_id FROM collect_run r WHERE r.id = a.run_id) AND r2.stopped IS NULL);
COMMENT ON VIEW current_assessment IS '계정마다 끝까지 마친 최신 수집의 현재 판정 (is_current 는 수집 실행 안에서만 하나라서, 계정 기준 최신은 이 보기로 본다)';

CREATE VIEW latest_stat_tech AS
SELECT r.account_id, s.id AS stat_id, t.tech, t.tech_id, t.level
FROM stat s
JOIN collect_run r ON r.id = s.run_id
JOIN stat_tech t ON t.stat_id = s.id
WHERE s.id = (SELECT max(s2.id) FROM stat s2 JOIN collect_run r2 ON r2.id = s2.run_id WHERE r2.account_id = r.account_id);
COMMENT ON VIEW latest_stat_tech IS '계정마다 가장 최근 STAT 의 기술별 LV';
COMMENT ON COLUMN latest_stat_tech.account_id IS '계정ID';
COMMENT ON COLUMN latest_stat_tech.stat_id    IS 'STAT ID';
COMMENT ON COLUMN latest_stat_tech.tech       IS '기술 이름';
COMMENT ON COLUMN latest_stat_tech.tech_id    IS '기술ID (job.tech, 사전에 없으면 비움)';
COMMENT ON COLUMN latest_stat_tech.level      IS '기술 LV (비우면 미확인)';

CREATE VIEW capability_level AS
WITH RECURSIVE reach (account_id, tech_id, level, capability_id) AS (
    SELECT l.account_id, l.tech_id, l.level, tc.capability_id
    FROM latest_stat_tech l
    JOIN job.tech_capability tc ON tc.tech_id = l.tech_id
    UNION
    SELECT r.account_id, r.tech_id, r.level, c.parent_id                -- 상위 능력으로 올라간다(관계형 DB → 데이터베이스)
    FROM reach r
    JOIN job.capability c ON c.id = r.capability_id
    WHERE c.parent_id IS NOT NULL
)
SELECT account_id, capability_id, max(level) AS level, count(DISTINCT tech_id) AS techs
FROM reach
GROUP BY account_id, capability_id;
COMMENT ON VIEW capability_level IS '능력별 내 LV (그 능력이나 하위 능력에 속한 기술 LV 중 최고, 모두 미확인이면 비움 — 공고 요건이 능력 단위라 쓴다, 제안. 상위 기술(EC2 → AWS)을 충족으로 볼지는 미정)';
COMMENT ON COLUMN capability_level.account_id    IS '계정ID';
COMMENT ON COLUMN capability_level.capability_id IS '능력ID (job.capability)';
COMMENT ON COLUMN capability_level.level         IS '능력 LV (속한 기술 LV 중 최고, 비우면 미확인)';
COMMENT ON COLUMN capability_level.techs         IS '그 능력으로 묶인 내 기술 수';

COMMIT;
