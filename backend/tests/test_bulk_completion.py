import pytest
from fastapi.testclient import TestClient
import database
from main import app

@pytest.fixture
def setup(tmp_path, monkeypatch):
    monkeypatch.setattr(database, 'DB_PATH', tmp_path/'bulk.db')
    database.initialize()
    a,b=TestClient(app),TestClient(app)
    for client,email in [(a,'a@example.test'),(b,'b@example.test')]:
        client.post('/auth/register',json={'email':email,'password':'test-password'})
    def create(client):
        rows=[{'date':'2026-11-09','start_time':t,'subject':subject,'minutes':60,'content':'內容','kind':kind} for t,subject,kind in [('08:00','英文','study'),('10:00','數學','study'),('12:00','午餐','todo')]]
        payload=client.post('/plans/serialize',json={'week_start':'2026-11-09','items':rows}).json()
        plan=client.post('/data/plans',json=payload).json()
        items=client.get(f'/plans/{plan["id"]}/items').json()['items']
        return plan,[r['plan_item_id'] for r in items]
    plan,ids=create(a)
    foreign,foreign_ids=create(b)
    return a,b,plan,ids,foreign,foreign_ids

def patch(client,plan,ids):
    return client.patch(f'/plans/{plan["id"]}/items/completion',json={'item_ids':ids,'original_content':plan['content']})

def test_batch_completion_persists_without_duplicate_logs(setup):
    a,b,plan,ids,_,_=setup
    a.post('/data/study_logs',json={'study_date':'2026-11-09','subject':'手動紀錄','minutes':20})
    result=patch(a,plan,[ids[0],ids[1],ids[0]])
    assert result.status_code==200,result.text
    saved=result.json()
    assert [r['completed'] for r in saved['items']]==[True,True,False]
    assert len(saved['study_logs'])==3
    assert sum(r['minutes'] for r in saved['study_logs'])==140
    assert {r['plan_item_id'] for r in saved['study_logs'] if r['plan_item_id']}==set(ids[:2])
    repeated=patch(a,saved['plan'],ids[:2]).json()
    assert len(repeated['study_logs'])==3
    assert [r['completed_at'] for r in repeated['items']]==[r['completed_at'] for r in saved['items']]
    database.initialize()
    assert [r['completed'] for r in a.get(f'/plans/{plan["id"]}/items').json()['items']]==[True,True,False]
    assert b.get('/data/study_logs').json()==[]

@pytest.mark.parametrize('bad', ['foreign','todo','missing','fraction'])
def test_invalid_item_rolls_back_entire_batch(setup,bad):
    a,_,plan,ids,_,foreign_ids=setup
    other={'foreign':foreign_ids[0],'todo':ids[2],'missing':99999,'fraction':ids[1]}[bad]
    if bad=='fraction':
        with database.connect() as c:
            c.execute('UPDATE plan_items SET planned_minutes=30.5 WHERE id=?',(other,))
    response=patch(a,plan,[ids[0],other])
    assert response.status_code in (404,422)
    assert a.get('/data/study_logs').json()==[]
    assert not any(r['completed'] for r in a.get(f'/plans/{plan["id"]}/items').json()['items'])
    assert a.get('/data/plans').json()[0]['content']==plan['content']

def test_stale_request_ownership_and_validation(setup):
    a,b,plan,ids,foreign,foreign_ids=setup
    assert patch(b,plan,ids[:2]).status_code==404
    assert patch(a,foreign,foreign_ids[:2]).status_code==404
    assert patch(TestClient(app),plan,ids[:2]).status_code==401
    for invalid in ([],[True],[-1],['1']):
        assert patch(a,plan,invalid).status_code==422
    saved=patch(a,plan,[ids[0]]).json()
    assert patch(a,plan,[ids[1]]).status_code==409
    assert len(a.get('/data/study_logs').json())==1
    assert saved['plan']['content']!=plan['content']
