BEGIN;
ALTER TABLE public.career_lv_member ADD COLUMN IF NOT EXISTS app_role TEXT NOT NULL DEFAULT 'MEMBER'
  CHECK (app_role IN ('MEMBER','ADMIN'));
ALTER TABLE public.career_lv_member ADD COLUMN IF NOT EXISTS preview_enabled BOOLEAN NOT NULL DEFAULT FALSE;
CREATE TABLE IF NOT EXISTS public.career_notice (
  id TEXT NOT NULL,
  namespace TEXT NOT NULL,
  title TEXT NOT NULL CHECK (length(title) BETWEEN 1 AND 120),
  content TEXT NOT NULL CHECK (length(content) BETWEEN 1 AND 12000),
  author_id TEXT NOT NULL,
  author_name TEXT NOT NULL,
  pinned BOOLEAN NOT NULL DEFAULT FALSE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  deleted_at TIMESTAMPTZ,
  PRIMARY KEY(namespace,id),
  FOREIGN KEY(namespace,author_id) REFERENCES public.career_lv_member(namespace,subject_id)
);
CREATE INDEX IF NOT EXISTS career_notice_list_idx ON public.career_notice(namespace,pinned DESC,created_at DESC) WHERE deleted_at IS NULL;
COMMIT;
