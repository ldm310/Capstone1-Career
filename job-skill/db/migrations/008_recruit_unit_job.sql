-- 2026-11-12 백엔드·데이터 엔지니어 자리만 필수·우대·업무를 정리한다(사용자 결정 — 그 외 직무는 버리는 데이터).
-- 자리마다 직무를 적는다. 이미 추출한 자리는 비어 있고 fill_unit_job.py 가 채운다. 여러 번 돌려도 안전.
BEGIN;
SET LOCAL search_path TO public;
ALTER TABLE recruit_unit ADD COLUMN IF NOT EXISTS job text CHECK (job IN ('백엔드', '데이터 엔지니어', '그 외'));
COMMENT ON COLUMN recruit_unit.job        IS '직무 (백엔드/데이터 엔지니어/그 외 — 그 외는 이름·경력만, 항목 없음. 업무 내용으로 판단. 2026-11-12 전에 추출한 자리는 fill_unit_job.py 로 채움, 비면 아직 모름)';
COMMIT;
