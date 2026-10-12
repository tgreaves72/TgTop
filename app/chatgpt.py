"""App-owned ChatGPT OAuth registration. Tokens never leave the encrypted service."""
import asyncio
import base64
import hashlib
import secrets
import time
import uuid
from urllib.parse import urlencode
import httpx
import jwt
from fastapi import Depends, HTTPException, Request
from fastapi.responses import HTMLResponse

ISSUER='https://auth.openai.com'
AUTHORIZE=ISSUER+'/api/accounts/authorize'
TOKEN=ISSUER+'/api/accounts/oauth/token'
RESOURCE='https://api.openai.com/v1'
SCOPES='openid profile email offline_access resource.invoke chatgpt.tokens.use.direct'

class Connection:
    def __init__(self, service):
        self.s=service
        self.lock=asyncio.Lock()

    def config(self): return self.s.store.config('chatgpt',{'accounts':{},'active':None})

    def selected(self):
        cfg=self.config()
        return cfg.get('accounts',{}).get(cfg.get('active'),{})

    def public(self):
        cfg=self.config();a=self.selected()
        return {'connected':bool(a.get('access_token')),'plan_enabled':'chatgpt.tokens.use.direct' in a.get('scopes',[]),
            'model':a.get('model',''),'active':cfg.get('active'),
            'accounts':[{'id':k,'label':v.get('email') or 'ChatGPT account '+str(i+1)} for i,(k,v) in enumerate(cfg.get('accounts',{}).items())]}

    def begin(self, session, account=None):
        if self.s.ORIGIN!='http://127.0.0.1:8765':
            raise HTTPException(409,'ChatGPT sign-in requires this Windows PC’s local TgTop service.')
        cfg=self.config();saved=cfg.get('accounts',{}).get(account,{})
        if account and not saved:raise HTTPException(404,'Account not found')
        host=self.s.store.config('chatgpt_host')
        if not host:
            host='urn:uuid:'+str(uuid.uuid4());self.s.store.set_config('chatgpt_host',host)
        state=secrets.token_urlsafe(32);verifier=secrets.token_urlsafe(64);nonce=secrets.token_urlsafe(32)
        callback=self.s.ORIGIN+'/auth/callback'
        client_id=saved.get('client_id','dynamic_agent_client')
        pending={'state':state,'verifier':verifier,'nonce':nonce,'callback':callback,'client_id':client_id,
            'account':account,'session':session['id'],'expires':time.time()+600,'host':host}
        self.s.store.set_config('chatgpt_pending',pending)
        params={'client_id':client_id,'ext_agent_host_id':host,'response_type':'code','redirect_uri':callback,
            'scope':SCOPES,'resource':RESOURCE,'state':state,'nonce':nonce,'code_challenge_method':'S256',
            'code_challenge':base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip('=')}
        if client_id=='dynamic_agent_client':params['agent_name_hint']='TgTop'
        # Do not send retained ID tokens in URLs returned to browser JavaScript.
        return {'url':AUTHORIZE+'?'+urlencode(params)}

    async def verify_identity(self, token, client_id, nonce):
        async with httpx.AsyncClient(timeout=20,follow_redirects=False) as client:
            response=await client.get(ISSUER+'/.well-known/jwks.json');response.raise_for_status()
        header=jwt.get_unverified_header(token)
        if header.get('alg')!='RS256':raise ValueError('Invalid signing algorithm')
        key=next(k for k in response.json()['keys'] if k.get('kid')==header.get('kid'))
        claims=jwt.decode(token,jwt.PyJWK.from_dict(key).key,algorithms=['RS256'],audience=client_id,issuer=ISSUER,
            options={'require':['exp','iss','aud','sub','nonce']})
        if not secrets.compare_digest(str(claims['nonce']),nonce):raise ValueError('Invalid nonce')
        return claims

    async def exchange(self, fields):
        async with httpx.AsyncClient(timeout=25,follow_redirects=False) as client:
            response=await client.post(TOKEN,data=fields);response.raise_for_status()
        data=response.json()
        if not data.get('access_token') or data.get('token_type','').lower()!='bearer':raise ValueError('Invalid token response')
        return data

    async def finish(self, params):
        async with self.lock:
            p=self.s.store.config('chatgpt_pending',{})
            if not p or p.get('expires',0)<=time.time() or not secrets.compare_digest(str(params.get('state','')),p['state']):
                raise ValueError('Invalid authorization state')
            self.s.store.set_config('chatgpt_pending',{})
            session=self.s.store.get(p['session'])
            if not session or session.get('revoked') or session['expires']<=self.s.now():raise ValueError('Session ended')
            if params.get('error') or not params.get('code'):raise ValueError('Authorization declined')
            cid=params.get('client_id',p['client_id'])
            if p['client_id']=='dynamic_agent_client':
                if not cid or cid=='dynamic_agent_client' or len(cid)>200:raise ValueError('Registration incomplete')
            elif cid!=p['client_id']:raise ValueError('Account registration mismatch')
            data=await self.exchange({'grant_type':'authorization_code','client_id':cid,'code':params['code'],
                'code_verifier':p['verifier'],'redirect_uri':p['callback'],'resource':RESOURCE})
            claims=await self.verify_identity(data['id_token'],cid,p['nonce'])
            cfg=self.config();old=cfg.get('accounts',{}).get(p.get('account'),{})
            if old and claims['sub']!=old['subject']:raise ValueError('Account identity mismatch')
            key=hashlib.sha256((cid+'|'+claims['sub']).encode()).hexdigest()
            a={'client_id':cid,'subject':claims['sub'],'email':claims.get('email',''),'model':old.get('model',''),
                'access_token':data['access_token'],'refresh_token':data.get('refresh_token'),'id_token':data['id_token'],
                'scopes':data.get('scope','').split(),'expires':time.time()+float(data.get('expires_in',3600))}
            cfg.setdefault('accounts',{})[key]=a;cfg['active']=key;self.s.store.set_config('chatgpt',cfg)
            self.s.audit('chatgpt_connected')
            return 'chatgpt.tokens.use.direct' in a['scopes']

    async def access(self):
        async with self.lock:
            cfg=self.config();a=self.selected()
            if not a.get('access_token') or 'chatgpt.tokens.use.direct' not in a.get('scopes',[]):
                raise HTTPException(409,'Continue with ChatGPT and authorize plan usage first.')
            if a.get('expires',0)<=time.time()+90:
                try:
                    data=await self.exchange({'grant_type':'refresh_token','client_id':a['client_id'],
                        'refresh_token':a['refresh_token'],'resource':RESOURCE})
                    scopes=data.get('scope',' '.join(a['scopes'])).split()
                    if 'chatgpt.tokens.use.direct' not in scopes:raise ValueError('Permission lost')
                    a.update(access_token=data['access_token'],refresh_token=data.get('refresh_token',a['refresh_token']),
                        expires=time.time()+float(data.get('expires_in',3600)),scopes=scopes)
                    cfg['accounts'][cfg['active']]=a;self.s.store.set_config('chatgpt',cfg)
                except Exception:raise HTTPException(409,'ChatGPT session needs a fresh sign-in. No API billing fallback was used.')
            return a['access_token']

    async def models(self):
        token=await self.access()
        async with httpx.AsyncClient(timeout=25,follow_redirects=False) as client:
            r=await client.get(RESOURCE+'/models',headers={'Authorization':'Bearer '+token});r.raise_for_status()
        return [{'slug':m['slug'],'display_name':m.get('display_name',m['slug'])} for m in r.json().get('models',[]) if m.get('visibility')=='list']

    async def response(self, **fields):
        from openai import AsyncOpenAI
        client=AsyncOpenAI(api_key=await self.access(),base_url=RESOURCE,max_retries=0,timeout=45)
        a=self.selected()
        if not a.get('model'):raise HTTPException(409,'Choose an available ChatGPT model in Connections.')
        try:
            stream=await client.responses.create(model=a['model'],store=False,stream=True,**fields)
            output_items={}
            async with stream:
                async for event in stream:
                    if event.type=='response.output_item.done':
                        output_items[event.output_index]=event.item
                    if event.type=='response.completed':
                        response=event.response
                        if not response.output and output_items:
                            response.output=[output_items[i] for i in sorted(output_items)]
                        return response
                    if event.type in ('response.failed','response.incomplete','error'):
                        raise HTTPException(502,'ChatGPT did not complete the request. Check plan limits or reconnect; no API billing fallback was used.')
            raise HTTPException(502,'ChatGPT connection interrupted. Review activity before retrying.')
        finally:await client.close()

