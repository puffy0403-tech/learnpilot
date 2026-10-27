import React, {useState} from 'react';

export default function StudyLogHistory({user, logs, renderLog}) {
  const [query, setQuery] = useState('');
  const [subject, setSubject] = useState('');
  const [from, setFrom] = useState('');
  const [to, setTo] = useState('');
  const invalid = from && to && from > to;
  const term = query.trim().toLocaleLowerCase();
  const subjects = [...new Set(logs.map(log => log.subject))].sort((a, b) => a.localeCompare(b, 'zh-TW'));
  const found = invalid ? [] : logs.filter(log => (!subject || log.subject === subject) && (!from || log.study_date >= from) && (!to || log.study_date <= to) &&
    (!term || (log.subject + '\n' + (log.note || '')).toLocaleLowerCase().includes(term)))
    .sort((a, b) => b.study_date.localeCompare(a.study_date) || b.id - a.id);
  return <div className="study-log-history">
    <div className="history-filters" aria-label="依帳號查詢學習紀錄">
      <label>使用者帳號<input value={user.email} readOnly aria-readonly="true"/></label>
      <label>科目<select value={subject} onChange={e => setSubject(e.target.value)}><option value="">全部科目</option>{subjects.map(name => <option key={name}>{name}</option>)}</select></label>
      <label>起始日期<input type="date" value={from} onChange={e => setFrom(e.target.value)}/></label>
      <label>結束日期<input type="date" value={to} onChange={e => setTo(e.target.value)}/></label>
      <label className="history-keyword">搜尋科目或筆記<input type="search" value={query} placeholder="例如：英文、觀念不熟、完成自動紀錄" onChange={e => setQuery(e.target.value)}/></label>
      <button type="button" className="ghost" onClick={() => {setQuery(''); setSubject(''); setFrom(''); setTo('');}}>清除篩選</button>
    </div>
    <p className="learning-data-hint">學習紀錄保存在目前登入帳號，包含手動新增與計畫完成紀錄。AI 規劃會參考這些紀錄與你最新的學習目標。</p>
    {invalid ? <p className="error" role="alert">起始日期不可晚於結束日期。</p> : <p role="status">找到 {found.length} 筆，共 {found.reduce((sum, log) => sum + log.minutes, 0)} 分鐘</p>}
    {!invalid && !found.length && <p>{logs.length ? '沒有符合條件的學習紀錄。' : '尚無學習紀錄。'}</p>}
    {found.map(renderLog)}
  </div>;
}
