-- 2026-11-24 사람 검토를 정상·제외·다시로 바꾸고 피드백 칸을 더한다(사용자 결정 — 팀원 별도 표 대신 추출 실행 표에).
--   정상: 결과 맞음 / 제외: 앞으로 자동 처리·웹에서 뺌 / 다시: 피드백을 붙여 다음 ① 때 다시 추출.
-- 팀원(team)은 이 검토 칸 세 개만 쓸 수 있다(나머지는 지금처럼 읽기만). 여러 번 돌려도 안전.
BEGIN;
SET LOCAL search_path TO public;

ALTER TABLE extraction_run ADD COLUMN IF NOT EXISTS review_feedback text;

ALTER TABLE extraction_run DROP CONSTRAINT IF EXISTS extraction_run_review_result_check,
                           DROP CONSTRAINT IF EXISTS extraction_run_review_feedback_check;
-- 옛 값(문제없음·고침)은 모두 사람이 보고 맞다고 한 것 — 정상으로(2026-11-24 RDS 에는 하나도 없음)
UPDATE extraction_run SET review_result = '정상' WHERE review_result IN ('문제없음', '고침');
ALTER TABLE extraction_run
    ADD CONSTRAINT extraction_run_review_result_check CHECK (review_result IN ('정상', '제외', '다시')),
    ADD CONSTRAINT extraction_run_review_feedback_check
        CHECK (review_result IS DISTINCT FROM '다시'   -- 공백·탭·줄바꿈·전각/줄바꿈 없는 공백만 있으면 빈 피드백
               OR btrim(coalesce(review_feedback, ''), E' \t\r\n 　') <> '');

COMMENT ON COLUMN extraction_run.review_result  IS '검토 결과 (정상: 결과 맞음 / 제외: 앞으로 자동 처리·웹에서 뺌 / 다시: 피드백을 붙여 다음 ① 때 다시 추출, 안 봤으면 비움)';
COMMENT ON COLUMN extraction_run.review_feedback IS '검토 피드백 (다시일 때 꼭, 다시 추출할 때 LLM 입력 끝에 붙인다)';

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'team') THEN   -- 노트북·CI 에는 team 이 없다
        GRANT UPDATE (review_result, review_feedback, reviewed_at) ON extraction_run TO team;
    END IF;
END $$;

COMMIT;
