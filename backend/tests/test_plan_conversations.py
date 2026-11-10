import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

import database
import chat_planner as chat
from main import app

WEEK = '2026-10-26'


@pytest.fixture
def conversations(tmp_path, monkeypatch):
    monkeypatch.setattr(database, 'DB_PATH', tmp_path / 'conversations.db')
    database.initialize()
    a, b = TestClient(app), TestClient(app)
    for client, email in ((a, 'a@example.test'), (b, 'b@example.test')):
        assert client.post('/auth/register', json={'email': email, 'password': 'test-password'}).status_code == 200
    async def fake(instructions, messages, output_type=None):
        if output_type is chat.ChatReply:
            return chat.ChatReply(reply='已確認需求：' + messages[-1]['content'], summary=messages[-1]['content'], ready=True), 'Mock AI'
        return chat.Draft(summary='一小時英文', assumptions=['依照對話'], questions=[],
            windows=[chat.Window(date=WEEK, start_time='08:00', end_time='10:00')],
            additional_fixed_items=[], tasks=[chat.Task(subject='英文', content='閱讀與檢核', minutes=60, date=None, start_time=None, deadline=None)]), 'Mock AI · model'
    monkeypatch.setattr(chat, 'ask_ai', fake)
    return a, b


def generate(client, message):
    state = client.get('/planning-chat', params={'week_start': WEEK}).json()
    response = client.post('/planning-chat/message', json={'week_start': WEEK, 'revision': state['revision'], 'message': message})
    assert response.status_code == 200, response.text
    messages = response.json()['messages']
    draft = client.post('/planning-chat/generate', json={'week_start': WEEK, 'revision': response.json()['revision']})
    assert draft.status_code == 200, draft.text
    return draft.json(), messages


def save(client, draft):
    payload = client.post('/plans/serialize', json={'week_start': WEEK, 'items': draft['items'], 'notes': draft['notes'], 'availability_windows': draft['availability_windows']}).json()
    response = client.post('/data/plans', json={**payload, 'chat_snapshot_id': draft['chat_snapshot_id']})
    assert response.status_code == 200, response.text
    return response.json()


def test_each_plan_keeps_its_own_original_conversation_after_reset(conversations):
    a, _ = conversations
    first, first_messages = generate(a, '第一份需求：英文閱讀')
    # Preserve the generation-time snapshot even if saving happens after reset.
    a.post('/planning-chat/reset', json={'week_start': WEEK})
    second, second_messages = generate(a, '第二份需求：準備考試')
    one, two = save(a, first), save(a, second)
    assert one['id'] != two['id']
    assert one['chat_snapshot_id'] != two['chat_snapshot_id']
    for plan, expected in ((one, first_messages), (two, second_messages)):
        snapshot = a.get(f"/plans/{plan['id']}/conversation").json()['snapshot']
        assert snapshot['messages'] == expected
        assert snapshot['source'] == 'Mock AI · model'
        assert snapshot['generated_at']
        assert snapshot['week_start'] == WEEK
    a.post('/planning-chat/reset', json={'week_start': WEEK})
    assert a.get(f"/plans/{one['id']}/conversation").json()['snapshot']['messages'] == first_messages
    fresh = TestClient(app)
    fresh.post('/auth/login', json={'email': 'a@example.test', 'password': 'test-password'})
    assert fresh.get(f"/plans/{two['id']}/conversation").json()['snapshot']['messages'] == second_messages


def test_snapshot_is_private_and_cannot_be_replaced(conversations):
    a, b = conversations
    first, _ = generate(a, '原始需求')
    second, _ = generate(a, '後續需求')
    plan = save(a, first)
    assert b.get(f"/plans/{plan['id']}/conversation").status_code == 404
    assert TestClient(app).get(f"/plans/{plan['id']}/conversation").status_code == 401
    content = plan['content']
    assert b.post('/data/plans', json={'week_start': WEEK, 'content': content, 'chat_snapshot_id': first['chat_snapshot_id']}).status_code == 404
    for replacement in (None, second['chat_snapshot_id']):
        assert a.patch(f"/data/plans/{plan['id']}", json={'chat_snapshot_id': replacement}).status_code == 409
    updated = a.patch(f"/data/plans/{plan['id']}", json={'content': content.replace('閱讀與檢核', '調整任務'), 'original_content': content})
    assert updated.status_code == 200
    assert updated.json()['chat_snapshot_id'] == first['chat_snapshot_id']


