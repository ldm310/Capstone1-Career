-- 2026-11-27 공고마다 기술 카테고리를 적는다(사용자 결정 — 회의에서 정한 팀원 7개판, 줄마다가 아니라 공고 단위로).
--   L 프로그래밍·CS 기초 / B 백엔드 개발 / D 데이터베이스 / E 데이터 엔지니어링·분석 / O 인프라·배포·운영 / F 프론트엔드·앱 개발 / A AI 기술
-- 현재 추출 결과의 백엔드·데이터 엔지니어 자리 필수·우대 줄에 붙은 카테고리를 모은 것(team_categories.py 가 채움).
-- 비어 있으면(NULL) 안 붙임(그 외 자리만 있는 공고·아직 처리 전), 빈 목록({})이면 백엔드·데이터 공고인데 붙일 기술이 없음(지원 조건만 있는 공고 등). 여러 번 돌려도 안전.
BEGIN;
SET LOCAL search_path TO public;
ALTER TABLE posting ADD COLUMN IF NOT EXISTS skill_categories text[]
    CHECK (skill_categories <@ ARRAY['L', 'B', 'D', 'E', 'O', 'F', 'A']::text[]);
COMMENT ON COLUMN posting.skill_categories IS '기술 카테고리 (팀원 7개판 코드 목록: L 프로그래밍·CS 기초/B 백엔드 개발/D 데이터베이스/E 데이터 엔지니어링·분석/O 인프라·배포·운영/F 프론트엔드·앱 개발/A AI 기술 — 현재 추출 결과의 필수·우대 줄에서 모음, 비면(NULL) 안 붙임(그 외 자리만 있는 공고·아직 처리 전), {}면 백엔드·데이터 공고인데 붙일 기술 없음)';
COMMIT;
