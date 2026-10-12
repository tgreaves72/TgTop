"""Test a packaged service at port 8768 using its isolated runtime/frozen-smoke data."""
import httpx
from datetime import datetime,timedelta,timezone

url='http://127.0.0.1:8768'
with httpx.Client(base_url=url,headers={'Origin':url,'X-TgTop':'1'},timeout=30) as c:
    if c.get('/api/status').json()['setup']:
        c.post('/api/setup',json={'username':'packaged-qa','name':'Packaged QA','password':'packaged-qa-pass-2026'}).raise_for_status()
    c.post('/api/login',json={'username':'packaged-qa','password':'packaged-qa-pass-2026','device':'Packaged QA'}).raise_for_status()
    p=c.post('/api/records/project',json={'title':'Packaged application QA','space':'personal','ai_allowed':True}).json()
    f=c.post('/api/files',data={'project_id':p['id']},files={'file':('qa.txt',b'Packaged file verified','text/plain')}).json()
    assert c.get('/api/files/'+f['id']+'/content').content==b'Packaged file verified'
    t=c.post('/api/records/task',json={'title':'Verify packaged task','project_id':p['id'],'file_ids':[f['id']],'status':'open','priority':'normal'}).json()
    assert c.patch('/api/records/'+t['id'],json={'version':t['version'],'status':'done'}).json()['status']=='done'
    if not c.get('/api/vault/status').json()['configured']:
        c.post('/api/vault/setup',json={'password':'packaged-vault-2026'}).raise_for_status()
    c.post('/api/vault/unlock',json={'password':'packaged-vault-2026'}).raise_for_status()
    v=c.post('/api/vault/save',json={'title':'QA credential','project_id':p['id'],'secret':'test-only-value'}).json()
    assert c.post('/api/vault/reveal',json={'id':v['id']}).json()['secret']=='test-only-value'
    c.post('/api/vault/lock',json={}).raise_for_status()
    assert c.post('/api/vault/reveal',json={'id':v['id']}).status_code==423
    assert c.post('/api/backup',json={'password':'packaged-backup-2026'}).content.startswith(b'TGTOP1')
    assert c.get('/icon-192.png').status_code==200
    assert c.get('/manifest.json').json()['display']=='standalone'
    print('Frozen service: task, file, vault, encrypted backup, and PWA asset checks passed')
