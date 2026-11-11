import React,{useEffect,useState} from 'react';
export const understandingLabels={1:'不太理解',2:'部分理解',3:'能獨立完成',4:'能向別人解釋'};
const sourceLabel={planned:'沿用預計時間（尚未回報實際時間）',manual:'手動填寫時間',self_reported:'回報實際時間',legacy:'舊紀錄，時間來源未確認'};
export function FeedbackSummary({log}){
 const f=log.feedback;
 return <div className="feedback-summary"><p>時間來源：{sourceLabel[log.time_source]||sourceLabel.legacy} · 目前紀錄 {log.minutes} 分鐘{log.planned_minutes!=null&&` · 原預計 ${log.planned_minutes} 分鐘`}</p>{f?<><p>{f.topic&&`主題：${f.topic} · `}理解程度：{understandingLabels[f.understanding]||'尚未填寫'}</p>{f.difficulty&&<p className="feedback-difficulty">困難點：{f.difficulty}</p>}</>:<p>尚未填寫學習回饋，可到學習紀錄管理補填。</p>}</div>
}
export default function LearningFeedback({log,onSave}){
 const [actual,A]=useState(''),[level,L]=useState(''),[topic,T]=useState(''),[difficulty,D]=useState(''),[busy,B]=useState(false),[error,E]=useState(''),[message,M]=useState('');
 useEffect(()=>{const f=log.feedback;A(f?.actual_minutes??(['manual','self_reported'].includes(log.time_source)?log.minutes:''));L(f?.understanding??'');T(f?.topic||'');D(f?.difficulty||'')},[log.id,log.minutes,log.time_source,log.feedback?.updated_at]);
 async function save(e){e.preventDefault();if(busy)return;B(true);E('');M('');try{await onSave(log.id,{actual_minutes:actual===''?null:Number(actual),understanding:level===''?null:Number(level),topic,difficulty});M('學習回饋已儲存，時間與目標進度已同步更新。')}catch(e){E(e.message)}finally{B(false)}}
 return <form className="learning-feedback" onSubmit={save}><h3>學習回饋（可稍後補填）</h3><FeedbackSummary log={log}/><fieldset disabled={busy}><div className="grid"><label>學習主題<input maxLength="200" value={topic} onChange={e=>T(e.target.value)} placeholder="例如：遞迴、閱讀推論"/></label><label>理解程度<select value={level} onChange={e=>L(e.target.value)}><option value="">尚未評估</option>{Object.entries(understandingLabels).map(([key,text])=><option key={key} value={key}>{text}</option>)}</select></label><label>實際學習分鐘<input type="number" min="0" max="1440" step="1" value={actual} placeholder={log.planned_minutes!=null?`未填則沿用預計 ${log.planned_minutes} 分鐘`:'可填實際學習時間'} onChange={e=>A(e.target.value)}/></label></div><p><small>{log.planned_minutes!=null?'留空會沿用原預計時間，不會視為精確實際時間。':'未填實際分鐘時保留目前學習時間及來源。'}自評只反映理解感受，不代表測驗成績。</small></p><label>困難點<textarea maxLength="4000" value={difficulty} onChange={e=>D(e.target.value)} placeholder="例如：看得懂範例，但還不會獨立解題"/></label><button disabled={busy}>{busy?'正在儲存…':'儲存學習回饋'}</button></fieldset>{error&&<p className="error" role="alert">{error}</p>}{message&&<p className="success" role="status">{message}</p>}</form>
}
