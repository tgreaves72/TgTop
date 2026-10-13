from datetime import datetime,timedelta,timezone
from test_workflows import env,project,task

def test_auto_sms_reschedule_completion_recurrence(env):
    s,c,_=env
    s.store.set_config('settings',dict(s.settings(),calendar_sms=True))
    p=project(c);t=task(c,p)
    r=s.store.list('reminder')[0]
    assert r['channel']=='sms' and r['calendar_auto']
    assert datetime.fromisoformat(t['due_at'])-datetime.fromisoformat(r['due_at'])==timedelta(hours=1)
    changed=c.patch('/api/records/'+t['id'],json={'version':t['version'],'due_at':(datetime.now(timezone.utc)+timedelta(days=2)).isoformat(),'recurrence':'daily'}).json()
    assert len(s.store.list('reminder'))==1
    assert s.store.get(r['id'])['due_at']!=r['due_at']
    done=c.patch('/api/records/'+t['id'],json={'version':changed['version'],'status':'done'})
    assert done.status_code==200
    assert s.store.get(r['id'])['state']=='cancelled'
    assert len([v for v in s.store.list('reminder') if v['state']=='pending'])==1

def test_auto_sms_backfill_restart_quiet_hours_dedup(env,monkeypatch):
    s,c,root=env;p=project(c);t=task(c,p)
    s.store.set_config('settings',dict(s.settings(),calendar_sms=True,quiet_start='00:00',quiet_end='23:59'))
    calls=[]
    monkeypatch.setattr(s,'send_sms',lambda message:(calls.append(message) or {'mode':'live','provider':'photon','sid':'test'}))
    at=datetime.fromisoformat(t['due_at'])-timedelta(hours=1)
    s.tick(at)
    assert len(calls)==1
    assert t['title'] not in calls[0]
    from app.store import Store
    reopened=Store(root)
    assert reopened.list('reminder')[0]['state']=='sent'
    reopened.db.close()
    s.tick(at+timedelta(minutes=1))
    assert len(calls)==1 and len(s.store.list('delivery'))==1

def test_auto_sms_overdue_skip_and_deleted_task_cancel(env,monkeypatch):
    s,c,_=env;p=project(c);t=task(c,p)
    s.store.set_config('settings',dict(s.settings(),calendar_sms=True))
    calls=[];monkeypatch.setattr(s,'send_sms',lambda message:calls.append(message))
    s.tick(datetime.fromisoformat(t['due_at'])+timedelta(minutes=1))
    assert s.store.list('reminder')[0]['state']=='expired' and not calls
    future=task(c,p)
    r=next(v for v in s.store.list('reminder') if v['task_id']==future['id'])
    assert c.post('/api/records/'+future['id']+'/trash',json={'confirm':True,'version':future['version']}).status_code==200
    assert s.store.get(r['id'])['state']=='cancelled'

def test_auto_sms_near_deadline_and_preference_cancel(env,monkeypatch):
    s,c,_=env;p=project(c);t=task(c,p)
    s.store.set_config('settings',dict(s.settings(),calendar_sms=True))
    calls=[]
    monkeypatch.setattr(s,'send_sms',lambda message:(calls.append(message) or {'mode':'live','provider':'photon','sid':'test'}))
    t=c.patch('/api/records/'+t['id'],json={'version':t['version'],'due_at':(datetime.now(timezone.utc)+timedelta(minutes=30)).isoformat()}).json()
    s.tick()
    assert len(calls)==1
    future=task(c,p)
    assert c.post('/api/settings',json={'calendar_sms':False}).status_code==200
    s.tick()
    assert next(r for r in s.store.list('reminder') if r['task_id']==future['id'])['state']=='cancelled'
    assert len(calls)==1
