"""Account-scoped deadline connectors. Credentials stay in encrypted config."""
import csv
import hashlib
import io
import ipaddress
import json
import secrets
import socket
import threading
import time
import uuid
from datetime import datetime, date, timedelta, timezone
from urllib.parse import urlparse
from zoneinfo import ZoneInfo
import httpx
from fastapi import Depends, HTTPException, Request, UploadFile, File
from fastapi.responses import HTMLResponse
from .store import now

PROVIDERS=('canvas','outlook','gradescope')
LOCK=threading.RLock()
MAX_ITEMS=1000

def public_url(value, hosts):
    if len(value)>4096:raise ValueError('Provider address is too long')
    p=urlparse(value)
    if p.scheme!='https' or p.username or p.password or p.port not in (None,443) or p.fragment:
        raise ValueError('Use an HTTPS provider address without credentials or fragments')
    host=(p.hostname or '').lower()
    if not any(host==h or host.endswith('.'+h) for h in hosts):
        raise ValueError('Address must belong to the selected provider')
    addresses=socket.getaddrinfo(host,443,type=socket.SOCK_STREAM)
    if not addresses or any(not ipaddress.ip_address(a[4][0]).is_global for a in addresses):
        raise ValueError('Provider address must resolve to a public server')
    return value

def fetch(url, hosts, headers=None):
    public_url(url,hosts)
    # Redirects are rejected so provider tokens never follow an arbitrary location.
    with httpx.Client(timeout=12,follow_redirects=False,trust_env=False) as client:
        with client.stream('GET',url,headers=headers) as response:
            response.raise_for_status()
            body=bytearray()
            for part in response.iter_bytes():
                body.extend(part)
                if len(body)>2*1024*1024:raise ValueError('Provider response exceeds 2 MB')
            return bytes(body),response.headers

def due(value,tz):
    if isinstance(value,date) and not isinstance(value,datetime):
        value=datetime.combine(value,datetime.min.time()).replace(hour=23,minute=59,tzinfo=ZoneInfo(tz))
    elif isinstance(value,str):
        value=datetime.fromisoformat(value.strip().replace('Z','+00:00'))
    if not isinstance(value,datetime):raise ValueError('A valid due date is required')
    if value.tzinfo is None:
        local=value.replace(tzinfo=ZoneInfo(tz))
        if local.astimezone(timezone.utc).astimezone(ZoneInfo(tz)).replace(tzinfo=None)!=value:
            raise ValueError('Due time falls in a daylight-saving gap')
        value=local
    return value.astimezone(timezone.utc).isoformat()

def parse_ics(content,tz):
    from icalendar import Calendar
    result=[]
    for event in Calendar.from_ical(content).walk('VEVENT'):
        if len(result)>=MAX_ITEMS:raise ValueError('Schedule exceeds 1,000 entries')
        if event.get('RRULE'):raise ValueError('Recurring feed events need an expanded schedule; use the provider API')
        identifier=str(event.get('UID',''))
        if not identifier or not event.get('DTSTART'):continue
        result.append({'source_id':identifier,'title':str(event.get('SUMMARY','Untitled deadline'))[:200],
                       'due_at':due(event.decoded('DTSTART'),tz),'url':str(event.get('URL',''))})
    return result

def parse_csv(content,tz):
    rows=csv.DictReader(io.StringIO(content.decode('utf-8-sig')))
    if not {'title','due_at'}.issubset(rows.fieldnames or []):
        raise ValueError('CSV needs title and due_at columns; optional source_id and url columns')
    result=[]
    for row in rows:
        if len(result)>=MAX_ITEMS:raise ValueError('Schedule exceeds 1,000 entries')
        title=(row.get('title') or '').strip()
        if not title:raise ValueError('Every deadline needs a title')
        result.append({'source_id':row.get('source_id') or title,'title':title[:200],
                       'due_at':due(row.get('due_at',''),tz),'url':row.get('url','')})
    return result

