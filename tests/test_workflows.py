import importlib
import io
import json
import os
from datetime import datetime,timedelta,timezone
from pathlib import Path
from unittest.mock import MagicMock
import pytest
from fastapi.testclient import TestClient

@pytest.fixture
def env(tmp_path,monkeypatch):
    monkeypatch.setenv('TGTOP_DATA',str(tmp_path))
    monkeypatch.setenv('TGTOP_MODE','development')
    monkeypatch.delenv('OPENAI_API_KEY',raising=False)
    import app.server as s
    s=importlib.reload(s)
    s.rates.clear()
    client=TestClient(s.app)
    client.headers.update({'Origin':s.ORIGIN,'X-TgTop':'1'})
    assert client.post('/api/setup',json={'name':'Test','password':'account-pass-12345'}).status_code==200
    assert client.post('/api/login',json={'username':'test','password':'account-pass-12345','device':'Device A'}).status_code==200
    yield s,client,tmp_path
    s.store.db.close()

def project(c,allowed=False):
    r=c.post('/api/records/project',json={'title':'Website','space':'personal','ai_allowed':allowed})
    assert r.status_code==200,r.text
    return r.json()

def task(c,p,title='Write chemistry assignment'):
    r=c.post('/api/records/task',json={'title':title,'project_id':p['id'],'status':'open','priority':'high','due_at':(datetime.now(timezone.utc)+timedelta(days=1)).isoformat()})
    assert r.status_code==200,r.text
    return r.json()

def test_project_file_task_context_and_permissions(env):
    s,c,root=env;p=project(c,True)
    f=c.post('/api/files',data={'project_id':p['id'],'tags':'school,chemistry'},files={'file':('chemistry.txt',b'Assignment: balance chemical equations','text/plain')}).json()
    t=task(c,p)
    assert c.patch('/api/records/'+t['id'],json={'version':t['version'],'file_ids':[f['id']]}).status_code==200
    assert c.get('/api/files/'+f['id']+'/content').content==b'Assignment: balance chemical equations'
    assert f['id'] not in [r['id'] for r in s.authorized_context('chemistry')]
    assert c.patch('/api/records/'+f['id'],json={'version':f['version'],'ai_allowed':True}).status_code==200
    r=c.post('/api/assistant',json={'message':'chemistry','project_id':p['id']}).json()
    assert 'simulator' in r['mode'].lower()
    assert f['id'] in [x['id'] for x in r['sources']]
    conversation=s.store.list('conversation')[0]
    current=s.store.get(f['id'])
    c.patch('/api/records/'+f['id'],json={'version':current['version'],'ai_allowed':False})
    assert conversation['id'] not in [x['id'] for x in s.authorized_context('chemistry',p['id'])]
    assert b'chemical equations' not in (root/'blobs'/f['id']).read_bytes()
    assert c.patch('/api/records/'+p['id'],json={'version':p['version'],'ai_allowed':False}).status_code==200
    assert not s.authorized_context('chemistry',p['id'])

def test_small_host_rejects_large_upload_before_blob_write(env, monkeypatch):
    s,c,root=env
    monkeypatch.setattr(s,'UPLOAD_BYTES',64)
    p=project(c)
    response=c.post('/api/files',data={'project_id':p['id']},files={'file':('large.txt',b'x'*65,'text/plain')})
    assert response.status_code==413
    assert not list((root/'blobs').iterdir())

def test_small_host_backup_limit_keeps_account_intact(env, monkeypatch):
    s,c,root=env
    p=project(c)
    monkeypatch.setattr(s,'BACKUP_BYTES',1)
    response=c.post('/api/backup',json={'password':'backup-pass-12345'})
    assert response.status_code==413
    assert c.get('/api/status').status_code==200
    assert s.store.get(p['id'])['title']=='Website'
    response=c.post('/api/restore',data={'confirm':'RESTORE','password':'backup-pass-12345'},files={'file':('backup.tgtop',b'TGTOP1too-large','application/octet-stream')})
    assert response.status_code==413
    assert s.store.get(p['id'])['title']=='Website'

def test_vault_lock_unlock_timeout_and_no_leak(env):
    s,c,root=env;p=project(c,True)
    assert c.post('/api/vault/setup',json={'password':'vault-master-12345'}).status_code==200
    assert c.post('/api/vault/save',json={'title':'API','project_id':p['id'],'secret':'super-secret-value'}).status_code==423
    assert c.post('/api/vault/unlock',json={'password':'wrong-password'}).status_code==403
    assert c.post('/api/vault/unlock',json={'password':'vault-master-12345'}).status_code==200
    r=c.post('/api/vault/save',json={'title':'API','project_id':p['id'],'secret':'super-secret-value'}).json()
    assert 'ciphertext' not in r
    assert 'super-secret-value' not in c.get('/api/state').text
    assert 'super-secret-value' not in json.dumps(s.authorized_context('API'))
    assert c.post('/api/vault/reveal',json={'id':r['id']}).json()['secret']=='super-secret-value'
    c.post('/api/vault/lock',json={})
    assert c.post('/api/vault/reveal',json={'id':r['id']}).status_code==423
    c.post('/api/vault/unlock',json={'password':'vault-master-12345'})
    sid=c.get('/api/state').json()['device_id'];key,_=s.vault.keys[sid];s.vault.keys[sid]=(key,0)
    assert c.post('/api/vault/reveal',json={'id':r['id']}).status_code==423

