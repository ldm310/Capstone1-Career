-- 2026-11-01 스킬이 아닌 낱말('기술 아님'·'일반 낱말')이 사용 중인 기술·능력의 이름·별칭과 같으면 막는다(대소문자·공백 무시).
-- 같으면 그 이름이 영영 잡히지 않는다(2026-11-01 사용자 결정). 'LLM 모델' 낱말은 정확히 같은 이름을 가리지 않아 막지 않는다.
-- 여러 번 돌려도 안전. 지금 사전에는 부딪치는 이름이 없다(LlamaIndex·llama 는 LLM 모델이라 해당 없음).
BEGIN;
SET LOCAL search_path TO public;

CREATE OR REPLACE FUNCTION block_hidden_dictionary_name() RETURNS trigger
LANGUAGE plpgsql SET search_path = pg_catalog, pg_temp AS $f$
DECLARE hit text;
BEGIN
    IF TG_TABLE_NAME = 'exclude_word' THEN
        IF NEW.kind IN ('기술 아님', '일반 낱말') THEN
            SELECT x.name INTO hit
            FROM (SELECT name, aliases FROM public.tech WHERE is_active
                  UNION ALL SELECT name, aliases FROM public.capability WHERE is_active) x
            WHERE lower(regexp_replace(NEW.word, '\s+', '', 'g'))
                  IN (SELECT lower(regexp_replace(a, '\s+', '', 'g')) FROM unnest(x.name || x.aliases) a WHERE a IS NOT NULL)
            LIMIT 1;
            IF hit IS NOT NULL THEN
                RAISE EXCEPTION '낱말 ''%'' 이 사전의 ''%'' 을 가립니다(그 이름이 잡히지 않음). 먼저 그쪽을 끄거나 별칭을 고치세요.', NEW.word, hit;
            END IF;
        END IF;
    ELSIF NEW.is_active THEN
        SELECT w.word || ' (' || w.kind || ')' INTO hit
        FROM public.exclude_word w
        WHERE w.kind IN ('기술 아님', '일반 낱말')
          AND lower(regexp_replace(w.word, '\s+', '', 'g'))
              IN (SELECT lower(regexp_replace(a, '\s+', '', 'g')) FROM unnest(NEW.name || NEW.aliases) a WHERE a IS NOT NULL)
        LIMIT 1;
        IF hit IS NOT NULL THEN
            RAISE EXCEPTION '''%'' 의 이름·별칭이 스킬이 아닌 낱말 % 과 같아 잡히지 않습니다. 먼저 exclude_word 에서 지우세요.', NEW.name, hit;
        END IF;
    END IF;
    RETURN NEW;
END $f$;

CREATE OR REPLACE TRIGGER dictionary_no_hidden_name BEFORE INSERT OR UPDATE ON capability
    FOR EACH ROW EXECUTE FUNCTION block_hidden_dictionary_name();
CREATE OR REPLACE TRIGGER dictionary_no_hidden_name BEFORE INSERT OR UPDATE ON tech
    FOR EACH ROW EXECUTE FUNCTION block_hidden_dictionary_name();
CREATE OR REPLACE TRIGGER dictionary_no_hidden_name BEFORE INSERT OR UPDATE ON exclude_word
    FOR EACH ROW EXECUTE FUNCTION block_hidden_dictionary_name();

COMMIT;
