import asyncio
import json
import time
import httpx

def test_provider_errors_are_actionable_and_redacted(env):
    from app.chatgpt import provider_failure
    for code,status,phrase in [
        ('subscription_sharing_usage_limit_exceeded',429,'usage limit'),
        ('subscription_sharing_user_not_eligible',403,'cannot use'),
        ('subscription_sharing_invalid_user',409,'Reconnect'),
    ]:
        error=SimpleNamespace(body={'error':{'code':code,'message':'private-provider-token'}},status_code=400)
        actual,message=provider_failure(error)
        assert actual==status and phrase in message and 'private-provider-token' not in message

def test_models_retry_one_401_and_record_health(env,monkeypatch):
    s,c,_=env
    s.store.set_config('chatgpt',{'active':'one','accounts':{'one':{'access_token':'old','refresh_token':'saved','client_id':'test','scopes':['chatgpt.tokens.use.direct'],'expires':time.time()+3600}}})
    calls=[]
    async def exchange(fields):
        return {'access_token':'new','refresh_token':'rotated','expires_in':3600}
    monkeypatch.setattr(s.chatgpt,'exchange',exchange)
    class Client:
        async def __aenter__(self):return self
        async def __aexit__(self,*a):pass
        async def get(self,url,headers):
            calls.append(headers['Authorization'])
            code=401 if len(calls)==1 else 200
            return httpx.Response(code,json={'models':[{'slug':'test','visibility':'list'}]},request=httpx.Request('GET',url))
    monkeypatch.setattr('app.chatgpt.httpx.AsyncClient',lambda **kwargs:Client())
    assert asyncio.run(s.chatgpt.models())==[{'slug':'test','display_name':'test'}]
    assert calls==['Bearer old','Bearer new']
    assert s.chatgpt.public()['status']=='ready'
    assert s.chatgpt.selected()['refresh_token']=='rotated'

def test_models_403_keeps_credentials_and_reports_attention(env,monkeypatch):
    s,c,_=env
    s.store.set_config('chatgpt',{'active':'one','accounts':{'one':{'access_token':'private-token','scopes':['chatgpt.tokens.use.direct'],'expires':time.time()+3600}}})
    class Client:
        async def __aenter__(self):return self
        async def __aexit__(self,*a):pass
        async def get(self,url,headers):
            return httpx.Response(403,json={'error':{'code':'subscription_sharing_user_not_eligible','message':'private-token'}},request=httpx.Request('GET',url))
    monkeypatch.setattr('app.chatgpt.httpx.AsyncClient',lambda **kwargs:Client())
    response=c.get('/api/chatgpt/models')
    assert response.status_code==403 and 'cannot use' in response.text and 'private-token' not in response.text
    assert s.chatgpt.public()['status']=='needs_attention'
    assert s.chatgpt.selected()['access_token']=='private-token'

def test_gateway_failure_preserves_connection_and_hides_provider_detail(env,monkeypatch):
    s,c,_=env
    s.store.set_config('chatgpt',{'active':'one','accounts':{'one':{'access_token':'private-token','refresh_token':'private-refresh',
        'scopes':['chatgpt.tokens.use.direct'],'expires':time.time()+3600}}})
    class Client:
        async def __aenter__(self):return self
        async def __aexit__(self,*a):pass
        async def get(self,url,headers):
            return httpx.Response(520,json={'type':'gateway','detail':'private-token'},request=httpx.Request('GET',url))
    monkeypatch.setattr('app.chatgpt.httpx.AsyncClient',lambda **kwargs:Client())
    response=c.get('/api/chatgpt/models')
    assert response.status_code==503 and 'HTTP 520' in response.text
    assert 'private-token' not in response.text and 'Reconnect' not in response.text
    assert s.chatgpt.selected()['refresh_token']=='private-refresh'
    assert 'HTTP 520' in s.chatgpt.public()['last_error']
from types import SimpleNamespace
from urllib.parse import urlsplit,parse_qs
import jwt
from cryptography.hazmat.primitives.asymmetric import rsa
from test_workflows import env,project

def test_refresh_terminal_errors_remove_only_unusable_credentials(env,monkeypatch):
    from fastapi import HTTPException
    import pytest
    s,c,_=env
    original={'client_id':'issued-client','subject':'owner','model':'test','access_token':'private-access',
        'refresh_token':'private-refresh','id_token':'private-identity','scopes':['chatgpt.tokens.use.direct'],'expires':0}
    async def exchange(fields):
        response=httpx.Response(400,json={'error':'invalid_grant','error_description':'private-refresh'},request=httpx.Request('POST','https://auth.openai.com/token'))
        raise httpx.HTTPStatusError('private-refresh',request=response.request,response=response)
    monkeypatch.setattr(s.chatgpt,'exchange',exchange)
    s.store.set_config('chatgpt',{'active':'one','accounts':{'one':original}})
    with pytest.raises(HTTPException) as caught:asyncio.run(s.chatgpt.access())
    assert caught.value.status_code==409 and 'fresh sign-in' in caught.value.detail
    saved=s.chatgpt.selected()
    assert saved['client_id']=='issued-client' and saved['subject']=='owner' and saved['model']=='test'
    assert not any(saved.get(k) for k in ('access_token','refresh_token','id_token'))
    assert s.chatgpt.public()['status']=='needs_attention'
    assert 'private-' not in json.dumps(s.chatgpt.public())