def microsoft(cfg):
    import msal
    cache=msal.SerializableTokenCache()
    if cfg.get('token_cache'):cache.deserialize(cfg['token_cache'])
    return msal.ConfidentialClientApplication(cfg['client_id'],client_credential=cfg['client_secret'],
        authority='https://login.microsoftonline.com/common',token_cache=cache),cache

def load_items(s,provider,cfg):
    tz=s.settings()['timezone']
    if provider=='gradescope' and cfg['mode']=='canvas':
        canvas=s.store.config('school_canvas',{})
        if not canvas.get('enabled') or canvas.get('mode')!='api':raise ValueError('Connect Canvas using an access token first')
        base=canvas['base'];host=urlparse(base).hostname;headers={'Authorization':'Bearer '+canvas['token']}
        raw,_=fetch(base+'/api/v1/courses?enrollment_state=active&per_page=100',(host,),headers)
        courses=json.loads(raw)
        if len(courses)>20:raise ValueError('Gradescope linked lookup supports up to 20 active courses')
        items=[]
        for course in courses:
            raw,response_headers=fetch(base+'/api/v1/courses/'+str(course['id'])+'/assignments?per_page=100',(host,),headers)
            if 'next' in httpx.Response(200,headers=response_headers).links:raise ValueError('Course exceeds 100 assignments')
            for assignment in json.loads(raw):
                tool=assignment.get('external_tool_tag_attributes') or {}
                host_name=urlparse(tool.get('url','')).hostname or ''
                if (host_name=='gradescope.com' or host_name.endswith('.gradescope.com')) and assignment.get('due_at'):
                    items.append({'source_id':str(course['id'])+':assignment:'+str(assignment['id']),
                        'title':assignment['name'][:200],'due_at':due(assignment['due_at'],tz),'url':assignment.get('html_url','')})
        return items
    if cfg['mode']=='feed':return parse_ics(fetch(cfg['feed'],('instructure.com',) if provider=='canvas' else ('outlook.live.com','outlook.office365.com','outlook.office.com'))[0],tz)
    if provider=='canvas':
        base=cfg['base'];items=[];url=base+'/api/v1/planner/items?per_page=100&start_date='+datetime.now(timezone.utc).date().isoformat()
        for _ in range(10):
            raw,headers=fetch(url,((urlparse(base).hostname),),{'Authorization':'Bearer '+cfg['token']})
            for row in json.loads(raw):
                obj=row.get('plannable',{});at=obj.get('due_at') or row.get('plannable_date')
                if at and row.get('plannable_type') in ('assignment','quiz','discussion_topic','sub_assignment'):
                    items.append({'source_id':str(row.get('course_id'))+':'+str(row.get('plannable_type'))+':'+str(obj['id']),
                        'title':str(obj.get('title','Assignment'))[:200],'due_at':due(at,tz),
                        'url':base+row['html_url'] if row.get('html_url','').startswith('/') else row.get('html_url',''),
                        'course_id':str(row.get('course_id',''))})
            links=httpx.Response(200,headers=headers).links
            if 'next' not in links:return items
            url=links['next']['url']
        raise ValueError('Canvas has more than 1,000 results; narrow your courses')
    if provider=='outlook':
        app,cache=microsoft(cfg);accounts=app.get_accounts()
        token=app.acquire_token_silent(['Calendars.Read'],account=accounts[0] if accounts else None)
        if not token or 'access_token' not in token:raise ValueError('Reconnect Outlook to authorize calendar access')
        cfg['token_cache']=cache.serialize();s.store.set_config('school_outlook',cfg)
        start=datetime.now(timezone.utc);end=start+timedelta(days=180)
        url='https://graph.microsoft.com/v1.0/me/calendarView?startDateTime='+start.isoformat().replace('+00:00','Z')+'&endDateTime='+end.isoformat().replace('+00:00','Z')+'&$top=100'
        items=[]
        for _ in range(10):
            raw,_=fetch(url,('graph.microsoft.com',),{'Authorization':'Bearer '+token['access_token'],'Prefer':'outlook.timezone="UTC", IdType="ImmutableId"'})
            data=json.loads(raw)
            for event in data.get('value',[]):
                if event.get('isCancelled'):continue
                at=event['start']['dateTime'].split('.')[0]+'+00:00'
                items.append({'source_id':event['id'],'title':event.get('subject','Calendar event')[:200],
                    'due_at':due(at,tz),'url':event.get('webLink','')})
            url=data.get('@odata.nextLink')
            if not url:return items
        raise ValueError('Outlook returned more than 1,000 events')
    raise ValueError('Gradescope uses a reviewed CSV/ICS upload or Canvas-linked deadlines')

