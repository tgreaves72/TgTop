import pytest
from test_workflows import env,project,task

def test_workflow_patch_cannot_approve(env):
    s,c,_=env
    workflow=c.post('/api/workflows/backup',json={}).json()
    assert c.patch('/api/records/'+workflow['id'],json={'version':workflow['version'],'status':'waiting_device','device_id':c.get('/api/state').json()['device_id']}).status_code==403
    assert s.store.get(workflow['id'])['status']=='awaiting_approval'

def test_sms_completion_recurs_once(env):
    s,c,_=env;p=project(c);t=task(c,p)
    t=c.patch('/api/records/'+t['id'],json={'version':t['version'],'recurrence':'daily'}).json()
    assert s.remote_command('mark '+t['title']+' complete')=='Task completed.'
    assert len(s.store.list('task'))==2
    s.save_task(dict(s.store.get(t['id']),status='done'),t['id'],s.store.get(t['id'])['version'])
    assert len(s.store.list('task'))==2

def test_sync_receipt_rolls_back_mutation_and_binds_payload(env,monkeypatch):
    s,c,_=env;p=project(c);t=task(c,p)
    change={'operation_id':'atomic-sync','id':t['id'],'kind':'task','version':t['version'],'data':dict(t,title='Updated')}
    original=s.store.set_config
    def fail(name,value):
        if name.startswith('sync:'):raise RuntimeError('injected receipt failure')
        original(name,value)
    monkeypatch.setattr(s.store,'set_config',fail)
    with pytest.raises(RuntimeError):s.sync_change(change)
    assert s.store.get(t['id'])['title']==t['title']
    monkeypatch.setattr(s.store,'set_config',original)
    first=s.sync_change(change)
    assert s.sync_change(change)==first
    with pytest.raises(Exception):s.sync_change(dict(change,data=dict(change['data'],title='Different')))

def test_phone_action_and_reply_recover_independently(env,monkeypatch):
    s,c,_=env
    from app.remote import receive,finish,replies
    s.store.set_config('settings',dict(s.settings(),phone='+15555550123',phone_verified=True,phone_verification_mode='live'))
    record=receive(s,'test','message-one','+15555550123','add task Recoverable')
    answer=finish(s,record['id'],lambda:s.remote_command(record['body']))
    assert len(s.store.list('task'))==1
    assert finish(s,record['id'],lambda:pytest.fail('action repeated'))==answer
    def failed(*args):raise RuntimeError('network outcome unknown')
    monkeypatch.setattr(s.messaging,'send',failed)
    replies(s)
    assert s.store.get(record['id'])['reply_status']=='needs_review'
    assert len(s.store.list('task'))==1
    assert c.post('/api/remote/'+record['id']+'/retry-reply',json={}).status_code==400
    assert c.post('/api/remote/'+record['id']+'/retry-reply',json={'confirm':True}).status_code==200
    monkeypatch.setattr(s.messaging,'send',lambda *args:{'sid':'test-reply','mode':'live'})
    replies(s)
    assert s.store.get(record['id'])['reply_status']=='submitted'
    assert len(s.store.list('task'))==1
    assert 'Recoverable' not in str(s.safe_record(s.store.get(record['id'])))

def test_monthly_recurrence_preserves_month_end(env):
    s,c,_=env;p=project(c)
    t=c.post('/api/records/task',json={'title':'Month end','project_id':p['id'],'status':'open','recurrence':'monthly','due_at':'2026-01-31T23:00:00+00:00'}).json()
    c.patch('/api/records/'+t['id'],json={'version':t['version'],'status':'done'})
    feb=next(t for t in s.store.list('task') if t['status']=='open')
    assert feb['due_at'].startswith('2026-02-28')
    c.patch('/api/records/'+feb['id'],json={'version':feb['version'],'status':'done'})
    march=next(t for t in s.store.list('task') if t['status']=='open')
    assert march['due_at'].startswith('2026-03-31')

def test_restart_rolls_back_interrupted_restore(env):
    s,c,_=env
    from app.recovery import prepare,recover
    from app.store import Store
    p=project(c);prepare(s.store)
    s.store.put('project',dict(p,title='Interrupted replacement'),p['id'],p['version'])
    s.store.db.close()
    restored=Store(s.store.root)
    assert restored.get(p['id'])['title']==p['title']
    assert not (restored.root/'restore-journal').exists()
    s.store.db=restored.db

def test_security_rate_limit_survives_memory_reset(env):
    s,c,_=env
    for _ in range(2):s.limit('login:durable-test',2,60)
    s.rates.clear()
    with pytest.raises(Exception) as e:s.limit('login:durable-test',2,60)
    assert e.value.status_code==429

def test_authenticator_setup_replay_and_recovery(env):
    s,c,_=env
    import pyotp
    from fastapi.testclient import TestClient
    start=c.post('/api/security/totp/start',json={'password':'account-pass-12345'})
    assert start.status_code==200
    secret=start.json()['secret'];code=pyotp.TOTP(secret).now()
    enabled=c.post('/api/security/totp/confirm',json={'code':code})
    assert enabled.status_code==200
    recovery=enabled.json()['recovery_codes'][0]
    anonymous=TestClient(s.app,headers={'Origin':s.ORIGIN,'X-TgTop':'1'})
    credentials={'username':'test','password':'account-pass-12345'}
    assert anonymous.post('/api/login',json=credentials).status_code==401
    assert anonymous.post('/api/login',json=dict(credentials,code=code)).status_code==401
    assert anonymous.post('/api/login',json=dict(credentials,code=recovery)).status_code==200
    assert anonymous.post('/api/login',json=dict(credentials,code=recovery)).status_code==401
    assert secret not in c.get('/api/state').text
    assert recovery not in (s.store.root/'tgtop.db').read_bytes().decode('latin1')

def test_resume_history_private_and_downloadable(env):
    s,c,root=env
    from test_personal import word_file
    path=root/'Resume.docx';word_file(path);original=path.read_bytes()
    assert c.post('/api/resume/upload',files={'file':('Resume.docx',original)}).status_code==200
    doc=c.get('/api/resume').json()
    assert c.post('/api/resume',json={'revision':doc['revision'],'paragraphs':[{'id':0,'text':'Revised resume'}]}).status_code==200
    versions=c.get('/api/resume/history').json()
    assert len(versions)==1
    assert c.get('/api/resume/history/'+versions[0]['id']).content==original
    assert 'Revised resume' not in c.get('/api/state').text

def test_backup_manifest_and_legacy_resume_recovery(env):
    s,c,root=env
    import io,json,zipfile
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    from test_personal import word_file
    path=root/'Resume.docx';word_file(path)
    c.post('/api/resume/link',json={'path':str(path),'confirm':True})
    doc=c.get('/api/resume').json()
    c.post('/api/resume',json={'revision':doc['revision'],'paragraphs':[{'id':0,'text':'Backup resume'}]})
    password='backup-integrity-test';raw=s.make_backup(password)
    key=s.vault.derive(password,raw[6:22]);data=AESGCM(key).decrypt(raw[22:34],raw[34:],b'TGTOP1')
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        manifest=json.loads(archive.read('manifest.json'))
        assert manifest['format']=='tgtop-backup-v2'
        assert 'blobs/resume-recovery.enc' in manifest['files']
    (s.store.root/'blobs'/'resume-recovery.enc').unlink()
    result=c.post('/api/restore',data={'password':password,'confirm':'RESTORE'},files={'file':('snapshot.tgtop',raw)})
    assert result.status_code==200
    assert (s.store.root/'blobs'/'resume-recovery.enc').exists()