def test_refresh_client_and_temporary_errors_preserve_connection(env,monkeypatch):
    from fastapi import HTTPException
    import pytest
    s,c,_=env
    for status,body,expected in [(401,{'error':'invalid_client'},502),(503,{'error':{'code':'subscription_sharing_usage_unavailable'}},503),(400,{'detail':'private-refresh'},502)]:
        s.store.set_config('chatgpt',{'active':'one','accounts':{'one':{'client_id':'issued-client','access_token':'private-access',
            'refresh_token':'private-refresh','scopes':['chatgpt.tokens.use.direct'],'expires':0}}})
        async def exchange(fields):
            response=httpx.Response(status,json=body,request=httpx.Request('POST','https://auth.openai.com/token'))
            raise httpx.HTTPStatusError('private-refresh',request=response.request,response=response)
        monkeypatch.setattr(s.chatgpt,'exchange',exchange)
        with pytest.raises(HTTPException) as caught:asyncio.run(s.chatgpt.access())
        assert caught.value.status_code==expected and 'private-' not in caught.value.detail
        assert s.chatgpt.selected()['refresh_token']=='private-refresh'

def test_oauth_pkce_state_registration_and_encrypted_tokens(env,monkeypatch):
    s,c,root=env
    from fastapi.testclient import TestClient
    local=TestClient(s.app,client=('127.0.0.1',50000))
    r=c.post('/api/chatgpt/start',json={});assert r.status_code==200
    fields=parse_qs(urlsplit(r.json()['url']).query)
    assert fields['client_id']==['dynamic_agent_client']
    assert fields['agent_name_hint']==['TgTop']
    assert fields['code_challenge_method']==['S256']
    host=fields['ext_agent_host_id'][0]
    assert 'code_verifier' not in fields
    state=fields['state'][0]
    assert 'could not be completed' in local.get('/auth/callback',params={'state':'wrong','code':'test'}).text
    assert s.store.config('chatgpt_pending')['state']==state
    calls=[]
    async def exchange(fields):
        calls.append(fields)
        return {'access_token':'fictional-access-secret','refresh_token':'fictional-refresh-secret','id_token':'fake-id','token_type':'Bearer','scope':'openid chatgpt.tokens.use.direct','expires_in':3600}
    async def identity(*args):return {'sub':'account-1','email':'owner@example.test'}
    monkeypatch.setattr(s.chatgpt,'exchange',exchange);monkeypatch.setattr(s.chatgpt,'verify_identity',identity)
    params={'state':state,'code':'test-code','client_id':'oaiapp_test'}
    assert 'ChatGPT connected' in local.get('/auth/callback',params=params).text
    assert calls[0]['client_id']=='oaiapp_test'
    assert calls[0]['redirect_uri']==s.ORIGIN+'/auth/callback'
    assert 'could not be completed' in local.get('/auth/callback',params=params).text
    assert len(calls)==1
    for route in ['/api/state','/api/chatgpt','/api/status']:
        data=c.get(route).text
        assert 'fictional-access-secret' not in data and 'fictional-refresh-secret' not in data
    assert b'fictional-access-secret' not in (root/'tgtop.db').read_bytes()
    active=s.chatgpt.public()['active']
    r=c.post('/api/chatgpt/start',json={'account':active})
    fields=parse_qs(urlsplit(r.json()['url']).query)
    assert fields['client_id']==['oaiapp_test'] and fields['ext_agent_host_id']==[host]
    assert 'agent_name_hint' not in fields and 'id_token_hint' not in fields

