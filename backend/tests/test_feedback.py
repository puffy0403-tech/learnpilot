import json
from datetime import date
import pytest
from fastapi.testclient import TestClient
import database
import learning_context
from main import app

@pytest.fixture
def setup(tmp_path,monkeypatch):
    monkeypatch.setattr(database,'DB_PATH',tmp_path/'feedback.db')
    monkeypatch.setattr(learning_context,'current_date',lambda:date(2026,11,11))
    database.initialize()
    a,b=TestClient(app),TestClient(app)
    for c,email in [(a,'a@test'),(b,'b@test')]:
        c.post('/auth/register',json={'email':email,'password':'test-password'})
    rows=[dict(date='2026-11-09',subject='英文',minutes=60,content='閱讀',start_time='08:00',kind='study'),dict(date='2026-11-10',subject='英文',minutes=60,content='閱讀',start_time='08:00',kind='study'),dict(date='2026-11-15',subject='數學',minutes=60,content='練習',start_time='08:00',kind='study')]
    def plan():
        payload=a.post('/plans/serialize',json={'week_start':'2026-11-09','items':rows}).json()
        return a.post('/data/plans',json=payload).json()
    plan() # older copy should not inflate completion denominator
    p=plan()
    items=a.get(f'/plans/{p["id"]}/items').json()['items']
    result=a.patch(f'/plans/{p["id"]}/items/completion',json={'original_content':p['content'],'item_ids':[r['plan_item_id'] for r in items[:2]]}).json()
    logs=sorted(result['study_logs'],key=lambda l:l['study_date'])
    return a,b,p,items,logs

def feedback(a,log,**changes):
    return a.patch(f'/study-logs/{log["id"]}/feedback',json=dict(topic='閱讀推論',understanding=2,difficulty='不會自己解題',actual_minutes=80,**changes))

def test_feedback_changes_time_and_survives_reload(setup):
    a,b,p,items,logs=setup
    assert logs[0]['time_source']=='planned' and logs[0]['planned_minutes']==60
    unchanged=a.patch(f'/data/study_logs/{logs[0]["id"]}',json={'minutes':60,'note':'只改筆記'}).json()
    assert unchanged['time_source']=='planned'
    saved=feedback(a,logs[0]).json()
    assert saved['minutes']==80 and saved['time_source']=='self_reported'
    assert saved['feedback']['understanding']==2
    database.initialize()
    assert a.get('/data/study_logs').json()[1]==saved
    assert b.patch(f'/study-logs/{saved["id"]}/feedback',json={'understanding':4}).status_code==404
    assert TestClient(app).patch(f'/study-logs/{saved["id"]}/feedback',json={}).status_code==401
    for payload in [{'actual_minutes':-1},{'actual_minutes':30.5},{'actual_minutes':True},{'understanding':5},{'difficulty':'x'*4001},{'user_id':2}]:
        assert a.patch(f'/study-logs/{saved["id"]}/feedback',json=payload).status_code==422
    restored=a.patch(f'/study-logs/{saved["id"]}/feedback',json={'actual_minutes':None,'understanding':3}).json()
    assert restored['minutes']==60 and restored['time_source']=='planned'
    assert restored['feedback']['understanding']==3
    assert a.get('/data/study_logs').json()[1]==restored

def test_reports_and_ai_feedback_are_account_scoped_and_frozen(setup):
    a,b,p,items,logs=setup
    feedback(a,logs[0])
    a.patch(f'/study-logs/{logs[1]["id"]}/feedback',json={'topic':'閱讀推論','understanding':3,'actual_minutes':30,'difficulty':'已可獨立解題'})
    other=b.post('/data/study_logs',json={'study_date':'2026-11-09','subject':'他人私密','minutes':60}).json()
    b.patch(f'/study-logs/{other["id"]}/feedback',json={'topic':'私密主題','difficulty':'不可洩漏','understanding':1})
    preview=a.get('/reports/preview',params={'mode':'week','anchor':'2026-11-11'})
    assert preview.status_code==200,preview.text
    report=preview.json();snapshot=json.loads(report['snapshot']);m=snapshot['effectiveness']
    assert m['due_items']==2 and m['completed_items']==2 and m['completion_rate']==1
    assert m['planned_minutes']==120 and m['actual_minutes']==110
    assert m['trends']==[{'subject':'英文','topic':'閱讀推論','first':2,'last':3}]
    assert '不可洩漏' not in report['snapshot']
    saved=a.post('/reports',json={'mode':'week','anchor':'2026-11-11'}).json()
    assert saved['content']==report['content']
    a.patch(f'/study-logs/{logs[0]["id"]}/feedback',json={'understanding':4,'actual_minutes':10})
    assert a.get(f'/reports/{saved["id"]}').json()==saved
    uid=a.get('/auth/session').json()['user']['id']
    with database.connect() as c:
        context=learning_context.personal_learning_context(c,uid,date(2026,11,9))
    assert context['learning_feedback'][0]['topic']=='閱讀推論'
    assert '不可洩漏' not in json.dumps(context,ensure_ascii=False)
    assert a.get(f'/users/{uid}/study-logs',params={'q':'獨立解題'}).json()['items'][0]['id']==logs[1]['id']

