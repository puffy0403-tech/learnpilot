import os
import json
from datetime import date
import pandas as pd
from dotenv import load_dotenv
from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ConfigDict, Field, StrictBool
from plan_items import item_rows, decode_plan, timestamp
from learning_context import personal_learning_context, GUIDANCE
from planning import build_rule_based_plan, editable_plan_data, serialize_editable_plan, schedule_available, ensure_study_content, fit_calendar_slots, plan_daily_starts, plan_availability

load_dotenv()
from database import initialize, add_routes, current_user, connect
initialize()
app = FastAPI(title="LearnPilot API")
app.add_middleware(CORSMiddleware, allow_origins=os.getenv("FRONTEND_ORIGINS", "http://localhost:5173").split(","), allow_credentials=True, allow_methods=["POST", "GET", "PATCH", "DELETE"], allow_headers=["Content-Type"])

class PlanRequest(BaseModel):
    content: str = ""
    week_start: date
    items: list[dict] = []
    notes: str = ""
    fixed_items: list[dict] = []
    daily_starts: dict[str, str] = {}
    availability_windows: list[dict] | None = None

class CompletionRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    completed: StrictBool
    original_content: str = Field(min_length=1, max_length=500000)

add_routes(app)
from chat_planner import router as chat_router
app.include_router(chat_router)
from password_reset import router as password_reset_router
app.include_router(password_reset_router)

@app.get("/health")
def health():
    return {"ok": True}

@app.get('/plans/{plan_id}/items')
def read_plan_items(plan_id: int, user=Depends(current_user)):
    with connect() as c:
        plan = c.execute('SELECT * FROM plans WHERE id=? AND user_id=?', (plan_id, user['id'])).fetchone()
        if not plan:
            raise HTTPException(404, '計畫不存在')
        _, notes, starts, windows = decode_plan(plan)
        return {'items': item_rows(c, plan_id), 'notes': notes, 'daily_starts': starts, 'availability_windows': windows}


def save_item_completion(c, plan, item_id, p, user):
    if plan['content'] != p.original_content:
        raise HTTPException(409, '計畫已變更，請重新整理後再勾選。')
    item = c.execute('SELECT * FROM plan_items WHERE id=? AND plan_id=?', (item_id, plan['id'])).fetchone()
    if not item:
        raise HTTPException(404, '讀書項目不存在')
    if item['kind'] != 'study':
        raise HTTPException(422, '只有讀書計畫可標記完成。')
    log = c.execute('SELECT id FROM study_logs WHERE plan_item_id=? AND user_id=?', (item_id, user['id'])).fetchone()
    if p.completed and not log:
        minutes = float(item['planned_minutes'])
        if not minutes.is_integer():
            raise HTTPException(422, '學習紀錄須為整數分鐘，請先調整此計畫時數。')
        c.execute('INSERT INTO study_logs(user_id,study_date,subject,minutes,note,plan_item_id) VALUES(?,?,?,?,?,?)',
            (user['id'], item['scheduled_date'], item['subject'], int(minutes),
             ('讀書計畫完成自動紀錄：' + item['content'])[:20000], item_id))
    elif not p.completed and log:
        c.execute('DELETE FROM study_logs WHERE id=? AND user_id=?', (log['id'], user['id']))
    completed_at = (item['completed_at'] or timestamp()) if p.completed else None
    c.execute('UPDATE plan_items SET completed_at=? WHERE id=?', (completed_at, item_id))
    rows = item_rows(c, plan['id'])
    try:
        _, notes, starts, windows = decode_plan(plan)
        _, content = serialize_editable_plan(rows, notes, starts, windows)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from None
    c.execute('UPDATE plans SET content=? WHERE id=?', (content, plan['id']))
    updated = dict(c.execute('SELECT * FROM plans WHERE id=?', (plan['id'],)).fetchone())
    logs = [dict(row) for row in c.execute('SELECT * FROM study_logs WHERE user_id=? ORDER BY id DESC', (user['id'],))]
    return {'plan': updated, 'items': rows, 'study_logs': logs}


@app.patch('/plan-items/{item_id}/completion')
def complete_item_by_id(item_id: int, p: CompletionRequest, user=Depends(current_user)):
    with connect() as c:
        c.execute('BEGIN IMMEDIATE')
        plan = c.execute('SELECT p.* FROM plans p JOIN plan_items i ON i.plan_id=p.id WHERE i.id=? AND p.user_id=?', (item_id, user['id'])).fetchone()
        if not plan:
            raise HTTPException(404, '讀書項目不存在')
        return save_item_completion(c, plan, item_id, p, user)


