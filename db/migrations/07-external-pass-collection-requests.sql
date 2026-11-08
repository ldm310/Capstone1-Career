-- Run through external_pass_crawler.migrate, after the canonical init/04 schema.
-- Only external_data objects are added. Existing public rows and objects are untouched.
CREATE TABLE IF NOT EXISTS external_data.collection_request (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    target_posting_id BIGINT NOT NULL REFERENCES public.posting(id) ON DELETE RESTRICT,
    target_recruit_unit_id BIGINT NOT NULL REFERENCES public.recruit_unit(id) ON DELETE RESTRICT,
    standard_role_code TEXT,
    policy_version TEXT NOT NULL CHECK (btrim(policy_version) <> ''),
    selection_status TEXT NOT NULL CHECK (selection_status IN ('SELECTED','NO_CANDIDATES','NOT_COMPARABLE')),
    request_source TEXT NOT NULL CHECK (request_source IN ('MANUAL_BATCH','POSTING_SAVED')),
    used_direct BOOLEAN NOT NULL DEFAULT false,
    requested_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (target_recruit_unit_id, policy_version)
);

CREATE TABLE IF NOT EXISTS external_data.collection_candidate (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    request_id BIGINT NOT NULL REFERENCES external_data.collection_request(id) ON DELETE RESTRICT,
    candidate_posting_id BIGINT NOT NULL REFERENCES public.posting(id) ON DELETE RESTRICT,
    candidate_recruit_unit_id BIGINT NOT NULL REFERENCES public.recruit_unit(id) ON DELETE RESTRICT,
    candidate_company_id BIGINT NOT NULL REFERENCES public.company(id) ON DELETE RESTRICT,
    standard_role_code TEXT NOT NULL CHECK (btrim(standard_role_code) <> ''),
    confidence TEXT NOT NULL CHECK (confidence IN ('HIGH','LOW')),
    feature_mode TEXT NOT NULL CHECK (feature_mode IN ('REQUIRED','FALLBACK_FEATURES')),
    evidence_count INTEGER NOT NULL CHECK (evidence_count >= 2),
    candidate_rank INTEGER NOT NULL CHECK (candidate_rank > 0),
    is_selected BOOLEAN NOT NULL DEFAULT true,
    requested BOOLEAN NOT NULL DEFAULT false,
    reused BOOLEAN NOT NULL DEFAULT false,
    requested_at TIMESTAMPTZ,
    UNIQUE (request_id, candidate_recruit_unit_id)
);
CREATE INDEX IF NOT EXISTS collection_candidate_company_idx
    ON external_data.collection_candidate(candidate_company_id, is_selected, requested);

CREATE OR REPLACE FUNCTION external_data.check_collection_provenance() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog AS $$
DECLARE target_posting BIGINT; target_company BIGINT; candidate_company BIGINT;
        unit_posting BIGINT; unit_current BOOLEAN; unit_it BOOLEAN; target_role TEXT;
BEGIN
    IF TG_TABLE_NAME = 'collection_request' THEN
        SELECT r.posting_id INTO unit_posting FROM public.recruit_unit u
            JOIN public.extraction_run r ON r.id=u.run_id WHERE u.id=NEW.target_recruit_unit_id;
        IF unit_posting IS DISTINCT FROM NEW.target_posting_id THEN
            RAISE EXCEPTION 'Target unit ownership mismatch' USING ERRCODE='23514';
        END IF;
    ELSE
        SELECT q.target_posting_id,p.company_id,q.standard_role_code
            INTO target_posting,target_company,target_role
            FROM external_data.collection_request q JOIN public.posting p ON p.id=q.target_posting_id
            WHERE q.id=NEW.request_id FOR SHARE OF q,p;
        SELECT p.company_id INTO candidate_company FROM public.posting p
            WHERE p.id=NEW.candidate_posting_id FOR SHARE;
        SELECT r.posting_id,r.is_current,u.is_it INTO unit_posting,unit_current,unit_it
            FROM public.recruit_unit u JOIN public.extraction_run r ON r.id=u.run_id
            WHERE u.id=NEW.candidate_recruit_unit_id FOR SHARE OF u,r;
        IF candidate_company IS DISTINCT FROM NEW.candidate_company_id
           OR candidate_company IS NOT DISTINCT FROM target_company
           OR unit_posting IS DISTINCT FROM NEW.candidate_posting_id
           OR target_role IS DISTINCT FROM NEW.standard_role_code
           OR (NEW.is_selected AND (NOT coalesce(unit_current,false) OR NOT coalesce(unit_it,false))) THEN
            RAISE EXCEPTION 'Candidate provenance mismatch' USING ERRCODE='23514';
        END IF;
    END IF;
    RETURN NEW;
END;
$$;

DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgrelid='external_data.collection_request'::regclass
                   AND tgname='collection_request_provenance_guard') THEN
        CREATE TRIGGER collection_request_provenance_guard BEFORE INSERT OR UPDATE
            ON external_data.collection_request FOR EACH ROW
            EXECUTE FUNCTION external_data.check_collection_provenance();
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgrelid='external_data.collection_candidate'::regclass
                   AND tgname='collection_candidate_provenance_guard') THEN
        CREATE TRIGGER collection_candidate_provenance_guard BEFORE INSERT OR UPDATE
            ON external_data.collection_candidate FOR EACH ROW
            EXECUTE FUNCTION external_data.check_collection_provenance();
    END IF;
END $$;

COMMENT ON TABLE external_data.collection_request IS
    'Read-only Backend selection provenance; registration belongs to the separate batch, never GET';
COMMENT ON TABLE external_data.collection_candidate IS
    'Cross-company reference provenance only; materials remain linked to their own company postings';
