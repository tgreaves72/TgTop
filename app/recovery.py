"""Encrypted rollback journal for multi-file account restoration."""
import os
import shutil
import sqlite3
from pathlib import Path

def recover(root,connection=None):
    root=Path(root);journal=root/'restore-journal'
    if not (journal/'ready').exists():return
    snapshot=sqlite3.connect(journal/'snapshot.db')
    target=connection or sqlite3.connect(root/'tgtop.db')
    try:snapshot.backup(target)
    finally:
        snapshot.close()
        if connection is None:target.close()
    pending=root/'server.key.restore'
    shutil.copyfile(journal/'server.key',pending)
    os.replace(pending,root/'server.key')
    for source in (journal/'blobs').iterdir():shutil.copyfile(source,root/'blobs'/source.name)
    shutil.rmtree(journal)

def prepare(store):
    journal=store.root/'restore-journal'
    if journal.exists():
        if (journal/'ready').exists():raise RuntimeError('An unfinished restore requires recovery before continuing')
        shutil.rmtree(journal)
    journal.mkdir(mode=0o700)
    (journal/'blobs').mkdir(mode=0o700)
    snapshot=sqlite3.connect(journal/'snapshot.db')
    try:store.db.backup(snapshot)
    finally:snapshot.close()
    shutil.copyfile(store.root/'server.key',journal/'server.key')
    if os.name!='nt':os.chmod(journal/'server.key',0o600)
    for blob in (store.root/'blobs').iterdir():
        if blob.is_file():shutil.copyfile(blob,journal/'blobs'/blob.name)
    with (journal/'ready').open('xb') as marker:
        marker.write(b'TGTOP-RESTORE-ROLLBACK-1');marker.flush();os.fsync(marker.fileno())
    return journal

def complete(journal):
    # Removing the marker commits restoration. Leftover snapshots can then be cleaned safely.
    (journal/'ready').unlink()
    shutil.rmtree(journal)
