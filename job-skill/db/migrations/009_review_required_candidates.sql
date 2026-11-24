BEGIN;
ALTER TABLE public.career_extraction_review ADD COLUMN IF NOT EXISTS source_run_id BIGINT;
ALTER TABLE public.career_extraction_review ADD COLUMN IF NOT EXISTS review_reasons JSONB NOT NULL DEFAULT '[]'::jsonb;
CREATE OR REPLACE VIEW public.career_extraction_review_candidates AS
SELECT p.site,p.site_posting_no AS posting_no,c.name AS company,p.title,
  CASE WHEN p.site='사람인' AND p.site_posting_no ~ '^[0-9]+$'
    THEN 'https://www.saramin.co.kr/zf_user/jobs/relay/view?rec_idx=' || p.site_posting_no ELSE '' END AS source_url,
  e.id AS source_run_id,e.review_reasons,
  left((SELECT string_agg(coalesce(reason->>'내용',reason::text),'; ' ORDER BY ordinal)
    FROM jsonb_array_elements(e.review_reasons) WITH ORDINALITY AS reasons(reason,ordinal)),160) AS error_code
FROM public.extraction_run e JOIN public.posting p ON p.id=e.posting_id JOIN public.company c ON c.id=p.company_id
WHERE e.is_current AND e.review_result IS NULL AND jsonb_array_length(e.review_reasons)>0;
-- Remove only untouched rows created by the former, incorrect no-extraction seed.
-- The source postings and any administrator action history are preserved.
DELETE FROM public.career_extraction_review r
WHERE stage='UNKNOWN' AND failure_count=0 AND status='OPEN' AND feedback='' AND source_run_id IS NULL
  AND NOT EXISTS(SELECT 1 FROM public.career_extraction_review_event e WHERE e.review_id=r.id);
COMMIT;