def test_reminder_restart_dedupe_and_desktop_ack(env):
    s,c,root=env;p=project(c);t=task(c,p)
    c.post('/api/settings',json={'quiet_start':'00:00','quiet_end':'00:00'})
    due=(datetime.now(timezone.utc)-timedelta(minutes=1)).isoformat()
    r=c.post('/api/records/reminder',json={'task_id':t['id'],'project_id':p['id'],'due_at':due,'channel':'desktop','state':'pending'}).json()
    from app.store import Store
    second=Store(root)
    assert second.get(r['id'])['state']=='pending'
    second.db.close()
    s.tick();s.tick()
    deliveries=s.store.list('delivery')
    assert len(deliveries)==1 and deliveries[0]['status']=='waiting_device'
    assert c.post('/api/deliveries/'+deliveries[0]['id']+'/ack',json={}).json()['status']=='delivered'

def test_sms_simulator_verified_and_duplicate(env):
    s,c,root=env
    assert c.post('/api/simulator/sms',json={'body':'add task Remote test','message_id':'a'}).status_code==403
    code=c.post('/api/phone/start',json={'phone':'+15555550123'}).json()['development_code']
    assert c.post('/api/phone/verify',json={'code':code}).status_code==200
    r=c.post('/api/simulator/sms',json={'body':'Remind me tomorrow at 6 PM to submit my assignment','message_id':'a'}).json()
    assert r['status']=='succeeded' and 'scheduled' in r['answer']
    assert c.post('/api/simulator/sms',json={'body':'add task Duplicate','message_id':'a'}).json()['status']=='duplicate'
    assert len(s.store.list('task'))==1
    assert 'private workspace' in s.remote_command('send my passwords')
    assert 'clarify' in s.remote_command('do that thing')
    assert 'waiting for approval' in s.remote_command('Start my approved backup workflow')
    assert s.store.list('workflow')[0]['status']=='awaiting_approval'

def test_provider_signature_unauthorized_replay_and_outbound(env,monkeypatch):
    s,c,root=env
    monkeypatch.setattr(s,'MODE','live')
    monkeypatch.setenv('TWILIO_AUTH_TOKEN','test-auth-token')
    monkeypatch.setenv('TWILIO_ACCOUNT_SID','AC'+'0'*32)
    monkeypatch.setenv('TWILIO_FROM','+15555550124')
    monkeypatch.setenv('TWILIO_WEBHOOK_URL','https://example.test/api/sms/incoming')
    cfg=s.settings();cfg.update(phone='+15555550123',phone_verified=True,phone_verification_mode='live');s.store.set_config('settings',cfg)
    from twilio.request_validator import RequestValidator
    payload={'From':cfg['phone'],'Body':'add task Verified command','MessageSid':'SM'+'a'*32}
    sig=RequestValidator('test-auth-token').compute_signature('https://example.test/api/sms/incoming',payload)
    assert c.post('/api/sms/incoming',data=payload).status_code==403
    fake=MagicMock();fake.messages.return_value.fetch.return_value=MagicMock(from_=cfg['phone'],body=payload['Body'],date_created=datetime.now(timezone.utc))
    fake.messages.create.return_value=MagicMock(sid='SM'+'b'*32)
    monkeypatch.setattr('twilio.rest.Client',lambda *args:fake)
    r=c.post('/api/sms/incoming',data=payload,headers={'X-Twilio-Signature':sig})
    assert r.status_code==200 and r.text=='<Response/>'
    assert fake.messages.create.call_args.kwargs['body'].startswith('Task created')
    assert fake.messages.create.call_count==1
    assert c.post('/api/sms/incoming',data=payload,headers={'X-Twilio-Signature':sig}).text=='<Response/>'
    assert len(s.store.list('task'))==1
    assert fake.messages.create.call_count==1
    bad={**payload,'From':'+15555550999','MessageSid':'SM'+'c'*32}
    sigbad=RequestValidator('test-auth-token').compute_signature('https://example.test/api/sms/incoming',bad)
    assert c.post('/api/sms/incoming',data=bad,headers={'X-Twilio-Signature':sigbad}).status_code==403
    assert s.send_sms('Generic reminder')['mode']=='live'
    assert fake.messages.create.call_args.kwargs['body']=='Generic reminder'

