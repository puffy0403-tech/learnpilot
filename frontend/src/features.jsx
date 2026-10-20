import React,{useEffect,useState,useRef} from 'react';
export const dateISO=d=>`${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`;
const planStart=r=>r.start_time||((r.content||'').match(/(?:^|[^0-9])([0-9]{1,2}:[0-9]{2})\s*[-–—~～至]/)?.[1]?.padStart(5,'0'))||'08:00';
const timeMinutes=t=>Number((t||'08:00').slice(0,2))*60+Number((t||'08:00').slice(3));
const itemKind=r=>['blocked','todo','study'].includes(r.kind)?r.kind:({'保留空白':'blocked','固定待辦':'todo'}[r.subject]||'study');
const kindName=r=>({blocked:'保留空白',todo:'固定待辦',study:'讀書計畫'}[itemKind(r)]||'讀書計畫');
const stamp=r=>new Date(`${r.date}T${r.start_time||'08:00'}:00`).getTime();
export function Reservations({items,setItems,start,title='先保留空白時間與固定待辦',description='保留時間不會排入學習。固定待辦也會佔用時段；AI 只安排剩餘空檔（依每日開始時間至 22:00）。'}){return <><h3>{title}</h3><p>{description}</p>{items.map((r,i)=><div className={'planrow reservation-row '+itemKind(r)} key={i}><span className="reservation-kind">{kindName(r)}</span><label>日期<input type="date" value={r.date} onChange={e=>setItems(items.map((x,j)=>j===i?{...x,date:e.target.value}:x))}/></label><label>開始時間<input type="time" value={r.start_time} onChange={e=>setItems(items.map((x,j)=>j===i?{...x,start_time:e.target.value}:x))}/></label><label>分鐘<input type="number" min="1" max="1440" value={r.minutes} onChange={e=>setItems(items.map((x,j)=>j===i?{...x,minutes:e.target.valueAsNumber}:x))}/></label><label>說明<input value={r.content} onChange={e=>setItems(items.map((x,j)=>j===i?{...x,content:e.target.value}:x))}/></label><button className="ghost" onClick={()=>setItems(items.filter((_,j)=>j!==i))}>移除</button></div>)}<div className="actions">{[['blocked','保留空白'],['todo','固定待辦']].map(([kind,label])=><button key={kind} className={'ghost reservation-add '+kind} onClick={()=>setItems([...items,{date:start,start_time:'12:00',minutes:120,subject:label,content:'',kind}])}>＋{label}</button>)}</div></>}
export function Calendar({rows,start,onStart,onComplete}) {
  const segments=rows.flatMap((r,itemIndex)=>{
    const beginAt=timeMinutes(planStart(r)),duration=Number(r.minutes),end=beginAt+duration;
    const parts=[];
    for(let slot=Math.floor(beginAt/120);slot<12&&slot*120<Math.max(beginAt+1,end);slot++){
      const begin=Math.max(beginAt,slot*120),finish=Math.min(end,(slot+1)*120);
      parts.push({...r,kind:itemKind(r),itemIndex,key:`${itemIndex}/${slot}`,
        start_time:`${String(Math.floor(begin/60)).padStart(2,'0')}:${String(begin%60).padStart(2,'0')}`,
        minutes:Math.max(0,finish-begin),original_start:planStart(r),original_minutes:duration,
        segment:duration>120||end>(Math.floor(beginAt/120)+1)*120});
    }
    return parts;
  });
  const [selectedKey,select]=useState(null),[saving,setSaving]=useState(false),[error,setError]=useState('');
  const [currentDay,setCurrentDay]=useState(()=>dateISO(new Date()));
  const selected=segments.find(r=>r.key===selectedKey);
  useEffect(()=>{const id=setInterval(()=>setCurrentDay(dateISO(new Date())),30000);return()=>clearInterval(id)},[]);
  const dates=Array.from({length:7},(_,i)=>{const d=new Date(start+'T00:00:00');d.setDate(d.getDate()+i);return dateISO(d)});
  const completed=r=>r.kind==='study'&&r.completed===true;
  const label=r=>completed(r)?'✓ 已完成':kindName(r);
  async function changeCompletion(value){
    if(saving||!selected)return;
    setSaving(true);setError('');
    try{await onComplete(selected.itemIndex,value)}catch(e){setError(e.message||'儲存失敗，請重試。')}
    finally{setSaving(false)}
  }
  function close(){if(!saving){select(null);setError('')}}
  return <>
    <div className="calendar-legend" aria-label="日曆顏色說明">
      <span className="legend blocked">保留空白</span><span className="legend todo">固定待辦</span>
      <span className="legend study">讀書計畫</span><span className="legend completed">✓ 已完成</span><span className="legend today">今天</span>
    </div>
    <div className="calendar-scroll"><table className="week-calendar"><thead><tr><th>時段</th>
      {dates.map(d=><th key={d} className={d===currentDay?'today-column':''} aria-current={d===currentDay?'date':undefined}>
        {['週一','週二','週三','週四','週五','週六','週日'][(new Date(d+'T00:00:00').getDay()+6)%7]}<small>{d}</small>
        {d===currentDay&&<span className="today-badge">今天</span>}
      </th>)}
    </tr></thead><tbody>{Array.from({length:12},(_,slot)=><tr key={slot}>
      <th>{String(slot*2).padStart(2,'0')}:00<br/>–{String(slot*2+2).padStart(2,'0')}:00</th>
      {dates.map(d=>{
        const items=segments.filter(r=>r.date===d&&timeMinutes(r.start_time)<slot*120+120&&timeMinutes(r.start_time)+Math.max(1,r.minutes)>slot*120);
        return <td key={d} className={(d===currentDay?'today-column ':'')+(!items.length?'empty-slot':'')}>
          {!items.length&&<span className="empty-label">空白／未安排</span>}
          {items.map(r=><button data-kind={r.kind} data-completed={completed(r)?'true':'false'} className={'task '+r.kind+(completed(r)?' completed':'')} key={r.key} onClick={()=>{select(r.key);setError('')}}>
            <small className="kind-label">{label(r)}</small><b>{r.subject}</b>
            <span>{r.start_time} · {r.minutes} 分鐘</span><span className="preview">{r.content||'點選查看詳細內容'}</span>
          </button>)}
        </td>;
      })}
    </tr>)}</tbody></table></div>
    {selected&&<div className="modal-backdrop" onClick={close}>
      <section role="dialog" aria-modal="true" aria-label="時段詳細計畫" className="modal" onClick={e=>e.stopPropagation()}>
        <button className="ghost" autoFocus disabled={saving} onClick={close}>關閉</button><h2>{selected.subject}</h2>
        <p className={'detail-kind '+selected.kind+(completed(selected)?' completed':'')}>{label(selected)}</p>
        <dl className="plan-details">
          {selected.segment&&<><dt>原計畫</dt><dd>{selected.original_start} 開始，共 {selected.original_minutes} 分鐘；以下為目前點選時段。</dd></>}
          <dt>日期</dt><dd>{selected.date}</dd><dt>起始時間</dt><dd>{planStart(selected)}</dd>
          <dt>結束時間</dt><dd>{(()=>{const end=timeMinutes(planStart(selected))+Number(selected.minutes);return `${String(Math.floor(end/60)).padStart(2,'0')}:${String(end%60).padStart(2,'0')}`})()}</dd>
          <dt>{selected.kind==='study'?'讀書時數':'佔用時數'}</dt><dd>{selected.minutes} 分鐘（{(selected.minutes/60).toFixed(2)} 小時）</dd>
          <dt>{selected.kind==='study'?'讀書計畫':'事項說明'}</dt><dd><pre>{selected.content||'尚未填寫內容'}</pre></dd>
        </dl>
        {selected.kind==='study'&&<>
          {onComplete&&<div className="completion-control">
            <label><input type="checkbox" checked={completed(selected)} disabled={saving} onChange={e=>changeCompletion(e.target.checked)}/>已完成這項讀書計畫</label>
            {selected.segment&&<small>完成標記會套用至此原計畫的所有分段。</small>}
            <small>勾選後依計畫日期與分鐘自動加入學習紀錄；取消時移除對應的自動紀錄，保留手動紀錄。</small>
            {saving&&<p role="status">正在儲存完成狀態…</p>}
            {error&&<p className="error" role="alert">{error}</p>}
          </div>}
          <button disabled={saving} onClick={()=>{onStart(selected);select(null)}}>開始倒計時</button>
        </>}
      </section>
    </div>}
  </>;
}
export function StudyClock({rows,userId,controller}){const key=`learnpilot-timer-${userId}`;const [timer,setTimer]=useState(()=>{try{return JSON.parse(localStorage.getItem(key))}catch{return null}}),[now,setNow]=useState(Date.now()),[enabled,setEnabled]=useState(false),[alarm,setAlarm]=useState('');const audio=useRef(null),seen=useRef(new Set());
function ring(text){setAlarm(text);if(enabled&&audio.current){const ctx=audio.current;ctx.resume();for(let i=0;i<3;i++){let o=ctx.createOscillator(),g=ctx.createGain();o.connect(g);g.connect(ctx.destination);o.frequency.value=880;g.gain.value=.15;o.start(ctx.currentTime+i*.4);o.stop(ctx.currentTime+i*.4+.2)}}if(enabled&&window.Notification?.permission==='granted')new Notification('LearnPilot 學習提醒',{body:text})}
controller.current=r=>{if(!(r.minutes>0))return;setTimer({label:r.subject,end:Date.now()+r.minutes*60000,left:r.minutes*60000,running:true})};
useEffect(()=>{localStorage.setItem(key,JSON.stringify(timer))},[timer,key]);useEffect(()=>{let id=setInterval(()=>setNow(Date.now()),1000);return()=>clearInterval(id)},[]);
useEffect(()=>{if(timer?.running&&timer.end<=now){setTimer({...timer,running:false,left:0});ring(`${timer.label}：讀書倒計時結束！`)}if(enabled)for(const r of rows){if(r.kind&&r.kind!=='study')continue;let t=stamp(r),id=`${r.date}/${r.start_time}/${r.subject}`;if(now>=t&&now<t+60000&&!seen.current.has(id)){seen.current.add(id);ring(`開始學習：${r.subject}（${r.minutes} 分鐘）`)}}},[now,enabled]);let left=timer?Math.max(0,timer.running?timer.end-now:timer.left):0;
return <section className="clock"><div className="actions"><button className="ghost" onClick={async()=>{try{audio.current ||= new (window.AudioContext||window.webkitAudioContext)();await audio.current.resume();setEnabled(true);if(window.Notification&&Notification.permission==='default')await Notification.requestPermission()}catch{setAlarm('瀏覽器無法播放音效，仍會顯示畫面提醒。')}}}>{enabled?'提醒音效已啟用':'啟用學習提醒與鬧鐘'}</button><small>頁面開啟時提醒；關閉網頁不會響鈴。</small></div>{timer&&<><b>{timer.label} · {String(Math.floor(left/3600000)).padStart(2,'0')}:{String(Math.floor(left/60000)%60).padStart(2,'0')}:{String(Math.ceil(left/1000)%60).padStart(2,'0')}</b><div className="actions"><button onClick={()=>setTimer({...timer,running:!timer.running,left,end:Date.now()+left})} disabled={left===0}>{timer.running?'暫停':'繼續'}</button><button className="ghost" onClick={()=>setTimer(null)}>結束計時</button></div></>}{alarm&&<p role="alert" className="success">{alarm} <button className="ghost" onClick={()=>setAlarm('')}>關閉提醒</button></p>}</section>}
export function Reports({logs,goals}){const [mode,setMode]=useState('week'),[anchor,setAnchor]=useState(dateISO(new Date()));let begin=new Date(anchor+'T00:00:00'),end=new Date(begin);if(mode==='week'){begin.setDate(begin.getDate()-(begin.getDay()+6)%7);end=new Date(begin);end.setDate(end.getDate()+6)}else{begin.setDate(1);end=new Date(begin.getFullYear(),begin.getMonth()+1,0)}const from=dateISO(begin),to=dateISO(end),entries=logs.filter(l=>l.study_date>=from&&l.study_date<=to),minutes=entries.reduce((s,r)=>s+r.minutes,0),subjects=[...new Set([...entries.map(r=>r.subject),...goals.map(g=>g.subject)])];const table=subjects.map(subject=>{let actual=entries.filter(r=>r.subject===subject).reduce((s,r)=>s+r.minutes,0)/60,target=goals.find(g=>g.subject===subject)?.weekly_hours;return {subject,actual,target:target==null?null:target*(mode==='week'?1:(end.getDate()/7))}});let report=`${mode==='week'?'學習週報':'學習月報'} ${from} ～ ${to}\n總學習時間：${minutes} 分鐘\n紀錄：${entries.length} 筆；學習天數：${new Set(entries.map(r=>r.study_date)).size} 天\n`+table.map(r=>`${r.subject}：${r.actual.toFixed(1)} 小時；目標 ${r.target==null?'未設定':r.target.toFixed(1)+' 小時'}${r.target?`；達成率 ${(r.actual/r.target*100).toFixed(0)}%`:''}`).join('\n')+'\n\n回顧建議：'+(!entries.length?'本期間尚無學習紀錄，請先記錄實際學習成果。':table.some(r=>r.target&&r.actual<r.target)?'下期優先安排未達目標科目，檢視時間安排並拆成較短的學習任務。':'保持目前節奏，回顧筆記並調整下一期目標。');return <section><h2>產生學習週報／月報</h2><div className="grid"><label>報告類型<select value={mode} onChange={e=>setMode(e.target.value)}><option value="week">每週</option><option value="month">每月</option></select></label><label>選擇期間內日期<input type="date" value={anchor} onChange={e=>e.target.value&&setAnchor(e.target.value)}/></label></div><pre>{report}</pre><p><small>依實際學習紀錄與目前目標計算；月目標按該月天數 ÷ 7 換算。</small></p><button onClick={()=>{let url=URL.createObjectURL(new Blob([report],{type:'text/plain;charset=utf-8'})),a=document.createElement('a');a.href=url;a.download=`LearnPilot-${mode}-${from}.txt`;a.click();URL.revokeObjectURL(url)}}>下載報告</button><details><summary>本期學習筆記</summary>{entries.map(r=><p key={r.id}>{r.study_date} · {r.subject}：{r.note||'無筆記'}</p>)}</details></section>}