def test_completion_and_manual_plans_preserve_correct_provenance(conversations):
    a, _ = conversations
    draft, messages = generate(a, '這份對話應保留')
    plan = save(a, draft)
    item_id = a.get(f"/plans/{plan['id']}/items").json()['items'][0]['plan_item_id']
    completed = a.patch(f'/plan-items/{item_id}/completion', json={'completed': True, 'original_content': plan['content']})
    assert completed.status_code == 200
    assert completed.json()['plan']['chat_snapshot_id'] == plan['chat_snapshot_id']
    assert a.get(f"/plans/{plan['id']}/conversation").json()['snapshot']['messages'] == messages
    manual = a.post('/data/plans', json={'week_start': WEEK, 'content': '手動計畫'}).json()
    assert a.get(f"/plans/{manual['id']}/conversation").json()['snapshot'] is None
    database.initialize()
    assert a.get(f"/plans/{plan['id']}/conversation").json()['snapshot']['messages'] == messages


def test_generation_does_not_auto_save_plan_and_failure_creates_no_snapshot(conversations, monkeypatch):
    a, _ = conversations
    draft, _ = generate(a, '先產生草稿')
    assert draft['chat_snapshot_id']
    assert a.get('/data/plans').json() == []
    with database.connect() as c:
        before = c.execute('SELECT count(*) FROM plan_chat_snapshots').fetchone()[0]
    async def fail(*args):
        raise HTTPException(503, 'AI 連線失敗')
    monkeypatch.setattr(chat, 'ask_ai', fail)
    revision = a.get('/planning-chat', params={'week_start': WEEK}).json()['revision']
    assert a.post('/planning-chat/generate', json={'week_start': WEEK, 'revision': revision}).status_code == 503
    with database.connect() as c:
        assert c.execute('SELECT count(*) FROM plan_chat_snapshots').fetchone()[0] == before


def test_reset_during_generation_rejects_stale_snapshot(conversations, monkeypatch):
    a, _ = conversations
    _, _ = generate(a, '原本需求')
    old = chat.ask_ai
    async def race(*args):
        with database.connect() as c:
            c.execute('UPDATE planning_chats SET revision=revision+1')
        return await old(*args)
    monkeypatch.setattr(chat, 'ask_ai', race)
    state = a.get('/planning-chat', params={'week_start': WEEK}).json()
    with database.connect() as c:
        before = c.execute('SELECT count(*) FROM plan_chat_snapshots').fetchone()[0]
    assert a.post('/planning-chat/generate', json={'week_start': WEEK, 'revision': state['revision']}).status_code == 409
    with database.connect() as c:
        assert c.execute('SELECT count(*) FROM plan_chat_snapshots').fetchone()[0] == before


def test_search_saved_plans_by_original_dialogue_and_account(conversations):
    a, b = conversations
    draft, original = generate(a, '特殊需求：只在晚餐後練習發音，保留100%_彈性')
    first = save(a, draft)
    assert '晚餐後練習發音' not in first['content']
    other_draft, _ = generate(b, '特殊需求：只在晚餐後練習發音')
    other = save(b, other_draft)
    a.post('/planning-chat/reset', json={'week_start': WEEK})
    later, _ = generate(a, '新的需求：閱讀文章')
    second = save(a, later)
    assert a.get('/plans/search', params={'q': '晚餐後練習發音'}).json()['plan_ids'] == [first['id']]
    assert b.get('/plans/search', params={'q': '晚餐後練習發音'}).json()['plan_ids'] == [other['id']]
    assert a.get('/plans/search', params={'q': '100%_'}).json()['plan_ids'] == [first['id']]
    assert a.get('/plans/search', params={'q': first['plan_number'].lower()}).json()['plan_ids'] == [first['id']]
    assert a.get('/plans/search', params={'q': '完全不存在'}).json()['plan_ids'] == []
    assert a.get('/plans/search').json()['plan_ids'] == [second['id'], first['id']]
    assert TestClient(app).get('/plans/search').status_code == 401
    assert a.get('/plans/search', params={'q': 'x' * 201}).status_code == 422
    before = a.get(f'/plans/{first["id"]}/conversation').json()
    assert before['snapshot']['messages'] == original
    edited = a.patch(f'/data/plans/{first["id"]}', json={'selected_at': '2026-11-10T12:00:00Z'})
    assert edited.status_code == 200
    assert a.get(f'/plans/{first["id"]}/conversation').json() == before
    assert a.delete(f'/data/plans/{first["id"]}').status_code == 200
    assert a.get('/plans/search', params={'q': '晚餐後練習發音'}).json()['plan_ids'] == []


def test_search_manual_plans_without_snapshot(conversations):
    a, _ = conversations
    plan = a.post('/data/plans', json={'week_start': WEEK, 'content': '手動建立的英文複習'}).json()
    assert a.get('/plans/search', params={'q': '手動建立'}).json()['plan_ids'] == [plan['id']]
    assert a.get(f'/plans/{plan["id"]}/conversation').json()['snapshot'] is None


