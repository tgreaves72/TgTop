"""Separate encrypted workspaces selected with request-local context."""
import contextvars
import re
import threading
import uuid
from contextlib import contextmanager
from fastapi import HTTPException
from .store import Store
from .security import Vault, token_hash

current = contextvars.ContextVar('tgtop_account', default='owner')

class Proxy:
    def __init__(self, resolve):object.__setattr__(self, '_resolve', resolve)
    def __getattr__(self, name):return getattr(self._resolve(), name)
    def __setattr__(self, name, value):setattr(self._resolve(), name, value)

class Accounts:
    def __init__(self, owner):
        self.owner=owner
        self.registry=Store(owner.root/'account-index')
        self.stores={'owner':owner};self.vaults={};self.connections={};self.sessions={};self.lock=threading.RLock()
        self.ensure_owner()
    @staticmethod
    def username(value):
        value=str(value or '').strip().lower()
        if not re.fullmatch(r'[a-z0-9][a-z0-9_.-]{2,31}',value):
            raise HTTPException(400,'Use a username of 3–32 letters, numbers, dots, underscores, or hyphens.')
        return value
    def entries(self):return self.registry.config('users',{})
    def ensure_owner(self):
        with self.lock:
            a=self.owner.config('account')
            if not a:return
            users=self.entries()
            if any(v=='owner' for v in users.values()):return
            name=a.get('username') or re.sub(r'[^a-z0-9_.-]','',str(a.get('name','tyler')).lower())
            if len(name)<3:name='owner'
            name=name[:32]
            if name in users:name='owner'
            self.owner.set_config('account',dict(a,username=name))
            users[name]='owner';self.registry.set_config('users',users)
    def get(self, identifier=None):
        identifier=identifier or current.get()
        with self.lock:
            if identifier not in self.stores:
                if identifier not in self.entries().values():raise HTTPException(401,'Sign in to continue')
                self.stores[identifier]=Store(self.owner.root/'users'/identifier)
            return self.stores[identifier]
    def vault(self):
        identifier=current.get()
        with self.lock:
            if identifier not in self.vaults:self.vaults[identifier]=Vault(self.get(identifier))
            return self.vaults[identifier]
    def connection(self, service):
        identifier=current.get()
        with self.lock:
            if identifier not in self.connections:
                from .chatgpt import Connection
                self.connections[identifier]=Connection(service)
            return self.connections[identifier]
    @contextmanager
    def use(self, identifier):
        token=current.set(identifier)
        try:yield
        finally:current.reset(token)
    def identify(self, token):
        if not token:return None
        hashed=token_hash(token)
        import secrets
        from .store import now
        cached=self.sessions.get(hashed)
        if cached:
            identifier,record_id=cached
            s=self.get(identifier).get(record_id)
            if s and not s['deleted'] and not s.get('revoked') and s['expires']>now() and secrets.compare_digest(s['token_hash'],hashed):return identifier
            self.sessions.pop(hashed,None)
            return None
        for identifier in set(self.entries().values()):
            for s in self.get(identifier).list('session'):
                if secrets.compare_digest(s['token_hash'],hashed) and not s.get('revoked') and s['expires']>now():
                    if len(self.sessions)>=4096:self.sessions.clear()
                    self.sessions[hashed]=(identifier,s['id'])
                    return identifier
        return None
    def by_phone(self, phone):
        matches=[]
        for identifier in set(self.entries().values()):
            cfg=self.get(identifier).config('settings',{})
            if phone and cfg.get('phone')==phone and cfg.get('phone_verified') and cfg.get('phone_verification_mode')=='live':matches.append(identifier)
        return matches[0] if len(matches)==1 else None
    def register(self, username, account):
        name=self.username(username)
        with self.lock:
            users=self.entries()
            if name in users:raise HTTPException(409,'Username is unavailable. Choose another or log in.')
            identifier='owner' if not self.owner.config('account') else str(uuid.uuid4())
            target=self.owner if identifier=='owner' else Store(self.owner.root/'users'/identifier)
            target.set_config('account',dict(account,username=name))
            for space in ('personal','school','work'):target.put('project',{'title':space.title(),'space':space,'ai_allowed':False,'description':''})
            self.stores[identifier]=target
            users[name]=identifier;self.registry.set_config('users',users)
            return identifier
