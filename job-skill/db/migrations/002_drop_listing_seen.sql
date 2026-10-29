-- 2026-10-29 버린 공고 표를 뺀다(사용자 결정). '연속 5개 멈춤'을 없앤 뒤로 쓸 곳이 없다 —
-- 새 공고 = 목록 − DB 에 있는 공고, 버린 공고(교육생 등)는 매일 목록 글로 다시 거른다. 여러 번 돌려도 안전.
BEGIN;
SET LOCAL search_path TO job;
DROP TABLE IF EXISTS listing_seen;
COMMIT;
