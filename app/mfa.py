"""Optional authenticator verification with durable replay protection."""
import secrets
import time
import pyotp
from fastapi import Depends,HTTPException,Request
from .security import hasher,token_hash

def consume(store,value):
    with store.transaction():
        cfg=store.config('mfa',{})
        if not cfg.get('enabled'):return
        code=str(value or '').strip().replace(' ','').replace('-','')
        digest=token_hash(code)
        recovery=cfg.get('recovery',[])
        if digest in recovery:
            store.set_config('mfa',dict(cfg,recovery=[c for c in recovery if c!=digest]));return
        if len(code)==6 and code.isdigit():
            totp=pyotp.TOTP(cfg['secret']);step=int(time.time()//30)
            for counter in (step,step-1,step+1):
                if counter>cfg.get('last_step',-1) and secrets.compare_digest(totp.at(counter*30),code):
                    store.set_config('mfa',dict(cfg,last_step=counter));return
        raise HTTPException(401,'Enter a new authenticator code or an unused recovery code')

def register(s):
    def password(data):
        try:hasher.verify(s.store.config('account')['password_hash'],data.get('password',''))
        except Exception:raise HTTPException(403,'Account password is incorrect')
    def revoke_others(session):
        for record in s.store.list('session'):
            if record['id']!=session['id']:
                s.vault.lock(record['id']);s.store.put('session',dict(record,revoked=True),record['id'],record['version'])
    @s.app.get('/api/security')
    def security(session=Depends(s.auth)):
        cfg=s.store.config('mfa',{})
        return {'mfa_enabled':bool(cfg.get('enabled')),'recovery_codes_remaining':len(cfg.get('recovery',[]))}
    @s.app.post('/api/security/totp/start')
    async def start(request:Request,session=Depends(s.auth)):
        s.limit('account-password:'+session['id'],5,300)
        data=await request.json();password(data)
        if s.store.config('mfa',{}).get('enabled'):raise HTTPException(409,'Authenticator already enabled')
        secret=pyotp.random_base32()
        s.store.set_config('mfa_pending',{'secret':secret,'expires':time.time()+600,'session_id':session['id']})
        return {'secret':secret,'uri':pyotp.TOTP(secret).provisioning_uri(name=s.store.config('account')['username'],issuer_name='TgTop')}
    @s.app.post('/api/security/totp/confirm')
    async def confirm(request:Request,session=Depends(s.auth)):
        s.limit('account-password:'+session['id'],5,300)
        data=await request.json()
        with s.store.transaction():
            pending=s.store.config('mfa_pending',{})
            if pending.get('expires',0)<time.time() or pending.get('session_id')!=session['id']:raise HTTPException(409,'Authenticator setup expired. Start again.')
            if not pyotp.TOTP(pending['secret']).verify(str(data.get('code','')),valid_window=1):raise HTTPException(400,'Authenticator code is incorrect')
            codes=[secrets.token_hex(10) for _ in range(10)]
            s.store.set_config('mfa',{'enabled':True,'secret':pending['secret'],'recovery':[token_hash(c) for c in codes],'last_step':-1})
            consume(s.store,data['code']);s.store.set_config('mfa_pending',{})
            revoke_others(session);s.audit('authenticator_enabled')
        return {'recovery_codes':codes}
    @s.app.post('/api/security/totp/disable')
    async def disable(request:Request,session=Depends(s.auth)):
        s.limit('account-password:'+session['id'],5,300)
        data=await request.json();password(data)
        if not data.get('confirm'):raise HTTPException(400,'Confirm disabling your authenticator')
        with s.store.transaction():
            consume(s.store,data.get('code'));s.store.set_config('mfa',{});revoke_others(session);s.audit('authenticator_disabled')
        return {'ok':True}
