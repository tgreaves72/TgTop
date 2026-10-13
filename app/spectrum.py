"""Official Photon Spectrum SDK, private stdin/stdout RPC; keys never enter argv."""
import json
import os
import shutil
import subprocess
import sys
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

class Bridge:
    def __init__(self):
        self.lock=threading.RLock(); self.pending={}; self.process=None; self.identity=None
        self.callback=None; self.pool=ThreadPoolExecutor(max_workers=1)
    @property
    def callback(self):return self._callback
    @callback.setter
    def callback(self,value):
        import contextvars
        self._callback=value;self.callback_context=contextvars.copy_context()
    def ensure(self,cfg):
        identity=(cfg.get('project_id'),cfg.get('project_secret'))
        with self.lock:
            if self.process and self.process.poll() is None and identity==self.identity:return
            self.close()
            base=Path(sys.executable).parent.parent/'photon' if getattr(sys,'frozen',False) else Path(__file__).resolve().parent.parent/'integrations'/'photon'
            node=base/'node.exe'
            executable=str(node) if node.exists() else shutil.which('node')
            if not executable:raise RuntimeError('Photon runtime is unavailable')
            self.process=subprocess.Popen([executable,str(base/'bridge.mjs')],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,text=True,encoding='utf-8',creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
            self.identity=identity
            threading.Thread(target=self.read,args=(self.process,),daemon=True).start()
            try:self.request('start',project_id=identity[0],project_secret=identity[1])
            except Exception:self.close();raise
    def read(self,process):
        try:
            for line in process.stdout:
                if len(line)>20000:continue
                try:data=json.loads(line)
                except ValueError:continue
                if data.get('event')=='incoming' and self.callback:
                    import contextvars
                    self.pool.submit(self.callback_context.run,self.callback,data)
                elif data.get('event')=='stream_failed':process.terminate()
                elif data.get('id') in self.pending:
                    event,result=self.pending[data['id']];result.update(data);event.set()
        finally:
            for event,result in list(self.pending.values()):event.set()
    def request(self,action,**fields):
        key=uuid.uuid4().hex;event=threading.Event();result={}
        with self.lock:
            if not self.process or self.process.poll() is not None:raise RuntimeError('Photon disconnected')
            self.pending[key]=(event,result)
            self.process.stdin.write(json.dumps(dict(fields,id=key,action=action))+'\n');self.process.stdin.flush()
        try:
            if not event.wait(30) or not result.get('ok'):raise RuntimeError('Photon operation failed or outcome unknown')
            return result
        finally:self.pending.pop(key,None)
    def close(self):
        with self.lock:
            if self.process and self.process.poll() is None:
                self.process.terminate()
                try:self.process.wait(timeout=5)
                except subprocess.TimeoutExpired:self.process.kill()
            self.process=None;self.identity=None

from .accounts import Proxy, current as account_context
_bridges={}
_bridge_lock=threading.RLock()
def selected_bridge():
    with _bridge_lock:
        return _bridges.setdefault(account_context.get(),Bridge())
bridge=Proxy(selected_bridge)
def close_all():
    for value in list(_bridges.values()):value.close()


def incoming(s,data):
    cfg=s.messaging.config(s.store);settings=s.settings()
    if cfg.get('provider')!='photon_spectrum' or not settings.get('phone_verified') or settings.get('phone_verification_mode')!='live':return
    if data.get('sender')!=settings.get('phone'):return
    import time
    try:
        if abs(time.time()-float(data['timestamp']))>300:return
        guid=data['guid'];body=data['text']
        if not isinstance(guid,str) or not 1<=len(guid)<=128 or not isinstance(body,str) or len(body)>2000:return
        s.limit('spectrum:'+data['sender'],10,60)
        from .remote import receive,finish
        record=receive(s,'photon_spectrum',guid,data['sender'],body)
        if record['status']!='received':return
        from .phone_ai import command
        import asyncio
        if body.lower().startswith('ai '):
            future=asyncio.run_coroutine_threadsafe(command(s,body,record['id']),s.app.state.main_loop)
            try:answer=future.result(timeout=60)
            except TimeoutError:
                future.cancel()
                current=s.store.get(record['id'])
                if current['status']=='received':s.store.put('remote_command',dict(current,status='failed',error='AI request timed out; review before retry'),current['id'],current['version'])
        else:answer=finish(s,record['id'],lambda:s.remote_command(body))
        from .remote import replies
        replies(s)
        s.audit('photon_command')
    except Exception:s.audit('photon_command',status='failed')
