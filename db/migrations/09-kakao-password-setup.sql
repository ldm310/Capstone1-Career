BEGIN;
ALTER TABLE public.career_account_oauth ADD COLUMN IF NOT EXISTS password_set_at TIMESTAMPTZ;
COMMENT ON COLUMN public.career_account_oauth.password_set_at IS
  'Time the member selected a Career password. NULL on legacy Kakao-only accounts until setup is completed.';
COMMIT;
