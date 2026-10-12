import asyncio
import importlib
from concurrent.futures import ThreadPoolExecutor
from fastapi.testclient import TestClient
from test_workflows import env

def new_user(s,name):
    c=TestClient(s.app,headers={'Origin':s.ORIGIN,'X-TgTop':'1'})
    assert c.post('/api/signup',json={'username':name,'name':name.title(),'password':'second-account-pass-2026'}).status_code==200
    assert c.post('/api/login',json={'username':name.upper(),'password':'second-account-pass-2026'}).status_code==200
    return c

def test_users_have_separate_records_files_vault_connections_and_events(env):
    s,owner,root=env
    p=owner.post('/api/records/project',json={'title':'Private owner project','ai_allowed':True}).json()
    f=owner.post('/api/files',data={'project_id':p['id']},files={'file':('private.txt',b'Owner private bytes','text/plain')}).json()
    t=owner.post('/api/records/task',json={'title':'Owner only task','project_id':p['id'],'status':'open'}).json()
    owner.post('/api/vault/setup',json={'password':'owner-vault-pass-2026'}).raise_for_status()
    owner.post('/api/vault/unlock',json={'password':'owner-vault-pass-2026'}).raise_for_status()
    secret=owner.post('/api/vault/save',json={'title':'Private credential','project_id':p['id'],'secret':'owner-secret'}).json()
    s.store.set_config('chatgpt',{'active':'one','accounts':{'one':{'access_token':'owner-only-token','scopes':['chatgpt.tokens.use.direct'],'model':'test'}}})
    user=new_user(s,'alex')
    state=user.get('/api/state').json()
    assert state['account']['username']=='alex'
    assert len([r for r in state['records'] if r['kind']=='project'])==3
    assert p['id'] not in str(state) and 'owner-only-token' not in str(state)
    assert not state['chatgpt']['connected'] and not state['vault_configured']
    assert user.get('/api/files/'+f['id']+'/content').status_code==404
    assert user.patch('/api/records/'+t['id'],json={'version':t['version'],'title':'Cross user'}).status_code==404
    assert user.post('/api/records/task',json={'title':'Invalid link','project_id':p['id']}).status_code==404
    assert user.post('/api/vault/reveal',json={'id':secret['id']}).status_code in (404,423)
    assert p['id'] not in str(user.get('/api/sync').json())
    assert p['id'] not in str(user.get('/api/export').json())
    assert owner.post('/api/vault/reveal',json={'id':secret['id']}).json()['secret']=='owner-secret'
    assert owner.get('/api/state').json()['account']['username']=='test'
    # Concurrent requests never switch another request's storage context.
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures=[pool.submit(c.get,'/api/state') for c in [owner,user]*8]
        for index,future in enumerate(futures):assert future.result().json()['account']['username']==('test' if index%2==0 else 'alex')
    cookie=user.cookies.get('tgtop_session')
    s=importlib.reload(s)
    reopened=TestClient(s.app,headers={'Origin':s.ORIGIN,'X-TgTop':'1'})
    reopened.cookies.set('tgtop_session',cookie)
    assert reopened.get('/api/state').json()['account']['username']=='alex'
    assert reopened.post('/api/logout',json={}).status_code==200
    assert reopened.post('/api/login',json={'username':'alex','password':'second-account-pass-2026'}).status_code==200

def test_username_required_duplicates_rejected_and_password_changes_are_scoped(env):
    s,owner,root=env
    user=new_user(s,'alex')
    assert user.post('/api/signup',json={'username':'ALEX','password':'other-account-pass-2026'}).status_code==409
    assert user.post('/api/signup',json={'username':'../test','password':'other-account-pass-2026'}).status_code==400
    unknown=TestClient(s.app,headers={'Origin':s.ORIGIN,'X-TgTop':'1'})
    for body in [{'password':'account-pass-12345'},{'username':'alex','password':'account-pass-12345'},{'username':'unknown','password':'second-account-pass-2026'}]:
        r=unknown.post('/api/login',json=body);assert r.status_code==401 and r.json()['detail']=='Username or password is incorrect'
    assert user.post('/api/account/password',json={'current_password':'second-account-pass-2026','new_password':'changed-account-pass-2026'}).status_code==200
    assert user.get('/api/state').status_code==401
    assert owner.get('/api/state').status_code==200
    user.headers['Authorization']='Bearer '+owner.post('/api/mcp-token',json={}).json()['token']
    user.cookies.clear()
    assert user.get('/api/state').status_code==403
    assert user.post('/api/tools/search_context',json={'query':'Private'}).status_code==200

def test_legacy_account_migration_preserves_sessions_and_records(tmp_path,monkeypatch):
    from app.store import Store,now
    from app.security import hasher,token_hash
    from datetime import datetime,timedelta,timezone
    original=Store(tmp_path)
    original.set_config('account',{'name':'Tyler','password_hash':hasher.hash('existing-account-pass-2026')})
    task=original.put('task',{'title':'Existing history','status':'open'})
    original.put('session',{'token_hash':token_hash('legacy-cookie'),'expires':(datetime.now(timezone.utc)+timedelta(days=1)).isoformat(),'revoked':False})
    original.db.close()
    monkeypatch.setenv('TGTOP_DATA',str(tmp_path));monkeypatch.setenv('TGTOP_MODE','development')
    import app.server as s
    s=importlib.reload(s)
    client=TestClient(s.app,headers={'Origin':s.ORIGIN,'X-TgTop':'1'})
    client.cookies.set('tgtop_session','legacy-cookie')
    state=client.get('/api/state').json()
    assert state['account']['username']=='tyler' and task['id'] in str(state)
    assert client.post('/api/login',json={'username':'tyler','password':'existing-account-pass-2026'}).status_code==200


def test_backup_restore_and_reminder_processing_stay_in_one_account(env):
    import io
    from datetime import datetime,timedelta,timezone
    s,owner,root=env
    user=new_user(s,'alex')
    p=user.get('/api/state').json()['records'][0]
    task=user.post('/api/records/task',json={'title':'Alex reminder','project_id':p['id'],'status':'open'}).json()
    due=(datetime.now(timezone.utc)-timedelta(minutes=1)).isoformat()
    user.post('/api/settings',json={'quiet_start':'00:00','quiet_end':'00:00'}).raise_for_status()
    reminder=user.post('/api/records/reminder',json={'task_id':task['id'],'project_id':p['id'],'due_at':due,'channel':'desktop'}).json()
    blob=user.post('/api/backup',json={'password':'alex-backup-pass-2026'}).content
    owner_task=owner.post('/api/records/task',json={'title':'Owner unaffected','status':'open'}).json()
    s.tick_accounts()
    assert reminder['id'] not in str(owner.get('/api/state').json())
    assert any(r['kind']=='delivery' for r in user.get('/api/state').json()['records'])
    restore=user.post('/api/restore',data={'password':'alex-backup-pass-2026','confirm':'RESTORE'},files={'file':('backup.tgtop',blob,'application/octet-stream')})
    assert restore.status_code==200
    assert user.get('/api/state').status_code==401
    assert owner_task['id'] in str(owner.get('/api/state').json())
    assert user.post('/api/login',json={'username':'alex','password':'second-account-pass-2026'}).status_code==200
    assert task['id'] in str(user.get('/api/state').json())
