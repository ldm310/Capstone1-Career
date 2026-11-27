-- Run manually ONLY after the new web deployment reports storage='extraction_run'
-- from its authenticated administrator GET /api/admin/extraction-reviews.
-- Not an automatic pipeline migration: the previous web release still needs these tables.
BEGIN;
SET LOCAL lock_timeout = '5s';
DO $$
BEGIN
  IF to_regclass('public.career_extraction_review') IS NOT NULL THEN
    LOCK TABLE public.career_extraction_review IN ACCESS EXCLUSIVE MODE;
    IF EXISTS (SELECT 1 FROM public.career_extraction_review
               WHERE status <> 'OPEN' OR feedback <> '' OR revision <> 0) THEN
      RAISE EXCEPTION 'Legacy review decisions must be preserved before retirement';
    END IF;
  END IF;
  IF to_regclass('public.career_extraction_review_event') IS NOT NULL THEN
    LOCK TABLE public.career_extraction_review_event IN ACCESS EXCLUSIVE MODE;
    IF EXISTS (SELECT 1 FROM public.career_extraction_review_event) THEN
      RAISE EXCEPTION 'Legacy review events must be preserved before retirement';
    END IF;
  END IF;
END $$;
DROP VIEW IF EXISTS public.career_extraction_review_candidates;
DROP TABLE IF EXISTS public.career_extraction_review_event;
DROP TABLE IF EXISTS public.career_extraction_review;
COMMIT;
