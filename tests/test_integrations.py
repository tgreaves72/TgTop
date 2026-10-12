from unittest.mock import MagicMock
from datetime import datetime,timedelta,timezone
import pytest
from test_workflows import env,project,task

def test_stale_provider_message_rejected_before_execution(env,monkeypatch):
    s,c,root=env;monkeypatch.setattr(s,'MODE','live')
    monkeypatch.setenv('TWILIO_AUTH_TOKEN','test-auth-token');monkeypatch.setenv('TWILIO_ACCOUNT_SID','AC'+'0'*32);monkeypatch.setenv('TWILIO_WEBHOOK_URL','https://example.test/api/sms/incoming')
    cfg=s.settings();cfg.update(phone='+15555550123',phone_verified=True,phone_verification_mode='live');s.store.set_config('settings',cfg)
    payload={'From':cfg['phone'],'Body':'add task Stale command','MessageSid':'SM'+'d'*32}
    from twilio.request_validator import RequestValidator
    signature=RequestValidator('test-auth-token').compute_signature('https://example.test/api/sms/incoming',payload)
    fake=MagicMock();fake.messages.return_value.fetch.return_value=MagicMock(from_=cfg['phone'],body=payload['Body'],date_created=datetime.now(timezone.utc)-timedelta(hours=1));monkeypatch.setattr('twilio.rest.Client',lambda *a:fake)
    assert c.post('/api/sms/incoming',data=payload,headers={'X-Twilio-Signature':signature}).status_code==403
    assert not s.store.list('task')
    assert not s.store.claimed('sms:'+payload['MessageSid'])

def test_openai_structured_tool_loop_and_sources(env,monkeypatch):
    s,c,root=env;p=project(c,True);t=task(c,p)
    monkeypatch.setenv('OPENAI_API_KEY','test-provider-key');monkeypatch.setenv('OPENAI_MODEL','configured-test-model')
    from types import SimpleNamespace
    import json
    class Call:
        type='function_call';name='search_context';call_id='call-1';arguments=json.dumps({'query':'chemistry','project_id':p['id']})
        def model_dump(self,**kwargs): return {'type':self.type,'name':self.name,'call_id':self.call_id,'arguments':self.arguments}
    calls=[]
    async def response(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(output=[Call()],output_text='') if len(calls)==1 else SimpleNamespace(output=[],output_text='Your chemistry task is due tomorrow. ['+t['id']+']')
    provider=SimpleNamespace(responses=SimpleNamespace(create=response))
    monkeypatch.setattr('openai.AsyncOpenAI',lambda **kwargs:provider)
    r=c.post('/api/assistant',json={'message':'What is next?','project_id':p['id']})
    assert r.status_code==200,r.text
    assert r.json()['mode']=='OpenAI Responses API' and t['id'] in [r['id'] for r in r.json()['sources']]
    assert all(call['store'] is False for call in calls)
    assert all(tool['strict'] for tool in calls[0]['tools'])
    assert calls[1]['input'][-1]['type']=='function_call_output'

def test_dispatch_crash_review_and_sim_verification_cannot_send_live(env,monkeypatch):
    s,c,root=env;p=project(c);t=task(c,p)
    c.post('/api/settings',json={'quiet_start':'00:00','quiet_end':'00:00'})
    due=(datetime.now(timezone.utc)-timedelta(minutes=2)).isoformat()
    r=c.post('/api/records/reminder',json={'task_id':t['id'],'project_id':p['id'],'due_at':due,'channel':'sms','state':'pending'}).json()
    d=s.store.put('delivery',{'task_id':t['id'],'reminder_id':r['id'],'channel':'sms','status':'dispatching','created_at':due})
    s.store.claim('reminder:'+r['id']+':'+due)
    s.tick()
    assert s.store.get(d['id'])['status']=='needs_review'
    assert s.store.get(r['id'])['state']=='failed'
    cfg=s.settings();cfg.update(phone='+15555550123',phone_verified=True,phone_verification_mode='development');s.store.set_config('settings',cfg)
    monkeypatch.setattr(s,'MODE','live')
    with pytest.raises(RuntimeError,match='live_phone_verification_required'): s.send_sms('Generic notice')

def test_subtask_cycles_and_rate_limits(env):
    s,c,root=env;p=project(c);t=task(c,p)
    assert c.patch('/api/records/'+t['id'],json={'version':t['version'],'parent_id':t['id']}).status_code==400
    for i in range(5): assert c.post('/api/login',json={'password':'wrong'}).status_code in (401,429)
    assert c.post('/api/login',json={'password':'wrong'}).status_code==429
