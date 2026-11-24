-- Apply after 01-job-schema.sql. Additive: no changes to collection/extraction tables.
BEGIN;
CREATE SCHEMA IF NOT EXISTS external_data;

CREATE TABLE external_data.pass_material (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    company_id BIGINT NOT NULL REFERENCES public.company(id) ON DELETE RESTRICT,
    source_platform TEXT NOT NULL CHECK (source_platform = lower(btrim(source_platform)) AND source_platform <> ''),
    external_record_id TEXT NOT NULL CHECK (external_record_id = btrim(external_record_id) AND external_record_id <> ''),
    job_family TEXT NOT NULL DEFAULT 'IT_SW' CHECK (job_family = 'IT_SW'),
    role_name TEXT NOT NULL CHECK (btrim(role_name) <> ''),
    title TEXT NOT NULL CHECK (btrim(title) <> ''),
    content TEXT NOT NULL CHECK (btrim(content) <> ''),
    source_url TEXT NOT NULL CHECK (source_url ~ '^https?://'),
    published_at TIMESTAMPTZ,
    collected_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (source_platform, external_record_id)
);
CREATE INDEX pass_material_company_idx ON external_data.pass_material(company_id);

CREATE TABLE external_data.company_collection (
    company_id BIGINT PRIMARY KEY REFERENCES public.company(id) ON DELETE RESTRICT,
    status TEXT NOT NULL DEFAULT 'PENDING'
        CHECK (status IN ('PENDING', 'RUNNING', 'READY', 'INSUFFICIENT', 'FAILED')),
    minimum_sample_size INTEGER NOT NULL DEFAULT 5 CHECK (minimum_sample_size > 0),
    attempt_count INTEGER NOT NULL DEFAULT 0 CHECK (attempt_count >= 0),
    requested_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    error_code VARCHAR(100),
    error_message TEXT,
    CHECK (status <> 'RUNNING' OR (started_at IS NOT NULL AND completed_at IS NULL)),
    CHECK (status NOT IN ('READY', 'INSUFFICIENT', 'FAILED') OR completed_at IS NOT NULL),
    CHECK (status <> 'FAILED' OR error_code IS NOT NULL)
);
CREATE INDEX company_collection_queue_idx ON external_data.company_collection(status, requested_at);

CREATE TABLE external_data.posting_pass_material (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    posting_id BIGINT NOT NULL REFERENCES public.posting(id) ON DELETE CASCADE,
    material_id BIGINT NOT NULL REFERENCES external_data.pass_material(id) ON DELETE RESTRICT,
    relation_type TEXT NOT NULL
        CHECK (relation_type IN ('EXACT_ROLE', 'SAME_JOB_FAMILY', 'SAME_IT_DOMAIN', 'EXCLUDED')),
    linked_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (posting_id, material_id)
);
CREATE INDEX posting_pass_material_material_idx ON external_data.posting_pass_material(material_id);

-- Direct DB writers must satisfy the same-company restriction too.
CREATE FUNCTION external_data.check_material_company() RETURNS trigger LANGUAGE plpgsql
SECURITY DEFINER SET search_path = pg_catalog AS $$
DECLARE posting_company BIGINT; material_company BIGINT;
BEGIN
    SELECT company_id INTO posting_company FROM public.posting WHERE id = NEW.posting_id FOR SHARE;
    SELECT company_id INTO material_company FROM external_data.pass_material WHERE id = NEW.material_id FOR SHARE;
    IF posting_company IS NULL OR material_company IS NULL OR posting_company <> material_company THEN
        RAISE EXCEPTION 'External material must belong to the posting company' USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END;
$$;
CREATE TRIGGER posting_pass_material_company_guard
    BEFORE INSERT OR UPDATE ON external_data.posting_pass_material
    FOR EACH ROW EXECUTE FUNCTION external_data.check_material_company();

-- Preserve the company identity of an external source record, including during upserts.
CREATE FUNCTION external_data.keep_material_company() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.company_id <> OLD.company_id THEN
        RAISE EXCEPTION 'External material company cannot be changed' USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END;
$$;
CREATE TRIGGER pass_material_company_immutable BEFORE UPDATE ON external_data.pass_material
    FOR EACH ROW EXECUTE FUNCTION external_data.keep_material_company();

COMMENT ON SCHEMA external_data IS 'External pass materials: written by data-pipeline, read by BE';
COMMENT ON TABLE external_data.pass_material IS 'Same-company IT/SW external materials, not verified service-user evaluations';
COMMENT ON TABLE external_data.company_collection IS 'One shared collection task per company; no row means not requested';
COMMENT ON TABLE external_data.posting_pass_material IS 'Explicit posting-to-material reference set; never market fallback';
COMMENT ON COLUMN external_data.posting_pass_material.relation_type IS 'Relation to this posting only; EXCLUDED links are not returned as comparison materials';
COMMIT;
