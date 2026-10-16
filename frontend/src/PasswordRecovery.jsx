import React, {useState} from 'react';

export function consumeResetToken() {
  const params = new URLSearchParams(window.location.hash.slice(1));
  const token = params.get('reset_token') || '';
  if (params.has('reset_token')) {
    params.delete('reset_token');
    const hash = params.toString();
    window.history.replaceState(null, '', window.location.pathname + window.location.search + (hash ? '#' + hash : ''));
  }
  return token;
}

export default function PasswordRecovery({token, request, onBack, onReset}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');
  const [complete, setComplete] = useState(false);
  const [resetMode, setResetMode] = useState(Boolean(token));

  async function submit(e) {
    e.preventDefault();
    const fields = new FormData(e.currentTarget);
    setError(''); setMessage('');
    if (resetMode && fields.get('password') !== fields.get('confirm')) {
      setError('兩次輸入的密碼不一致');
      return;
    }
    setBusy(true);
    try {
      const result = resetMode
        ? await request('/auth/reset-password', {token, password: fields.get('password')})
        : await request('/auth/forgot-password', {email: fields.get('email')});
      setMessage(result.message);
      if (resetMode) {setComplete(true); onReset();}
    } catch (e) {setError(e.message);}
    finally {setBusy(false);}
  }

  return <main className="login">
    <img src="/logo.png" alt="LearnPilot"/>
    <h1>{resetMode ? '重設密碼' : '忘記密碼'}</h1>
    {!complete && <>
      <p>{resetMode ? '請設定至少 6 個字元的新密碼。' : '輸入註冊的 Email，我們將寄送 30 分鐘內有效的重設連結。'}</p>
      <form onSubmit={submit}>
        {resetMode ? <>
          <label>新密碼<input name="password" type="password" required minLength="6" maxLength="256" autoComplete="new-password" disabled={busy}/></label>
          <label>確認新密碼<input name="confirm" type="password" required minLength="6" maxLength="256" autoComplete="new-password" disabled={busy}/></label>
        </> : <label>Email<input name="email" type="email" required maxLength="254" autoComplete="email" disabled={busy}/></label>}
        <button disabled={busy}>{busy ? '處理中…' : resetMode ? '儲存新密碼' : '寄送重設連結'}</button>
      </form>
    </>}
    {error && <p className="error" role="alert">{error}</p>}
    {message && <p className="success" role="status">{message}</p>}
    {!resetMode && <p className="recovery-help">最近重新下載過專案？原帳號保存在原本電腦的資料庫。若未收到信，請確認使用原資料；可先關閉後端，再執行專案中的「還原原本帳號資料.bat」選取舊資料庫。只有程式檔無法還原帳號。</p>}
    {resetMode && !complete && <button className="ghost" disabled={busy} onClick={() => {setResetMode(false); setError(''); setMessage('');}}>重新申請連結</button>}
    <button className="ghost" disabled={busy} onClick={onBack}>返回登入</button>
  </main>;
}
