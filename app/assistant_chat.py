"""Encrypted account-owned chat history, independent of provider processes."""
import asyncio
from collections import defaultdict
from fastapi import Depends, HTTPException, Request
from .store import uid

locks = defaultdict(asyncio.Lock)

def current(s):
    chat=s.store.config('assistant_chat')
    if not chat:
        chat={'id':uid(),'turns':[]}
        s.store.set_config('assistant_chat',chat)
    return chat

def allowed(s,identifier,seen=None):
    seen=seen or set()
    if identifier in seen:return False
    r=s.store.get(identifier)
    if not r or r['deleted'] or r['kind'] not in ('project','task','note','file','conversation'):return False
    pid=r['id'] if r['kind']=='project' else r.get('project_id')
    p=s.store.get(pid) if pid else None
    if not p or p['deleted'] or not p.get('ai_allowed'):return False
    if r['kind']=='file' and not r.get('ai_allowed'):return False
    return all(allowed(s,i,seen|{identifier}) for i in r.get('source_ids',[]))

def history(s,chat,project_id):
    messages=[]
    for turn in chat['turns']:
        pid=turn.get('project_id')
        if pid and (not allowed(s,pid) or (project_id and pid!=project_id)):continue
        if any(not allowed(s,identifier) for identifier in turn.get('source_ids',[])):continue
        messages.extend([{'role':'user','content':turn['user']},{'role':'assistant','content':turn['assistant']}])
    return messages

def public(chat):
    messages=[]
    for turn in chat['turns']:
        messages.extend([{'text':turn['user']},{'text':turn['assistant'],'mode':turn['mode'],
                         'sources':turn.get('sources',[]),'actions':turn.get('actions',[])}])
    return {'id':chat['id'],'messages':messages}

def register(s):
    @s.app.get('/api/assistant/chat')
    async def read(session=Depends(s.auth)):
        async with locks[s.account_context.get()]:return public(current(s))

    @s.app.post('/api/assistant/chat/clear')
    async def clear(request:Request,session=Depends(s.auth)):
        async with locks[s.account_context.get()]:
            chat=current(s);data=await request.json()
            if data.get('chat_id') and data['chat_id']!=chat['id']:raise HTTPException(409,'This chat changed on another device. Refresh before clearing it.')
            if chat['turns']:s.store.put('chat_archive',{'title':'Cleared assistant chat','chat_id':chat['id'],'turns':chat['turns']})
            chat={'id':uid(),'turns':[]};s.store.set_config('assistant_chat',chat)
            return public(chat)

    @s.app.post('/api/assistant')
    async def send(request:Request,session=Depends(s.auth)):
        async with locks[s.account_context.get()]:
            data=await request.json();chat=current(s)
            if not isinstance(data.get('message'),str) or not data['message'].strip():raise HTTPException(400,'Enter a message.')
            if len(data['message'])>4000:raise HTTPException(413,'Keep each message within 4,000 characters. Nothing was sent.')
            if data.get('chat_id') and data['chat_id']!=chat['id']:raise HTTPException(409,'This chat was cleared on another device. Refresh to start a new conversation.')
            messages=history(s,chat,data.get('project_id'))
            if sum(len(m['content']) for m in messages)+len(str(data.get('message','')))>200000:
                raise HTTPException(413,'This chat has reached its context limit. Use Clear chat to start a new conversation; no earlier messages were silently removed.')
            result=await s.assistant_reply(request,session,messages)
            chat['turns'].append({'user':str(data.get('message',''))[:4000],'assistant':result['answer'],
                'mode':result['mode'],'project_id':data.get('project_id'),'sources':result['sources'],
                'source_ids':[r['id'] for r in result['sources']],'actions':result['actions']})
            s.store.set_config('assistant_chat',chat)
            return dict(result,chat_id=chat['id'])
