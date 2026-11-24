-- $1 is the web/pipeline namespace. Preserve decisions for the same extraction run.
INSERT INTO public.career_extraction_review AS saved
  (namespace,site,posting_no,company,title,source_url,stage,error_code,source_run_id,review_reasons)
SELECT $1,site,posting_no,company,title,source_url,'REVIEW',error_code,source_run_id,review_reasons
FROM public.career_extraction_review_candidates
ON CONFLICT(namespace,site,posting_no) DO UPDATE SET
  company=EXCLUDED.company,title=EXCLUDED.title,source_url=EXCLUDED.source_url,
  stage='REVIEW',error_code=EXCLUDED.error_code,source_run_id=EXCLUDED.source_run_id,review_reasons=EXCLUDED.review_reasons,
  status=CASE WHEN saved.source_run_id IS DISTINCT FROM EXCLUDED.source_run_id THEN 'OPEN' ELSE saved.status END,
  request_id=CASE WHEN saved.source_run_id IS DISTINCT FROM EXCLUDED.source_run_id THEN NULL ELSE saved.request_id END,
  revision=saved.revision+1,updated_at=now()
WHERE saved.status<>'RUNNING' AND
  (saved.source_run_id IS DISTINCT FROM EXCLUDED.source_run_id OR saved.review_reasons IS DISTINCT FROM EXCLUDED.review_reasons OR saved.stage<>'REVIEW');
