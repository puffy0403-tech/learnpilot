import React,{useEffect,useRef,useState} from 'react';
import {Reservations} from './features.jsx';

const examples=[
 '我這週要準備英文考試，但不知道怎麼分配單字、閱讀和聽力，可以先幫我釐清嗎？',
 '我平日只有晚上19:00到21:00可以讀書，週六下午14:00到17:00有空，想安排統計和Python。',
 '我常常把讀書計畫排太滿，想先討論優先順序和每天適合安排多少時間。'
];
export function reservationError(items,start){
 const end=new Date(start+'T00:00:00');end.setDate(end.getDate()+6);
 const last=`${end.getFullYear()}-${String(end.getMonth()+1).padStart(2,'0')}-${String(end.getDate()).padStart(2,'0')}`;
 const occupied=[];
 for(let i=0;i<items.length;i++){
  const r=items[i],prefix=`第 ${i+1} 筆固定事項：`;
  if(!r.date||r.date<start||r.date>last)return prefix+'日期須在選定週的七天內。';
  if(!/^(?:[01]\d|2[0-3]):[0-5]\d$/.test(r.start_time||''))return prefix+'請填寫有效的開始時間。';
  const minutes=Number(r.minutes),begin=Number(r.start_time.slice(0,2))*60+Number(r.start_time.slice(3));
  if(!Number.isFinite(minutes)||minutes<=0||minutes>1440)return prefix+'分鐘須大於 0 且不超過 1440。';
  if(begin+minutes>1440)return prefix+'時間不可跨越午夜，請拆成兩筆。';
  if(occupied.some(x=>x.date===r.date&&begin<x.end&&x.begin<begin+minutes))return prefix+'與其他保留空白或固定待辦重疊，請調整時間。';
  occupied.push({date:r.date,begin,end:begin+minutes});
 }
 return '';
}

