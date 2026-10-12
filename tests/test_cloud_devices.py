from fastapi.testclient import TestClient
from test_workflows import env, project, task

def test_same_account_two_devices_share_files_tasks_and_conflicts(env):
    s,a,root=env
    b=TestClient(s.app,headers={'Origin':s.ORIGIN,'X-TgTop':'1'})
    assert b.post('/api/login',json={'username':'test','password':'account-pass-12345','device':'Home PC'}).status_code==200
    p=project(a); t=task(a,p)
    f=a.post('/api/files',data={'project_id':p['id']},files={'file':('home.txt',b'visible on both devices','text/plain')}).json()
    assert b.get('/api/files/'+f['id']+'/content').content==b'visible on both devices'
    assert a.get('/api/state').json()['device_id']!=b.get('/api/state').json()['device_id']
    change={'operation_id':'home-pc-offline-1','kind':'task','id':t['id'],'version':t['version'],'data':dict(t,title='Edited at home')}
    first=b.post('/api/sync',json={'changes':[change]}).json()['results'][0]
    assert first['status']=='saved'
    retry=b.post('/api/sync',json={'changes':[change]}).json()['results'][0]
    assert retry==first
    assert next(r for r in a.get('/api/state').json()['records'] if r['id']==t['id'])['title']=='Edited at home'
    stale=dict(change,operation_id='other-pc-offline-1',data=dict(t,title='Edited at school'))
    conflict=a.post('/api/sync',json={'changes':[stale]}).json()['results'][0]
    assert conflict['status']=='conflict' and conflict['current']['title']=='Edited at home'
    resolved=a.patch('/api/records/'+t['id'],json={'version':first['record']['version'],'title':'Reviewed merged task'}).json()
    assert next(r for r in b.get('/api/state').json()['records'] if r['id']==t['id'])['version']==resolved['version']
    bid=b.get('/api/state').json()['device_id']
    assert a.post('/api/devices/'+bid+'/revoke').status_code==200
    assert b.get('/api/state').status_code==401
    assert a.get('/api/state').status_code==200
