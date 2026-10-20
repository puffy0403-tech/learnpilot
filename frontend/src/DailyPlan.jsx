import React from 'react';

const weekdays = ['週日', '週一', '週二', '週三', '週四', '週五', '週六'];
const kindOf = item => item.kind || ({'保留空白': 'blocked', '固定待辦': 'todo'}[item.subject]) || 'study';

export default function DailyPlan({rows = [], notes = ''}) {
  const days = [...new Set(rows.map(row => row.date))].sort();
  return <div className="daily-plan" aria-label="按日期分組的學習計畫">
    {!days.length && <p className="daily-plan-empty">尚未安排學習項目。</p>}
    {days.map(day => {
      const items = rows.filter(row => row.date === day).sort((a, b) => (a.start_time || '08:00').localeCompare(b.start_time || '08:00'));
      const minutes = items.filter(item => kindOf(item) === 'study').reduce((sum, item) => sum + Number(item.minutes || 0), 0);
      return <article className="daily-plan-day" key={day}>
        <header className="daily-plan-heading">
          <div><span className="daily-plan-weekday">{weekdays[new Date(day + 'T00:00:00').getDay()] || '日期未設定'}</span><h3>{day || '日期未設定'}</h3></div>
          <span className="daily-plan-total">計畫讀書 {minutes} 分鐘</span>
        </header>
        <div className="daily-plan-items">{items.map((item, index) => {
          const kind = kindOf(item);
          const complete = kind === 'study' && item.completed === true;
          return <div className={'daily-plan-item ' + kind + (complete ? ' completed' : '')} key={index}>
            <div className="daily-plan-item-heading">
              <span className="daily-plan-time">{item.start_time || '08:00'}<small>{item.minutes} 分鐘</small></span>
              <div><span className="daily-plan-kind">{complete ? '✓ 已完成' : {study: '讀書計畫', blocked: '保留空白', todo: '固定待辦'}[kind]}</span><h4>{item.subject}</h4></div>
            </div>
            <p className="daily-plan-content">{item.content || '尚未填寫詳細內容。'}</p>
          </div>;
        })}</div>
      </article>;
    })}
    {notes.trim() && <div className="daily-plan-notes"><h3>分析與調整建議</h3><p>{notes}</p></div>}
  </div>;
}
