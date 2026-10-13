"""Durable incoming actions and an independently recoverable reply outbox."""
import uuid
from datetime import datetime, timezone
from fastapi import HTTPException

def receive(s,provider,guid,phone,body):
    identifier=str(uuid.uuid5(uuid.NAMESPACE_URL,provider+':'+guid))
    with s.store.transaction():
        old=s.store.get(identifier)
        if old:return old
        return s.store.put('remote_command',{'title':'Phone command','provider':provider,'phone':phone,'body':body,'status':'received','reply_status':'pending'},identifier)

def finish(s,identifier,action):
    with s.store.transaction():
        record=s.store.get(identifier)
        if record.get('status')=='succeeded':return record['reply']
        if record.get('status')!='received':raise HTTPException(409,'This command requires review before running again')
        answer=action()
        s.store.put('remote_command',dict(record,status='succeeded',reply=answer,reply_status='pending'),identifier,record['version'])
        return answer

def replies(s):
    cfg=s.messaging.config(s.store)
    settings=s.settings()
    if not settings.get('phone_verified') or settings.get('phone_verification_mode')!='live':return
    for record in s.store.list('remote_command'):
        if record['phone']!=settings.get('phone'):continue
        if record['status']=='received' and not record['body'].lower().startswith('ai '):
            try:finish(s,record['id'],lambda:s.remote_command(record['body']))
            except Exception:
                current=s.store.get(record['id']);s.store.put('remote_command',dict(current,status='failed',error='Action failed; review before retry'),current['id'],current['version'])
            record=s.store.get(record['id'])
        if record['status']=='received' and record['body'].lower().startswith('ai '):
            if (datetime.now(timezone.utc)-datetime.fromisoformat(record['updated_at'])).total_seconds()>120:
                s.store.put('remote_command',dict(record,status='failed',error='AI processing interrupted; review before retry'),record['id'],record['version'])
            continue
        if record.get('reply_status')=='dispatching':
            if (datetime.now(timezone.utc)-datetime.fromisoformat(record['updated_at'])).total_seconds()>60:
                s.store.put('remote_command',dict(record,reply_status='needs_review',error='Reply outcome unknown; check provider history before retry'),record['id'],record['version'])
            continue
        if record['status']!='succeeded' or record.get('reply_status')!='pending':continue
        with s.store.transaction():
            current=s.store.get(record['id'])
            if current['reply_status']!='pending':continue
            sending=s.store.put('remote_command',dict(current,reply_status='dispatching'),current['id'],current['version'])
        try:
            result=s.messaging.send(cfg,record['phone'],record['reply'])
            s.store.put('remote_command',dict(sending,reply_status='submitted',reply_provider=result),sending['id'],sending['version'])
        except Exception:s.store.put('remote_command',dict(sending,reply_status='needs_review',error='Reply failed or outcome unknown; review before retry'),sending['id'],sending['version'])

def register(s):
    from fastapi import Depends,Request
    @s.app.post('/api/remote/{identifier}/retry-action')
    async def retry_action(identifier:str,request:Request,session=Depends(s.auth)):
        data=await request.json()
        if not data.get('confirm'):raise HTTPException(400,'Confirm retrying the failed action')
        with s.store.transaction():
            record=s.item(identifier,'remote_command')
            if record['status']!='failed':raise HTTPException(409,'Only a failed action can be retried')
            if record['phone']!=s.settings().get('phone') or s.settings().get('phone_verification_mode')!='live' or not s.settings().get('phone_verified'):raise HTTPException(403,'Verified phone connection required')
            record=s.store.put('remote_command',dict(record,status='received',error=None),identifier,record['version'])
        if record['body'].lower().startswith('ai '):
            from .phone_ai import command
            try:await command(s,record['body'],identifier)
            except Exception:
                current=s.store.get(identifier)
                if current['status']=='received':s.store.put('remote_command',dict(current,status='failed',error='AI request failed; review before retry'),identifier,current['version'])
        return s.safe_record(s.store.get(identifier))
    @s.app.post('/api/remote/{identifier}/retry-reply')
    async def retry(identifier:str,request:Request,session=Depends(s.auth)):
        data=await request.json()
        if not data.get('confirm'):raise HTTPException(400,'Confirm after checking provider history')
        with s.store.transaction():
            record=s.item(identifier,'remote_command')
            if record['status']!='succeeded' or record['reply_status']!='needs_review':raise HTTPException(409,'Reply does not need review')
            result=s.store.put('remote_command',dict(record,reply_status='pending',error=None),identifier,record['version'])
        return s.safe_record(result)