export default function PlanningChat({request,userId,start,setStart,fixed,setFixed,dailyStarts,onImport}){
 const [chat,setChat]=useState({messages:[],summary:'',ready:false,revision:0});
 const [reloadCount,refresh]=useState(0);
 const [config,configure]=useState(null),[text,setText]=useState(''),[pending,wait]=useState(''),[error,fail]=useState(''),[draft,setDraft]=useState(null),[loaded,load]=useState(false);
 const sequence=useRef(0),bottom=useRef(null);
 const signature=JSON.stringify({userId,start,fixed,dailyStarts});
 const current=useRef(signature);current.current=signature;
 useEffect(()=>{const id=++sequence.current;load(false);fail('');setDraft(null);setText('');setChat({messages:[],summary:'',ready:false,revision:0});configure(null);wait('');request('/planning-chat?week_start='+encodeURIComponent(start),undefined,'GET').then(r=>{if(sequence.current===id){setChat(r);configure(r.ai);load(true)}}).catch(e=>{if(sequence.current===id)fail(e.message)});return()=>{sequence.current++}},[start,userId,reloadCount]);
 useEffect(()=>{setDraft(null)},[signature]);
 useEffect(()=>{bottom.current?.scrollIntoView({block:'nearest',behavior:'smooth'})},[chat.messages.length,pending]);
 const context=()=>({week_start:start,fixed_items:fixed,fixed_items_authoritative:true,daily_starts:dailyStarts,revision:chat.revision});
 async function run(kind,fn){if(pending)return;const id=sequence.current,sig=signature;wait(kind);fail('');try{await fn(()=>sequence.current===id&&current.current===sig)}catch(e){if(sequence.current===id)fail(e.message)}finally{if(sequence.current===id)wait('')}}
 const send=e=>{e.preventDefault();if(!text.trim()||reservationError(fixed,start))return;run('正在整理你的需求…',async active=>{const r=await request('/planning-chat/message',{...context(),message:text.trim()});if(active()){setChat(r);setText('');setDraft(null)}})};
 const makeDraft=()=>{if(reservationError(fixed,start))return;return run('正在依照對話安排讀書時段…',async active=>{const r=await request('/planning-chat/generate',context());if(active())setDraft(r)})};
 const reset=()=>{if(!window.confirm('清除這一週的規劃對話？已儲存的讀書計畫會保留。'))return;run('正在開始新對話…',async active=>{const r=await request('/planning-chat/reset',context());if(active()){setChat(r);setDraft(null);setText('')}})};
 const fixedError=reservationError(fixed,start);
 const disabled=!!pending||!loaded||!config?.configured||!!fixedError;
 return <>
  <section className="planning-chat-intro"><h2>先聊一聊，再安排這一週</h2><p>告訴我你要讀什麼、希望完成什麼，以及什麼時候有空。我會先幫你釐清需求，再產生可編輯的計畫草稿。</p>
   <label>對話規劃週起始日<input type="date" value={start} disabled={!!pending} onChange={e=>{if(e.target.value)setStart(e.target.value)}}/></label>
   <p className={'chat-status '+(config?.configured?'connected':'')} role="status">{config?`${config.configured?config.provider+' · '+config.model+'｜':''}${config.message}`:'正在讀取此週對話…'}</p>
   {config&&!config.configured&&<details><summary>如何啟用 OpenAI 對話</summary><p>在 backend/.env 設定 AI_PROVIDER=openai、OPENAI_API_KEY 與 OPENAI_MODEL（例如 gpt-4.1-mini），安裝更新後的 requirements.txt，再重新啟動後端。金鑰只填在後端檔案。</p></details>}
   <details><summary>目前編輯區提供的時間設定（{fixed.length} 筆固定事項）</summary><p>每日開始時間：{['週一','週二','週三','週四','週五','週六','週日'].map((d,i)=>d+' '+(dailyStarts[String(i)]||'08:00')).join('、')}</p>{fixed.length?fixed.map((r,i)=><p key={i}>{r.kind==='blocked'?'保留空白':'固定待辦'}：{r.date} {r.start_time}，{r.minutes} 分鐘，{r.content||r.subject}</p>):<p>尚未設定固定事項；也可以在對話中告訴我。</p>}<p>固定事項可在下方直接修改，並與「AI Study Plan」同步。每日開始時間可在「AI Study Plan」修改。</p></details>
  </section>
  <section className="chat-reservation-settings"><fieldset disabled={!!pending} className="reservation-editor"><Reservations items={fixed} setItems={setFixed} start={start} title="保留空白時間與固定待辦" description="灰色為保留空白，橘色為固定待辦。新增、修改與移除會即時同步至 AI Study Plan；下次產生計畫會以這裡的最新設定為準，避開這些時段。對話中提到的固定行程也請填入此處。"/></fieldset>{fixedError?<p className="error" role="alert">{fixedError}</p>:<p className="chat-settings-sync" role="status">時間設定已同步（{fixed.length} 筆）。修改後請重新產生建議計畫，使用最新設定。</p>}</section>
  <div className="chat-layout"><section className="chat-panel"><div className="chat-heading"><h2>AI 規劃對話</h2><button className="ghost" disabled={!!pending||!loaded||!chat.messages.length} onClick={reset}>開始新對話</button></div>
   <div className="chat-messages" role="log" aria-label="規劃對話紀錄" aria-live="polite" aria-busy={!!pending}>
    <div className="chat-bubble assistant"><b>規劃助理</b><p>你這週最想完成什麼？可以先說說要讀的科目、最近的考試或作業，以及目前安排時間最困擾你的地方。</p></div>
    {chat.messages.map((m,i)=><div className={'chat-bubble '+m.role} key={i}><b>{m.role==='user'?'你':'規劃助理'}</b><p>{m.content}</p></div>)}
    {pending&&<p className="chat-pending" role="status">{pending}</p>}<div ref={bottom}/>
   </div>
   {!chat.messages.length&&<div className="chat-examples">{examples.map(x=><button key={x} className="ghost" disabled={!!pending} onClick={()=>setText(x)}>{x}</button>)}</div>}
   <form onSubmit={send}><label htmlFor="chat-message">你的讀書與時間安排需求</label><textarea id="chat-message" maxLength={3000} placeholder="例如：週二、週四19:00–21:00能讀書，英文想讀2小時，統計想讀2小時，但不知道先安排哪個。" value={text} disabled={!!pending||!loaded} onChange={e=>{setText(e.target.value);setDraft(null)}}/><div className="chat-send"><small>{text.length}/3000；對話按帳號與週次保留。</small><button disabled={disabled||!text.trim()}>傳送</button></div></form>
   {error&&<p className="error" role="alert">{error}<button type="button" className="ghost" disabled={!!pending} onClick={()=>refresh(n=>n+1)}>重新讀取對話</button></p>}
  </section>
  <section className="chat-summary"><h2>需求整理</h2><p className="chat-summary-text">{chat.summary||'開始對話後，這裡會整理你的目標、優先順序、可用時間與待釐清事項。'}</p><p>{chat.ready?'需求已初步釐清，可以產生草稿，也可以繼續補充。':'請先回答助理的問題，釐清讀書目標與可用時間。'}</p><button disabled={disabled||!chat.ready||!!text.trim()} onClick={makeDraft}>根據對話產生建議計畫</button>{text.trim()&&<p><small>請先傳送輸入中的需求，再產生草稿。</small></p>}<p><small>產生後可先檢查安排，再匯入編輯區儲存。</small></p></section></div>
  {draft&&<section className="chat-draft"><h2>建議計畫草稿</h2><p>{draft.summary}</p><p><small>{draft.source}</small></p>{draft.weekly_distribution&&<div className="weekly-load" aria-label="七天讀書時數分配">{draft.weekly_distribution.map(r=><div key={r.date}><small>{r.date}</small><strong>{r.minutes>0?`${r.minutes} 分鐘`:'休息／未安排'}</strong></div>)}</div>}{draft.assumptions.length>0&&<><h3>安排依據與假設</h3><ul>{draft.assumptions.map((x,i)=><li key={i}>{x}</li>)}</ul></>}
    <details><summary>對話確認的可用時段與固定事項</summary>{draft.availability_windows.map((w,i)=><p key={i}>{w.date} {w.start_time}–{w.end_time}</p>)}{draft.fixed_items.map((r,i)=><p key={i}>{r.kind==='blocked'?'保留空白':'固定待辦'}：{r.date} {r.start_time} · {r.minutes} 分鐘 · {r.content||r.subject}</p>)}</details>
    {draft.unplaced.length>0&&<div className="error" role="alert">可用時間不足，尚未安排：{draft.unplaced.map(r=>`${r.subject} ${r.minutes} 分鐘`).join('、')}。可以回到對話調整目標或增加可用時間。</div>}
    <div className="chat-draft-scroll"><table className="chat-draft-table"><thead><tr><th>日期</th><th>開始時間</th><th>科目</th><th>分鐘</th><th>學習內容</th></tr></thead><tbody>{draft.items.filter(r=>r.kind==='study').map((r,i)=><tr key={i}><td>{r.date}</td><td>{r.start_time}</td><td>{r.subject}</td><td>{r.minutes}</td><td>{r.content}</td></tr>)}</tbody></table></div>
    <button disabled={!!pending||!draft.items.some(r=>r.kind==='study')} onClick={()=>onImport(draft)}>匯入目前計畫編輯區</button><p><small>匯入後可修改科目與內容，最後按「儲存計畫並查看日曆」。</small></p>
  </section>}
 </>;
}
