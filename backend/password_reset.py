import hashlib
import logging
import os
import secrets
import time
from urllib.parse import urlsplit

import httpx
from fastapi import APIRouter, BackgroundTasks, HTTPException, Request, Response
from pydantic import BaseModel, Field

import database

router = APIRouter()
logger = logging.getLogger('uvicorn.error.password_reset')
NOTICE = '申請已收到。若此 Email 已註冊，我們將嘗試寄出重設連結；請檢查收件匣與垃圾郵件。若未收到，請等 60 秒後重試或聯絡管理者。'


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
        logger.info('MAIL_ACCEPTED: Resend 已接受重設信，請至 Resend Emails 確認送達狀態。')
        return True
    except httpx.HTTPStatusError as exc:
        status = exc.response.status_code
        try:
            body = exc.response.json()
            message = str(body.get('message', '')).lower() if isinstance(body, dict) else ''
        except ValueError:
            message = ''
        if 'testing emails' in message or 'own email address' in message:
            reason = 'MAIL_TEST_RECIPIENT: 測試寄件網域只能寄給 Resend 帳號 Email；其他收件人需驗證自有網域。'
        elif 'domain is not verified' in message or 'verify a domain' in message:
            reason = 'MAIL_SENDER_DOMAIN: 請在 Resend 驗證寄件網域並檢查 RESET_EMAIL_FROM。'
        elif status == 401:
            reason = 'MAIL_AUTH: 請檢查 RESEND_API_KEY 是否有效，設定後重新啟動後端。'
        elif status == 403:
            reason = 'MAIL_PERMISSION: 請檢查金鑰寄信權限、寄件網域及測試收件人限制。'
        elif status == 429:
            reason = 'MAIL_LIMIT: 寄信額度或頻率受限，請查看 Resend 用量後稍候重試。'
        else:
            reason = 'MAIL_REJECTED: 寄信服務拒絕請求，請到 Resend Logs 查看原因。'
        # Log fixed guidance only: provider error bodies may echo secrets or PII.
        logger.warning('%s HTTP %s', reason, status)
        return False
    except httpx.HTTPError:
        logger.warning('MAIL_CONNECTION: 無法連線到 Resend，請檢查網路、防火牆與 TLS 憑證。')
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
                logger.warning('MAIL_THROTTLED: 重設申請過於頻繁，請等 60 秒後重試。')
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
    else:
        logger.warning('MAIL_ACCOUNT_NOT_FOUND: 此重設申請未符合目前資料庫的帳號；不寄送郵件。請確認註冊 Email 及正在使用的資料庫。')
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
