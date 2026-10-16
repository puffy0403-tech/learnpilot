import sqlite3
from pathlib import Path
import pytest
import database
from local_storage import default_database_path, inspect_database, restore_database


def create_database(path, monkeypatch, email):
    monkeypatch.setattr(database, 'DB_PATH', path)
    database.initialize()
    with database.connect() as c:
        c.execute('INSERT INTO users(email,password_hash) VALUES(?,?)', (email, database.password_hash('original-password')))
        uid = c.execute('SELECT id FROM users').fetchone()[0]
        c.execute('INSERT INTO goals(user_id,subject,weekly_hours) VALUES(?,?,?)', (uid, '英文', 7))
        c.execute('INSERT INTO sessions VALUES(?,?,?)', ('old-session-hash', uid, 9999999999))
    return path


def test_fresh_windows_downloads_share_data_location(tmp_path):
    appdata = tmp_path / 'LocalAppData'
    one = default_database_path(tmp_path / 'download-one/backend', appdata)
    two = default_database_path(tmp_path / 'download-two/backend', appdata)
    assert one == two == appdata / 'LearnPilot/data/learnpilot.db'


def test_existing_project_database_is_preserved(tmp_path):
    backend = tmp_path / 'backend'
    old = backend / 'data/learnpilot.db'
    old.parent.mkdir(parents=True)
    old.touch()
    assert default_database_path(backend, tmp_path / 'appdata') == old


def test_restore_preserves_original_and_backs_up_destination(tmp_path, monkeypatch):
    source = create_database(tmp_path / 'old.db', monkeypatch, 'old@example.test')
    target = create_database(tmp_path / 'current.db', monkeypatch, 'current@example.test')
    before = source.read_bytes()
    backup = restore_database(source, target)
    assert backup.is_file()
    assert source.read_bytes() == before
    with sqlite3.connect(target) as c:
        assert c.execute('SELECT email FROM users').fetchone()[0] == 'old@example.test'
        assert c.execute('SELECT count(*) FROM goals').fetchone()[0] == 1
        assert c.execute('SELECT count(*) FROM sessions').fetchone()[0] == 0
    with sqlite3.connect(backup) as c:
        assert c.execute('SELECT email FROM users').fetchone()[0] == 'current@example.test'


def test_restore_old_account_supports_password_reset(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from main import app
    import password_reset
    source = create_database(tmp_path / 'old.db', monkeypatch, 'old@example.test')
    target = tmp_path / 'persistent/learnpilot.db'
    restore_database(source, target)
    monkeypatch.setattr(database, 'DB_PATH', target)
    monkeypatch.setenv('RESEND_API_KEY', 'test-key')
    monkeypatch.setenv('RESET_EMAIL_FROM', 'sender@example.test')
    monkeypatch.setenv('PASSWORD_RESET_URL', 'https://example.test/')
    sent = []
    monkeypatch.setattr(password_reset, 'deliver_reset', lambda email, token, settings: sent.append((email, token)) or True)
    client = TestClient(app)
    assert client.post('/auth/forgot-password', json={'email': 'old@example.test'}).status_code == 200
    assert len(sent) == 1
    assert client.post('/auth/reset-password', json={'token': sent[0][1], 'password': 'replacement-password'}).status_code == 200
    assert client.post('/auth/login', json={'email': 'old@example.test', 'password': 'replacement-password'}).status_code == 200
    assert len(client.get('/data/goals').json()) == 1


def test_invalid_or_empty_source_cannot_replace_data(tmp_path, monkeypatch):
    target = create_database(tmp_path / 'current.db', monkeypatch, 'current@example.test')
    original = target.read_bytes()
    invalid = tmp_path / 'invalid.db'
    invalid.write_bytes(b'not a database')
    with pytest.raises(sqlite3.DatabaseError):
        restore_database(invalid, target)
    empty = tmp_path / 'empty.db'
    monkeypatch.setattr(database, 'DB_PATH', empty)
    database.initialize()
    with pytest.raises(ValueError, match='沒有帳號'):
        restore_database(empty, target)
    assert target.read_bytes() == original


def test_same_source_cannot_replace_itself(tmp_path, monkeypatch):
    source = create_database(tmp_path / 'old.db', monkeypatch, 'old@example.test')
    with pytest.raises(ValueError, match='不需還原'):
        restore_database(source, source)


def test_unrelated_sqlite_rejected(tmp_path):
    source = tmp_path / 'unrelated.db'
    with sqlite3.connect(source) as c:
        c.execute('CREATE TABLE users(id integer)')
    with pytest.raises(ValueError, match='不是有效'):
        inspect_database(source)


def test_launcher_detects_occupied_port():
    import socket
    from check_startup import port_available
    with socket.socket() as server:
        server.bind(('127.0.0.1', 0))
        server.listen()
        assert not port_available(server.getsockname()[1])


def test_launcher_preflight_stops_on_busy_port(monkeypatch, capsys):
    import check_startup
    monkeypatch.setattr(check_startup, 'port_available', lambda port: port != 8000)
    assert check_startup.main() == 1
    assert '8000' in capsys.readouterr().out