def register(s):
    from .accounts import Proxy
    connection=Proxy(lambda:s.accounts.connection(s));s.chatgpt=connection
    @s.app.get('/api/chatgpt')
    def status(session=Depends(s.auth)):return connection.public()
    @s.app.post('/api/chatgpt/start')
    async def start(request:Request,session=Depends(s.auth)):
        s.limit('chatgpt-signin:'+session['id'],5,300)
        data=await request.json();return connection.begin(session,data.get('account'))
    @s.app.get('/auth/callback')
    async def callback(request:Request):
        if request.client.host!='127.0.0.1':raise HTTPException(403,'Local callback required')
        try:
            enabled=await connection.finish(dict(request.query_params))
            message='ChatGPT connected. Return to TgTop and choose a model.' if enabled else 'Account linked, but plan usage was not authorized. Reconnect to grant access.'
        except Exception:message='Sign-in could not be completed. Return to TgTop and try again. Your existing data remains safe.'
        return HTMLResponse('<!doctype html><meta name="referrer" content="no-referrer"><title>TgTop</title><h1>TgTop</h1><p>'+message+'</p>',headers={'Cache-Control':'no-store','Content-Security-Policy':"default-src 'none'; style-src 'none'"})
    @s.app.get('/api/chatgpt/models')
    async def models(session=Depends(s.auth)):
        try:return await connection.models()
        except HTTPException:raise
        except Exception:raise HTTPException(502,'ChatGPT model list unavailable. Reconnect or check plan access.')
    @s.app.post('/api/chatgpt/model')
    async def model(request:Request,session=Depends(s.auth)):
        data=await request.json()
        try:models=await connection.models()
        except HTTPException:raise
        except Exception:raise HTTPException(502,'Could not validate model access.')
        if data.get('model') not in [m['slug'] for m in models]:raise HTTPException(400,'Choose a model available to this account.')
        cfg=connection.config();cfg['accounts'][cfg['active']]['model']=data['model'];s.store.set_config('chatgpt',cfg)
        return connection.public()
    @s.app.post('/api/chatgpt/disconnect')
    async def disconnect(session=Depends(s.auth)):
        async with connection.lock:
            cfg=connection.config();a=connection.selected();revoked=False
            try:
                async with httpx.AsyncClient(timeout=15,follow_redirects=False) as client:
                    r=await client.get(ISSUER+'/.well-known/openid-configuration');r.raise_for_status()
                    endpoint=r.json()['revocation_endpoint']
                    if not endpoint.startswith(ISSUER+'/'):raise ValueError('Invalid endpoint')
                    r=await client.post(endpoint,data={'token':a.get('refresh_token',''),'token_type_hint':'refresh_token','client_id':a.get('client_id','')});revoked=r.status_code==200
            except Exception:pass
            if cfg.get('active'):
                for key in ('access_token','refresh_token','id_token'):cfg['accounts'][cfg['active']].pop(key,None)
            self_pending={};s.store.set_config('chatgpt_pending',self_pending);s.store.set_config('chatgpt',cfg)
            s.audit('chatgpt_disconnected')
            return {'remote_revocation_confirmed':revoked,'message':'Disconnected.' if revoked else 'Disconnected locally. Remote revocation was not confirmed; disconnect TgTop in ChatGPT Settings.'}
