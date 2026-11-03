-- Existing databases: apply this file once after 01/02. No extraction rows are changed.
BEGIN;
CREATE TABLE IF NOT EXISTS profile.comparison_target (
    unit_id BIGINT PRIMARY KEY REFERENCES job.recruit_unit(id) ON DELETE CASCADE,
    role_group TEXT NOT NULL,
    career_band TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS profile.successful_application (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES profile.app_user(user_id) ON DELETE CASCADE,
    company_id BIGINT NOT NULL REFERENCES job.company(id),
    posting_id BIGINT NOT NULL REFERENCES job.posting(id),
    role_group TEXT NOT NULL,
    career_band TEXT NOT NULL,
    stage TEXT NOT NULL CHECK (stage IN ('APPLIED','DOCUMENT_PASSED','INTERVIEW_PASSED','FINAL_PASSED')),
    verified BOOLEAN NOT NULL DEFAULT FALSE,
    accepted_at DATE NOT NULL,
    UNIQUE(user_id, posting_id, role_group, career_band)
);
CREATE INDEX IF NOT EXISTS successful_application_comparison_idx
    ON profile.successful_application(role_group, career_band, accepted_at, company_id) WHERE verified;
COMMIT;
