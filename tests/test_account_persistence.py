import importlib
from fastapi.testclient import TestClient


def test_account_and_history_survive_restart_and_logout(tmp_path, monkeypatch):
    monkeypatch.setenv('TGTOP_DATA', str(tmp_path))
    monkeypatch.setenv('TGTOP_MODE', 'development')
    import app.server as server
    server = importlib.reload(server)
    headers = {'Origin': server.ORIGIN, 'X-TgTop': '1'}
    client = TestClient(server.app, headers=headers)
    assert client.get('/api/status').json()['setup']
    assert client.post('/api/setup', json={'name': 'Test', 'password': 'persistent-account-123'}).status_code == 200
    assert client.post('/api/login', json={'username':'test','password': 'persistent-account-123'}).status_code == 200
    task = client.post('/api/records/task', json={'title': 'Keep this task', 'status': 'open'}).json()
    cookie = client.cookies.get('tgtop_session')
    server.store.db.close()
    server = importlib.reload(server)
    reopened = TestClient(server.app, headers=headers)
    reopened.cookies.set('tgtop_session', cookie)
    assert not reopened.get('/api/status').json()['setup']
    saved = reopened.get('/api/state').json()['records']
    assert any(r['id'] == task['id'] for r in saved)
    assert any(r['kind'] == 'activity' and r.get('target') == task['id'] for r in saved)
    assert reopened.post('/api/logout').status_code == 200
    assert reopened.get('/api/state').status_code == 401
    assert reopened.post('/api/setup', json={'password': 'replacement-account-123'}).status_code == 409
    assert reopened.post('/api/login', json={'username':'test','password': 'persistent-account-123'}).status_code == 200
    assert any(r['id'] == task['id'] for r in reopened.get('/api/state').json()['records'])
    server.store.db.close()


def test_default_storage_does_not_depend_on_working_directory(tmp_path, monkeypatch):
    from app.paths import data_root
    monkeypatch.delenv('TGTOP_DATA', raising=False)
    before = data_root()
    import os
    from pathlib import Path
    if os.name == 'nt': assert before == Path.home() / '.tgtop' / 'data'
    monkeypatch.chdir(tmp_path)
    assert data_root() == before
    monkeypatch.setenv('TGTOP_DATA', str(tmp_path / 'explicit'))
    assert data_root() == tmp_path / 'explicit'


def test_windows_legacy_migration_preserves_account_and_key(tmp_path,monkeypatch):
    import os
    import pytest
    from pathlib import Path
    from app.store import Store
    if os.name!='nt': pytest.skip('Windows storage migration')
    monkeypatch.setenv('APPDATA',str(tmp_path/'roaming'))
    monkeypatch.setenv('LOCALAPPDATA',str(tmp_path/'local'))
    monkeypatch.setattr(Path,'home',classmethod(lambda cls:tmp_path/'home'))
    legacy=tmp_path/'roaming'/'TgTop'/'data'
    old=Store(legacy);old.set_config('account',{'name':'Migration QA','password_hash':'fixture-hash'})
    task=old.put('task',{'title':'Preserve across folder migration'})
    key=(legacy/'server.key').read_bytes();old.db.close()
    new=Store(Path.home()/'.tgtop'/'data')
    assert new.config('account')['password_hash']=='fixture-hash'
    assert new.get(task['id'])['title']=='Preserve across folder migration'
    assert (new.root/'server.key').read_bytes()==key
    assert (legacy/'tgtop.db').exists()
    new.db.close()


def test_windows_corrupt_legacy_account_blocks_new_signup(tmp_path,monkeypatch):
    import os
    import pytest
    from pathlib import Path
    from app.store import Store
    if os.name!='nt':pytest.skip('Windows storage migration')
    monkeypatch.setenv('APPDATA',str(tmp_path/'roaming'))
    monkeypatch.setenv('LOCALAPPDATA',str(tmp_path/'local'))
    monkeypatch.setattr(Path,'home',classmethod(lambda cls:tmp_path/'home'))
    legacy=tmp_path/'roaming'/'TgTop'/'data'
    old=Store(legacy);old.set_config('account',{'password_hash':'fixture-hash'});old.db.close()
    (legacy/'server.key').write_bytes(os.urandom(32))
    target=Path.home()/'.tgtop'/'data'
    with pytest.raises(RuntimeError,match='could not be decrypted'):Store(target)
    assert not (target/'tgtop.db').exists()


def test_service_reopening_never_rewrites_encryption_key(tmp_path):
    from app.store import Store
    first = Store(tmp_path)
    first.set_config('account', {'name': 'Persistent test'})
    original = (tmp_path / 'server.key').read_bytes()
    first.db.close()
    second = Store(tmp_path)
    assert second.config('account')['name'] == 'Persistent test'
    assert (tmp_path / 'server.key').read_bytes() == original
    second.db.close()


def test_concurrent_first_launch_uses_one_key(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    from app.store import Store
    def open_store(_):
        s = Store(tmp_path)
        key = s.key
        s.db.close()
        return key
    with ThreadPoolExecutor(max_workers=4) as pool:
        assert len(set(pool.map(open_store, range(4)))) == 1
