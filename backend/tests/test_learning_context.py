import json
from datetime import date

import pytest
from fastapi.testclient import TestClient

import database
import learning_context as learning
import chat_planner as chat
import ai_service
from main import app


@pytest.fixture
def accounts(tmp_path, monkeypatch):
    monkeypatch.setattr(database, 'DB_PATH', tmp_path / 'learning.db')
    monkeypatch.setattr(learning, 'current_date', lambda: date(2026, 10, 27))
    database.initialize()
    a, b = TestClient(app), TestClient(app)
    ids = []
    for client, email in ((a, 'a@example.test'), (b, 'b@example.test')):
        ids.append(client.post('/auth/register', json={'email': email, 'password': 'test-password'}).json()['user']['id'])
    a.post('/data/goals', json={'subject': '英文', 'weekly_hours': 2, 'target_score': 70, 'target_date': '2026-11-01'})
    a.post('/data/goals', json={'subject': '英文', 'weekly_hours': 4, 'target_score': 90, 'target_date': '2026-10-31'})
    b.post('/data/goals', json={'subject': '他人私密目標', 'weekly_hours': 8, 'target_score': 100})
    for client, subject, note in ((a, '英文', '閱讀推論題不熟，完成100%複習'), (b, '他人私密科目', '不應洩漏的筆記')):
        client.post('/data/study_logs', json={'study_date': '2026-10-26', 'subject': subject, 'minutes': 60, 'note': note})
    return a, b, ids


def test_latest_goals_complete_history_and_weekly_progress_are_account_scoped(accounts):
    a, _, ids = accounts
    for i in range(20):
        a.post('/data/study_logs', json={'study_date': '2026-10-25', 'subject': '英文', 'minutes': 10, 'note': f'練習{i}'})
    a.post('/data/study_logs', json={'study_date': '2026-12-01', 'subject': '英文', 'minutes': 999, 'note': '未來紀錄不可當成目前完成'})
    with database.connect() as c:
        basis = learning.personal_learning_context(c, ids[0], date(2026, 10, 26))
    assert len(basis['goals']) == 1
    assert basis['goals'][0]['weekly_hours'] == 4
    assert basis['goals'][0]['target_score'] == 90
    assert basis['goals'][0]['target_date'] == '2026-10-31'
    assert len(basis['recent_logs']) == 15
    assert basis['study_summary_28_days'][0]['minutes'] == 260
    assert basis['all_time_study_summary'][0]['minutes'] == 260
    assert basis['weekly_progress'][0]['completed_minutes'] == 60
    assert basis['weekly_progress'][0]['remaining_minutes'] == 180
    text = json.dumps(basis, ensure_ascii=False)
    assert '私密' not in text and '不應洩漏' not in text and '未來紀錄' not in text
    with database.connect() as c:
        future = learning.personal_learning_context(c, ids[0], date(2026, 11, 2))
    assert future['weekly_progress'][0]['remaining_minutes'] == 240


def test_user_lookup_filters_records_and_rejects_other_accounts(accounts):
    a, b, ids = accounts
    query = {'subject': '英文', 'from_date': '2026-10-26', 'to_date': '2026-10-27', 'q': '100%'}
    response = a.get(f'/users/{ids[0]}/study-logs', params=query)
    assert response.status_code == 200
    assert len(response.json()['items']) == 1
    assert response.json()['items'][0]['user_id'] == ids[0]
    assert b.get(f'/users/{ids[0]}/study-logs').status_code == 403
    assert TestClient(app).get(f'/users/{ids[0]}/study-logs').status_code == 401
    assert a.get(f'/users/{ids[0]}/study-logs', params={'from_date': '2026-10-28', 'to_date': '2026-10-26'}).status_code == 422
    assert a.get(f'/users/{ids[0]}/study-logs', params={'q': "' OR 1=1 --"}).json()['items'] == []
    assert a.get(f'/users/{ids[0]}/study-logs', params={'subject': '他人私密科目'}).json()['items'] == []
    fresh = TestClient(app)
    fresh.post('/auth/login', json={'email': 'a@example.test', 'password': 'test-password'})
    assert len(fresh.get(f'/users/{ids[0]}/study-logs').json()['items']) == 1


