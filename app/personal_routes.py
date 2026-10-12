"""Authenticated local resume editing and private messaging setup."""
import hashlib
import hmac
import json
import secrets
import time
from pathlib import Path
from urllib.parse import quote
from fastapi import Depends, HTTPException, Request, UploadFile, File, Response
from .store import uid
from . import resume, messaging
from .security import token_hash

def register(s):
    app,store,auth=s.app,s.store,s.auth

    def resume_source():
        cfg=store.config('resume',{})
        if cfg.get('blob_id'):
            blob=store.root/'blobs'/cfg['blob_id']
            return cfg,store.decrypt(blob.read_bytes(),cfg['blob_id'].encode())
        path=resume_file()
        return {'path':str(path),'filename':path.name},path.read_bytes()

    def write_resume(cfg,data):
        if cfg.get('blob_id'):
            resume.replace_file(store.root/'blobs'/cfg['blob_id'],store.encrypt(data,cfg['blob_id'].encode()))
        else: resume.replace_file(cfg['path'],data)

    @app.post('/api/resume/upload')
    async def upload_resume(file:UploadFile=File(...),session=Depends(auth)):
        name=Path((file.filename or '').replace('\\','/')).name
        if not name.lower().endswith('.docx'):raise HTTPException(400,'Choose a Word .docx file')
        content=await file.read(min(s.UPLOAD_BYTES,10_000_000)+1)
        if len(content)>min(s.UPLOAD_BYTES,10_000_000):raise HTTPException(413,'Resume upload is too large')
        try:resume.inspect(content)
        except Exception:raise HTTPException(400,'Could not open this Word document')
        with store.lock:
            if store.config('resume'):raise HTTPException(409,'A resume is already linked. Edit or download it before replacing it.')
            identifier=uid()
            (store.root/'blobs'/identifier).write_bytes(store.encrypt(content,identifier.encode()))
            store.set_config('resume',{'blob_id':identifier,'filename':name})
            store.set_config('resume_recovery',{})
            s.audit('resume_uploaded')
        return {'ok':True}

    @app.get('/api/resume/download')
    def download_resume(session=Depends(auth)):
        cfg,content=resume_source()
        return Response(content,media_type='application/vnd.openxmlformats-officedocument.wordprocessingml.document',headers={'Content-Disposition':"attachment; filename*=UTF-8''"+quote(cfg['filename'])})

    def resume_file():
        name=store.config('resume',{}).get('path')
        if not name: raise HTTPException(404,'Link your resume file first')
        path=Path(name)
        if not path.is_file(): raise HTTPException(409,'Resume device or file is unavailable')
        return path

    @app.post('/api/resume/link')
    async def link(request:Request,session=Depends(auth)):
        data=await request.json()
        from .accounts import current
        if current.get()!='owner':raise HTTPException(403,'Local resume files require approval by the device owner')
        path=Path(data.get('path','')).resolve()
        if not data.get('confirm'): raise HTTPException(400,'Confirm access to this resume file')
        if path.suffix.lower()!='.docx' or not path.is_file(): raise HTTPException(400,'Choose an existing Word .docx file on this service computer')
        try: resume.inspect(path.read_bytes())
        except Exception: raise HTTPException(400,'Could not open this Word document')
        store.set_config('resume',{'path':str(path),'device_id':session['id']})
        s.audit('resume_linked')
        return {'ok':True}

    @app.get('/api/resume')
    def read(session=Depends(auth)):
        cfg,content=resume_source()
        try: result=resume.inspect(content)
        except Exception: raise HTTPException(409,'Could not read resume; open it in Word to check the file')
        return dict(result,filename=cfg['filename'],path=cfg.get('path','Encrypted account storage'),managed=bool(cfg.get('blob_id')),recovery_available=bool(store.config('resume_recovery')))

    @app.post('/api/resume')
    async def save(request:Request,session=Depends(auth)):
        data=await request.json()
        with store.lock:
            cfg,original=resume_source()
            if hashlib.sha256(original).hexdigest()!=data.get('revision'):
                raise HTTPException(409,'Resume changed outside TgTop. Reload it before saving your edits.')
            try: updated=resume.edit(original,data.get('paragraphs'))
            except ValueError as e: raise HTTPException(400,str(e))
            # Recovery copy is encrypted and excluded from exports and AI context.
            recovery_id=uid() if cfg.get('blob_id') else 'resume-recovery.enc'
            recovery=store.root/'blobs'/recovery_id
            recovery.write_bytes(store.encrypt(original,b'tgtop-resume-recovery'))
            try: write_resume(cfg,updated)
            except OSError: raise HTTPException(409,'Close the resume in Word and try saving again')
            store.set_config('resume_recovery',{'path':cfg.get('path'),'blob_id':cfg.get('blob_id'),'recovery_id':recovery_id,'revision':hashlib.sha256(updated).hexdigest()})
            s.audit('resume_saved')
            return {'revision':hashlib.sha256(updated).hexdigest(),'ok':True}

    @app.post('/api/resume/restore')
    async def restore(request:Request,session=Depends(auth)):
        data=await request.json()
        if not data.get('confirm'): raise HTTPException(400,'Confirm restoration')
        with store.lock:
            source,content=resume_source(); cfg=store.config('resume_recovery',{})
            if not cfg or source.get('path')!=cfg.get('path') or source.get('blob_id')!=cfg.get('blob_id'): raise HTTPException(404,'No recovery copy for this file')
            if hashlib.sha256(content).hexdigest()!=data.get('revision'):
                raise HTTPException(409,'Resume changed; reload it before restoring')
            original=store.decrypt((store.root/'blobs'/cfg.get('recovery_id','resume-recovery.enc')).read_bytes(),b'tgtop-resume-recovery')
            try: write_resume(source,original)
            except OSError: raise HTTPException(409,'Close Word and try again')
            store.set_config('resume_recovery',{})
            s.audit('resume_restored')
            return {'ok':True}

    @app.get('/api/messaging')
    def status(session=Depends(auth)):
        cfg=messaging.config(store)
        return dict(messaging.public(cfg),phone_verified=s.settings().get('phone_verification_mode')=='live' and s.settings().get('phone_verified',False))

    @app.post('/api/messaging')
    async def configure(request:Request,session=Depends(auth)):
        s.limit('messaging-setup:'+session['id'],5,300)
        data=await request.json()
        prior=messaging.config(store)
        provider=data.get('provider')
        cfg={'provider':provider}
        for field in ('server_url','api_key','signing_secret','webhook_url','account_sid','auth_token','from','verify_sid','project_id','project_secret'):
            value=data.get(field,'')
            if not isinstance(value,str) or len(value)>2000: raise HTTPException(400,'Invalid provider setting')
            cfg[field]=value.strip() or (prior.get(field,'') if prior.get('provider')==provider else '')
        try: messaging.validate(cfg)
        except ValueError as e: raise HTTPException(400,str(e))
        # Local protected service settings let the scheduler operate while the user vault is locked.
        store.set_config('messaging',cfg)
        settings=s.settings(); settings.update(phone_verified=False,phone_verification_mode=None)
        store.set_config('settings',settings); store.set_config('phone_challenge',{})
        s.audit('messaging_configured')
        return messaging.public(cfg)

    @app.post('/api/messaging/check')
    def check(session=Depends(auth)):
        s.limit('messaging-check:'+session['id'],3,60)
        cfg=messaging.config(store)
        if not messaging.configured(cfg): raise HTTPException(400,'Configure the provider first')
        try: messaging.check(cfg)
        except Exception: raise HTTPException(502,'Provider check failed. Review the account settings in the provider dashboard.')
        cfg['checked']=True; store.set_config('messaging',cfg)
        s.audit('messaging_connection_checked')
        return {'ok':True,'message':'Provider accepted credentials. Verify your phone next.' + (' Incoming commands use the authenticated Photon stream while this service runs.' if cfg.get('provider')=='photon_spectrum' else ' Incoming commands require the HTTPS webhook.')}

    @app.post('/api/sms/photon/incoming')
    async def photon_incoming(request:Request):
        cfg=messaging.config(store)
        if cfg.get('provider')!='photon' or not messaging.configured(cfg): raise HTTPException(503,'Photon is not configured')
        raw=await request.body()
        if len(raw)>100000: raise HTTPException(413,'Message too large')
        stamp=request.headers.get('x-photon-timestamp','')
        try:
            if abs(time.time()-int(stamp))>300: raise ValueError()
        except ValueError: raise HTTPException(403,'Expired provider request')
        expected='v0='+hmac.new(cfg['signing_secret'].encode(),b'v0:'+stamp.encode()+b':'+raw,hashlib.sha256).hexdigest()
        if not secrets.compare_digest(expected,request.headers.get('x-photon-signature','')):
            raise HTTPException(403,'Invalid provider signature')
        try: payload=json.loads(raw)
        except ValueError: raise HTTPException(400,'Invalid message')
        if payload.get('event')!='new-message': return {'status':'ignored'}
        msg=payload.get('data',{})
        if msg.get('isFromMe'): return {'status':'ignored'}
        sender=(msg.get('handle') or {}).get('address')
        settings=s.settings()
        if not settings.get('phone_verified') or settings.get('phone_verification_mode')!='live' or sender!=settings.get('phone'):
            raise HTTPException(403,'Unauthorized sender')
        guid=msg.get('guid',''); body=msg.get('text','')
        if not isinstance(guid,str) or not 1<=len(guid)<=128 or not isinstance(body,str) or len(body)>2000:
            raise HTTPException(400,'Invalid message')
        # Confirm the message against the provider, including freshness and sender.
        try:
            actual=messaging.photon_request(cfg,'/messages/'+quote(guid,safe=''))
            created=actual.get('sentAt',0)
            if created>10**11: created/=1000
            if actual.get('from')!=sender or actual.get('text')!=body or abs(time.time()-created)>300: raise ValueError()
        except Exception: raise HTTPException(403,'Message freshness check failed')
        s.limit('photon:'+sender,10,60)
        if not store.claim('photon:'+guid): return {'status':'duplicate'}
        try:
            answer=s.remote_command(body)
            messaging.send(cfg,sender,answer)
            s.audit('photon_command')
            return {'status':'succeeded'}
        except Exception:
            s.audit('photon_command',status='failed')
            return {'status':'failed','message':'Review activity in the authenticated application; this command will not execute twice.'}