def test_resume_copies_snapshot_then_continues_into_new_plan(conversations):
    a, b = conversations
    draft, messages = generate(a, '原始需求：英文閱讀一小時')
    original = save(a, draft)
    snapshot = a.get(f'/plans/{original["id"]}/conversation').json()
    revision = a.get('/planning-chat', params={'week_start': WEEK}).json()['revision']
    endpoint = f'/plans/{original["id"]}/conversation/resume'
    assert b.post(endpoint, json={'revision': revision}).status_code == 404
    assert TestClient(app).post(endpoint, json={'revision': revision}).status_code == 401
    resumed = a.post(endpoint, json={'revision': revision})
    assert resumed.status_code == 200, resumed.text
    assert resumed.json()['week_start'] == WEEK
    current = a.get('/planning-chat', params={'week_start': WEEK}).json()
    assert current['messages'] == messages
    assert current['summary'] == snapshot['snapshot']['summary']
    assert current['revision'] == revision + 1
    assert current['inherited_messages'] == len(messages)
    assert a.post(endpoint, json={'revision': revision}).status_code == 409
    response = a.post('/planning-chat/message', json={'week_start': WEEK, 'revision': current['revision'], 'message': '新增需求：改練聽力'})
    assert response.status_code == 200
    assert response.json()['messages'][:len(messages)] == messages
    assert response.json()['messages'][-2]['content'] == '新增需求：改練聽力'
    next_draft = a.post('/planning-chat/generate', json={'week_start': WEEK, 'revision': response.json()['revision']})
    assert next_draft.status_code == 200, next_draft.text
    new_plan = save(a, next_draft.json())
    assert new_plan['id'] != original['id']
    assert new_plan['chat_snapshot_id'] != original['chat_snapshot_id']
    assert a.get(f'/plans/{original["id"]}/conversation').json() == snapshot
    assert a.get('/data/plans').json()[1] == original
    assert a.get(f'/plans/{new_plan["id"]}/conversation').json()['snapshot']['messages'] == response.json()['messages']


def test_resume_settings_no_snapshot_and_round_limit(conversations):
    import json
    a, _ = conversations
    draft, _ = generate(a, '保留英文閱讀需求')
    original = save(a, draft)
    payload = a.post('/plans/serialize', json={'week_start': WEEK, 'items': [*draft['items'], {'kind': 'todo', 'date': WEEK, 'start_time': '12:00', 'minutes': 60, 'subject': '午餐', 'content': '吃飯'}], 'daily_starts': {'0': '09:00'}}).json()
    assert a.patch(f'/data/plans/{original["id"]}', json=payload).status_code == 200
    # Canonical saved content contains old item identities; resumed drafts must not reuse them.
    current_plan = a.get('/data/plans').json()[0]
    item_id = a.get(f'/plans/{original["id"]}/items').json()['items'][0]['plan_item_id']
    assert a.patch(f'/plan-items/{item_id}/completion', json={'completed': True, 'original_content': current_plan['content']}).status_code == 200
    # A full-length historical conversation still permits new rounds after resume.
    with database.connect() as c:
        messages = [{'role': 'user' if i % 2 == 0 else 'assistant', 'content': f'歷史訊息 {i}'} for i in range(60)]
        c.execute('UPDATE plan_chat_snapshots SET messages=? WHERE id=?', (json.dumps(messages), original['chat_snapshot_id']))
    revision = a.get('/planning-chat', params={'week_start': WEEK}).json()['revision']
    result = a.post(f'/plans/{original["id"]}/conversation/resume', json={'revision': revision})
    assert result.status_code == 200
    assert result.json()['daily_starts'] == {'0': '09:00'}
    assert result.json()['fixed_items'][0]['subject'] == '午餐'
    assert 'plan_item_id' not in result.json()['fixed_items'][0]
    current = a.get('/planning-chat', params={'week_start': WEEK}).json()
    sent = a.post('/planning-chat/message', json={'week_start': WEEK, 'revision': current['revision'], 'message': '接續新需求'})
    assert sent.status_code == 200
    assert len(sent.json()['messages']) == 62
    reset = a.post('/planning-chat/reset', json={'week_start': WEEK}).json()
    assert reset['inherited_messages'] == 0
    manual = a.post('/data/plans', json={'week_start': WEEK, 'content': '手動計畫'}).json()
    assert a.post(f'/plans/{manual["id"]}/conversation/resume', json={'revision': reset['revision']}).status_code == 422
    assert a.get('/planning-chat', params={'week_start': WEEK}).json() == {**reset, 'ai': a.get('/planning-chat', params={'week_start': WEEK}).json()['ai']}
