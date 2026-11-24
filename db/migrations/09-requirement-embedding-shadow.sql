-- Installed only by requirement_embeddings.migrate; placeholders are fixed allowlisted replacements.
CREATE TABLE public.be_embedding_schema_migration (
    version TEXT PRIMARY KEY, checksum TEXT NOT NULL, storage_backend TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE public.be_embedding_request (
    id UUID PRIMARY KEY, model_name TEXT NOT NULL, model_revision TEXT NOT NULL,
    embedding_dimension INTEGER NOT NULL CHECK(embedding_dimension>0), preprocessing_version TEXT NOT NULL,
    input_hashes TEXT[] NOT NULL, status TEXT NOT NULL CHECK(status IN ('IN_FLIGHT','READY','FAILED','UNKNOWN')),
    error_code TEXT CHECK(error_code IS NULL OR error_code IN ('AUTH_FAILED','RATE_LIMITED','DELIVERY_UNCERTAIN','API_REJECTED','RESPONSE_MAPPING_INVALID','MODEL_MISMATCH','DIMENSION_MISMATCH','INVALID_VECTOR','DB_SAVE_FAILED')),
    prompt_tokens BIGINT NOT NULL DEFAULT 0 CHECK(prompt_tokens>=0),
    api_calls INTEGER NOT NULL DEFAULT 1 CHECK(api_calls=1), estimated_cost_usd NUMERIC,
    price_per_million_tokens NUMERIC, pricing_version TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(), updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE public.be_embedding_cache (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    model_name TEXT NOT NULL, model_revision TEXT NOT NULL,
    embedding_dimension INTEGER NOT NULL CHECK(embedding_dimension>0), preprocessing_version TEXT NOT NULL,
    input_hash TEXT NOT NULL CHECK(input_hash ~ '^[0-9a-f]{64}$'), input_text TEXT NOT NULL,
    embedding __EMBEDDING_TYPE__,
    status TEXT NOT NULL CHECK(status IN ('IN_FLIGHT','READY','FAILED','UNKNOWN')),
    error_code TEXT CHECK(error_code IS NULL OR error_code IN ('AUTH_FAILED','RATE_LIMITED','DELIVERY_UNCERTAIN','API_REJECTED','RESPONSE_MAPPING_INVALID','MODEL_MISMATCH','DIMENSION_MISMATCH','INVALID_VECTOR','DB_SAVE_FAILED')),
    request_id UUID NOT NULL REFERENCES public.be_embedding_request(id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(), updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(model_name,model_revision,embedding_dimension,preprocessing_version,input_hash),
    UNIQUE(id,model_name,model_revision,embedding_dimension,preprocessing_version,input_hash),
    CHECK((status='READY')=(embedding IS NOT NULL)),
    CHECK(embedding IS NULL OR (__DIMENSION_CHECK__))
);
CREATE TABLE public.be_requirement_embedding (
    requirement_id BIGINT NOT NULL REFERENCES public.requirement(id) ON DELETE CASCADE,
    recruit_unit_id BIGINT NOT NULL REFERENCES public.recruit_unit(id) ON DELETE CASCADE,
    source_run_id BIGINT NOT NULL, category TEXT NOT NULL CHECK(category IN ('REQUIRED','PREFERRED','DUTIES')),
    role_code TEXT, source_fingerprint TEXT NOT NULL, taxonomy_hash TEXT NOT NULL,
    model_name TEXT NOT NULL, model_revision TEXT NOT NULL, embedding_dimension INTEGER NOT NULL,
    preprocessing_version TEXT NOT NULL, input_hash TEXT, cache_id BIGINT,
    eligibility TEXT NOT NULL CHECK(eligibility IN ('ELIGIBLE','EXCLUDED')), exclusion_code TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(), updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY(requirement_id,model_name,model_revision,embedding_dimension,preprocessing_version),
    FOREIGN KEY(cache_id,model_name,model_revision,embedding_dimension,preprocessing_version,input_hash)
        REFERENCES public.be_embedding_cache(id,model_name,model_revision,embedding_dimension,preprocessing_version,input_hash),
    CHECK((eligibility='ELIGIBLE' AND cache_id IS NOT NULL AND input_hash IS NOT NULL AND exclusion_code IS NULL)
        OR (eligibility='EXCLUDED' AND cache_id IS NULL AND input_hash IS NULL AND exclusion_code IS NOT NULL))
);
CREATE INDEX be_requirement_embedding_unit_idx ON public.be_requirement_embedding(recruit_unit_id);

CREATE VIEW public.be_embedding_source AS
WITH linked_tech AS (
    SELECT DISTINCT rt.requirement_id,t.id,t.name FROM public.requirement_tech rt
    JOIN public.tech t ON t.id=rt.tech_id WHERE t.is_active
), techs AS (
    SELECT requirement_id,array_agg(id ORDER BY id) AS tech_ids,
        array_agg(name ORDER BY name COLLATE "C") AS tech_names FROM linked_tech GROUP BY requirement_id
)
SELECT q.id AS requirement_id,u.id AS recruit_unit_id,r.id AS source_run_id,
    CASE i.category WHEN '필수' THEN 'REQUIRED' WHEN '우대' THEN 'PREFERRED' WHEN '업무' THEN 'DUTIES' END AS category,
    u.name AS unit_name,p.title AS posting_title,p.site_job_category,co.name AS company_name,
    i.text AS item_text,c.name AS capability_name,c.is_active AS capability_active,
    coalesce(techs.tech_names,ARRAY[]::TEXT[]) AS tech_names,
    md5(jsonb_build_array(r.id,u.id,u.name,p.title,p.site_job_category,co.name,i.category,i.text,
        c.id,c.name,c.is_active,coalesce(techs.tech_ids,ARRAY[]::BIGINT[]),coalesce(techs.tech_names,ARRAY[]::TEXT[]))::text) AS source_fingerprint
FROM public.requirement q JOIN public.unit_item i ON i.id=q.item_id
JOIN public.recruit_unit u ON u.id=i.unit_id JOIN public.extraction_run r ON r.id=u.run_id
JOIN public.posting p ON p.id=r.posting_id JOIN public.company co ON co.id=p.company_id
JOIN public.capability c ON c.id=q.capability_id LEFT JOIN techs ON techs.requirement_id=q.id
WHERE r.is_current AND u.is_it AND i.category IN ('필수','우대','업무');

CREATE VIEW public.be_requirement_embedding_view AS
SELECT e.*,c.status AS embedding_status,c.error_code,c.embedding,c.embedding::text AS embedding_text
FROM public.be_requirement_embedding e LEFT JOIN public.be_embedding_cache c ON c.id=e.cache_id;
