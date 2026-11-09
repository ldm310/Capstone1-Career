import contextlib
import io
import json
import math
import os
from pathlib import Path
import unittest
from unittest.mock import Mock,patch
from requirement_embeddings.config import Config
from requirement_embeddings.preprocessing import Taxonomy,prepare,ROOT
from requirement_embeddings.client import validate_response,SafeFailure,OpenAIClient
from requirement_embeddings.batch import pack


def source(text='Spring Boot 기반 REST API 개발',**changes):
    row=dict(requirement_id=1,recruit_unit_id=11,source_run_id=101,source_fingerprint='f',
             category='REQUIRED',unit_name='backend',site_job_category='',posting_title='',
             company_name='예시회사',capability_name='백엔드 프레임워크',capability_active=True,
             tech_names=['Spring Boot'],item_text=text)
    return {**row,**changes}


class EmbeddingTests(unittest.TestCase):
    def setUp(self):self.taxonomy=Taxonomy();self.config=Config(dimensions=3)

    def test_input_is_deterministic_and_different_text_changes_hash(self):
        a=prepare(source('Spring Boot  기반\nREST API 개발',tech_names=['SQL','Spring Boot','SQL']),self.taxonomy)
        b=prepare(source('Spring Boot 기반 REST API 개발',requirement_id=99,tech_names=['Spring Boot','SQL']),self.taxonomy)
        self.assertEqual(a.text,b.text);self.assertEqual(a.input_hash,b.input_hash)
        self.assertNotEqual(a.input_hash,prepare(source('Spring Boot 운영'),self.taxonomy).input_hash)
        self.assertNotEqual(a.input_hash,prepare(source(category='PREFERRED'),self.taxonomy).input_hash)

    def test_private_company_school_attitude_and_html_are_not_inputs(self):
        for text in ('예시회사 서비스 개발','성실한 태도','컴퓨터공학 학사','담당자: 홍길동','a@example.invalid','010-1234-5678','<p>Spring 개발</p>'):
            self.assertIsNotNone(prepare(source(text),self.taxonomy).error)
        a=prepare(source('경력 3년 이상 Spring Boot 개발 경험'),self.taxonomy)
        self.assertNotIn('3년',a.text)

    def test_planned_and_actual_actions_and_java_javascript_stay_distinct(self):
        a=prepare(source('Docker 배포를 학습할 예정',tech_names=['Docker']),self.taxonomy)
        b=prepare(source('Docker 배포를 구현했습니다',tech_names=['Docker']),self.taxonomy)
        self.assertNotEqual(a.input_hash,b.input_hash)
        java=prepare(source('Java 개발',tech_names=['Java']),self.taxonomy)
        javascript=prepare(source('JavaScript 개발',tech_names=['JavaScript']),self.taxonomy)
        self.assertNotEqual(java.input_hash,javascript.input_hash)
        self.assertIn('tech=Java;',java.text);self.assertIn('tech=JavaScript;',javascript.text)

    def test_role_mapping_uses_shared_contract(self):
        pairs=json.loads((ROOT/'backend/src/test/resources/embedding-role-contract.json').read_text(encoding='utf-8'))
        for row in pairs:self.assertEqual(self.taxonomy.role(row)[0],row['role'])

    def test_response_index_mapping_and_invalid_mapping(self):
        data={'model':self.config.model,'data':[{'index':1,'embedding':[0,1,0]},{'index':0,'embedding':[1,0,0]}],'usage':{'prompt_tokens':7}}
        values,tokens=validate_response(data,2,self.config)
        self.assertEqual(values[0][0],[1.,0.,0.]);self.assertEqual(tokens,7)
        for indexes in ((0,0),(0,2),(0,)):
            bad={**data,'data':[{'index':i,'embedding':[1,0,0]} for i in indexes]}
            with self.assertRaises(SafeFailure):validate_response(bad,2,self.config)

    def test_bad_vectors_are_local_failures_and_null_is_not_a_vector(self):
        for vector in (None,[],[1,0],[0,0,0],[1e-60,0,0],[math.nan,0,1],[math.inf,0,1]):
            result,_=validate_response({'model':self.config.model,'data':[{'index':0,'embedding':vector}],'usage':{'prompt_tokens':1}},1,self.config)
            self.assertIsNone(result[0][0]);self.assertIsNotNone(result[0][1])

    def test_sdk_has_no_automatic_retry_and_errors_never_include_secret(self):
        with patch.dict(os.environ,{'OPENAI_API_KEY':'synthetic-secret-marker'}),patch('openai.OpenAI') as sdk:
            api=OpenAIClient(self.config)
            self.assertEqual(sdk.call_args.kwargs['max_retries'],0)
            sdk.return_value.embeddings.create.side_effect=RuntimeError('synthetic-secret-marker')
            with self.assertRaises(SafeFailure) as error:api.create(['synthetic'])
            self.assertEqual(str(error.exception),'DELIVERY_UNCERTAIN')
        with patch.dict(os.environ,{},clear=True),contextlib.redirect_stdout(io.StringIO()) as output:
            from requirement_embeddings.__main__ import main
            self.assertEqual(main(['--apply']),1)
        self.assertNotIn('synthetic-secret-marker',output.getvalue())

    def test_requests_are_bounded_by_count_and_tokens(self):
        p=prepare(source(),self.taxonomy)
        config=Config(dimensions=3,batch_items=2,batch_tokens=4,input_tokens=3)
        batches=list(pack([p]*5,config,lambda text:2))
        self.assertEqual([len(b) for b in batches],[2,2,1])


@unittest.skipUnless(os.getenv('RUN_OPENAI_EMBEDDING_SMOKE')=='1','Explicit opt-in required for actual OpenAI smoke')
class OptionalSmoke(unittest.TestCase):
    def test_synthetic_only_max_ten_sentences(self):
        pairs=json.loads((Path(__file__).parent/'fixtures/benchmark-pairs.json').read_text(encoding='utf-8'))
        inputs=[text for row in pairs for text in (row['a'],row['b'])][:10]
        config=Config.from_env();result=OpenAIClient(config).create(inputs)
        vectors,tokens=validate_response(result,len(inputs),config)
        self.assertTrue(all(error is None for _,error in vectors.values()))
        price=os.getenv('EMBEDDING_PRICE_PER_MILLION_TOKENS')
        report={'synthetic_sentences':len(inputs),'api_calls':1,'prompt_tokens':tokens,
                'estimated_cost_usd':None if price is None else tokens*float(price)/1_000_000,
                'price_per_million_tokens':price,'pricing_version':'configured-estimate-v1',
                'model':config.model,'dimension':config.dimensions,'pairs':[]}
        from datetime import datetime,timezone
        report['recorded_at_utc']=datetime.now(timezone.utc).isoformat()
        for i,pair in enumerate(pairs):
            similarity=None
            if i*2+1<len(inputs):
                a=vectors[i*2][0];b=vectors[i*2+1][0]
                if a is not None and b is not None:
                    similarity=sum(x*y for x,y in zip(a,b))/math.sqrt(sum(x*x for x in a)*sum(y*y for y in b))
            report['pairs'].append({'type':pair['type'],'similarity':similarity})
        path=ROOT/'work/embedding-shadow-real-smoke.json';path.parent.mkdir(exist_ok=True)
        path.write_text(json.dumps(report),encoding='utf-8')
