import json
from datetime import datetime, timezone
import pytest
from test_workflows import env, project
from app import school

def configure(s,c,p,provider='gradescope',mode='upload'):
    r=c.post('/api/school/'+provider+'/configure',json={'project_id':p['id'],'mode':mode})
    assert r.status_code==200,r.text

def upload(c,body,provider='gradescope'):
    r=c.post('/api/school/'+provider+'/upload',files={'file':('schedule.csv',body,'text/csv')})
    assert r.status_code==200,r.text
    return r.json()

def accept(s,c):
    r=s.store.list('school_deadline')[0]
    response=c.post('/api/school/deadlines/'+r['id']+'/review',json={'decision':'import','version':r['version']})
    assert response.status_code==200,response.text
    return s.store.list('task')[0]

def test_review_dedup_updates_completion_conflicts(env):
    s,c,_=env;p=project(c);configure(s,c,p)
    upload(c,b'source_id,title,due_at\n1,Chemistry,2026-11-03T18:00:00-05:00\n')
    assert not s.store.list('task')
    t=accept(s,c)
    t=s.save_task(dict(t,status='done'),t['id'],t['version'])
    upload(c,b'source_id,title,due_at\n1,Chemistry,2026-11-04T18:00:00-05:00\n')
    assert len(s.store.list('task'))==1
    t=s.store.get(t['id']);assert t['status']=='done' and t['due_at'].startswith('2026-11-04')
    s.save_task(dict(t,title='My title'),t['id'],t['version'])
    upload(c,b'source_id,title,due_at\n1,Chemistry revised,2026-11-05T18:00:00-05:00\n')
    candidate=s.store.list('school_deadline')[0]
    assert candidate['status']=='conflict'
    assert s.store.get(t['id'])['title']=='My title'
    assert c.post('/api/school/deadlines/'+candidate['id']+'/review',json={'decision':'import','version':candidate['version'],'task_version':0}).status_code==409
    assert c.post('/api/school/deadlines/'+candidate['id']+'/review',json={'decision':'import','version':candidate['version'],'task_version':s.store.get(t['id'])['version']}).status_code==200
    assert s.store.get(t['id'])['status']=='done'

def test_deleted_task_and_missing_source_preserved(env):
    s,c,_=env;p=project(c);configure(s,c,p)
    body=b'source_id,title,due_at\na,Exam,2026-11-03T18:00:00Z\n'
    upload(c,body);t=accept(s,c)
    upload(c,b'title,due_at\n')
    assert not s.store.get(t['id'])['deleted']
    s.store.put('task',t,t['id'],t['version'],deleted=True)
    upload(c,body)
    assert not s.store.list('task')
    assert s.store.list('school_deadline')[0]['status']=='removed_locally'

def test_duplicates_rollback_and_invalid_upload(env):
    s,c,_=env;p=project(c);configure(s,c,p)
    response=c.post('/api/school/gradescope/upload',files={'file':('schedule.csv',b'source_id,title,due_at\na,A,2026-11-03\na,B,2026-11-04','text/csv')})
    assert response.status_code==400
    assert not s.store.list('school_deadline')
    assert c.post('/api/school/gradescope/upload',files={'file':('schedule.pdf',b'no','application/pdf')}).status_code==400

def test_ics_timezone_and_recurring_rejection():
    content=b'BEGIN:VCALENDAR\nVERSION:2.0\nBEGIN:VEVENT\nUID:exam-1\nSUMMARY:Exam\nDTSTART;VALUE=DATE:20261103\nEND:VEVENT\nEND:VCALENDAR'
    values=school.parse_ics(content,'America/New_York')
    assert values[0]['due_at']=='2026-11-04T04:59:00+00:00'
    with pytest.raises(ValueError):school.parse_ics(content.replace(b'SUMMARY:Exam',b'SUMMARY:Exam\nRRULE:FREQ=WEEKLY'),'America/New_York')
    with pytest.raises(ValueError):school.due('2026-03-08T02:30:00','America/New_York')

def test_provider_url_blocks_private_and_foreign(monkeypatch):
    monkeypatch.setattr(school.socket,'getaddrinfo',lambda *a,**k:[(2,1,6,'',('127.0.0.1',443))])
    with pytest.raises(ValueError):school.public_url('https://school.instructure.com/feed',('instructure.com',))
    for url in ('http://school.instructure.com','https://instructure.com.evil.test','https://token@school.instructure.com'):
        with pytest.raises(ValueError):school.public_url(url,('instructure.com',))

def test_canvas_live_adapter_and_secret_redaction(env,monkeypatch):
    s,c,_=env;p=project(c)
    monkeypatch.setattr(school,'public_url',lambda value,hosts:value)
    token='private-canvas-test-token'
    assert c.post('/api/school/canvas/configure',json={'project_id':p['id'],'mode':'api','base':'https://school.instructure.com','token':token}).status_code==200
    def fake(url,hosts,headers=None):
        assert headers['Authorization']=='Bearer '+token
        return json.dumps([{'course_id':3,'plannable_type':'assignment','plannable':{'id':4,'title':'Exam','due_at':'2026-11-03T18:00:00Z'},'html_url':'/courses/3/assignments/4'}]).encode(),{}
    monkeypatch.setattr(school,'fetch',fake)
    assert c.post('/api/school/canvas/sync',json={}).status_code==200
    assert token not in c.get('/api/school').text+c.get('/api/state').text+c.get('/api/export').text
    assert token.encode() not in (s.store.root/'tgtop.db').read_bytes()
    assert not s.store.list('task')

