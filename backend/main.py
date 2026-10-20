import os
from datetime import date
import pandas as pd
from dotenv import load_dotenv
from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ConfigDict, Field, StrictBool
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

@app.patch('/plans/{plan_id}/items/{item_index}/completion')
def complete_item(plan_id: int, item_index: int, p: CompletionRequest, user=Depends(current_user)):
    with connect() as c:
        c.execute('BEGIN IMMEDIATE')
        plan = c.execute('SELECT * FROM plans WHERE id=? AND user_id=?', (plan_id, user['id'])).fetchone()
        if not plan:
            raise HTTPException(404, '計畫不存在')
        if plan['content'] != p.original_content:
            raise HTTPException(409, '計畫已變更，請重新整理後再勾選。')
        try:
            rows, notes = editable_plan_data(plan['content'], date.fromisoformat(plan['week_start']))
            starts = plan_daily_starts(plan['content'])
            windows = plan_availability(plan['content'])
            rows = fit_calendar_slots(rows, starts, windows)
            if not 0 <= item_index < len(rows):
                raise HTTPException(404, '讀書項目不存在')
            if rows[item_index].get('kind', 'study') != 'study':
                raise HTTPException(422, '只有讀書計畫可標記完成。')
            rows[item_index]['completed'] = p.completed
            _, content = serialize_editable_plan(rows, notes, starts, windows)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from None
        c.execute('UPDATE plans SET content=? WHERE id=? AND user_id=?', (content, plan_id, user['id']))
        updated = dict(c.execute('SELECT * FROM plans WHERE id=?', (plan_id,)).fetchone())
    return {'plan': updated, 'items': rows}

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
            prompt = f"以繁體中文規劃下一週，分析完成狀況與調整建議。每個時段必須包含具體主題、練習與檢核方式；不要杜撰教材章節。每個排程獨立一行：- 週一：科目｜1.0 小時｜任務。目標：{goals.to_json(force_ascii=False)}；紀錄：{logs.to_json(force_ascii=False)}。只建議學習任務，不含固定事項。"
            content, source = await ask_ai('你是讀書計畫教練。', [{'role':'user','content':prompt}])
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
