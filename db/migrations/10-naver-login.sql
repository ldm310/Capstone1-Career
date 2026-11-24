BEGIN;
ALTER TABLE public.career_account_oauth DROP CONSTRAINT IF EXISTS career_account_oauth_provider_check;
ALTER TABLE public.career_account_oauth ADD CONSTRAINT career_account_oauth_provider_check CHECK (provider IN ('kakao','naver'));
COMMIT;
