"""Encrypted application records, optimistic versions and durable event stream."""
import base64
import json
import os
import sqlite3
import threading
import uuid
from pathlib import Path
from datetime import datetime, timezone
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

def now():
    return datetime.now(timezone.utc).isoformat()

def uid():
    return str(uuid.uuid4())

class Store:
    def __init__(self, root):
        self.root = Path(root).resolve()
        from .migration import migrate_legacy
        migrate_legacy(self.root)
        self.root.mkdir(parents=True, exist_ok=True)
        if os.name != 'nt': os.chmod(self.root,0o700)
        (self.root / 'blobs').mkdir(exist_ok=True)
        keyfile = self.root / 'server.key'
        if keyfile.exists():
            encoded = keyfile.read_bytes()
            if encoded.startswith(b'DPAPI1'):
                import win32crypt
                self.key = win32crypt.CryptUnprotectData(encoded[6:],None,None,None,0)[1]
            else: self.key=encoded
        else:
            if (self.root / 'tgtop.db').exists():
                raise RuntimeError('Workspace encryption key is missing. Preserve this folder and restore an encrypted backup; do not create a new account here.')
            key = AESGCM.generate_key(bit_length=256)
            if os.name == 'nt':
                import win32crypt
                encoded = b'DPAPI1'+win32crypt.CryptProtectData(key,'TgTop service key',None,None,None,0)
            else: encoded = key
            pending = self.root / ('server.key.'+uuid.uuid4().hex+'.pending')
            try:
                with pending.open('xb') as f:
                    f.write(encoded)
                    f.flush()
                    os.fsync(f.fileno())
                # Linking the fully written file publishes it atomically and exclusively.
                os.link(pending, keyfile)
                self.key = key
            except FileExistsError:
                # Another service won first-run creation. Never overwrite its key.
                encoded = keyfile.read_bytes()
                if encoded.startswith(b'DPAPI1'):
                    import win32crypt
                    self.key = win32crypt.CryptUnprotectData(encoded[6:],None,None,None,0)[1]
                else: self.key = encoded
            finally:
                pending.unlink(missing_ok=True)
            if os.name != 'nt': os.chmod(keyfile,0o600)
        self.aes = AESGCM(self.key)
        self.lock = threading.RLock()
        self.db = sqlite3.connect(self.root / 'tgtop.db', check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.executescript('''
          PRAGMA journal_mode=WAL;
          CREATE TABLE IF NOT EXISTS migrations(version INTEGER PRIMARY KEY, applied TEXT);
          CREATE TABLE IF NOT EXISTS records(id TEXT PRIMARY KEY, kind TEXT NOT NULL, version INTEGER NOT NULL, deleted INTEGER NOT NULL DEFAULT 0, data BLOB NOT NULL);
          CREATE TABLE IF NOT EXISTS events(seq INTEGER PRIMARY KEY AUTOINCREMENT, id TEXT UNIQUE, kind TEXT, entity TEXT, at TEXT);
          CREATE TABLE IF NOT EXISTS config(name TEXT PRIMARY KEY, data BLOB);
          CREATE TABLE IF NOT EXISTS dedupe(id TEXT PRIMARY KEY, at TEXT);
          INSERT OR IGNORE INTO migrations VALUES(1, CURRENT_TIMESTAMP);
        ''')
        self.db.commit()

    def save_key(self,key):
        if os.name == 'nt':
            import win32crypt
            encoded=b'DPAPI1'+win32crypt.CryptProtectData(key,'TgTop service key',None,None,None,0)
        else: encoded=key
        (self.root/'server.key').write_bytes(encoded)
        if os.name != 'nt': os.chmod(self.root/'server.key',0o600)

    def encrypt(self, data, aad=b'tgtop-record-v1'):
        nonce = os.urandom(12)
        return nonce + self.aes.encrypt(nonce, data, aad)

    def decrypt(self, data, aad=b'tgtop-record-v1'):
        return self.aes.decrypt(data[:12], data[12:], aad)

    def config(self, name, default=None):
        with self.lock:
            row = self.db.execute('SELECT data FROM config WHERE name=?', (name,)).fetchone()
            return json.loads(self.decrypt(row[0])) if row else default

    def set_config(self, name, value):
        with self.lock, self.db:
            self.db.execute('INSERT OR REPLACE INTO config VALUES(?,?)', (name, self.encrypt(json.dumps(value).encode())))

    def get(self, id):
        with self.lock:
            row = self.db.execute('SELECT * FROM records WHERE id=?', (id,)).fetchone()
            if not row: return None
            data = json.loads(self.decrypt(row['data']))
            return dict(data, id=id, kind=row['kind'], version=row['version'], deleted=bool(row['deleted']))

    def list(self, kind=None, trash=False):
        with self.lock:
            rows = self.db.execute('SELECT id FROM records WHERE deleted=?' + (' AND kind=?' if kind else ''), (int(trash), kind) if kind else (int(trash),)).fetchall()
            return [self.get(r[0]) for r in rows]

    def put(self, kind, data, id=None, version=None, deleted=False):
        with self.lock, self.db:
            id = id or uid()
            old = self.get(id)
            if old and (version is None or version != old['version']):
                raise Conflict(old)
            clean = {k:v for k,v in data.items() if k not in ('id','kind','version','deleted')}
            clean['updated_at'] = now()
            clean.setdefault('created_at', old.get('created_at') if old else now())
            ver = old['version'] + 1 if old else 1
            self.db.execute('INSERT OR REPLACE INTO records VALUES(?,?,?,?,?)', (id, kind, ver, int(deleted), self.encrypt(json.dumps(clean).encode())))
            self.db.execute('INSERT INTO events(id,kind,entity,at) VALUES(?,?,?,?)', (uid(), kind, id, now()))
            return self.get(id)

    def claim(self, id):
        with self.lock, self.db:
            try:
                self.db.execute('INSERT INTO dedupe VALUES(?,?)', (id, now()))
                return True
            except sqlite3.IntegrityError: return False

    def claimed(self,id):
        with self.lock: return bool(self.db.execute('SELECT 1 FROM dedupe WHERE id=?',(id,)).fetchone())

    def cursor(self):
        with self.lock: return self.db.execute('SELECT COALESCE(MAX(seq),0) FROM events').fetchone()[0]

    def events(self, after=0):
        with self.lock:
            return [dict(r) for r in self.db.execute('SELECT * FROM events WHERE seq>? ORDER BY seq LIMIT 500', (after,))]

class Conflict(Exception):
    def __init__(self, current): self.current = current
