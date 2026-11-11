"""Account-owned immutable learning report snapshots and matching previews."""
import calendar
import json
from datetime import date,timedelta
from fastapi import APIRouter,Depends,HTTPException
from pydantic import BaseModel,ConfigDict
from typing import Literal
from database import connect,current_user
from learning_metrics import log_views,effectiveness,effectiveness_text

router=APIRouter(prefix='/reports')
class ReportRequest(BaseModel):
    model_config=ConfigDict(extra='forbid')
    mode:Literal['week','month']
    anchor:date

def build_report(c,user_id,mode,anchor):
    start=anchor-timedelta(days=anchor.weekday()) if mode=='week' else anchor.replace(day=1)
    end=start+timedelta(days=6) if mode=='week' else start.replace(day=calendar.monthrange(start.year,start.month)[1])
    logs=log_views(c,c.execute('SELECT * FROM study_logs WHERE user_id=? AND study_date BETWEEN ? AND ? ORDER BY study_date,id',(user_id,str(start),str(end))).fetchall())
    goals={}
    for r in c.execute('SELECT * FROM goals WHERE user_id=? ORDER BY id DESC',(user_id,)):
        goals.setdefault(r['subject'],dict(r))
    minutes=sum(r['minutes'] for r in logs)
    title=f"{'學習週報' if mode=='week' else '學習月報'} {start} ～ {end}"
    lines=[title,f'總學習時間：{minutes} 分鐘',f'紀錄：{len(logs)} 筆；學習天數：{len({r["study_date"] for r in logs})} 天']
    behind=False
    for subject in sorted(set(goals)|{r['subject'] for r in logs}):
        actual=sum(r['minutes'] for r in logs if r['subject']==subject)/60
        target=goals[subject]['weekly_hours']*(1 if mode=='week' else end.day/7) if subject in goals else None
        lines.append(f'{subject}：{actual:.1f} 小時；目標 '+('未設定' if target is None else f'{target:.1f} 小時；達成率 {actual/target*100:.0f}%'))
        behind|=target is not None and actual<target
    advice='本期間尚無學習紀錄，請先記錄實際學習成果。' if not logs else '下期優先安排未達目標科目，檢視時間安排並拆成較短的學習任務。' if behind else '保持目前節奏，回顧筆記並調整下一期目標。'
    metrics=effectiveness(c,user_id,start,end,logs)
    content='\n'.join(lines)+'\n\n'+effectiveness_text(metrics)+'\n\n回顧建議：'+advice
    return dict(mode=mode,period_start=str(start),period_end=str(end),title=title,content=content,
        snapshot=json.dumps({'logs':logs,'goals':list(goals.values()),'effectiveness':metrics},ensure_ascii=False))

@router.get('/preview')
def preview_report(mode:Literal['week','month'],anchor:date,user=Depends(current_user)):
    with connect() as c:
        return build_report(c,user['id'],mode,anchor)

@router.post('')
def save_report(p:ReportRequest,user=Depends(current_user)):
    with connect() as c:
        c.execute('BEGIN IMMEDIATE')
        r=build_report(c,user['id'],p.mode,p.anchor)
        cur=c.execute('INSERT INTO learning_reports(user_id,mode,period_start,period_end,title,content,snapshot) VALUES(?,?,?,?,?,?,?)',(user['id'],r['mode'],r['period_start'],r['period_end'],r['title'],r['content'],r['snapshot']))
        return dict(c.execute('SELECT * FROM learning_reports WHERE id=?',(cur.lastrowid,)).fetchone())

@router.get('')
def list_reports(user=Depends(current_user)):
    with connect() as c:
        return [dict(r) for r in c.execute('SELECT * FROM learning_reports WHERE user_id=? ORDER BY id DESC',(user['id'],))]

@router.get('/{report_id}')
def read_report(report_id:int,user=Depends(current_user)):
    with connect() as c:
        row=c.execute('SELECT * FROM learning_reports WHERE id=? AND user_id=?',(report_id,user['id'])).fetchone()
        if not row: raise HTTPException(404,'報告不存在')
        return dict(row)
