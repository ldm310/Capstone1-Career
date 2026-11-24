BEGIN;
CREATE TABLE IF NOT EXISTS public.career_extraction_review (
  id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  namespace TEXT NOT NULL,
  site TEXT NOT NULL DEFAULT '사람인',
  posting_no TEXT NOT NULL,
  company TEXT NOT NULL DEFAULT '',
  title TEXT NOT NULL DEFAULT '',
  source_url TEXT NOT NULL DEFAULT '',
  stage TEXT NOT NULL DEFAULT 'EXTRACTION',
  error_code VARCHAR(160) NOT NULL DEFAULT '',
  failure_count INTEGER NOT NULL DEFAULT 0 CHECK (failure_count >= 0),
  status TEXT NOT NULL DEFAULT 'OPEN' CHECK (status IN ('OPEN','SKIPPED','RETRY_REQUESTED','RUNNING','RESOLVED')),
  feedback TEXT NOT NULL DEFAULT '' CHECK (length(feedback) <= 2000),
  actor_name TEXT,
  request_id TEXT,
  attempt_id TEXT,
  claimed_at TIMESTAMPTZ,
  last_failed_at TIMESTAMPTZ,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  revision INTEGER NOT NULL DEFAULT 0,
  UNIQUE(namespace,site,posting_no)
);
CREATE INDEX IF NOT EXISTS career_extraction_review_queue_idx ON public.career_extraction_review(namespace,status,updated_at DESC,id);
CREATE TABLE IF NOT EXISTS public.career_extraction_review_event (
  id TEXT PRIMARY KEY,
  review_id BIGINT NOT NULL REFERENCES public.career_extraction_review(id) ON DELETE CASCADE,
  action TEXT NOT NULL CHECK (action IN ('PASS','RETRY','START','FAIL','RESOLVE')),
  feedback TEXT NOT NULL DEFAULT '',
  actor_id TEXT,
  actor_name TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
COMMIT;
