-- Owned external-material tables only. Never modify pipeline company/posting/dictionary tables.
ALTER TABLE public.external_pass_company_collection ALTER COLUMN minimum_sample_size SET DEFAULT 2;
UPDATE public.external_pass_company_collection c
SET minimum_sample_size=2,
    status=CASE WHEN status IN ('READY','INSUFFICIENT') THEN
        CASE WHEN (SELECT count(*) FROM public.external_pass_material m WHERE m.company_id=c.company_id AND m.job_family='IT_SW')>=2
            THEN 'READY' ELSE 'INSUFFICIENT' END ELSE status END,
    updated_at=now();

CREATE TABLE public.external_pass_material_body (
    material_id BIGINT PRIMARY KEY REFERENCES public.external_pass_material(id) ON DELETE CASCADE,
    plain_text TEXT NOT NULL CHECK (length(btrim(plain_text)) BETWEEN 1 AND 200000),
    content_sha256 TEXT NOT NULL CHECK (content_sha256 ~ '^[0-9a-f]{64}$'),
    extraction_status TEXT NOT NULL DEFAULT 'PENDING' CHECK (extraction_status IN ('PENDING','EXTRACTED','FAILED')),
    collected_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
COMMENT ON TABLE public.external_pass_material_body IS 'Essay paragraphs for future extraction; excluded from public APIs and logs; not fully anonymized';

CREATE TABLE public.external_pass_daily_company (
    source_platform TEXT NOT NULL CHECK (source_platform='linkareer'),
    company_id BIGINT NOT NULL REFERENCES public.company(id),
    last_attempt_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY(source_platform,company_id)
);
CREATE TABLE public.external_pass_daily_run (
    source_platform TEXT NOT NULL CHECK (source_platform='linkareer'),
    run_date DATE NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('RUNNING','SUCCEEDED','FAILED','BLOCKED')),
    started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at TIMESTAMPTZ,
    report JSONB NOT NULL DEFAULT '{}',
    PRIMARY KEY(source_platform,run_date)
);