def test_gradescope_canvas_link_and_cross_provider_dedup(env,monkeypatch):
    s,c,_=env;p=project(c)
    s.store.set_config('school_canvas',{'enabled':True,'mode':'api','base':'https://school.instructure.com','token':'private','source_key':'canvas-key','project_id':p['id']})
    configure(s,c,p,mode='canvas')
    def fake(url,*a):
        if '/assignments?' in url:return json.dumps([{'id':4,'name':'Homework','due_at':'2026-11-03T18:00:00Z','external_tool_tag_attributes':{'url':'https://www.gradescope.com/courses/1'},'html_url':'https://school.instructure.com/courses/3/assignments/4'}]).encode(),{}
        return b'[{"id":3}]',{}
    monkeypatch.setattr(school,'fetch',fake)
    assert c.post('/api/school/gradescope/sync',json={}).status_code==200
    t=accept(s,c)
    school.stage(s,'canvas',[{'source_id':'3:assignment:4','title':'Homework','due_at':t['due_at']}])
    canvas=next(r for r in s.store.list('school_deadline') if r['provider']=='canvas')
    assert canvas['task_id']==t['id'] and len(s.store.list('task'))==1

def test_account_isolation_and_ai_no_connector_access(env):
    s,c,_=env;p=project(c);configure(s,c,p)
    upload(c,b'title,due_at\nPrivate exam,2026-11-03T18:00:00Z')
    deadline=s.store.list('school_deadline')[0]
    token=c.post('/api/mcp-token',json={}).json()['token']
    c.cookies.clear()
    assert c.get('/api/school',headers={'Authorization':'Bearer '+token}).status_code==403
    assert c.post('/api/signup',json={'username':'second','name':'Second','password':'second-pass-12345'}).status_code==200
    assert c.post('/api/login',json={'username':'second','password':'second-pass-12345','device':'Second'}).status_code==200
    assert c.get('/api/school').json()['gradescope']=={}
    assert c.post('/api/school/deadlines/'+deadline['id']+'/review',json={'decision':'import','version':deadline['version']}).status_code==404

def test_outlook_oauth_state_callback_and_graph(env,monkeypatch):
    s,c,_=env;p=project(c)
    assert c.post('/api/school/outlook/configure',json={'project_id':p['id'],'client_id':'12345678-1234-1234-1234-123456789abc','client_secret':'private-test-secret'}).status_code==200
    class Cache:
        def serialize(self):return 'encrypted-only-test-cache'
    class Microsoft:
        def initiate_auth_code_flow(self,*a,**k):return {'state':'unique-test-state','auth_uri':'https://login.microsoftonline.com/common/oauth2/v2.0/authorize'}
        def acquire_token_by_auth_code_flow(self,flow,response):
            assert flow['state']==response['state'];return {'access_token':'private-test-token'}
        def get_accounts(self):return [{'id':'test'}]
        def acquire_token_silent(self,*a,**k):return {'access_token':'private-test-token'}
    monkeypatch.setattr(school,'microsoft',lambda cfg:(Microsoft(),Cache()))
    assert c.post('/api/school/outlook/authorize',json={}).status_code==200
    assert c.get('/school/outlook/callback?state=forged&code=fake').status_code==400
    assert c.get('/school/outlook/callback?state=unique-test-state&code=fake').status_code==200
    assert c.get('/school/outlook/callback?state=unique-test-state&code=fake').status_code==400
    monkeypatch.setattr(school,'fetch',lambda *a:(b'{"value":[{"id":"event-1","subject":"Exam","start":{"dateTime":"2026-11-03T18:00:00.0000000"}}]}',{}))
    assert c.post('/api/school/outlook/sync',json={}).status_code==200
    assert 'private-test-secret' not in c.get('/api/school').text
    assert s.store.list('school_deadline')[0]['fields']['due_at'].startswith('2026-11-03T18:00:00')

def test_sync_failure_retains_tasks_and_disconnect_clears_secrets(env,monkeypatch):
    s,c,_=env;p=project(c);configure(s,c,p)
    upload(c,b'title,due_at\nExam,2026-11-03T18:00:00Z');accept(s,c)
    monkeypatch.setattr(school,'load_items',lambda *a:(_ for _ in ()).throw(ValueError('sensitive-provider-body')))
    assert c.post('/api/school/gradescope/sync',json={}).status_code==400
    assert 'sensitive-provider-body' not in c.get('/api/school').text
    assert len(s.store.list('task'))==1
    assert c.post('/api/school/gradescope/disconnect',json={}).status_code==200
    assert s.store.config('school_gradescope')=={'enabled':False,'status':'disconnected'}