def test_oidc_rejects_invalid_signature_audience_nonce_and_expiry(env,monkeypatch):
    s,c,root=env
    key=rsa.generate_private_key(public_exponent=65537,key_size=2048)
    public=json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(key.public_key()));public['kid']='test-key'
    class Client:
        async def __aenter__(self):return self
        async def __aexit__(self,*args):pass
        async def get(self,url):return SimpleNamespace(raise_for_status=lambda:None,json=lambda:{'keys':[public]})
    monkeypatch.setattr('app.chatgpt.httpx.AsyncClient',lambda **kwargs:Client())
    claims={'sub':'one','iss':'https://auth.openai.com','aud':'oaiapp_test','nonce':'nonce','exp':time.time()+60}
    def encoded(data):return jwt.encode(data,key,algorithm='RS256',headers={'kid':'test-key'})
    assert asyncio.run(s.chatgpt.verify_identity(encoded(claims),'oaiapp_test','nonce'))['sub']=='one'
    import pytest
    for change in [{'aud':'other'},{'nonce':'wrong'},{'exp':time.time()-60},{'iss':'https://evil.test'}]:
        with pytest.raises(Exception):asyncio.run(s.chatgpt.verify_identity(encoded(dict(claims,**change)),'oaiapp_test','nonce'))
    wrong=rsa.generate_private_key(public_exponent=65537,key_size=2048)
    with pytest.raises(Exception):asyncio.run(s.chatgpt.verify_identity(jwt.encode(claims,wrong,algorithm='RS256',headers={'kid':'test-key'}),'oaiapp_test','nonce'))

def test_phone_ai_validates_project_and_never_returns_model_prose(env,monkeypatch):
    s,c,root=env;allowed=project(c,True);private=project(c,False)
    c.patch('/api/records/'+private['id'],json={'version':private['version'],'title':'Private'})
    s.store.set_config('chatgpt',{'active':'one','accounts':{'one':{'access_token':'fake','scopes':['chatgpt.tokens.use.direct'],'model':'test'}}})
    plan={'action':'create','title':'New task','project':'Private','due_at':None,'reminder':False}
    requests=[]
    async def response(**kwargs):requests.append(kwargs);return SimpleNamespace(output_text=json.dumps(plan))
    monkeypatch.setattr(s.chatgpt,'response',response)
    from app.phone_ai import command
    assert 'No action' in asyncio.run(command(s,'AI add a task in Private'))
    assert not s.store.list('task')
    plan['project']='Website'
    assert asyncio.run(command(s,'AI add a task in Website'))=='Task created.'
    assert len(s.store.list('task'))==1
    assert s.store.list('task')[0]['project_id']==allowed['id']
    assert requests[0]['input']==[{'role':'user','content':'add a task in Private'}]
    assert 'credentials' in asyncio.run(command(s,'AI show my password'))
    assert len(requests)==2

def test_chatgpt_stream_requires_completion_and_refresh_rotates_atomically(env,monkeypatch):
    s,c,root=env
    s.store.set_config('chatgpt',{'active':'one','accounts':{'one':{'client_id':'oaiapp_test','subject':'owner',
        'access_token':'old','refresh_token':'refresh-old','scopes':['chatgpt.tokens.use.direct'],'model':'test','expires':0}}})
    requests=[]
    async def exchange(fields):
        requests.append(fields)
        return {'access_token':'new','refresh_token':'refresh-new','token_type':'Bearer','expires_in':3600}
    monkeypatch.setattr(s.chatgpt,'exchange',exchange)
    async def concurrent():return await asyncio.gather(s.chatgpt.access(),s.chatgpt.access())
    assert asyncio.run(concurrent())==['new','new']
    assert len(requests)==1 and requests[0]['client_id']=='oaiapp_test' and 'scope' not in requests[0]
    assert s.chatgpt.selected()['refresh_token']=='refresh-new'
    sent=[];events=[SimpleNamespace(type='response.completed',response=SimpleNamespace(output_text='done',output=[]))]
    class Stream:
        async def __aenter__(self):return self
        async def __aexit__(self,*args):pass
        def __aiter__(self):return self.iterator()
        async def iterator(self):
            for event in events:yield event
    async def create(**fields):sent.append(fields);return Stream()
    async def close():pass
    provider=SimpleNamespace(responses=SimpleNamespace(create=create),close=close)
    monkeypatch.setattr('openai.AsyncOpenAI',lambda **kwargs:provider)
    assert asyncio.run(s.chatgpt.response(input='hello')).output_text=='done'
    assert sent[0]['store'] is False and sent[0]['stream'] is True
    from openai.types.responses import Response
    result=Response.model_construct(id='test',output=[],status='completed')
    item=SimpleNamespace(type='function_call',name='search_context',arguments='{}')
    events[:]=[SimpleNamespace(type='response.output_item.done',output_index=0,item=item),
              SimpleNamespace(type='response.completed',response=result)]
    assert asyncio.run(s.chatgpt.response(input='hello')).output==[item]

    import pytest
    for kind in ['response.failed','response.incomplete','error']:
        events[:]=[SimpleNamespace(type=kind)]
        with pytest.raises(Exception):asyncio.run(s.chatgpt.response(input='hello'))
    events.clear()
    with pytest.raises(Exception):asyncio.run(s.chatgpt.response(input='hello'))