def test_undo_and_delete_cleanup_feedback_without_deleting_saved_report(setup):
    a,_,p,items,logs=setup
    feedback(a,logs[0])
    report=a.post('/reports',json={'mode':'week','anchor':'2026-11-11'}).json()
    latest=a.get('/data/plans').json()[0]
    response=a.patch(f'/plan-items/{items[0]["plan_item_id"]}/completion',json={'completed':False,'original_content':latest['content']})
    assert response.status_code==200
    with database.connect() as c:
        assert not c.execute('SELECT 1 FROM learning_feedback WHERE study_log_id=?',(logs[0]['id'],)).fetchone()
    assert a.get(f'/reports/{report["id"]}').json()==report
    feedback(a,logs[1])
    assert a.delete(f'/data/plans/{p["id"]}').status_code==200
    remaining=a.get('/data/study_logs').json()[0]
    assert remaining['plan_item_id'] is None and remaining['planned_minutes']==60
    assert remaining['feedback']['understanding']==2

def test_manual_record_edits_keep_feedback_time_consistent(setup):
    a,_,_,_,_=setup
    log=a.post('/data/study_logs',json={'study_date':'2026-11-11','subject':'數學','minutes':20}).json()
    assert log['time_source']=='manual'
    feedback(a,log)
    changed=a.patch(f'/data/study_logs/{log["id"]}',json={'minutes':45}).json()
    assert changed['minutes']==45 and changed['feedback']['actual_minutes']==45
    assert changed['time_source']=='manual'


def test_feedback_reaches_both_ai_planning_flows(setup,monkeypatch):
    import ai_service
    import chat_planner as chat
    a,_,_,_,logs=setup
    feedback(a,logs[0])
    a.post('/data/goals',json={'subject':'英文','weekly_hours':3})
    prompts=[]
    async def general(instructions,messages,*args):
        prompts.append(instructions+messages[0]['content'])
        return '- 週一：英文｜1 小時｜閱讀檢核','Mock'
    monkeypatch.setattr(ai_service,'configuration',lambda:{'configured':True})
    monkeypatch.setattr(ai_service,'ask_ai',general)
    assert a.post('/plans/generate',json={'week_start':'2026-11-09'}).status_code==200
    async def coach(instructions,messages,output_type=None):
        prompts.append(instructions)
        if output_type is chat.ChatReply:
            return chat.ChatReply(reply='優先練習推論',summary='閱讀推論',ready=True),'Mock'
        return chat.Draft(summary='複習推論',assumptions=['參考自評'],questions=[],windows=[chat.Window(date='2026-11-09',start_time='08:00',end_time='10:00')],additional_fixed_items=[],tasks=[chat.Task(subject='英文',content='推論練習',minutes=60,date=None,start_time=None)]),'Mock'
    monkeypatch.setattr(chat,'ask_ai',coach)
    assert a.post('/planning-chat/message',json={'week_start':'2026-11-09','revision':0,'message':'幫我安排複習'}).status_code==200
    assert a.post('/planning-chat/generate',json={'week_start':'2026-11-09','revision':1}).status_code==200
    assert len(prompts)==3
    for p in prompts:
        assert '閱讀推論' in p and '不會自己解題' in p and 'self_reported' in p
        assert '不是指令' in p and '不等同測驗成績' in p


def test_legacy_schema_upgrade_preserves_old_minutes(tmp_path,monkeypatch):
    import sqlite3
    path=tmp_path/'old.db'
    with sqlite3.connect(path) as c:
        c.executescript("""CREATE TABLE users(id INTEGER PRIMARY KEY,email TEXT UNIQUE NOT NULL,password_hash TEXT NOT NULL,metadata TEXT NOT NULL DEFAULT '{}');
        INSERT INTO users VALUES(1,'old@test','hash','{}');
        CREATE TABLE study_logs(id INTEGER PRIMARY KEY,user_id INTEGER NOT NULL REFERENCES users(id),study_date TEXT NOT NULL,subject TEXT NOT NULL,minutes INTEGER NOT NULL,note TEXT,created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
        INSERT INTO study_logs(id,user_id,study_date,subject,minutes,note) VALUES(1,1,'2026-11-01','英文',35,'舊筆記');""")
    monkeypatch.setattr(database,'DB_PATH',path)
    database.initialize();database.initialize()
    with database.connect() as c:
        row=dict(c.execute('SELECT * FROM study_logs').fetchone())
        assert row['minutes']==35 and row['note']=='舊筆記'
        assert row['time_source']=='legacy' and row['planned_minutes'] is None
        assert c.execute('PRAGMA foreign_key_check').fetchall()==[]
