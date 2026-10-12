"""Preserve and validate legacy Windows stores before choosing one physical location."""
import hashlib
import json
import os
import shutil
import sqlite3
import uuid
from pathlib import Path
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

def migrate_legacy(root):
    if os.name!='nt' or root!=(Path.home()/'.tgtop'/'data').resolve() or (root/'tgtop.db').exists(): return
    import win32crypt
    roaming=Path(os.environ['APPDATA'])/'TgTop'/'data'
    packages=Path(os.environ['LOCALAPPDATA'])/'Packages'
    candidates=[roaming]
    for pattern in ('PythonSoftwareFoundation.Python.*/LocalCache/Roaming/TgTop/data','OpenAI.Codex_*/LocalCache/Roaming/tgtop/data'):
        candidates.extend(packages.glob(pattern))
    valid=[];unreadable=False
    for source in candidates:
        if not (source/'tgtop.db').exists(): continue
        # Work only on recovery copies so SQLite checkpointing cannot change the source.
        recovery=root.parent/('legacy-copy-'+uuid.uuid4().hex)
        recovery.parent.mkdir(parents=True,exist_ok=True)
        shutil.copytree(source,recovery)
        db=sqlite3.connect(str(recovery/'tgtop.db'))
        try:
            tables={r[0] for r in db.execute('select name from sqlite_master where type="table"')}
            if 'config' not in tables: continue
            configs=db.execute('select name,data from config').fetchall()
            records=db.execute('select data from records').fetchall()
            if not configs and not records: continue
            encoded=(recovery/'server.key').read_bytes()
            key=win32crypt.CryptUnprotectData(encoded[6:],None,None,None,0)[1] if encoded.startswith(b'DPAPI1') else encoded
            aes=AESGCM(key)
            def decode(blob):return json.loads(aes.decrypt(blob[:12],blob[12:],b'tgtop-record-v1'))
            values={name:decode(blob) for name,blob in configs}
            for (blob,) in records:decode(blob)
            identity=hashlib.sha256(json.dumps(values.get('account'),sort_keys=True).encode()).hexdigest() if values.get('account') else None
            valid.append((recovery,identity,len(records)))
        except Exception:
            unreadable=True
        finally:db.close()
    accounts=[v for v in valid if v[1]]
    if len({v[1] for v in accounts})>1:
        raise RuntimeError('Multiple legacy accounts found. Recovery copies are preserved in your .tgtop folder; choose the intended account before migration.')
    if unreadable and not accounts:
        raise RuntimeError('A legacy workspace could not be decrypted. Recovery copies are preserved; recover it before creating a replacement account.')
    if not valid:
        if unreadable:raise RuntimeError('Legacy workspace could not be decrypted. Recovery copies are preserved; restore the original key or an encrypted backup before signing up.')
        return
    selected=max(accounts or valid,key=lambda v:v[2])[0]
    shutil.copytree(selected,root)