# Retain the old positional route while existing local frontends are updated.
@app.patch('/plans/{plan_id}/items/{item_index}/completion')
def complete_item(plan_id: int, item_index: int, p: CompletionRequest, user=Depends(current_user)):
    with connect() as c:
        c.execute('BEGIN IMMEDIATE')
        plan = c.execute('SELECT * FROM plans WHERE id=? AND user_id=?', (plan_id, user['id'])).fetchone()
        if not plan:
            raise HTTPException(404, '計畫不存在')
        if plan['content'] != p.original_content:
            raise HTTPException(409, '計畫已變更，請重新整理後再勾選。')
        item = c.execute('SELECT id FROM plan_items WHERE plan_id=? AND position=?', (plan_id, item_index)).fetchone()
        if not item:
            raise HTTPException(404, '讀書項目不存在')
        return save_item_completion(c, plan, item['id'], p, user)

@app.post("/plans/parse")
async def parse(p: PlanRequest, user=Depends(current_user)):
    try:
        rows, notes = editable_plan_data(p.content, p.week_start)
        daily_starts = plan_daily_starts(p.content)
        windows = plan_availability(p.content)
        return {"items": fit_calendar_slots(rows, daily_starts, windows), "notes": notes, "daily_starts": daily_starts, "availability_windows": windows}
    except ValueError as e:
        raise HTTPException(422, str(e))

@app.post("/plans/serialize")
async def serialize(p: PlanRequest, user=Depends(current_user)):
    try:
        start, content = serialize_editable_plan(p.items, p.notes, p.daily_starts, p.availability_windows)
        return {"week_start": start, "content": content}
    except ValueError as e:
        raise HTTPException(422, str(e))

@app.post("/plans/generate")
async def generate(p: PlanRequest, user=Depends(current_user)):
    with connect() as c:
        goals = pd.DataFrame([dict(r) for r in c.execute('SELECT * FROM goals WHERE user_id=? ORDER BY id DESC',(user['id'],))], columns=["subject", "weekly_hours", "target_score", "target_date"])
        logs = pd.DataFrame([dict(r) for r in c.execute('SELECT * FROM study_logs WHERE user_id=? ORDER BY id DESC',(user['id'],))], columns=["study_date", "subject", "minutes", "note"])
        learning = personal_learning_context(c, user['id'], p.week_start)
    if goals.empty:
        raise HTTPException(422, "請先設定至少一個學習目標")
    try:
        schedule_available([], p.fixed_items, p.week_start, p.daily_starts)
    except ValueError as e:
        raise HTTPException(422, str(e))
    content, source, warning = build_rule_based_plan(goals, logs), "規則式規劃", None
    from ai_service import configuration, ask_ai
    if configuration()['configured']:
        try:
            prompt = f"以繁體中文規劃下一週，分析完成狀況與調整建議。每個時段必須包含具體主題、練習與檢核方式；不要杜撰教材章節。每個排程獨立一行：- 週一：科目｜1.0 小時｜任務。個人學習資料：{json.dumps(learning, ensure_ascii=False)}。只建議學習任務，不含固定事項。"
            content, source = await ask_ai('你是讀書計畫教練。'+GUIDANCE, [{'role':'user','content':prompt}])
        except HTTPException as exc:
            warning = str(exc.detail) + ' 已改用規則式規劃。'
    try:
        rows, notes = editable_plan_data(content, p.week_start)
        if not rows:
            raise ValueError("無有效排程")
    except ValueError:
        content, source = build_rule_based_plan(goals, logs), "規則式規劃"
        rows, notes = editable_plan_data(content, p.week_start)
        warning = "AI 排程格式無法解析，已改用規則式規劃。"
    rows = ensure_study_content(rows, logs)
    rows, unplaced = schedule_available(rows, p.fixed_items, p.week_start, p.daily_starts)
    if unplaced:
        warning = (warning or "") + f" 可用時間不足，尚有 {unplaced:g} 分鐘未安排。"
    return {"content": content, "items": rows, "notes": notes, "source": source, "warning": warning}


@app.get('/users/{user_id}/study-logs')
def user_study_logs(user_id: int, subject: str = '', from_date: date | None = None, to_date: date | None = None, q: str = '', user=Depends(current_user)):
    if user_id != user['id']:
        raise HTTPException(403, '只能查詢目前登入帳號的學習紀錄。')
    if from_date and to_date and from_date > to_date:
        raise HTTPException(422, '起始日期不可晚於結束日期。')
    clauses, params = ['user_id=?'], [user['id']]
    if subject.strip():
        clauses.append('subject=?'); params.append(subject.strip())
    if from_date:
        clauses.append('study_date>=?'); params.append(str(from_date))
    if to_date:
        clauses.append('study_date<=?'); params.append(str(to_date))
    if q.strip():
        term = q.strip().replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')
        clauses.append("(subject LIKE ? ESCAPE '\\' OR note LIKE ? ESCAPE '\\')")
        params.extend(['%'+term+'%', '%'+term+'%'])
    with connect() as c:
        items = [dict(row) for row in c.execute('SELECT * FROM study_logs WHERE '+ ' AND '.join(clauses)+' ORDER BY study_date DESC,id DESC', params)]
    return {'user_id': user['id'], 'items': items}
