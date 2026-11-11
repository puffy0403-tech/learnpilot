import React,{useEffect,useState} from 'react';
import {Calendar} from './features.jsx';
import StudyLogHistory from './StudyLogHistory.jsx';
import PlanConversation from './PlanConversation.jsx';
import {FeedbackSummary,understandingLabels} from './LearningFeedback.jsx';

export function SavedReports({reports,collapsible=false}){
 const [query,Q]=useState(''),[mode,M]=useState(''),[from,F]=useState(''),[to,T]=useState('');
 const invalid=from&&to&&from>to;
 const found=invalid?[]:reports.filter(r=>(!mode||r.mode===mode)&&(!from||r.period_end>=from)&&(!to||r.period_start<=to)&&(!query.trim()||`${r.title}\n${r.content}`.toLocaleLowerCase().includes(query.trim().toLocaleLowerCase())));
 const Wrapper=collapsible?'details':'div';
 return <section><Wrapper className={collapsible?'personal-archive-group':undefined}>{collapsible?<summary>已儲存的學習報告（{reports.length} 份）</summary>:<h2>已儲存的學習報告</h2>}<div className="history-filters"><label>報告類型<select value={mode} onChange={e=>M(e.target.value)}><option value="">全部</option><option value="week">週報</option><option value="month">月報</option></select></label><label>起始日期<input type="date" value={from} onChange={e=>F(e.target.value)}/></label><label>結束日期<input type="date" value={to} onChange={e=>T(e.target.value)}/></label><label>搜尋報告<input type="search" value={query} onChange={e=>Q(e.target.value)} placeholder="科目、日期或報告內容"/></label><button className="ghost" onClick={()=>{Q('');M('');F('');T('')}}>清除篩選</button></div>{invalid?<p className="error" role="alert">起始日期不可晚於結束日期。</p>:<p role="status">找到 {found.length} 份報告</p>}{!invalid&&!found.length&&<p>尚無符合條件的報告；請先到學習報告頁儲存。</p>}{found.map(r=><details key={r.id}><summary>{r.title} · 儲存時間 {r.created_at}（UTC）</summary><pre>{r.content}</pre><details><summary>儲存當時的學習筆記</summary>{JSON.parse(r.snapshot).logs.map(l=><p key={l.id}>{l.study_date} · {l.subject} · {l.minutes} 分鐘：{l.note||'無筆記'}{l.feedback&&<span> · 主題：{l.feedback.topic||'未填'} · 理解程度：{understandingLabels[l.feedback.understanding]||'未填'} · 困難點：{l.feedback.difficulty||'未填'}</span>}</p>)}</details><button className="ghost" onClick={()=>{const url=URL.createObjectURL(new Blob([r.content],{type:'text/plain;charset=utf-8'}));const a=document.createElement('a');a.href=url;a.download=`LearnPilot-${r.mode}-${r.period_start}.txt`;a.click();URL.revokeObjectURL(url)}}>下載已儲存報告</button></details>)}</Wrapper></section>
}
function ArchiveCalendar({plan,request,actionBusy,onEdit,onShow,onDelete,selectedPlanId,onContinue}){
 const [result,R]=useState(null),[error,E]=useState(''),[busy,B]=useState(false);
 async function load(){if(result||busy)return;B(true);E('');try{R(await request(`/plans/${plan.id}/items`,undefined,'GET'))}catch(e){E(e.message)}finally{B(false)}}
 return <article><h3>{plan.week_start} 學習計畫 · 編號 {plan.plan_number}{selectedPlanId===plan.id?' · 目前顯示':''}</h3><div className="actions"><button disabled={actionBusy} onClick={()=>onEdit(plan)}>編輯</button><button className="ghost" disabled={actionBusy} onClick={()=>onShow(plan)}>顯示於日曆</button><button className="danger" disabled={actionBusy} onClick={()=>onDelete(plan)}>刪除</button></div><PlanConversation planId={plan.id} request={request} onContinue={onContinue} continuationBusy={actionBusy}/><button className="ghost" disabled={busy} onClick={()=>result?R(null):load()}>{busy?'載入中…':result?'收合日曆':'查看每週日曆'}</button>{error&&<p className="error" role="alert">{error}</p>}{result&&<Calendar rows={result.items} start={plan.week_start}/>}</article>
}
export default function PersonalArchive({user,plans,logs,reports,request,busy=false,onEdit,onShow,onDelete,selectedPlanId,onContinue}){
 const [week,W]=useState(''),[query,Q]=useState('');
 const [matches,SM]=useState(null),[searching,SB]=useState(false),[searchError,SE]=useState('');
 useEffect(()=>{
   let active=true;
   const term=query.trim();SM(null);SE('');
   if(!term){SB(false);return}
   SB(true);
   const timer=setTimeout(async()=>{
     try{const result=await request('/plans/search?q='+encodeURIComponent(term),undefined,'GET');if(active)SM(result.plan_ids)}
     catch(e){if(active)SE(e.message)}
     finally{if(active)SB(false)}
   },250);
   return()=>{active=false;clearTimeout(timer)};
 },[query,plans,request]);
 const found=plans.filter(p=>(!week||(week>=p.week_start&&week<=(()=>{const end=new Date(p.week_start+'T00:00:00');end.setDate(end.getDate()+6);return `${end.getFullYear()}-${String(end.getMonth()+1).padStart(2,'0')}-${String(end.getDate()).padStart(2,'0')}`})()))&&(!query.trim()||matches?.includes(p.id)));
 return <><section><details className="personal-archive-group"><summary>個人的每週學習日曆（{plans.length} 份）</summary><div className="history-filters"><label>選擇週內日期<input type="date" value={week} onChange={e=>W(e.target.value)}/></label><label>搜尋計畫<input type="search" value={query} onChange={e=>Q(e.target.value)} maxLength="200" placeholder="計畫編號、科目、日期或原始 AI 對話"/></label><button className="ghost" onClick={()=>{W('');Q('')}}>清除篩選</button></div><p className="learning-data-hint">可搜尋計畫內容與產生當時的 AI 對話；展開下方「查看原始 AI 對話」可閱讀完整紀錄。</p>{searchError&&<p className="error" role="alert">{searchError}</p>}<p role="status">{searching?'正在查找計畫與 AI 對話…':`找到 ${found.length} 份計畫`}</p>{!searching&&!searchError&&!found.length&&<p>尚無符合條件的學習計畫。</p>}{found.map(p=><ArchiveCalendar key={`${p.id}-${p.content}`} plan={p} request={request} actionBusy={busy} onEdit={onEdit} onShow={onShow} onDelete={onDelete} selectedPlanId={selectedPlanId} onContinue={onContinue}/>)}</details></section><section><details className="personal-archive-group"><summary>已完成的學習紀錄（{logs.length} 筆）</summary><p>包含手動記錄的學習成果，以及勾選計畫完成後自動建立的紀錄。</p><StudyLogHistory user={user} logs={logs} renderLog={l=><article key={l.id}><strong>{l.study_date} · {l.subject} · {l.minutes} 分鐘</strong><p>{l.note||'無筆記'}</p><FeedbackSummary log={l}/></article>}/></details></section><SavedReports reports={reports} collapsible/></>
}
