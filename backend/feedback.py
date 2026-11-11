from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from database import connect, current_user
from learning_metrics import log_views
from plan_items import timestamp

router=APIRouter()
class Feedback(BaseModel):
    model_config=ConfigDict(extra='forbid',str_strip_whitespace=True)
    actual_minutes: Annotated[int,Field(strict=True,ge=0,le=1440)] | None = None
    understanding: Annotated[int,Field(strict=True,ge=1,le=4)] | None = None
    topic: str=Field(default='',max_length=200)
    difficulty: str=Field(default='',max_length=4000)

@router.patch('/study-logs/{log_id}/feedback')
def save_feedback(log_id:int,p:Feedback,user=Depends(current_user)):
    with connect() as c:
        c.execute('BEGIN IMMEDIATE')
        log=c.execute('SELECT * FROM study_logs WHERE id=? AND user_id=?',(log_id,user['id'])).fetchone()
        if not log: raise HTTPException(404,'學習紀錄不存在')
        minutes=p.actual_minutes
        source='self_reported' if minutes is not None else log['time_source']
        if minutes is None and log['planned_minutes'] is not None:
            minutes=log['planned_minutes'];source='planned'
            if not float(minutes).is_integer(): raise HTTPException(422,'預計時間不是整數分鐘，請填實際分鐘。')
        if minutes is None: minutes=log['minutes']
        c.execute('UPDATE study_logs SET minutes=?,time_source=? WHERE id=?',(int(minutes),source,log_id))
        c.execute('''INSERT INTO learning_feedback(study_log_id,topic,understanding,difficulty,actual_minutes,updated_at)
            VALUES(?,?,?,?,?,?) ON CONFLICT(study_log_id) DO UPDATE SET topic=excluded.topic,
            understanding=excluded.understanding,difficulty=excluded.difficulty,
            actual_minutes=excluded.actual_minutes,updated_at=excluded.updated_at''',
            (log_id,p.topic,p.understanding,p.difficulty,p.actual_minutes,timestamp()))
        return log_views(c,[c.execute('SELECT * FROM study_logs WHERE id=?',(log_id,)).fetchone()])[0]