def stage(s,provider,items):
    if len(items)>MAX_ITEMS:raise ValueError('Schedule exceeds 1,000 entries')
    seen=set();counts={'new':0,'updated':0,'conflicts':0}
    with s.store.transaction():
        cfg=s.store.config('school_'+provider,{})
        s.item(cfg.get('project_id'),'project')
        for value in items:
            external=str(value['source_id'])[:500]
            if external in seen:raise ValueError('Schedule contains duplicate source IDs')
            seen.add(external)
            identifier=str(uuid.uuid5(uuid.NAMESPACE_URL,'tgtop-school:'+provider+':'+cfg['source_key']+':'+external))
            old=s.store.get(identifier)
            fields={'title':value['title'],'due_at':value['due_at'],'project_id':cfg['project_id']}
            link=value.get('url','')
            if link and (urlparse(link).scheme!='https' or urlparse(link).username):link=''
            candidate=dict(old or {},title=fields['title'],project_id=cfg['project_id'],provider=provider,
                source_id=external,source_key=cfg['source_key'],fields=fields,source_url=link,last_seen=now())
            canonical=cfg['source_key']+':'+external
            candidate['canonical']=canonical
            if not candidate.get('task_id'):
                linked=next((t for t in s.store.list('task') if t.get('school_source')==canonical),None)
                if linked:candidate.update(task_id=linked['id'],baseline={k:linked.get(k) for k in fields})
            task=s.store.get(candidate.get('task_id')) if candidate.get('task_id') else None
            if task and not task['deleted']:
                baseline=(old or {}).get('baseline',{})
                candidate['status']='imported'
                if fields!=baseline:
                    if any(task.get(k)!=baseline.get(k) for k in fields):
                        candidate['status']='conflict';counts['conflicts']+=1
                    else:
                        s.save_task(dict(task,**fields),task['id'],task['version'])
                        candidate.update(status='imported',baseline=fields);counts['updated']+=1
            elif task and task['deleted']:candidate['status']='removed_locally'
            else:candidate['status']='review';counts['new']+=int(old is None)
            if old and old.get('status')=='ignored' and old.get('fields')==fields:candidate['status']='ignored'
            if not old or any(candidate.get(k)!=old.get(k) for k in ('title','project_id','provider','source_id','source_key','fields','source_url','status','task_id','baseline')):
                s.store.put('school_deadline',candidate,identifier,old['version'] if old else None)
        # Absence never deletes a task, because feeds can use limited time windows.
        for candidate in s.store.list('school_deadline'):
            if candidate.get('provider')==provider and candidate.get('source_key')==cfg['source_key'] and candidate['source_id'] not in seen and candidate.get('status')!='missing':
                s.store.put('school_deadline',dict(candidate,status='missing'),candidate['id'],candidate['version'])
        cfg.update(last_sync=now(),next_sync=time.time()+900,status='ready',error=None,last_counts=counts)
        s.store.set_config('school_'+provider,cfg)
    return counts

def sync(s,provider):
    with LOCK:
        cfg=s.store.config('school_'+provider,{})
        if not cfg.get('enabled'):raise ValueError('Connect this service first')
        try:return stage(s,provider,load_items(s,provider,cfg))
        except Exception:
            cfg=s.store.config('school_'+provider,{})
            cfg.update(status='failed',error='Sync failed. Check authorization and the provider address. Existing tasks remain saved.',next_sync=time.time()+900)
            s.store.set_config('school_'+provider,cfg)
            raise ValueError(cfg['error']) from None

def tick(s):
    for provider in PROVIDERS:
        cfg=s.store.config('school_'+provider,{})
        if cfg.get('enabled') and cfg.get('mode')!='upload' and cfg.get('next_sync',0)<=time.time():
            try:sync(s,provider)
            except ValueError:pass

