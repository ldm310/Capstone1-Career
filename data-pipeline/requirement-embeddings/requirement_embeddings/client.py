import math
import os
import struct


class SafeFailure(Exception):
    def __init__(self,code,uncertain=False):
        super().__init__(code)
        self.code,self.uncertain=code,uncertain


def validate_response(response,count,config):
    if not isinstance(response,dict):raise SafeFailure('RESPONSE_MAPPING_INVALID')
    if response.get('model')!=config.model:raise SafeFailure('MODEL_MISMATCH')
    data=response.get('data')
    if not isinstance(data,list) or len(data)!=count:raise SafeFailure('RESPONSE_MAPPING_INVALID')
    if any(not isinstance(r,dict) for r in data):raise SafeFailure('RESPONSE_MAPPING_INVALID')
    indexes=[r.get('index') for r in data]
    if any(type(i) is not int for i in indexes) or set(indexes)!=set(range(count)) or len(set(indexes))!=count:
        raise SafeFailure('RESPONSE_MAPPING_INVALID')
    result={}
    for row in data:
        vector=row.get('embedding')
        error=None
        if not isinstance(vector,list) or len(vector)!=config.dimensions:error='DIMENSION_MISMATCH'
        elif any(type(x) not in (float,int) or not math.isfinite(x) or abs(x)>3.4e38 for x in vector) or sum(x*x for x in vector)==0:error='INVALID_VECTOR'
        if not error:
            vector=[struct.unpack('f',struct.pack('f',x))[0] for x in vector]
            if not any(vector):error='INVALID_VECTOR'
        result[row['index']]=(None,error) if error else (vector,None)
    usage=response.get('usage')
    tokens=usage.get('prompt_tokens') if isinstance(usage,dict) else None
    if type(tokens) is not int or tokens<0:raise SafeFailure('RESPONSE_MAPPING_INVALID')
    return result,tokens


class OpenAIClient:
    def __init__(self,config):
        key=os.environ.get('OPENAI_API_KEY')
        if not key:raise SafeFailure('AUTH_FAILED')
        from openai import OpenAI
        # SDK retries are disabled: uncertain deliveries must never be silently sent twice.
        self.client=OpenAI(api_key=key,max_retries=0,timeout=30.0)
        self.config=config

    def create(self,texts):
        try:
            return self.client.embeddings.create(model=self.config.model,input=texts,
                dimensions=self.config.dimensions,encoding_format='float').model_dump()
        except Exception as exc:
            status=getattr(exc,'status_code',None)
            if status in (401,403):raise SafeFailure('AUTH_FAILED') from None
            if status==429:raise SafeFailure('RATE_LIMITED') from None
            if status is not None and 400<=status<500 and status!=408:raise SafeFailure('API_REJECTED') from None
            raise SafeFailure('DELIVERY_UNCERTAIN',True) from None
