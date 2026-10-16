import hashlib
import os
import secrets
import time
from urllib.parse import urlsplit

import httpx
from fastapi import APIRouter, BackgroundTasks, HTTPException, Request, Response
from pydantic import BaseModel, Field

import database

router = APIRouter()
NOTICE = '若此 Email 已註冊，你將收到重設密碼連結，請檢查收件匣與垃圾郵件。'


class ForgotPassword(BaseModel):
    email: str = Field(min_length=3, max_length=254)


class ResetPassword(BaseModel):
    token: str = Field(min_length=32, max_length=256)
    password: str = Field(min_length=6, max_length=256)


def mail_settings():
    key = os.getenv('RESEND_API_KEY', '').strip()
    sender = os.getenv('RESET_EMAIL_FROM', '').strip()
    url = os.getenv('PASSWORD_RESET_URL', '').strip()
    parsed = urlsplit(url)
    local = parsed.hostname in ('localhost', '127.0.0.1')
    if not key or not sender or not parsed.hostname or parsed.fragment or parsed.username or parsed.password or (parsed.scheme != 'https' and not (local and parsed.scheme == 'http')):
        raise HTTPException(503, '密碼重設寄信服務尚未設定，請聯絡管理者。')
    return key, sender, url


def deliver_reset(email, token, settings):
    key, sender, url = settings
    # The fragment is never sent to the frontend HTTP server or in Referer headers.
    link = f'{url}#reset_token={token}'
    try:
        with httpx.Client(timeout=15) as client:
            response = client.post('https://api.resend.com/emails', headers={'Authorization': f'Bearer {key}'}, json={
                'from': sender, 'to': [email], 'subject': 'LearnPilot 重設密碼',
                'text': f'請開啟以下連結設定新密碼（30 分鐘內有效，僅能使用一次）：\n{link}\n\n若你未提出此要求，請忽略此信。'
            })
            response.raise_for_status()
        return True
    except httpx.HTTPError:
        # Do not log provider bodies, tokens, or credentials.
        return False


def deliver_and_cleanup(email, token, settings):
    if not deliver_reset(email, token, settings):
        with database.connect() as c:
            c.execute('DELETE FROM password_resets WHERE token_hash=?', (database.token_hash(token),))


@router.post('/auth/forgot-password')
def forgot_password(p: ForgotPassword, request: Request, background_tasks: BackgroundTasks):
    settings = mail_settings()
    email = p.email.strip().lower()
    if '@' not in email:
        raise HTTPException(422, 'Email 格式有誤')
    now = int(time.time())
    # Use the actual peer, not user-supplied forwarded headers. Rate limiting is
    # persisted across workers and restarts. Unknown accounts take the same path.
    peer = request.client.host if request.client else 'unknown'
    buckets = [('email:' + email, 60), ('peer:' + peer, 10)]
    with database.connect() as c:
        c.execute('BEGIN IMMEDIATE')
        c.execute('DELETE FROM reset_requests WHERE requested<?', (now - 3600,))
        c.execute('DELETE FROM password_resets WHERE expires<=?', (now,))
        for value, interval in buckets:
            bucket = hashlib.sha256(value.encode()).hexdigest()
            row = c.execute('SELECT requested FROM reset_requests WHERE bucket=?', (bucket,)).fetchone()
            if row and row['requested'] > now - interval:
                return {'message': NOTICE}
        for value, _ in buckets:
            c.execute('INSERT OR REPLACE INTO reset_requests VALUES(?,?)', (hashlib.sha256(value.encode()).hexdigest(), now))
        user = c.execute('SELECT id FROM users WHERE email=?', (email,)).fetchone()
        token = secrets.token_urlsafe(32)
        digest = database.token_hash(token)
        if user:
            c.execute('INSERT INTO password_resets VALUES(?,?,?)', (digest, user['id'], now + 1800))
    # Send after responding, so provider latency does not reveal account existence.
    if user:
        background_tasks.add_task(deliver_and_cleanup, email, token, settings)
    # Never disclose account existence, delivery state or reset tokens.
    return {'message': NOTICE}


@router.post('/auth/reset-password')
def reset_password(p: ResetPassword, response: Response):
    digest = database.token_hash(p.token)
    with database.connect() as c:
        c.execute('BEGIN IMMEDIATE')
        row = c.execute('SELECT user_id FROM password_resets WHERE token_hash=? AND expires>?', (digest, int(time.time()))).fetchone()
        if not row:
            raise HTTPException(400, '重設連結已失效或已使用，請重新申請。')
        c.execute('UPDATE users SET password_hash=? WHERE id=?', (database.password_hash(p.password), row['user_id']))
        c.execute('DELETE FROM sessions WHERE user_id=?', (row['user_id'],))
        c.execute('DELETE FROM password_resets WHERE user_id=?', (row['user_id'],))
    response.delete_cookie('learnpilot_session', path='/')
    return {'message': '密碼已重設，請使用新密碼登入。'}
