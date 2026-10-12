"""Private provider adapters. No credentials or message contents in errors/logs."""
import base64
import os
from urllib.parse import urlsplit, quote
import httpx

PHOTON_PROXY = 'https://imessage-swagger.photon.codes'

def config(store):
    saved = store.config('messaging', {})
    if saved: return saved
    from .accounts import current
    if current.get()!='owner':return {'provider':'twilio'}
    return {'provider':'twilio', 'account_sid':os.getenv('TWILIO_ACCOUNT_SID',''),
            'auth_token':os.getenv('TWILIO_AUTH_TOKEN',''), 'from':os.getenv('TWILIO_FROM',''),
            'verify_sid':os.getenv('TWILIO_VERIFY_SERVICE_SID',''), 'webhook_url':os.getenv('TWILIO_WEBHOOK_URL','')}

def configured(cfg):
    if cfg.get('provider')=='photon_spectrum':return all(cfg.get(key) for key in ('project_id','project_secret'))
    keys = ('server_url','api_key','signing_secret') if cfg.get('provider')=='photon' else ('account_sid','auth_token','from','verify_sid')
    return all(cfg.get(key) for key in keys)

def public(cfg):
    return {'provider':cfg.get('provider','twilio'),'configured':configured(cfg),
            'checked':bool(cfg.get('checked')), 'webhook_url':cfg.get('webhook_url',''),
            'server_url':cfg.get('server_url',''),'from':cfg.get('from',''),
            'project_id':cfg.get('project_id',''),
            'secret_fields_saved':[k for k in ('api_key','signing_secret','auth_token','project_secret') if cfg.get(k)]}

def photon_request(cfg, path, body=None):
    token=base64.b64encode((cfg['server_url'].rstrip('/')+'/|'+cfg['api_key']).encode()).decode()
    with httpx.Client(timeout=20,follow_redirects=False) as client:
        response=client.request('POST' if body is not None else 'GET',PHOTON_PROXY+path,
                                headers={'Authorization':'Bearer '+token},json=body)
        response.raise_for_status()
        data=response.json()
        if not data.get('ok'): raise RuntimeError('Provider rejected request')
        return data.get('data',{})

def send(cfg,phone,text):
    if cfg.get('provider')=='photon_spectrum':
        from .spectrum import bridge
        bridge.ensure(cfg)
        result=bridge.request('send',phone=phone,text=text)
        return {'mode':'live','provider':'photon_spectrum','sid':result['sid']}
    if cfg.get('provider')=='photon':
        data=photon_request(cfg,'/send',{'to':phone,'text':text,'service':'SMS'})
        if not data.get('id'): raise RuntimeError('Provider returned no message ID')
        return {'mode':'live','provider':'photon','sid':data['id']}
    from twilio.rest import Client
    msg=Client(cfg['account_sid'],cfg['auth_token']).messages.create(to=phone,from_=cfg['from'],body=text)
    return {'mode':'live','provider':'twilio','sid':msg.sid}

def check(cfg):
    if cfg.get('provider')=='photon_spectrum':
        from .spectrum import bridge
        bridge.ensure(cfg)
        return
    if cfg.get('provider')=='photon':
        photon_request(cfg,'/server')
    else:
        from twilio.rest import Client
        Client(cfg['account_sid'],cfg['auth_token']).api.accounts(cfg['account_sid']).fetch()

def validate(cfg):
    if cfg.get('provider') not in ('photon','photon_spectrum','twilio'): raise ValueError('Choose Photon or Twilio')
    if cfg.get('provider')=='photon_spectrum':
        import uuid
        try:uuid.UUID(cfg.get('project_id',''))
        except ValueError:raise ValueError('Enter the Photon project ID')
    if cfg.get('webhook_url'):
        url=urlsplit(cfg['webhook_url'])
        if url.scheme!='https' or not url.hostname or url.username or url.password or url.fragment:
            raise ValueError('Webhook address must use HTTPS')
    if cfg.get('provider')=='photon':
        url=urlsplit(cfg.get('server_url',''))
        if url.scheme!='https' or not url.hostname or url.username or url.password or url.query or url.fragment:
            raise ValueError('Use the HTTPS server address supplied by Photon')
        # The official hosted proxy receives this address and key; never forward to arbitrary hosts locally.
        if not url.hostname.endswith('.photon.codes'):
            raise ValueError('This connection supports hosted photon.codes server addresses')
    if not configured(cfg): raise ValueError('Complete the provider settings')
