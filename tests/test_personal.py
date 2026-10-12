import hashlib
import hmac
import importlib
import io
import json
import time
import zipfile
import pytest
from fastapi.testclient import TestClient
from app import resume, messaging

@pytest.fixture
def workspace(tmp_path,monkeypatch):
    monkeypatch.setenv('TGTOP_DATA',str(tmp_path/'data'))
    monkeypatch.setenv('TGTOP_MODE','development')
    import app.server as server
    server=importlib.reload(server)
    client=TestClient(server.app,headers={'Origin':server.ORIGIN,'X-TgTop':'1'})
    client.post('/api/setup',json={'password':'test-private-workspace'})
    client.post('/api/login',json={'username':'tyler','password':'test-private-workspace'})
    yield server,client,tmp_path
    server.store.db.close()

def word_file(path):
    with zipfile.ZipFile(path,'w') as z:
        z.writestr('word/document.xml',b'<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:rPr><w:b/></w:rPr><w:t>Resume </w:t></w:r><w:r><w:t>example</w:t></w:r></w:p><w:sectPr/></w:body></w:document>')
        z.writestr('word/styles.xml',b'original styles unchanged')

def test_resume_saves_original_with_styles_recovery_conflicts(workspace):
    s,c,root=workspace
    path=root/'Resume.docx';word_file(path);original=path.read_bytes()
    assert c.post('/api/resume/link',json={'path':str(path),'confirm':True}).status_code==200
    doc=c.get('/api/resume').json()
    assert doc['paragraphs'][0]['text']=='Resume example'
    saved=c.post('/api/resume',json={'revision':doc['revision'],'paragraphs':[{'id':0,'text':'Resume updated example'}]})
    assert saved.status_code==200
    assert resume.inspect(path.read_bytes())['paragraphs'][0]['text']=='Resume updated example'
    with zipfile.ZipFile(path) as z:
        assert z.read('word/styles.xml')==b'original styles unchanged'
        assert b'<w:b/>' in z.read('word/document.xml')
    assert c.post('/api/resume',json={'revision':doc['revision'],'paragraphs':[]}).status_code==409
    recovery=(s.store.root/'blobs'/'resume-recovery.enc').read_bytes()
    assert original not in recovery
    assert c.post('/api/resume/restore',json={'revision':saved.json()['revision'],'confirm':True}).status_code==200
    assert path.read_bytes()==original
    assert 'Resume updated example' not in c.get('/api/state').text

def test_messaging_settings_redacted_and_phone_reset(workspace):
    s,c,root=workspace
    s.store.set_config('settings',dict(s.settings(),phone='+15551112222',phone_verified=True))
    payload={'provider':'photon','server_url':'https://test.photon.codes','api_key':'private-api-value','signing_secret':'private-signing-value','webhook_url':'https://app.example/api/sms/photon/incoming'}
    result=c.post('/api/messaging',json=payload)
    assert result.status_code==200
    public=c.get('/api/messaging').text+c.get('/api/state').text
    assert 'private-api-value' not in public and 'private-signing-value' not in public
    assert not s.settings()['phone_verified']
    assert b'private-api-value' not in (s.store.root/'tgtop.db').read_bytes()

def test_account_resume_encrypted_edit_download_recovery(workspace):
    s,c,root=workspace
    path=root/'Resume.docx';word_file(path);original=path.read_bytes()
    assert c.post('/api/resume/upload',files={'file':('Resume.docx',original)}).status_code==200
    cfg=s.store.config('resume')
    assert original not in (s.store.root/'blobs'/cfg['blob_id']).read_bytes()
    doc=c.get('/api/resume').json();assert doc['managed']
    saved=c.post('/api/resume',json={'revision':doc['revision'],'paragraphs':[{'id':0,'text':'Updated resume'}]})
    assert saved.status_code==200
    assert c.post('/api/resume',json={'revision':doc['revision'],'paragraphs':[]}).status_code==409
    assert resume.inspect(c.get('/api/resume/download').content)['paragraphs'][0]['text']=='Updated resume'
    assert path.read_bytes()==original
    assert 'Updated resume' not in c.get('/api/state').text
    assert c.post('/api/resume/restore',json={'revision':saved.json()['revision'],'confirm':True}).status_code==200
    assert c.get('/api/resume/download').content==original
    assert c.post('/api/resume/upload',files={'file':('Resume.docx',original)}).status_code==409
    backup=c.post('/api/backup',json={'password':'resume-backup-private'}).content
    assert c.post('/api/restore',files={'file':('Resume.tgtop',backup)},data={'password':'resume-backup-private','confirm':'RESTORE'}).status_code==200
    c.post('/api/login',json={'username':'tyler','password':'test-private-workspace'})
    assert c.get('/api/resume/download').content==original
    c.post('/api/signup',json={'username':'resume-other','password':'other-private-workspace'})
    assert c.post('/api/login',json={'username':'resume-other','password':'other-private-workspace'}).status_code==200
    assert c.get('/api/resume').status_code==404
    c.cookies.clear()
    assert c.get('/api/resume').status_code==401