def test_two_devices_sync_conflict_idempotency_revocation(env):
    s,a,root=env;p=project(a);t=task(a,p)
    b=TestClient(s.app);b.headers.update({'Origin':s.ORIGIN,'X-TgTop':'1'})
    assert b.post('/api/login',json={'username':'test','password':'account-pass-12345','device':'Device B'}).status_code==200
    change={'operation_id':'op-1','id':t['id'],'kind':'task','version':t['version'],'data':{**t,'title':'Device B revision'}}
    r=b.post('/api/sync',json={'changes':[change]}).json()['results'][0]
    assert r['status']=='saved'
    assert b.post('/api/sync',json={'changes':[change]}).json()['results'][0]['record']['version']==2
    stale={**change,'operation_id':'op-2','data':{**t,'title':'Device A proposed'}}
    conflict=a.post('/api/sync',json={'changes':[stale]}).json()['results'][0]
    assert conflict['status']=='conflict' and conflict['current']['title']=='Device B revision'
    assert a.patch('/api/records/'+t['id'],json={'version':conflict['current']['version'],'title':'Merged resolution'}).status_code==200
    assert any(e['record']['title']=='Merged resolution' for e in b.get('/api/sync').json()['events'] if e['kind']=='task')
    sid=b.get('/api/state').json()['device_id'];a.post('/api/devices/'+sid+'/revoke',json={})
    assert b.get('/api/state').status_code==401

def test_backup_restore_file_vault_and_sessions(env):
    s,c,root=env;p=project(c);t=task(c,p)
    f=c.post('/api/files',data={'project_id':p['id']},files={'file':('test.txt',b'original','text/plain')}).json()
    c.post('/api/vault/setup',json={'password':'master-vault-pass'})
    c.post('/api/vault/unlock',json={'password':'master-vault-pass'})
    v=c.post('/api/vault/save',json={'title':'Test','project_id':p['id'],'secret':'protected'}).json()
    backup=c.post('/api/backup',json={'password':'backup-long-pass'}).content
    assert backup.startswith(b'TGTOP1') and b'original' not in backup
    c.patch('/api/records/'+t['id'],json={'version':t['version'],'title':'Changed'})
    bad=c.post('/api/restore',data={'password':'incorrect','confirm':'RESTORE'},files={'file':('backup.tgtop',backup)})
    assert bad.status_code==400
    r=c.post('/api/restore',data={'password':'backup-long-pass','confirm':'RESTORE'},files={'file':('backup.tgtop',backup)})
    assert r.status_code==200,r.text
    assert (root/'before-restore.tgtop').exists()
    assert c.get('/api/state').status_code==401
    c.post('/api/login',json={'username':'test','password':'account-pass-12345','device':'Restored device'})
    assert s.store.get(t['id'])['title']==t['title']
    assert c.get('/api/files/'+f['id']+'/content').content==b'original'
    assert c.post('/api/vault/reveal',json={'id':v['id']}).status_code==423
    c.post('/api/vault/unlock',json={'password':'master-vault-pass'})
    assert c.post('/api/vault/reveal',json={'id':v['id']}).json()['secret']=='protected'

def test_auth_csrf_scope_paths_dependencies_and_trash(env):
    s,c,root=env;p=project(c,True);t=task(c,p)
    anon=TestClient(s.app)
    assert anon.get('/api/state').status_code==401
    bad=TestClient(s.app);bad.cookies.update(c.cookies)
    assert bad.post('/api/records/task',json={'title':'CSRF'}).status_code==403
    token=c.post('/api/mcp-token',json={}).json()['token']
    headers={'Authorization':'Bearer '+token}
    assert anon.get('/api/state',headers=headers).status_code==403
    assert anon.post('/api/tools/search_context',headers=headers,json={'query':'chemistry'}).status_code==200
    assert c.post('/api/files/reference',json={'path':str(root/'server.key'),'project_id':p['id']}).status_code==403
    other=task(c,p,'Dependency')
    assert c.patch('/api/records/'+t['id'],json={'version':t['version'],'dependencies':[other['id']]}).status_code==200
    assert c.patch('/api/records/'+other['id'],json={'version':other['version'],'dependencies':[t['id']]}).status_code==400
    assert c.patch('/api/records/'+t['id'],json={'version':2,'status':'done'}).status_code==409
    assert c.post('/api/records/'+t['id']+'/trash',json={'version':2}).status_code==400
    assert c.post('/api/records/'+t['id']+'/trash',json={'version':2,'confirm':True}).status_code==200
    assert c.post('/api/records/'+t['id']+'/restore',json={}).status_code==200

def test_quiet_hours_dst_and_workflow_approval(env):
    s,c,root=env
    assert s.quiet_until(datetime(2026,11,1,5,30,tzinfo=timezone.utc)).hour==12
    r=c.post('/api/workflows/backup',json={}).json()
    assert c.post('/api/workflows/'+r['id']+'/run',json={'password':'long-backup-pass'}).status_code==403
    assert c.post('/api/workflows/'+r['id']+'/approve',json={'confirm':True}).status_code==200
    result=c.post('/api/workflows/'+r['id']+'/run',json={'password':'long-backup-pass'})
    assert result.status_code==200 and result.content.startswith(b'TGTOP1')
    assert s.store.get(r['id'])['status']=='completed'
