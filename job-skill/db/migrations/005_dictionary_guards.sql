-- 2026-10-31 최종 검토에서 찾은 것(004 는 이미 RDS·로컬에 적용돼 여기서 고친다). 여러 번 돌려도 안전.
--   - 빈 낱말(공백뿐) 금지: 'LLM 모델' 종류의 빈 낱말은 모든 이름 안에 들어 있어 모든 기술이 빠진다
--   - 기록 함수는 public 의 사전 표에서만: 팀원이 임시 표에 이 함수를 걸어 가짜 기록을 넣지 못하게
BEGIN;
SET LOCAL search_path TO public;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'exclude_word_word_not_blank') THEN
        ALTER TABLE exclude_word ADD CONSTRAINT exclude_word_word_not_blank CHECK (btrim(word) <> '');
    END IF;
END $$;

CREATE OR REPLACE FUNCTION log_dictionary_change() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $f$
BEGIN
    IF TG_TABLE_SCHEMA <> 'public' THEN   -- 임시 표 등에 이 함수를 걸어 가짜 기록을 넣지 못하게
        RAISE EXCEPTION '사전 변경 기록은 public 의 사전 표에서만 남깁니다(%.%)', TG_TABLE_SCHEMA, TG_TABLE_NAME;
    END IF;
    IF TG_OP = 'UPDATE' AND to_jsonb(OLD) = to_jsonb(NEW) THEN
        RETURN NULL;   -- 값이 그대로인 고치기는 남기지 않는다
    END IF;
    INSERT INTO public.dictionary_change (changed_by, table_name, action, old_row, new_row)
    VALUES (session_user, TG_TABLE_NAME,
            CASE TG_OP WHEN 'INSERT' THEN '넣기' WHEN 'UPDATE' THEN '고치기' ELSE '지우기' END,
            CASE WHEN TG_OP <> 'INSERT' THEN to_jsonb(OLD) END,
            CASE WHEN TG_OP <> 'DELETE' THEN to_jsonb(NEW) END);
    RETURN NULL;
END $f$;

COMMIT;
