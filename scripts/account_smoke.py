"""Restart the frozen service twice using disposable data, never the user's account."""
from pathlib import Path
import os
import sys
import subprocess
import tempfile
import time
import zipfile
import httpx

root = Path(__file__).resolve().parent.parent
sys.path.insert(0,str(root))
url = 'http://127.0.0.1:8772'
exe = root / 'dist' / 'tgtop-server' / 'tgtop-server.exe'
qa_root=Path.home()/'.tgtop'/'qa'
qa_root.mkdir(parents=True,exist_ok=True)
with tempfile.TemporaryDirectory(prefix='tgtop-account-qa-',dir=qa_root) as data:
    assert Path(data).resolve().is_relative_to(qa_root.resolve())
    env = dict(os.environ, TGTOP_DATA=data, TGTOP_PORT='8772', TGTOP_ORIGIN=url, TGTOP_MODE='development')
    process = None
    def start():
        p = subprocess.Popen([str(exe)], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        for _ in range(100):
            if p.poll() is not None: raise RuntimeError('Frozen service failed to start')
            try:
                if httpx.get(url+'/api/status').status_code == 200: return p
            except httpx.HTTPError: pass
            time.sleep(.1)
        p.terminate();p.wait()
        raise RuntimeError('Frozen service did not become ready')
    try:
        process = start()
        with httpx.Client(base_url=url, headers={'Origin':url,'X-TgTop':'1'}) as c:
            assert c.get('/api/status').json()['setup']
            c.post('/api/setup',json={'username':'qa-user','name':'QA','password':'qa-persistence-2026'}).raise_for_status()
            c.post('/api/login',json={'username':'qa-user','password':'qa-persistence-2026'}).raise_for_status()
            task = c.post('/api/records/task',json={'title':'Retain after restart','status':'open'}).json()
            # Store Python and the frozen executable must read the same physical database/key.
            from app.store import Store
            source_store=Store(data)
            assert source_store.config('account')['name']=='QA'
            assert source_store.get(task['id'])['title']=='Retain after restart'
            source_store.put('note',{'title':'Source/native storage check','body':'Fictional QA'})
            source_store.db.close()
            assert any(r.get('title')=='Source/native storage check' for r in c.get('/api/state').json()['records'])
            resume_path=Path(data)/'QA Resume.docx'
            with zipfile.ZipFile(resume_path,'w') as z:
                z.writestr('word/document.xml','<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>Frozen resume test</w:t></w:r></w:p></w:body></w:document>')
            c.post('/api/resume/link',json={'path':str(resume_path),'confirm':True}).raise_for_status()
            resume=c.get('/api/resume').json()
            saved=c.post('/api/resume',json={'revision':resume['revision'],'paragraphs':[{'id':0,'text':'Frozen resume saved'}]})
            saved.raise_for_status()
            assert c.get('/api/resume').json()['paragraphs'][0]['text']=='Frozen resume saved'
            c.post('/api/resume/restore',json={'confirm':True,'revision':saved.json()['revision']}).raise_for_status()
            assert c.get('/api/resume').json()['paragraphs'][0]['text']=='Frozen resume test'
            assert 'calendarHtml' in c.get('/personal.js').text
            assert not c.get('/api/messaging').json()['configured']
            with httpx.Client(base_url=url,headers={'Origin':url,'X-TgTop':'1'}) as second:
                second.post('/api/signup',json={'username':'qa-second','name':'Second QA','password':'second-qa-pass-2026'}).raise_for_status()
                second.post('/api/login',json={'username':'qa-second','password':'second-qa-pass-2026'}).raise_for_status()
                assert task['id'] not in str(second.get('/api/state').json())
                assert second.patch('/api/records/'+task['id'],json={'version':task['version'],'title':'Denied'}).status_code==404
            original_key = (Path(data)/'server.key').read_bytes()
            process.terminate();process.wait();process = start()
            assert not c.get('/api/status').json()['setup']
            assert (Path(data)/'server.key').read_bytes() == original_key
            assert any(r['id']==task['id'] for r in c.get('/api/state').json()['records'])
            c.post('/api/logout').raise_for_status()
            process.terminate();process.wait();process = start()
            assert c.get('/api/state').status_code == 401
            c.post('/api/login',json={'username':'qa-user','password':'qa-persistence-2026'}).raise_for_status()
            assert any(r['id']==task['id'] for r in c.get('/api/state').json()['records'])
        with httpx.Client(base_url=url,headers={'Origin':url,'X-TgTop':'1'}) as second:
            second.post('/api/login',json={'username':'qa-second','password':'second-qa-pass-2026'}).raise_for_status()
            assert second.get('/api/state').json()['account']['username']=='qa-second'
            assert task['id'] not in str(second.get('/api/state').json())
        print('Packaged account: separate username accounts, cross-user access rejection, persistent session, two process restarts, saved task, original resume save/restore, messaging setup routes, and calendar assets passed.')
    finally:
        if process and process.poll() is None: process.terminate();process.wait()
