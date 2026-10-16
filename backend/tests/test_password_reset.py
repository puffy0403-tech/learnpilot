import httpx
import pytest
from fastapi.testclient import TestClient
import database
import password_reset as reset
from main import app


@pytest.fixture
def recovery(tmp_path, monkeypatch):
    monkeypatch.setattr(database, 'DB_PATH', tmp_path / 'reset.db')
    database.initialize()
    monkeypatch.setenv('RESEND_API_KEY', 'test-mail-key')
    monkeypatch.setenv('RESET_EMAIL_FROM', 'LearnPilot <noreply@example.test>')
    monkeypatch.setenv('PASSWORD_RESET_URL', 'https://learn.example.test/')
    sent = []
    monkeypatch.setattr(reset, 'deliver_reset', lambda email, token, settings: sent.append((email, token)) or True)
    client = TestClient(app)
    assert client.post('/auth/register', json={'email': 'owner@example.test', 'password': 'original-password'}).status_code == 200
    return client, sent


def issue(client):
    return client.post('/auth/forgot-password', json={'email': ' OWNER@example.test '})


def test_reset_single_use_revokes_sessions_and_preserves_data(recovery):
    client, sent = recovery
    client.post('/data/goals', json={'subject': '英文', 'weekly_hours': 7})
    other_session = TestClient(app)
    other_session.post('/auth/login', json={'email': 'owner@example.test', 'password': 'original-password'})
    response = issue(client)
    assert response.status_code == 200
    token = sent[0][1]
    assert token not in response.text
    with database.connect() as c:
        row = c.execute('SELECT * FROM password_resets').fetchone()
        assert row['token_hash'] == database.token_hash(token)
        assert token != row['token_hash']
    response = client.post('/auth/reset-password', json={'token': token, 'password': 'replacement-password'})
    assert response.status_code == 200
    assert client.get('/auth/session').status_code == 401
    assert other_session.get('/auth/session').status_code == 401
    assert client.post('/auth/reset-password', json={'token': token, 'password': 'reuse-password'}).status_code == 400
    assert client.post('/auth/login', json={'email': 'owner@example.test', 'password': 'original-password'}).status_code == 401
    assert client.post('/auth/login', json={'email': 'owner@example.test', 'password': 'replacement-password'}).status_code == 200
    assert len(client.get('/data/goals').json()) == 1


def test_unknown_email_same_response_and_no_token(recovery):
    client, sent = recovery
    unknown = client.post('/auth/forgot-password', json={'email': 'unknown@example.test'})
    with database.connect() as c:
        c.execute('DELETE FROM reset_requests')
    known = issue(client)
    assert known.json() == unknown.json()
    assert len(sent) == 1
    with database.connect() as c:
        assert c.execute('SELECT count(*) FROM password_resets').fetchone()[0] == 1


def test_expired_invalid_and_short_password_rejected(recovery):
    client, sent = recovery
    issue(client)
    token = sent[0][1]
    assert client.post('/auth/reset-password', json={'token': token, 'password': 'short'}).status_code == 422
    assert client.post('/auth/reset-password', json={'token': 'x' * 43, 'password': 'new-password'}).status_code == 400
    with database.connect() as c:
        c.execute('UPDATE password_resets SET expires=0')
    assert client.post('/auth/reset-password', json={'token': token, 'password': 'new-password'}).status_code == 400
    assert client.get('/auth/session').status_code == 200


def test_resend_throttled_and_all_links_revoked_on_success(recovery):
    client, sent = recovery
    issue(client); issue(client)
    assert len(sent) == 1
    with database.connect() as c:
        c.execute('DELETE FROM reset_requests')
    issue(client)
    assert len(sent) == 2
    assert client.post('/auth/reset-password', json={'token': sent[1][1], 'password': 'new-password'}).status_code == 200
    assert client.post('/auth/reset-password', json={'token': sent[0][1], 'password': 'another-password'}).status_code == 400


def test_missing_mail_configuration_is_explicit(recovery, monkeypatch):
    client, sent = recovery
    monkeypatch.delenv('RESEND_API_KEY')
    assert issue(client).status_code == 503
    assert not sent


def test_delivery_failure_removes_unusable_token(recovery, monkeypatch):
    client, sent = recovery
    monkeypatch.setattr(reset, 'deliver_reset', lambda *args: False)
    response = issue(client)
    assert response.status_code == 200
    with database.connect() as c:
        assert c.execute('SELECT count(*) FROM password_resets').fetchone()[0] == 0


@pytest.mark.parametrize('url', ['http://example.test/', 'https://example.test/#bad', 'https://user:pass@example.test/', 'javascript:alert(1)'])
def test_unsafe_reset_url_rejected(recovery, monkeypatch, url):
    monkeypatch.setenv('PASSWORD_RESET_URL', url)
    assert issue(recovery[0]).status_code == 503


def test_email_transport_uses_fixed_https_destination_and_fragment(monkeypatch):
    def handler(request):
        import json
        assert str(request.url) == 'https://api.resend.com/emails'
        data = json.loads(request.content)
        assert data['to'] == ['owner@example.test']
        assert 'https://learn.example.test/#reset_token=one-time-token' in data['text']
        return httpx.Response(200, json={'id': 'test-message'})
    original = httpx.Client
    monkeypatch.setattr(httpx, 'Client', lambda **kwargs: original(transport=httpx.MockTransport(handler), **kwargs))
    assert reset.deliver_reset('owner@example.test', 'one-time-token', ('test-key', 'noreply@example.test', 'https://learn.example.test/'))
