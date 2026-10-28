import json
import pytest
from fastapi.testclient import TestClient
import database
from main import app

@pytest.fixture
def clients(tmp_path, monkeypatch):
    monkeypatch.setattr(database, 'DB_PATH', tmp_path / 'reports.db')
    database.initialize()
    a, b = TestClient(app), TestClient(app)
    for client, email in [(a, 'a@example.test'), (b, 'b@example.test')]:
        assert client.post('/auth/register', json={'email': email, 'password': 'test-password'}).status_code == 200
    return a, b

def test_snapshot_persistence_and_ownership(clients):
    a, b = clients
    for hours in [2, 4]:
        a.post('/data/goals', json={'subject': '英文', 'weekly_hours': hours})
    log = a.post('/data/study_logs', json={'study_date': '2026-10-26', 'subject': '英文', 'minutes': 60, 'note': '原本筆記'}).json()
    b.post('/data/study_logs', json={'study_date': '2026-10-26', 'subject': '他人私密', 'minutes': 500})
    saved = a.post('/reports', json={'mode': 'week', 'anchor': '2026-10-28'})
    assert saved.status_code == 200
    r = saved.json()
    assert (r['period_start'], r['period_end']) == ('2026-10-26', '2026-11-01')
    assert '60 分鐘' in r['content'] and '目標 4.0 小時' in r['content']
    assert '他人私密' not in json.dumps(r, ensure_ascii=False)
    assert json.loads(r['snapshot'])['logs'][0]['note'] == '原本筆記'
    a.patch(f'/data/study_logs/{log["id"]}', json={'minutes': 120, 'note': '更新筆記'})
    database.initialize()
    assert a.get(f'/reports/{r["id"]}').json() == r
    assert a.get('/reports').json() == [r]
    assert b.get('/reports').json() == []
    assert b.get(f'/reports/{r["id"]}').status_code == 404
    assert TestClient(app).get('/reports').status_code == 401

def test_month_boundaries_empty_and_validation(clients):
    a, _ = clients
    r = a.post('/reports', json={'mode': 'month', 'anchor': '2028-02-15'}).json()
    assert (r['period_start'], r['period_end']) == ('2028-02-01', '2028-02-29')
    assert '尚無學習紀錄' in r['content']
    for payload in [{'mode': 'year', 'anchor': '2026-10-28'}, {'mode': 'week', 'anchor': 'invalid'}, {'mode': 'week', 'anchor': '2026-10-28', 'user_id': 999}]:
        assert a.post('/reports', json=payload).status_code == 422
