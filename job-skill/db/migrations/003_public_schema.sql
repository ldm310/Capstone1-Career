-- 2026-10-31 표를 job 스키마에서 기본 스키마 public 으로 옮긴다(사용자 결정). BE 표와 한 곳에 두고 바로 조인한다.
-- 표에 딸린 색인·제약·자동 번호·권한·COMMENT 는 표와 함께 옮겨 간다. 여러 번 돌려도 안전(job 이 없으면 아무것도 안 함).
BEGIN;

DO $$
DECLARE t text;
BEGIN
    IF to_regnamespace('job') IS NOT NULL THEN
        FOR t IN SELECT tablename FROM pg_tables WHERE schemaname = 'job' LOOP
            EXECUTE format('ALTER TABLE job.%I SET SCHEMA public', t);   -- public 에 같은 이름이 있으면 멈추고 되돌린다
        END LOOP;
        DROP SCHEMA job;   -- 빈 폴더만 지운다(무엇이 남았으면 멈추고 되돌린다)
    END IF;
END $$;

COMMIT;
