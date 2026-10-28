-- 임시 사용자 역량 스키마
-- 실행 순서: 01-job-schema.sql 실행 후 이 파일을 실행한다.
-- 별도의 skill 테이블을 만들지 않고 표준화 사전의 job.capability를 참조한다.

BEGIN;

CREATE SCHEMA IF NOT EXISTS profile;

-- PostgreSQL의 USER 키워드와 충돌하지 않도록 테이블명을 app_user로 사용한다.
CREATE TABLE IF NOT EXISTS profile.app_user (
    user_id      BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    email        TEXT        NOT NULL UNIQUE,
    name         TEXT        NOT NULL,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

COMMENT ON TABLE profile.app_user IS '사용자';
COMMENT ON COLUMN profile.app_user.user_id IS '사용자 ID';
COMMENT ON COLUMN profile.app_user.email IS '이메일';
COMMENT ON COLUMN profile.app_user.name IS '사용자 이름';
COMMENT ON COLUMN profile.app_user.created_at IS '생성 시각';
COMMENT ON COLUMN profile.app_user.updated_at IS '수정 시각';

CREATE TABLE IF NOT EXISTS profile.project (
    project_id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id                 BIGINT NOT NULL
                            REFERENCES profile.app_user(user_id) ON DELETE CASCADE,
    project_name            TEXT        NOT NULL,
    repository_url          TEXT,
    description_file_path   TEXT,
    description_file_type   VARCHAR(50),
    created_at              TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

COMMENT ON TABLE profile.project IS '사용자 프로젝트';
COMMENT ON COLUMN profile.project.project_id IS '프로젝트 ID';
COMMENT ON COLUMN profile.project.user_id IS '프로젝트 소유 사용자 ID';
COMMENT ON COLUMN profile.project.project_name IS '프로젝트 이름';
COMMENT ON COLUMN profile.project.repository_url IS 'GitHub 등 저장소 주소';
COMMENT ON COLUMN profile.project.description_file_path IS 'PDF, Markdown 등 설명 파일 위치';
COMMENT ON COLUMN profile.project.description_file_type IS '설명 파일 형식';
COMMENT ON COLUMN profile.project.created_at IS '생성 시각';
COMMENT ON COLUMN profile.project.updated_at IS '수정 시각';

CREATE TABLE IF NOT EXISTS profile.user_skill_evaluation (
    evaluation_id    BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    project_id       BIGINT NOT NULL
                     REFERENCES profile.project(project_id) ON DELETE CASCADE,
    capability_id    BIGINT NOT NULL
                     REFERENCES job.capability(id) ON DELETE RESTRICT,
    confirmed_score  SMALLINT NOT NULL
                     CHECK (confirmed_score BETWEEN 0 AND 100),
    evaluated_at     TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    -- 임시 버전에서는 프로젝트별 능력 하나에 최신 평가 하나만 저장한다.
    UNIQUE (project_id, capability_id)
);

COMMENT ON TABLE profile.user_skill_evaluation IS '프로젝트 기반 사용자 역량 평가';
COMMENT ON COLUMN profile.user_skill_evaluation.evaluation_id IS '평가 ID';
COMMENT ON COLUMN profile.user_skill_evaluation.project_id IS '평가 대상 프로젝트 ID';
COMMENT ON COLUMN profile.user_skill_evaluation.capability_id IS '표준화 사전의 능력 ID';
COMMENT ON COLUMN profile.user_skill_evaluation.confirmed_score IS '확정 역량 점수, 0~100';
COMMENT ON COLUMN profile.user_skill_evaluation.evaluated_at IS '평가 시각';

CREATE INDEX IF NOT EXISTS idx_profile_project_user
    ON profile.project(user_id);

CREATE INDEX IF NOT EXISTS idx_profile_evaluation_project
    ON profile.user_skill_evaluation(project_id);

CREATE INDEX IF NOT EXISTS idx_profile_evaluation_capability
    ON profile.user_skill_evaluation(capability_id);

COMMIT;

