import json
import sqlite3

import pytest
from fastapi.testclient import TestClient

import database
from main import app
from planning import serialize_editable_plan
from plan_items import VERSION


@pytest.fixture
def clients(tmp_path, monkeypatch):
    monkeypatch.setattr(database, 'DB_PATH', tmp_path / 'items.db')
    database.initialize()
    owner, other = TestClient(app), TestClient(app)
    for client, email in ((owner, 'owner@example.test'), (other, 'other@example.test')):
        assert client.post('/auth/register', json={'email': email, 'password': 'test-password'}).status_code == 200
    return owner, other


def create_plan(client):
    rows = [dict(date='2026-10-26', start_time='08:00', subject='英文', minutes=60, content='閱讀', kind='study'),
            dict(date='2026-10-26', start_time='10:00', subject='數學', minutes=60, content='練習', kind='study')]
    payload = client.post('/plans/serialize', json={'week_start': '2026-10-26', 'items': rows, 'notes': '備註'}).json()
    response = client.post('/data/plans', json=payload)
    assert response.status_code == 200, response.text
    return response.json()


def test_stable_item_id_directly_links_one_learning_log(clients):
    owner, other = clients
    plan = create_plan(owner)
    items = owner.get(f"/plans/{plan['id']}/items").json()['items']
    item_id = items[0]['plan_item_id']
    assert isinstance(item_id, int)
    assert owner.get(f"/plans/{plan['id']}/items").json()['items'][0]['plan_item_id'] == item_id
    assert other.get(f"/plans/{plan['id']}/items").status_code == 404
    assert other.patch(f'/plan-items/{item_id}/completion', json={'completed': True, 'original_content': plan['content']}).status_code == 404
    response = owner.patch(f'/plan-items/{item_id}/completion', json={'completed': True, 'original_content': plan['content']})
    assert response.status_code == 200, response.text
    result = response.json()
    assert result['items'][0]['completed_at']
    assert result['study_logs'][0]['plan_item_id'] == item_id
    repeated = owner.patch(f'/plan-items/{item_id}/completion', json={'completed': True, 'original_content': result['plan']['content']}).json()
    assert len(repeated['study_logs']) == 1
    assert repeated['items'][0]['completed_at'] == result['items'][0]['completed_at']
    with pytest.raises(sqlite3.IntegrityError):
        with database.connect() as c:
            c.execute('INSERT INTO study_logs(user_id,study_date,subject,minutes,plan_item_id) VALUES(?,?,?,?,?)', (1, '2026-10-26', '英文', 60, item_id))
    undo = owner.patch(f'/plan-items/{item_id}/completion', json={'completed': False, 'original_content': repeated['plan']['content']}).json()
    assert undo['study_logs'] == []
    assert undo['items'][0]['completed_at'] is None


def test_reorder_and_edit_keep_identity_and_log_history(clients):
    owner, _ = clients
    plan = create_plan(owner)
    parsed = owner.get(f"/plans/{plan['id']}/items").json()
    item_id = parsed['items'][0]['plan_item_id']
    done = owner.patch(f'/plan-items/{item_id}/completion', json={'completed': True, 'original_content': plan['content']}).json()
    parsed = owner.get(f"/plans/{plan['id']}/items").json()
    parsed['items'][0].update(start_time='12:00', content='修改後的閱讀內容')
    serialized = owner.post('/plans/serialize', json={'week_start': plan['week_start'], **parsed}).json()
    edited = owner.patch(f"/data/plans/{plan['id']}", json={**serialized, 'original_content': done['plan']['content']}).json()
    reordered = owner.get(f"/plans/{plan['id']}/items").json()['items']
    assert reordered[1]['plan_item_id'] == item_id
    assert reordered[1]['completed_at'] == done['items'][0]['completed_at']
    assert owner.get('/data/study_logs').json() == done['study_logs']
    assert owner.patch(f'/plan-items/{item_id}/completion', json={'completed': False, 'original_content': edited['content']}).status_code == 200
    assert owner.get('/data/study_logs').json() == []


def test_delete_plan_retains_history_and_detaches_reference(clients):
    owner, _ = clients
    plan = create_plan(owner)
    item_id = owner.get(f"/plans/{plan['id']}/items").json()['items'][0]['plan_item_id']
    owner.patch(f'/plan-items/{item_id}/completion', json={'completed': True, 'original_content': plan['content']})
    assert owner.delete(f"/data/plans/{plan['id']}").status_code == 200
    logs = owner.get('/data/study_logs').json()
    assert len(logs) == 1 and logs[0]['plan_item_id'] is None
    with database.connect() as c:
        assert c.execute('SELECT count(*) FROM plan_items').fetchone()[0] == 0
        assert c.execute('PRAGMA foreign_key_check').fetchall() == []


