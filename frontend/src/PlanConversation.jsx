import React, {useEffect, useRef, useState} from 'react';

export default function PlanConversation({planId, request}) {
  const [result, setResult] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const active = useRef(0);
  const loading = useRef(false);
  useEffect(() => () => {active.current++;}, []);
  async function load() {
    if (loading.current) return;
    const version = active.current;
    loading.current = true; setBusy(true); setError('');
    try {
      const data = await request(`/plans/${planId}/conversation`, undefined, 'GET');
      if (active.current === version) setResult(data);
    } catch (e) {
      if (active.current === version) setError(e.message);
    } finally {
      if (active.current === version) {loading.current = false; setBusy(false);}
    }
  }
  const snapshot = result?.snapshot;
  return <details className="plan-conversation" onToggle={e => {if (e.currentTarget.open && !result && !error) load();}}>
    <summary>查看原始 AI 對話</summary>
    {busy && <p role="status">正在讀取原始對話…</p>}
    {error && <div className="error" role="alert">{error}<button className="ghost" disabled={busy} onClick={load}>重新讀取</button></div>}
    {result && !snapshot && <p>{result.message}</p>}
    {snapshot && <>
      <p className="plan-conversation-meta">原對話週起始日：{snapshot.week_start} · 產生時間：{new Date(snapshot.generated_at).toLocaleString('zh-TW')} · {snapshot.source}</p>
      <p className="plan-conversation-description">這是產生此計畫時保存的對話；後續聊天或開始新對話不會改變此紀錄。</p>
      {snapshot.summary && <div className="plan-conversation-summary"><b>當時的需求摘要</b><p>{snapshot.summary}</p></div>}
      <ol className="plan-conversation-messages" aria-label="此計畫的原始對話">{snapshot.messages.map((message, index) => <li className={'chat-bubble ' + message.role} key={index}>
        <b>{message.role === 'user' ? '你' : '規劃助理'}</b><p>{message.content}</p>
      </li>)}</ol>
    </>}
  </details>;
}
