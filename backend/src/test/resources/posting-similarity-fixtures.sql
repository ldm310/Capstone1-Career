-- Synthetic rows for a NEW, isolated extcrawler_test_similarity_* database only.
INSERT INTO public.company(id,name) OVERRIDING SYSTEM VALUE VALUES
 (1,'fixture-target'),(2,'fixture-other-a'),(3,'fixture-other-b');
INSERT INTO public.capability(id,name,is_active) OVERRIDING SYSTEM VALUE VALUES
 (1,'fixture-language',true),(2,'fixture-database',true),(3,'기타',true),(4,'fixture-inactive',false);
INSERT INTO public.tech(id,name,is_active) OVERRIDING SYSTEM VALUE VALUES
 (10,'fixture-java',true),(20,'fixture-sql',true),(30,'fixture-disabled',false);
INSERT INTO public.posting(id,company_id,site_posting_no,title,kind,raw_hash)
 OVERRIDING SYSTEM VALUE VALUES
 (1,1,'sim-1','Backend fixture','글',repeat('0',64)),
 (2,1,'sim-2','Same company backend','글',repeat('0',64)),
 (3,2,'sim-3','Mixed posting fixture','글',repeat('0',64)),
 (4,2,'sim-4','Non IT fixture','글',repeat('0',64)),
 (5,3,'sim-5','Backend current fixture','글',repeat('0',64)),
 (6,3,'sim-6','Backend empty fixture','글',repeat('0',64)),
 (7,1,'sim-7','Non IT target','글',repeat('0',64)),
 (8,1,'sim-8','No extraction target','글',repeat('0',64));
INSERT INTO public.extraction_run(id,posting_id,model,prompt_version,dict_version,input_hash,
 input_tokens,output_tokens,cost_usd,is_current) OVERRIDING SYSTEM VALUE
 SELECT x.id,x.posting_id,'fixture','fixture','fixture',repeat('0',64),0,0,0,x.is_current
 FROM (VALUES (101,1,true),(201,2,true),(301,3,true),(401,4,true),
              (501,5,false),(502,5,true),(601,6,true),(701,7,true)) AS x(id,posting_id,is_current);
INSERT INTO public.recruit_unit(id,run_id,seq,name,is_it,career) OVERRIDING SYSTEM VALUE VALUES
 (11,101,1,'백엔드',true,'신입'),(12,101,2,'프론트엔드',true,'신입'),(13,101,3,'백엔드',false,'신입'),
 (21,201,1,'백엔드',true,'신입'),
 (31,301,1,'백엔드',true,'신입'),(32,301,2,'백엔드',true,'신입'),(33,301,3,'프론트엔드',true,'신입'),
 (41,401,1,'백엔드',false,'신입'),(51,501,1,'백엔드',true,'신입'),(52,502,1,'백엔드',true,'신입'),
 (61,601,1,'백엔드',true,'신입'),(62,601,2,'백엔드',true,'신입'),(71,701,1,'백엔드',false,'신입');
INSERT INTO public.unit_item(id,unit_id,category,seq,text,quote) OVERRIDING SYSTEM VALUE VALUES
 (111,11,'필수',1,'fixture','fixture'),(112,11,'우대',1,'fixture','fixture'),(113,11,'업무',1,'fixture','fixture'),
 (114,11,'기타',1,'fixture','fixture'),(121,12,'필수',1,'fixture','fixture'),(131,13,'필수',1,'fixture','fixture'),
 (211,21,'필수',1,'fixture','fixture'),(311,31,'필수',1,'fixture','fixture'),(321,32,'필수',1,'fixture','fixture'),
 (331,33,'필수',1,'fixture','fixture'),(411,41,'필수',1,'fixture','fixture'),(511,51,'필수',1,'fixture','fixture'),
 (521,52,'필수',1,'fixture','fixture'),(621,62,'필수',1,'fixture','fixture');
INSERT INTO public.requirement(id,item_id,capability_id,relation) OVERRIDING SYSTEM VALUE VALUES
 (1111,111,1,'모두'),(1112,111,3,'모두'),(1113,111,4,'모두'),(1114,111,1,'능력만'),
 (1121,112,2,'모두'),(1131,113,2,'모두'),(1141,114,2,'모두'),
 (1211,121,2,'모두'),(1311,131,2,'모두'),(2111,211,1,'모두'),
 (3111,311,1,'모두'),(3211,321,2,'모두'),(3311,331,2,'모두'),
 (4111,411,1,'모두'),(5111,511,2,'모두'),(5211,521,1,'모두'),(6211,621,2,'능력만');
INSERT INTO public.requirement_tech(requirement_id,tech_id,written_name) VALUES
 (1111,10,'fixture'),(1111,10,'duplicate'),(1111,30,'inactive'),(1114,NULL,'unmapped'),
 (1112,20,'valid tech under other capability'),(1113,10,'valid tech under inactive capability'),
 (1121,20,'fixture'),(1131,10,'fixture'),(1141,30,'ignored category'),
 (1211,20,'fixture'),(1311,20,'fixture'),(2111,10,'fixture'),
 (3111,10,'fixture'),(3211,20,'fixture'),(3311,20,'fixture'),
 (4111,10,'fixture'),(5111,20,'old'),(5211,10,'current'),(6211,NULL,'unmapped');