def test_removed_item_retains_history_and_detaches_reference(clients):
    owner, _ = clients
    plan = create_plan(owner)
    parsed = owner.get(f"/plans/{plan['id']}/items").json()
    item_id = parsed['items'][0]['plan_item_id']
    done = owner.patch(f'/plan-items/{item_id}/completion', json={'completed': True, 'original_content': plan['content']}).json()
    parsed['items'] = [parsed['items'][1]]
    serialized = owner.post('/plans/serialize', json={'week_start': plan['week_start'], **parsed}).json()
    assert owner.patch(f"/data/plans/{plan['id']}", json={**serialized, 'original_content': done['plan']['content']}).status_code == 200
    assert owner.get('/data/study_logs').json()[0]['plan_item_id'] is None
    assert owner.patch(f'/plan-items/{item_id}/completion', json={'completed': False, 'original_content': serialized['content']}).status_code == 404


def test_foreign_item_ids_and_malformed_content_do_not_partially_save(clients):
    owner, other = clients
    plan = create_plan(owner)
    foreign = create_plan(other)
    foreign_id = other.get(f"/plans/{foreign['id']}/items").json()['items'][0]['plan_item_id']
    parsed = owner.get(f"/plans/{plan['id']}/items").json()
    parsed['items'][0]['plan_item_id'] = foreign_id
    payload = owner.post('/plans/serialize', json={'week_start': plan['week_start'], **parsed}).json()
    assert owner.patch(f"/data/plans/{plan['id']}", json={**payload, 'original_content': plan['content']}).status_code == 422
    assert owner.patch(f"/data/plans/{plan['id']}", json={'content': '<!-- learnpilot-v1:invalid -->'}).status_code == 422
    assert owner.get('/data/plans').json()[0]['content'] == plan['content']
    assert owner.get(f"/plans/{plan['id']}/items").json()['items'][0]['subject'] == '英文'


def legacy_database(path, *, corrupt=False):
    key = 'a' * 32
    _, content = serialize_editable_plan([dict(date='2026-10-26', start_time='08:00', subject='英文', minutes=60, content='閱讀', kind='study', completed=True, completion_key=key)], '原始備註')
    if corrupt:
        content = '<!-- learnpilot-v1:invalid -->'
    password = database.password_hash('original-password')
    with sqlite3.connect(path) as c:
        c.executescript('''CREATE TABLE users(id INTEGER PRIMARY KEY, email TEXT NOT NULL UNIQUE, password_hash TEXT NOT NULL, metadata TEXT NOT NULL DEFAULT '{}');
        CREATE TABLE plans(id INTEGER PRIMARY KEY,user_id INTEGER NOT NULL REFERENCES users(id),week_start TEXT NOT NULL,content TEXT NOT NULL,selected_at TEXT,created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE study_logs(id INTEGER PRIMARY KEY,user_id INTEGER NOT NULL REFERENCES users(id),study_date TEXT NOT NULL,subject TEXT NOT NULL,minutes INTEGER NOT NULL,note TEXT,created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE plan_completion_logs(plan_id INTEGER NOT NULL REFERENCES plans(id) ON DELETE CASCADE,item_key TEXT NOT NULL,log_id INTEGER UNIQUE REFERENCES study_logs(id) ON DELETE SET NULL,PRIMARY KEY(plan_id,item_key));''')
        c.execute('INSERT INTO users(id,email,password_hash) VALUES(1,?,?)', ('legacy@example.test', password))
        c.execute('INSERT INTO plans(id,user_id,week_start,content) VALUES(7,1,?,?)', ('2026-10-26', content))
        c.execute('INSERT INTO study_logs(id,user_id,study_date,subject,minutes,note) VALUES(9,1,?,?,?,?)', ('2026-10-26', '英文', 60, '原始自動紀錄'))
        c.execute('INSERT INTO study_logs(id,user_id,study_date,subject,minutes,note) VALUES(10,1,?,?,?,?)', ('2026-10-26', '英文', 30, '手動紀錄'))
        c.execute('INSERT INTO plan_completion_logs VALUES(7,?,9)', (key,))
    return content, password


