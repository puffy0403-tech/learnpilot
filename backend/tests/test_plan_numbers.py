import pytest
from fastapi.testclient import TestClient
import database
from main import app

@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(database, 'DB_PATH', tmp_path / 'numbers.db')
    database.initialize()
    c=TestClient(app)
    c.post('/auth/register',json={'email':'number@example.test','password':'test-password'})
    return c

def save(client):
    return client.post('/data/plans',json={'week_start':'2026-10-26','content':'學習計畫'}).json()

def test_number_immutable_unique_and_never_reused(client):
    first=save(client)
    assert first['plan_number']=='LP-000001'
    assert client.patch(f'/data/plans/{first["id"]}',json={'week_start':'2026-11-02'}).json()['plan_number']==first['plan_number']
    assert client.patch(f'/data/plans/{first["id"]}',json={'plan_number':'LP-999999'}).status_code==422
    assert client.delete(f'/data/plans/{first["id"]}').status_code==200
    second=save(client)
    assert second['plan_number']=='LP-000002'
    database.initialize()
    assert client.get('/data/plans').json()[0]['plan_number']==second['plan_number']
    assert save(client)['plan_number']=='LP-000003'

def test_existing_plan_backfill_preserves_data(client):
    first=save(client)
    with database.connect() as c:
        c.execute('UPDATE plans SET plan_number=NULL WHERE id=?',(first['id'],))
    database.initialize()
    migrated=client.get('/data/plans').json()[0]
    assert migrated['id']==first['id'] and migrated['content']==first['content']
    assert migrated['plan_number']=='LP-000002'
    database.initialize()
    assert client.get('/data/plans').json()[0]['plan_number']==migrated['plan_number']
