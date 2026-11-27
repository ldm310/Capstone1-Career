-- Web publication controls are independent of extraction_run review decisions.
BEGIN;
CREATE TABLE IF NOT EXISTS public.career_posting_visibility (
  id BIGSERIAL PRIMARY KEY,
  namespace TEXT NOT NULL,
  posting_id BIGINT NOT NULL REFERENCES public.posting(id) ON DELETE CASCADE,
  hidden BOOLEAN NOT NULL DEFAULT FALSE,
  revision INTEGER NOT NULL DEFAULT 1 CHECK (revision > 0),
  changed_by TEXT NOT NULL,
  changed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE(namespace, posting_id)
);
COMMIT;
