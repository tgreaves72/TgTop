import asyncio
import json
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from test_workflows import env, project


def test_runtime_disables_os_tools_and_delegation():
    import tomllib
    from app.codex_bridge import CONFIG
    cfg=tomllib.loads(CONFIG)
    assert cfg['agents']['enabled'] is False
    assert cfg['features']['shell_tool'] is False and cfg['features']['apps'] is False
    assert cfg['web_search']=='disabled' and cfg['sandbox_mode']=='read-only'
    assert cfg['forced_login_method']=='chatgpt'


def configure(s):
    managed=s.chatgpt.codex
    managed.update(enabled=True,connected=True,status='not_checked',model='test-model')
    s.store.set_config('codex_auth',{'tokens':{'access_token':'private-codex-token'}})
    return managed


def fake_session(monkeypatch, events, requests, sent):
    class Session:
        def __init__(self,store):self.home='/private/empty';self.events=list(events)
        async def __aenter__(self):return self
        async def __aexit__(self,*args):pass
        async def rpc(self,method,params):
            requests.append((method,params))
            return {'thread':{'id':'test-thread'}} if method=='thread/start' else {}
        async def event(self):return self.events.pop(0)
        async def send(self,message):sent.append(message)
    monkeypatch.setattr('app.codex_bridge.Session',Session)


def test_codex_tools_deduplicate_and_deny_added_permissions(env,monkeypatch):
    s,c,root=env;managed=configure(s);requests=[];sent=[];calls=[]
    call={'id':100,'method':'item/tool/call','params':{'threadId':'test-thread','callId':'same-call','tool':'create_task','arguments':{'title':'One'}}}
    events=[{'id':99,'method':'item/permissions/requestApproval','params':{}},call,dict(call,id=101),
            {'method':'item/completed','params':{'threadId':'test-thread','item':{'type':'agentMessage','id':'answer','text':'Created one task.'}}},
            {'method':'turn/completed','params':{'threadId':'test-thread','turn':{'status':'completed'}}}]
    fake_session(monkeypatch,events,requests,sent)
    def execute(name,args):calls.append((name,args));return {'id':'created'}
    result=asyncio.run(managed.run('Create one task','Use authorized tools',[{'name':'create_task','description':'Create task','parameters':{'type':'object'}}],execute))
    assert result['answer']=='Created one task.' and len(calls)==1 and len(result['actions'])==1
    assert 'error' in sent[0] and sent[1]['result']==sent[2]['result']
    thread=requests[0][1]
    assert thread['sandbox']=='read-only' and thread['ephemeral'] is True and thread['approvalPolicy']=='never'
    assert s.chatgpt.codex.public()['status']=='ready'
    assert 'private-codex-token' not in json.dumps(c.get('/api/state').json())


def test_codex_unknown_tool_never_executes_and_failed_turn_is_not_success(env,monkeypatch):
    s,c,root=env;managed=configure(s);requests=[];sent=[]
    events=[{'id':100,'method':'item/tool/call','params':{'threadId':'test-thread','callId':'bad','tool':'read_vault','arguments':{}}},
            {'method':'turn/completed','params':{'threadId':'test-thread','turn':{'status':'failed','error':{'message':'private-provider-details'}}}}]
    fake_session(monkeypatch,events,requests,sent)
    def execute(*args):raise AssertionError('Unauthorized tool executed')
    with pytest.raises(HTTPException) as error:asyncio.run(managed.run('hello','instructions',execute=execute))
    assert sent[0]['result']['success'] is False
    assert 'private-provider-details' not in error.value.detail
    assert s.store.config('codex_auth')['tokens']['access_token']=='private-codex-token'
    assert managed.public()['status']=='needs_attention'


def test_codex_assistant_honors_selected_project(env,monkeypatch):
    s,c,root=env;configure(s);p=project(c,True);other=project(c,True)
    async def run(query,instructions,tools,execute):
        with pytest.raises(HTTPException) as denied:execute('create_task',{'project_id':other['id'],'title':'Wrong project'})
        assert denied.value.status_code==403
        result=execute('create_task',{'project_id':p['id'],'title':'Connected task'})
        return {'answer':'Created task','actions':[{'tool':'create_task','status':'succeeded'}],'sources':[]}
    monkeypatch.setattr(s.chatgpt.codex,'run',run)
    result=c.post('/api/assistant',json={'message':'Create task','project_id':p['id']})
    assert result.status_code==200 and result.json()['mode']=='Codex · ChatGPT plan'
    assert len(s.store.list('task'))==1 and s.store.list('task')[0]['project_id']==p['id']


def test_codex_connection_is_account_scoped(env):
    s,c,root=env;configure(s)
    assert c.post('/api/signup',json={'username':'second','name':'Second','password':'second-account-pass'}).status_code==200
    assert c.post('/api/login',json={'username':'second','password':'second-account-pass','device':'B'}).status_code==200
    result=c.get('/api/codex').json()
    assert not result['connected']
    with s.accounts.use(s.accounts.entries()['second']):
        assert not s.store.config('codex_auth',{})


def test_phone_codex_uses_structured_intent_without_workspace_content(env,monkeypatch):
    s,c,root=env;managed=configure(s);p=project(c,True);sent=[]
    async def run(query,instructions,**kwargs):
        sent.append((query,kwargs))
        return {'answer':json.dumps({'action':'create','title':'Phone task','project':'Website','due_at':None,'reminder':False})}
    monkeypatch.setattr(managed,'run',run)
    from app.phone_ai import command
    assert asyncio.run(command(s,'AI create Phone task in Website'))=='Task created.'
    assert sent[0][0]=='create Phone task in Website' and set(sent[0][1])=={'output_schema'}
    assert s.store.list('task')[0]['project_id']==p['id']


def test_codex_routes_require_signin(env):
    s,c,root=env;c.cookies.clear()
    for path in ['/api/codex','/api/codex/models']:
        assert c.get(path).status_code==401
    for path in ['/api/codex/start','/api/codex/model','/api/codex/disconnect']:
        assert c.post(path,json={}).status_code==401


def test_signin_requires_the_original_tgtop_session_to_remain_valid(env,monkeypatch):
    s,c,root=env;managed=s.chatgpt.codex;instances=[]
    class Session:
        def __init__(self,store):self.persist_auth=True;instances.append(self)
        async def __aenter__(self):return self
        async def __aexit__(self,*args):pass
        async def rpc(self,method,params):
            if method=='account/login/start':return {'verificationUrl':'https://auth.openai.com/codex/device','userCode':'test-only-code'}
            if method=='account/read':return {'account':{'type':'chatgpt'}}
            if method=='model/list':return {'data':[{'model':'test-model','isDefault':True}]}
        async def event(self):return {'method':'account/login/completed','params':{'success':True}}
    monkeypatch.setattr('app.codex_bridge.Session',Session)
    async def login(identifier):
        await managed.start(identifier)
        await managed.login_task
    asyncio.run(login('ended-session'))
    assert not managed.active() and instances[-1].persist_auth is False
    assert 'session ended' in managed.public()['last_error']
    asyncio.run(login(s.store.list('session')[-1]['id']))
    assert managed.active() and instances[-1].persist_auth is True
    assert managed.public()['status']=='not_checked' and managed.public()['user_code'] is None