def test_chat_and_general_ai_receive_updated_goals_and_history(accounts, monkeypatch):
    a, _, _ = accounts
    seen = []
    async def fake_chat(instructions, messages, output_type=None):
        seen.append(instructions)
        return chat.ChatReply(reply='會依目標與弱項安排。', summary='英文', ready=True), 'Mock'
    monkeypatch.setattr(chat, 'ask_ai', fake_chat)
    assert a.post('/planning-chat/message', json={'week_start': '2026-10-26', 'message': '幫我安排', 'revision': 0}).status_code == 200
    assert 'target_score' in seen[0] and '90.0' in seen[0] and '2026-10-31' in seen[0]
    assert '閱讀推論題不熟' in seen[0] and 'study_summary_28_days' in seen[0]
    assert '他人私密' not in seen[0] and '不應洩漏' not in seen[0]
    prompts = []
    async def fake_general(instructions, messages, *args):
        prompts.append(instructions + messages[0]['content'])
        return '- 週一：英文｜1 小時｜推論題練習與訂正', 'Mock'
    monkeypatch.setattr(ai_service, 'ask_ai', fake_general)
    monkeypatch.setattr(ai_service, 'configuration', lambda: {'configured': True})
    assert a.post('/plans/generate', json={'week_start': '2026-10-26'}).status_code == 200
    a.post('/data/goals', json={'subject': '英文', 'weekly_hours': 6, 'target_score': 95, 'target_date': '2026-11-02'})
    a.post('/data/study_logs', json={'study_date': '2026-10-27', 'subject': '英文', 'minutes': 30, 'note': '新增弱項：文法'})
    assert a.post('/plans/generate', json={'week_start': '2026-10-26'}).status_code == 200
    assert '90.0' in prompts[0] and 'target_date' in prompts[0]
    assert '95.0' in prompts[1] and '新增弱項：文法' in prompts[1]
    assert '90.0' not in prompts[1]
    assert '他人私密' not in ''.join(prompts)


def test_records_from_completed_plan_are_used_in_learning_context(accounts):
    a, _, ids = accounts
    serialized = a.post('/plans/serialize', json={'week_start': '2026-10-26', 'items': [dict(date='2026-10-27', start_time='08:00', subject='英文', minutes=45, content='推論題練習')]}).json()
    plan = a.post('/data/plans', json=serialized).json()
    item_id = a.get(f"/plans/{plan['id']}/items").json()['items'][0]['plan_item_id']
    assert a.patch(f'/plan-items/{item_id}/completion', json={'completed': True, 'original_content': plan['content']}).status_code == 200
    with database.connect() as c:
        basis = learning.personal_learning_context(c, ids[0], date(2026, 10, 26))
    assert basis['weekly_progress'][0]['completed_minutes'] == 105
    assert any('推論題練習' in row['note'] for row in basis['recent_logs'])


def test_ai_chat_draft_uses_the_same_personal_goals_and_records(accounts, monkeypatch):
    a, _, _ = accounts
    captured = []
    async def fake(instructions, messages, output_type=None):
        if output_type is chat.ChatReply:
            return chat.ChatReply(reply='已確認時段', summary='英文閱讀', ready=True), 'Mock'
        captured.append(instructions)
        return chat.Draft(summary='針對英文推論題', assumptions=['參考個人目標與筆記'], questions=[],
            windows=[chat.Window(date='2026-10-26', start_time='08:00', end_time='10:00')], additional_fixed_items=[],
            tasks=[chat.Task(subject='英文', content='推論題與錯題檢核', minutes=60, date=None, start_time=None, deadline=None)]), 'Mock'
    monkeypatch.setattr(chat, 'ask_ai', fake)
    assert a.post('/planning-chat/message', json={'week_start': '2026-10-26', 'message': '請規劃英文', 'revision': 0}).status_code == 200
    result = a.post('/planning-chat/generate', json={'week_start': '2026-10-26', 'revision': 1})
    assert result.status_code == 200, result.text
    assert 'target_score' in captured[0] and '90.0' in captured[0]
    assert '閱讀推論題不熟' in captured[0] and 'completed_minutes' in captured[0]
    assert '他人私密' not in captured[0]