def test_photon_webhook_authentication_dedupe_and_remote_task(workspace,monkeypatch):
    s,c,root=workspace
    cfg={'provider':'photon','server_url':'https://test.photon.codes','api_key':'secret','signing_secret':'signature-key'}
    s.store.set_config('messaging',cfg)
    s.store.set_config('settings',dict(s.settings(),phone='+15551112222',phone_verified=True,phone_verification_mode='live'))
    actual={'from':'+15551112222','text':'add task Chemistry assignment','sentAt':time.time()}
    monkeypatch.setattr(messaging,'photon_request',lambda *a,**k:actual)
    monkeypatch.setattr(messaging,'send',lambda *a,**k:{'sid':'reply'})
    raw=json.dumps({'event':'new-message','data':{'guid':'message-123','handle':{'address':'+15551112222'},'text':actual['text']}}).encode()
    stamp=str(int(time.time()))
    signature='v0='+hmac.new(b'signature-key',b'v0:'+stamp.encode()+b':'+raw,hashlib.sha256).hexdigest()
    headers={'X-Photon-Timestamp':stamp,'X-Photon-Signature':signature,'Content-Type':'application/json'}
    assert c.post('/api/sms/photon/incoming',content=raw).status_code==403
    assert c.post('/api/sms/photon/incoming',content=raw,headers=headers).json()['status']=='succeeded'
    assert c.post('/api/sms/photon/incoming',content=raw,headers=headers).json()['status']=='duplicate'
    assert len([t for t in s.store.list('task') if t['title']=='Chemistry assignment'])==1
    headers['X-Photon-Timestamp']=str(int(time.time())-600)
    assert c.post('/api/sms/photon/incoming',content=raw,headers=headers).status_code==403

def test_photon_outbound_contract(monkeypatch):
    sent=[]
    monkeypatch.setattr(messaging,'photon_request',lambda cfg,path,body:sent.append((path,body)) or {'id':'message-guid'})
    result=messaging.send({'provider':'photon'},'+15551112222','Reminder ready')
    assert result['mode']=='live' and result['provider']=='photon'
    assert sent==[('/send',{'to':'+15551112222','text':'Reminder ready','service':'SMS'})]

def test_spectrum_settings_private_and_commands_authorized(workspace,monkeypatch):
    from app.spectrum import incoming
    s,c,root=workspace
    cfg={'provider':'photon_spectrum','project_id':'11111111-1111-4111-8111-111111111111','project_secret':'spectrum-private-test-key'}
    assert c.post('/api/messaging',json=cfg).status_code==200
    assert cfg['project_secret'] not in c.get('/api/messaging').text+c.get('/api/state').text
    assert cfg['project_secret'].encode() not in (s.store.root/'tgtop.db').read_bytes()
    replies=[]
    monkeypatch.setattr(messaging,'send',lambda *args:replies.append(args))
    message={'guid':'spectrum-message','sender':'+15551112222','timestamp':time.time(),'text':'add task Spectrum task'}
    incoming(s,message)
    assert not s.store.list('task')
    s.store.set_config('settings',dict(s.settings(),phone=message['sender'],phone_verified=True,phone_verification_mode='live'))
    incoming(s,dict(message,sender='+15550000000'))
    incoming(s,dict(message,timestamp=time.time()-600))
    assert not s.store.list('task')
    incoming(s,message);incoming(s,message)
    assert len(s.store.list('task'))==1 and len(replies)==1

def test_spectrum_adapter_uses_private_rpc(monkeypatch):
    from app.spectrum import bridge
    calls=[]
    monkeypatch.setattr(bridge,'ensure',lambda cfg:calls.append('ensure'))
    monkeypatch.setattr(bridge,'request',lambda action,**fields:calls.append((action,fields)) or {'sid':'spectrum-guid'})
    result=messaging.send({'provider':'photon_spectrum'},'+15551112222','Private reminder')
    assert result=={'mode':'live','provider':'photon_spectrum','sid':'spectrum-guid'}
    assert calls==['ensure',('send',{'phone':'+15551112222','text':'Private reminder'})]

def test_photon_phone_verification_sends_code_without_exposing_it(workspace,monkeypatch):
    s,c,root=workspace
    s.store.set_config('messaging',{'provider':'photon','server_url':'https://test.photon.codes','api_key':'key','signing_secret':'signing'})
    messages=[]
    monkeypatch.setattr(messaging,'send',lambda cfg,phone,text:messages.append(text) or {'sid':'verification'})
    response=c.post('/api/phone/start',json={'phone':'+15551112222'})
    assert response.status_code==200 and response.json()['mode']=='live'
    assert 'development_code' not in response.json()
    code=messages[0].split(': ')[1].split('.')[0]
    assert code not in response.text and code not in c.get('/api/state').text
    assert c.post('/api/phone/verify',json={'code':'wrong'}).status_code==403
    assert c.post('/api/phone/verify',json={'code':code}).status_code==200
    assert s.settings()['phone_verification_mode']=='live'
    assert c.post('/api/phone/verify',json={'code':code}).status_code==403
