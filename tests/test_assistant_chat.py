import importlib
import json
from test_workflows import env,project

def mock_ai(s,monkeypatch):
    seen=[]
    s.chatgpt.codex.update(enabled=True,connected=True,model='test')
    async def run(query,*args,**kwargs):
        seen.append(query)
        return {'answer':'Remembered answer','sources':[],'actions':[]}
    monkeypatch.setattr(s.chatgpt.codex,'run',run)
    return seen

def test_followup_receives_history_and_clear_starts_fresh(env,monkeypatch):
    s,c,root=env;seen=mock_ai(s,monkeypatch)
    chat=c.get('/api/assistant/chat').json()
    assert c.post('/api/assistant',json={'message':'My meeting is Philosophy Club.','chat_id':chat['id']}).status_code==200
    assert c.post('/api/assistant',json={'message':'Make it Monday at 7.','chat_id':chat['id']}).status_code==200
    assert 'Philosophy Club' in seen[1] and 'Remembered answer' in seen[1] and 'Monday at 7' in seen[1]
    saved=c.get('/api/assistant/chat').json()
    assert len(saved['messages'])==4 and saved['id']==chat['id']
    encrypted=s.store.db.execute('SELECT data FROM config WHERE name=?',('assistant_chat',)).fetchone()[0]
    assert b'Philosophy Club' not in bytes(encrypted)
    cleared=c.post('/api/assistant/chat/clear',json={'chat_id':chat['id']}).json()
    assert cleared['id']!=chat['id'] and cleared['messages']==[]
    assert c.post('/api/assistant',json={'message':'stale request','chat_id':chat['id']}).status_code==409
    c.post('/api/assistant',json={'message':'Fresh conversation','chat_id':cleared['id']})
    assert seen[-1]=='Fresh conversation' and not s.store.list('task')

def test_history_survives_service_reload_and_stays_account_scoped(env,monkeypatch):
    s,c,root=env;mock_ai(s,monkeypatch)
    c.post('/api/assistant',json={'message':'Persistent meeting name'})
    chat=c.get('/api/assistant/chat').json()
    s=importlib.reload(s)
    from fastapi.testclient import TestClient
    client=TestClient(s.app);client.headers.update({'Origin':s.ORIGIN,'X-TgTop':'1'});client.cookies.update(c.cookies)
    assert client.get('/api/assistant/chat').json()==chat
    assert client.post('/api/signup',json={'username':'other','name':'Other','password':'another-account-pass'}).status_code==200
    client.post('/api/login',json={'username':'other','password':'another-account-pass'})
    other=client.get('/api/assistant/chat').json()
    assert other['messages']==[] and other['id']!=chat['id']

def test_revoked_sources_do_not_reenter_model_history(env,monkeypatch):
    s,c,root=env;seen=mock_ai(s,monkeypatch);p=project(c,True)
    chat=c.get('/api/assistant/chat').json()
    s.store.set_config('assistant_chat',{'id':chat['id'],'turns':[{'user':'Prior question','assistant':'private-source-answer','project_id':p['id'],'source_ids':[p['id']],'mode':'test'}]})
    c.patch('/api/records/'+p['id'],json={'version':p['version'],'ai_allowed':False})
    assert c.post('/api/assistant',json={'message':'Next question'}).status_code==200
    assert 'private-source-answer' not in seen[-1]

def test_history_is_not_silently_truncated(env,monkeypatch):
    s,c,root=env;seen=mock_ai(s,monkeypatch);chat=c.get('/api/assistant/chat').json()
    assert c.post('/api/assistant',json={'message':'x'*4001}).status_code==413
    s.store.set_config('assistant_chat',{'id':chat['id'],'turns':[{'user':'x'*200000,'assistant':'answer','mode':'test'}]})
    assert c.post('/api/assistant',json={'message':'next'}).status_code==413 and not seen
