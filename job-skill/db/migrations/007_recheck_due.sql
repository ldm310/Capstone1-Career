-- 2026-11-01 '수정'으로 고른 공고의 확인·다시 저장이 실패하면 다음 날 다시 고르게(사용자 결정).
-- 사람인 '수정' 표시는 하루쯤 뒤 사라져서, 실패한 공고를 DB 에 표시해 둔다. 여러 번 돌려도 안전.
BEGIN;
SET LOCAL search_path TO public;
ALTER TABLE posting ADD COLUMN IF NOT EXISTS recheck_due boolean NOT NULL DEFAULT false;
COMMENT ON COLUMN posting.recheck_due       IS '다시 확인할 공고 (''수정''으로 골랐는데 아직 확인·다시 저장을 못 함 — 사람인 수정 표시가 하루 뒤 사라져도 다음 날 다시 고른다)';
COMMIT;