def test_real_legacy_schema_migrates_once_with_verified_backup(tmp_path, monkeypatch):
    path = tmp_path / 'legacy.db'
    content, password = legacy_database(path)
    monkeypatch.setattr(database, 'DB_PATH', path)
    database.initialize()
    with database.connect() as c:
        item = c.execute('SELECT * FROM plan_items').fetchone()
        assert item['completed_at']
        assert c.execute('SELECT plan_item_id FROM study_logs WHERE id=9').fetchone()[0] == item['id']
        assert c.execute('SELECT plan_item_id FROM study_logs WHERE id=10').fetchone()[0] is None
        assert c.execute('SELECT content FROM plans WHERE id=7').fetchone()[0] == content
        assert c.execute('SELECT password_hash FROM users WHERE id=1').fetchone()[0] == password
        assert c.execute('PRAGMA foreign_key_check').fetchall() == []
    backup = list((tmp_path / 'backups').glob('*.db'))
    assert len(backup) == 1
    with sqlite3.connect(backup[0]) as c:
        assert c.execute('PRAGMA quick_check').fetchone()[0] == 'ok'
        assert 'plan_item_id' not in {r[1] for r in c.execute('PRAGMA table_info(study_logs)')}
        assert c.execute('SELECT count(*) FROM study_logs').fetchone()[0] == 2
    database.initialize()
    assert len(list((tmp_path / 'backups').glob('*.db'))) == 1
    with database.connect() as c:
        assert c.execute('SELECT count(*) FROM plan_items').fetchone()[0] == 1
        assert c.execute('SELECT count(*) FROM schema_migrations WHERE version=?', (VERSION,)).fetchone()[0] == 1
    owner = TestClient(app)
    assert owner.post('/auth/login', json={'email': 'legacy@example.test', 'password': 'original-password'}).status_code == 200
    assert owner.patch(f"/plan-items/{item['id']}/completion", json={'completed': False, 'original_content': content}).status_code == 200
    logs = owner.get('/data/study_logs').json()
    assert len(logs) == 1 and logs[0]['note'] == '手動紀錄'


def test_failed_migration_rolls_back_and_keeps_backup(tmp_path, monkeypatch):
    path = tmp_path / 'legacy.db'
    content, _ = legacy_database(path, corrupt=True)
    monkeypatch.setattr(database, 'DB_PATH', path)
    with pytest.raises(RuntimeError, match='已回復'):
        database.initialize()
    with sqlite3.connect(path) as c:
        assert c.execute('SELECT content FROM plans').fetchone()[0] == content
        assert c.execute('SELECT count(*) FROM study_logs').fetchone()[0] == 2
        assert 'plan_item_id' not in {r[1] for r in c.execute('PRAGMA table_info(study_logs)')}
        assert not c.execute("SELECT 1 FROM sqlite_master WHERE name='plan_items'").fetchone()
    assert len(list((tmp_path / 'backups').glob('*.db'))) == 1


def test_legacy_cross_account_link_aborts_migration(tmp_path, monkeypatch):
    path = tmp_path / 'legacy.db'
    legacy_database(path)
    with sqlite3.connect(path) as c:
        c.execute("INSERT INTO users(id,email,password_hash) VALUES(2,'other@example.test','hash')")
        c.execute('UPDATE study_logs SET user_id=2 WHERE id=9')
    monkeypatch.setattr(database, 'DB_PATH', path)
    with pytest.raises(RuntimeError):
        database.initialize()
    with sqlite3.connect(path) as c:
        assert c.execute('SELECT user_id FROM study_logs WHERE id=9').fetchone()[0] == 2
        assert 'plan_item_id' not in {r[1] for r in c.execute('PRAGMA table_info(study_logs)')}


def test_new_id_endpoint_rejects_stale_snapshot(clients):
    owner, _ = clients
    plan = create_plan(owner)
    item_id = owner.get(f"/plans/{plan['id']}/items").json()['items'][0]['plan_item_id']
    first = owner.patch(f'/plan-items/{item_id}/completion', json={'completed': True, 'original_content': plan['content']})
    assert first.status_code == 200
    assert owner.patch(f'/plan-items/{item_id}/completion', json={'completed': False, 'original_content': plan['content']}).status_code == 409
    assert len(owner.get('/data/study_logs').json()) == 1
    assert owner.get(f"/plans/{plan['id']}/items").json()['items'][0]['completed'] is True
