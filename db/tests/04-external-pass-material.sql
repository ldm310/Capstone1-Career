-- Run on an isolated PostgreSQL database after init/01 and init/04; all fixtures roll back.
\set ON_ERROR_STOP on
BEGIN;
DO $$
DECLARE c1 BIGINT; c2 BIGINT; p1 BIGINT; p2 BIGINT; p3 BIGINT; m1 BIGINT; m2 BIGINT; state TEXT;
BEGIN
    INSERT INTO job.company(name) VALUES ('external-test-company-1') RETURNING id INTO c1;
    INSERT INTO job.company(name) VALUES ('external-test-company-2') RETURNING id INTO c2;
    INSERT INTO job.posting(company_id,site_posting_no,title,kind,raw_path,raw_hash)
        VALUES(c1,'external-test-1','IT SW','글','test',repeat('0',64)) RETURNING id INTO p1;
    INSERT INTO job.posting(company_id,site_posting_no,title,kind,raw_path,raw_hash)
        VALUES(c2,'external-test-2','IT SW','글','test',repeat('1',64)) RETURNING id INTO p2;
    INSERT INTO job.posting(company_id,site_posting_no,title,kind,raw_path,raw_hash)
        VALUES(c1,'external-test-3','Other IT role','글','test',repeat('2',64)) RETURNING id INTO p3;
    INSERT INTO external_data.company_collection(company_id) VALUES(c1),(c2);
    -- Multiple postings from the same company resolve to one work item.
    INSERT INTO external_data.company_collection(company_id)
        SELECT company_id FROM job.posting WHERE id IN (p1,p3)
        ON CONFLICT(company_id) DO NOTHING;
    IF (SELECT count(*) FROM external_data.company_collection WHERE company_id=c1) <> 1 THEN
        RAISE EXCEPTION 'Duplicate company collection task';
    END IF;
    INSERT INTO external_data.pass_material(company_id,source_platform,external_record_id,role_name,title,content,source_url)
        VALUES(c1,'test','same-id','백엔드','후기','개발 경험','https://example.com/1') RETURNING id INTO m1;
    INSERT INTO external_data.pass_material(company_id,source_platform,external_record_id,role_name,title,content,source_url)
        VALUES(c2,'other','same-id','백엔드','후기','개발 경험','https://example.com/2') RETURNING id INTO m2;
    INSERT INTO external_data.posting_pass_material(posting_id,material_id,relation_type) VALUES(p1,m1,'EXACT_ROLE');
    INSERT INTO external_data.posting_pass_material(posting_id,material_id,relation_type) VALUES(p3,m1,'SAME_IT_DOMAIN');
    IF (SELECT relation_type FROM external_data.posting_pass_material WHERE posting_id=p1 AND material_id=m1) <> 'EXACT_ROLE'
        OR (SELECT relation_type FROM external_data.posting_pass_material WHERE posting_id=p3 AND material_id=m1) <> 'SAME_IT_DOMAIN' THEN
        RAISE EXCEPTION 'Relations must be independent per posting';
    END IF;
    UPDATE external_data.posting_pass_material SET relation_type='EXCLUDED' WHERE posting_id=p3;
    UPDATE external_data.posting_pass_material SET relation_type='SAME_JOB_FAMILY' WHERE posting_id=p3;
    BEGIN
        UPDATE external_data.posting_pass_material SET relation_type='UNKNOWN' WHERE posting_id=p3;
        RAISE EXCEPTION 'Expected invalid relation type to fail';
    EXCEPTION WHEN check_violation THEN NULL; END;

    BEGIN
        INSERT INTO external_data.pass_material(company_id,source_platform,external_record_id,role_name,title,content,source_url)
            VALUES(c1,'test','same-id','백엔드','중복','중복','https://example.com/1');
        RAISE EXCEPTION 'Expected duplicate source+ID to fail';
    EXCEPTION WHEN unique_violation THEN NULL; END;
    BEGIN
        INSERT INTO external_data.posting_pass_material(posting_id,material_id,relation_type) VALUES(p1,m1,'EXACT_ROLE');
        RAISE EXCEPTION 'Expected duplicate link to fail';
    EXCEPTION WHEN unique_violation THEN NULL; END;
    BEGIN
        INSERT INTO external_data.posting_pass_material(posting_id,material_id,relation_type) VALUES(p1,m2,'SAME_IT_DOMAIN');
        RAISE EXCEPTION 'Expected other company with same role to fail';
    EXCEPTION WHEN check_violation THEN NULL; END;
    BEGIN
        UPDATE external_data.posting_pass_material SET posting_id=p2 WHERE posting_id=p1;
        RAISE EXCEPTION 'Expected link reassignment to another company to fail';
    EXCEPTION WHEN check_violation THEN NULL; END;
    BEGIN
        UPDATE external_data.pass_material SET company_id=c2 WHERE id=m1;
        RAISE EXCEPTION 'Expected source company change to fail';
    EXCEPTION WHEN check_violation THEN NULL; END;
    BEGIN
        INSERT INTO external_data.pass_material(company_id,source_platform,external_record_id,job_family,role_name,title,content,source_url)
            VALUES(c1,'test','sales','SALES','영업','후기','경험','https://example.com/3');
        RAISE EXCEPTION 'Expected non-IT/SW material to fail';
    EXCEPTION WHEN check_violation THEN NULL; END;
    BEGIN
        UPDATE external_data.company_collection SET status='UNKNOWN' WHERE company_id=c1;
        RAISE EXCEPTION 'Expected invalid status to fail';
    EXCEPTION WHEN check_violation THEN NULL; END;
    BEGIN
        UPDATE external_data.company_collection SET status='READY' WHERE company_id=c1;
        RAISE EXCEPTION 'Expected READY without completion time to fail';
    EXCEPTION WHEN check_violation THEN NULL; END;
    BEGIN
        UPDATE external_data.company_collection SET status='FAILED',completed_at=now() WHERE company_id=c1;
        RAISE EXCEPTION 'Expected FAILED without error code to fail';
    EXCEPTION WHEN check_violation THEN NULL; END;
    BEGIN
        UPDATE external_data.company_collection SET minimum_sample_size=0 WHERE company_id=c1;
        RAISE EXCEPTION 'Expected nonpositive minimum to fail';
    EXCEPTION WHEN check_violation THEN NULL; END;

    UPDATE external_data.company_collection SET status='RUNNING',started_at=now(),attempt_count=1 WHERE company_id=c1;
    FOREACH state IN ARRAY ARRAY['READY','INSUFFICIENT','FAILED'] LOOP
        UPDATE external_data.company_collection SET status=state,completed_at=now(),
            error_code=CASE WHEN state='FAILED' THEN 'SOURCE_UNAVAILABLE' ELSE NULL END WHERE company_id=c1;
    END LOOP;
    UPDATE external_data.company_collection SET status='PENDING',started_at=NULL,completed_at=NULL,error_code=NULL WHERE company_id=c1;
    -- An idempotent update preserves identity and existing links.
    INSERT INTO external_data.pass_material(company_id,source_platform,external_record_id,role_name,title,content,source_url)
        VALUES(c1,'test','same-id','백엔드','새 제목','새 본문','https://example.com/1')
        ON CONFLICT(source_platform,external_record_id) DO UPDATE SET content=excluded.content,updated_at=now();
    IF (SELECT count(*) FROM external_data.pass_material WHERE source_platform='test' AND external_record_id='same-id') <> 1 THEN
        RAISE EXCEPTION 'Upsert produced duplicate material';
    END IF;
    RAISE NOTICE 'External material PostgreSQL constraints: PASS';
END;
$$;
-- The pipeline does not need UPDATE privileges on existing posting tables.
CREATE ROLE external_material_test_writer NOLOGIN;
GRANT USAGE ON SCHEMA job, external_data TO external_material_test_writer;
GRANT SELECT ON job.posting, external_data.pass_material TO external_material_test_writer;
GRANT SELECT, INSERT ON external_data.posting_pass_material TO external_material_test_writer;
GRANT USAGE ON ALL SEQUENCES IN SCHEMA external_data TO external_material_test_writer;
SET LOCAL ROLE external_material_test_writer;
INSERT INTO external_data.posting_pass_material(posting_id,material_id,relation_type)
SELECT p.id,m.id,'EXACT_ROLE' FROM job.posting p JOIN external_data.pass_material m ON m.company_id=p.company_id
WHERE p.site_posting_no='external-test-1' AND m.source_platform='test' AND m.external_record_id='same-id'
ON CONFLICT(posting_id,material_id) DO NOTHING;
RESET ROLE;
ROLLBACK;
