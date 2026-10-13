import os
from datetime import date
import pandas as pd
from dotenv import load_dotenv
from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from planning import build_rule_based_plan, editable_plan_data, serialize_editable_plan

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

add_routes(app)

@app.get("/health")
def health():
    return {"ok": True}

@app.post("/plans/parse")
async def parse(p: PlanRequest, user=Depends(current_user)):
    try:
        rows, notes = editable_plan_data(p.content, p.week_start)
        return {"items": rows, "notes": notes}
    except ValueError as e:
        raise HTTPException(422, str(e))

@app.post("/plans/serialize")
async def serialize(p: PlanRequest, user=Depends(current_user)):
    try:
        start, content = serialize_editable_plan(p.items, p.notes)
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
    content, source, warning = build_rule_based_plan(goals, logs), "規則式規劃", None
    if os.getenv("GEMINI_API_KEY") and os.getenv("GEMINI_MODEL"):
        try:
            from google import genai
            import asyncio
            prompt = f"以繁體中文規劃下一週，分析完成狀況與調整建議。每個排程獨立一行：- 週一：科目｜1.0 小時｜任務。目標：{goals.to_json(force_ascii=False)}；紀錄：{logs.to_json(force_ascii=False)}"
            client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
            response = await asyncio.wait_for(client.aio.models.generate_content(model=os.environ["GEMINI_MODEL"], contents=prompt), timeout=45)
            if not response.text:
                raise ValueError("empty")
            content, source = response.text, "Gemini AI"
        except Exception:
            warning = "AI 暫時無法使用，已改用規則式規劃。"
    try:
        rows, notes = editable_plan_data(content, p.week_start)
        if not rows:
            raise ValueError("無有效排程")
    except ValueError:
        content, source = build_rule_based_plan(goals, logs), "規則式規劃"
        rows, notes = editable_plan_data(content, p.week_start)
        warning = "AI 排程格式無法解析，已改用規則式規劃。"
    return {"content": content, "items": rows, "notes": notes, "source": source, "warning": warning}
