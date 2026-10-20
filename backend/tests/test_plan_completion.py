from datetime import date

import pytest
from fastapi.testclient import TestClient

import database
from main import app
from planning import editable_plan_data, serialize_editable_plan


@pytest.fixture
def saved_plan(tmp_path, monkeypatch):
    monkeypatch.setattr(database, 'DB_PATH', tmp_path / 'completion.db')
    database.initialize()
    owner, other = TestClient(app), TestClient(app)
    for client, email in ((owner, 'owner@example.test'), (other, 'other@example.test')):
        assert client.post('/auth/register', json={'email': email, 'password': 'test-password'}).status_code == 200
    items = [
        dict(date='2026-10-19', start_time='08:00', subject='英文', minutes=60, content='閱讀', kind='study'),
        dict(date='2026-10-19', start_time='10:00', subject='英文', minutes=60, content='練習', kind='study'),
        dict(date='2026-10-19', start_time='12:00', subject='固定待辦', minutes=60, content='午餐', kind='todo'),
    ]
    payload = owner.post('/plans/serialize', json={'week_start': '2026-10-19', 'items': items, 'notes': '保留備註', 'daily_starts': {'0': '08:00'}}).json()
    plan = owner.post('/data/plans', json={**payload, 'selected_at': '2026-10-19T00:00:00Z'}).json()
    return owner, other, plan


def mark(client, plan, index=0, completed=True):
    return client.patch(f"/plans/{plan['id']}/items/{index}/completion", json={'completed': completed, 'original_content': plan['content']})


def test_complete_persists_and_can_be_undone_with_study_logs(saved_plan):
    owner, _, plan = saved_plan
    response = mark(owner, plan)
    assert response.status_code == 200
    result = response.json()
    assert result['items'][0]['completed'] is True
    assert result['items'][1].get('completed', False) is False
    assert result['plan']['selected_at'] == plan['selected_at']
    persisted = owner.get('/data/plans').json()[0]
    parsed = owner.post('/plans/parse', json=persisted).json()
    assert parsed['items'][0]['completed'] is True
    assert parsed['notes'] == '保留備註'
    assert parsed['daily_starts'] == {'0': '08:00'}
    logs = owner.get('/data/study_logs').json()
    assert len(logs) == 1
    assert logs[0]['minutes'] == 60
    assert logs[0]['study_date'] == '2026-10-19'
    assert logs[0]['subject'] == '英文'
    fresh = TestClient(app)
    assert fresh.post('/auth/login', json={'email': 'owner@example.test', 'password': 'test-password'}).status_code == 200
    restored = fresh.get('/data/plans').json()[0]
    assert mark(fresh, restored, completed=False).json()['items'][0]['completed'] is False
    assert fresh.get('/data/study_logs').json() == []


def test_completion_requires_ownership_and_login(saved_plan):
    owner, other, plan = saved_plan
    assert mark(other, plan).status_code == 404
    assert mark(TestClient(app), plan).status_code == 401
    assert owner.get('/data/plans').json()[0]['content'] == plan['content']


def test_completion_rejects_stale_plan_without_overwriting(saved_plan):
    owner, _, plan = saved_plan
    first = mark(owner, plan).json()['plan']
    assert mark(owner, plan, index=1).status_code == 409
    assert owner.get('/data/plans').json()[0]['content'] == first['content']


@pytest.mark.parametrize('index,status', [(-1, 404), (99, 404), (2, 422)])
def test_only_existing_study_items_can_be_completed(saved_plan, index, status):
    owner, _, plan = saved_plan
    assert mark(owner, plan, index=index).status_code == status
    assert owner.get('/data/plans').json()[0]['content'] == plan['content']


def test_completion_requires_boolean(saved_plan):
    owner, _, plan = saved_plan
    assert mark(owner, plan, completed='false').status_code == 422


