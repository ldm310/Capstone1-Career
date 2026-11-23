-- Additive migration. Does not modify crawler data or existing profile tables.
BEGIN;

CREATE TABLE IF NOT EXISTS public.career_lv_member (
    namespace TEXT NOT NULL,
    subject_id TEXT NOT NULL,
    is_demo BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY(namespace, subject_id)
);
CREATE TABLE IF NOT EXISTS public.career_lv_analysis_source (
    namespace TEXT NOT NULL,
    subject_id TEXT NOT NULL,
    source_id TEXT NOT NULL,
    kind TEXT NOT NULL CHECK (kind IN ('GITHUB', 'PDF')),
    title TEXT NOT NULL,
    locator TEXT NOT NULL,
    is_simulated BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY(namespace, subject_id, source_id),
    FOREIGN KEY(namespace, subject_id) REFERENCES public.career_lv_member ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS public.career_lv_posting_keyword_level (
    namespace TEXT NOT NULL,
    subject_id TEXT NOT NULL,
    job_id TEXT NOT NULL,
    keyword_id TEXT NOT NULL,
    taxonomy_version TEXT NOT NULL,
    keyword_text TEXT NOT NULL,
    category_codes TEXT[] NOT NULL CHECK (cardinality(category_codes) > 0),
    score SMALLINT NOT NULL CHECK (score BETWEEN 0 AND 100),
    reference_score SMALLINT CHECK (reference_score BETWEEN 0 AND 100),
    reference_kind TEXT CHECK (reference_kind IN ('SYNTHETIC_APPLICANTS', 'VERIFIED_APPLICANTS', 'REQUIREMENT')),
    evidence_source_ids TEXT[] NOT NULL CHECK (cardinality(evidence_source_ids) > 0),
    evaluation_kind TEXT NOT NULL CHECK (evaluation_kind IN ('DEMO', 'CONFIRMED')),
    method_version TEXT NOT NULL,
    evaluated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY(namespace, subject_id, job_id, keyword_id, taxonomy_version),
    FOREIGN KEY(namespace, subject_id) REFERENCES public.career_lv_member ON DELETE CASCADE,
    CHECK ((reference_score IS NULL) = (reference_kind IS NULL))
);
COMMENT ON TABLE public.career_lv_posting_keyword_level IS
    'Session subject scoped posting/keyword LV snapshots. DEMO is never a real proficiency assessment. 0..100 display scale; no new LV rubric.';
COMMIT;