def register(s):
    app=s.app
    @app.get('/api/school')
    def status(session=Depends(s.auth)):
        return {p:{k:v for k,v in s.store.config('school_'+p,{}).items() if k in ('mode','enabled','project_id','status','last_sync','error','last_counts')} for p in PROVIDERS}

    @app.post('/api/school/{provider}/configure')
    async def configure(provider:str,request:Request,session=Depends(s.auth)):
        if provider not in PROVIDERS:raise HTTPException(404,'Unknown connector')
        data=await request.json();s.item(data.get('project_id'),'project')
        old=s.store.config('school_'+provider,{})
        # A new source needs a separate account to avoid reinterpreting imported IDs.
        if old.get('enabled'):raise HTTPException(409,'Disconnect before changing this source')
        cfg={'project_id':data['project_id'],'enabled':True,'next_sync':time.time()+900,'status':'configured'}
        try:
            if provider=='gradescope':
                cfg['mode']='canvas' if data.get('mode')=='canvas' else 'upload'
                if cfg['mode']=='canvas':
                    canvas=s.store.config('school_canvas',{})
                    if not canvas.get('enabled') or canvas.get('mode')!='api':raise ValueError('Connect Canvas API first')
                    cfg['source_key']=canvas['source_key']
            elif data.get('mode')=='feed':
                cfg.update(mode='feed',feed=public_url(str(data.get('feed','')),('instructure.com',) if provider=='canvas' else ('outlook.live.com','outlook.office365.com','outlook.office.com')))
            elif provider=='canvas':
                base=str(data.get('base','')).rstrip('/')
                public_url(base,('instructure.com',))
                if urlparse(base).path:raise ValueError('Enter the Canvas site address without a path')
                token=str(data.get('token',''))
                if not 10<=len(token)<=4096:raise ValueError('Enter a Canvas access token')
                cfg.update(mode='api',base=base,token=token)
            else:
                client=str(data.get('client_id',''));uuid.UUID(client)
                secret=str(data.get('client_secret',''))
                if not 10<=len(secret)<=4096:raise ValueError('Enter your Microsoft application secret privately')
                cfg.update(mode='oauth',client_id=client,client_secret=secret,status='authorization_needed')
            cfg.setdefault('source_key',hashlib.sha256((provider+':'+str(cfg.get('base') or cfg.get('feed') or cfg.get('client_id') or 'upload')).encode()).hexdigest())
        except (ValueError,OSError):raise HTTPException(400,'Check the provider address and required connection fields') from None
        with LOCK:s.store.set_config('school_'+provider,cfg)
        s.audit('school_configured',provider)
        return {'status':cfg['status']}

    @app.post('/api/school/outlook/authorize')
    def authorize(session=Depends(s.auth)):
        cfg=s.store.config('school_outlook',{})
        if cfg.get('mode')!='oauth' or not cfg.get('enabled'):raise HTTPException(400,'Configure Outlook first')
        app,_=microsoft(cfg)
        flow=app.initiate_auth_code_flow(['Calendars.Read'],redirect_uri=s.ORIGIN+'/school/outlook/callback')
        cfg.update(oauth_flow=flow,oauth_expires=time.time()+600,oauth_session=session['id'])
        s.store.set_config('school_outlook',cfg)
        return {'url':flow['auth_uri']}

    @app.get('/school/outlook/callback')
    def callback(request:Request):
        with LOCK:
            cfg=s.store.config('school_outlook',{});flow=cfg.pop('oauth_flow',None)
            session=s.store.get(cfg.pop('oauth_session',None))
            expires=cfg.pop('oauth_expires',0)
            s.store.set_config('school_outlook',cfg)
            if not flow or expires<time.time() or not session or session.get('revoked') or datetime.fromisoformat(session['expires'])<datetime.now(timezone.utc):
                raise HTTPException(400,'Authorization expired. Restart Outlook sign-in in TgTop.')
            try:
                app,cache=microsoft(cfg)
                result=app.acquire_token_by_auth_code_flow(flow,dict(request.query_params))
                if 'access_token' not in result:raise ValueError()
                cfg.update(token_cache=cache.serialize(),status='configured')
                s.store.set_config('school_outlook',cfg)
            except Exception:raise HTTPException(400,'Outlook authorization failed. Restart from TgTop.') from None
        return HTMLResponse('<h1>Outlook connected</h1><p>Return to TgTop, open School connections, and fetch deadlines for review.</p><a href="/">Open TgTop</a>',headers={'Cache-Control':'no-store','Referrer-Policy':'no-referrer'})

    @app.post('/api/school/{provider}/sync')
    def sync_route(provider:str,session=Depends(s.auth)):
        if provider not in PROVIDERS:raise HTTPException(404,'Unknown connector')
        s.limit('school:'+session['id'],6,60)
        try:return sync(s,provider)
        except ValueError as e:raise HTTPException(400,str(e)) from None

    @app.post('/api/school/{provider}/upload')
    async def upload(provider:str,file:UploadFile=File(...),session=Depends(s.auth)):
        if provider not in PROVIDERS:raise HTTPException(404,'Unknown connector')
        cfg=s.store.config('school_'+provider,{})
        if not cfg.get('enabled'):raise HTTPException(400,'Choose a project and configure this connector first')
        content=await file.read(2*1024*1024+1)
        if len(content)>2*1024*1024:raise HTTPException(413,'Schedule exceeds 2 MB')
        try:
            if (file.filename or '').lower().endswith('.ics'):items=parse_ics(content,s.settings()['timezone'])
            elif (file.filename or '').lower().endswith('.csv'):items=parse_csv(content,s.settings()['timezone'])
            else:raise ValueError('Upload CSV or ICS')
            with LOCK:return stage(s,provider,items)
        except (ValueError,KeyError,UnicodeError):raise HTTPException(400,'Check schedule format. CSV requires title and due_at columns, with ISO dates. Recurring ICS events require expansion.') from None

    @app.post('/api/school/deadlines/{identifier}/review')
    async def review(identifier:str,request:Request,session=Depends(s.auth)):
        data=await request.json()
        with LOCK,s.store.transaction():
            candidate=s.item(identifier,'school_deadline')
            if data.get('version')!=candidate['version']:raise HTTPException(409,'Deadline changed. Refresh before reviewing.')
            if data.get('decision')=='ignore':candidate['status']='ignored'
            elif data.get('decision')=='import':
                s.item(candidate['fields']['project_id'],'project')
                task=s.store.get(candidate.get('task_id')) if candidate.get('task_id') else None
                if task and task['deleted']:raise HTTPException(409,'Task was deleted locally. Restore it before importing changes.')
                if task:
                    if data.get('task_version')!=task['version']:raise HTTPException(409,'Task changed. Refresh before replacing its dates.')
                    task=s.save_task(dict(task,**candidate['fields']),task['id'],task['version'])
                else:
                    existing=next((t for t in s.store.list('task') if t.get('school_source')==candidate['canonical']),None)
                    if existing:
                        raise HTTPException(409,'This assignment already has a task from another connector. Refresh the connector to link it.')
                    task=s.save_task(dict(candidate['fields'],school_source=candidate['canonical'],status='open',priority='normal',description='Imported from '+candidate['provider']+('\n'+candidate['source_url'] if candidate.get('source_url') else '')))
                candidate.update(task_id=task['id'],baseline=candidate['fields'],status='imported')
            else:raise HTTPException(400,'Choose import or ignore')
            s.store.put('school_deadline',candidate,identifier,candidate['version'])
        return {'status':candidate['status']}

    @app.post('/api/school/{provider}/disconnect')
    def disconnect(provider:str,session=Depends(s.auth)):
        if provider not in PROVIDERS:raise HTTPException(404,'Unknown connector')
        with LOCK:s.store.set_config('school_'+provider,{'enabled':False,'status':'disconnected'})
        return {'status':'disconnected','message':'Saved tasks remain. Provider permission can also be revoked at its account settings.'}