def test_editing_and_resaving_preserves_completion(saved_plan):
    owner, _, plan = saved_plan
    updated = mark(owner, plan).json()['plan']
    parsed = owner.post('/plans/parse', json=updated).json()
    parsed['items'][0]['content'] = '新增筆記'
    serialized = owner.post('/plans/serialize', json={'week_start': plan['week_start'], **parsed}).json()
    assert owner.patch(f"/data/plans/{plan['id']}", json={**serialized, 'original_content': updated['content']}).status_code == 200
    assert owner.post('/plans/parse', json=serialized).json()['items'][0]['completed'] is True


def test_legacy_text_plan_can_be_marked(saved_plan):
    owner, _, _ = saved_plan
    plan = owner.post('/data/plans', json={'week_start': '2026-10-19', 'content': '原本的備註\n- 週一：英文｜1 小時｜閱讀'}).json()
    response = mark(owner, plan)
    assert response.status_code == 200
    parsed = owner.post('/plans/parse', json=response.json()['plan']).json()
    assert parsed['items'][0]['completed'] is True
    assert parsed['items'][0]['minutes'] == 60
    assert parsed['notes'] == '原本的備註'


def test_split_tasks_keep_completion_during_serialization():
    rows = [dict(date='2026-10-19', start_time='09:00', subject='英文', minutes=180, content='閱讀', completed=True)]
    start, content = serialize_editable_plan(rows, '備註')
    restored, _ = editable_plan_data(content, start)
    assert len(restored) == 2
    assert all(row['completed'] is True for row in restored)
    assert sum(row['minutes'] for row in restored) == 180


def test_completion_retains_availability_windows(saved_plan):
    owner, _, _ = saved_plan
    windows = [{'date': '2026-10-19', 'start_time': '08:00', 'end_time': '10:00'}]
    payload = owner.post('/plans/serialize', json={'week_start': '2026-10-19', 'items': [dict(date='2026-10-19', start_time='08:00', subject='英文', minutes=60)], 'availability_windows': windows}).json()
    plan = owner.post('/data/plans', json=payload).json()
    result = mark(owner, plan).json()
    parsed = owner.post('/plans/parse', json=result['plan']).json()
    assert parsed['availability_windows'] == windows
    assert parsed['items'][0]['completed'] is True



def test_repeated_completion_does_not_duplicate_and_manual_logs_survive(saved_plan):
    owner, _, plan = saved_plan
    manual = owner.post('/data/study_logs', json={'study_date': '2026-10-19', 'subject': '英文', 'minutes': 60, 'note': '手動紀錄'}).json()
    updated = mark(owner, plan).json()['plan']
    repeated = mark(owner, updated).json()['plan']
    assert len(owner.get('/data/study_logs').json()) == 2
    mark(owner, repeated, completed=False)
    assert owner.get('/data/study_logs').json() == [manual]


def test_uncheck_uses_stable_key_after_reordering_plan(saved_plan):
    owner, _, plan = saved_plan
    updated = mark(owner, plan).json()['plan']
    parsed = owner.post('/plans/parse', json=updated).json()
    parsed['items'][0]['start_time'] = '11:00'
    serialized = owner.post('/plans/serialize', json={'week_start': plan['week_start'], **parsed}).json()
    edited = owner.patch(f"/data/plans/{plan['id']}", json={**serialized, 'original_content': updated['content']}).json()
    items = owner.post('/plans/parse', json=edited).json()['items']
    index = next(i for i, item in enumerate(items) if item.get('completed'))
    assert index == 1
    assert mark(owner, edited, index=index, completed=False).status_code == 200
    assert owner.get('/data/study_logs').json() == []


def test_manual_deletion_of_auto_log_allows_recreation(saved_plan):
    owner, _, plan = saved_plan
    first = mark(owner, plan).json()
    log = first['study_logs'][0]
    assert owner.delete(f"/data/study_logs/{log['id']}").status_code == 200
    assert len(mark(owner, first['plan']).json()['study_logs']) == 1


def test_other_user_cannot_change_auto_logs(saved_plan):
    owner, other, plan = saved_plan
    updated = mark(owner, plan).json()['plan']
    assert mark(other, updated, completed=False).status_code == 404
    assert other.get('/data/study_logs').json() == []
    assert len(owner.get('/data/study_logs').json()) == 1
