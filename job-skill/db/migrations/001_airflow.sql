-- 2026-10-28 Airflow DAG 용: 버린 공고번호 표. 이미 있는 career-db 에 적용한다(여러 번 돌려도 안전).
BEGIN;
SET LOCAL search_path TO public;   -- 2026-10-31 표를 job 에서 public 으로 옮김(003)

CREATE TABLE IF NOT EXISTS listing_seen (
    site             text        NOT NULL DEFAULT '사람인',
    site_posting_no  text        NOT NULL,
    reason           text        NOT NULL,
    first_seen_at    timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (site, site_posting_no)
);
COMMENT ON TABLE  listing_seen                 IS '버린 공고번호 (4년 이상·교육생 등, 본문은 받지 않음) — 연속 5개 멈춤 규칙에서 아는 번호로 셈';
COMMENT ON COLUMN listing_seen.site            IS '사이트 (사람인)';
COMMENT ON COLUMN listing_seen.site_posting_no IS '사이트 공고번호 (사람인 rec_idx)';
COMMENT ON COLUMN listing_seen.reason          IS '버린 이유 (4년 이상 / 교육생 / 경력 조건 모름)';
COMMENT ON COLUMN listing_seen.first_seen_at   IS '처음 본 시각';

COMMIT;
