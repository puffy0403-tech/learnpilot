import asyncio
from datetime import date, timedelta
from pathlib import Path
from types import SimpleNamespace
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
import database
import chat_planner as chat
from main import app
from planning import serialize_editable_plan, editable_plan_data, plan_availability, fit_calendar_slots
from ai_service import ask_ai, configuration


@pytest.fixture
def clients(tmp_path,monkeypatch):
    monkeypatch.setattr(database,'DB_PATH',tmp_path/'chat.db')
    database.initialize()
    a,b=TestClient(app),TestClient(app)
    for client,name in [(a,'a'),(b,'b')]:
        assert client.post('/auth/register',json={'email':name+'@test.com','password':'test123'}).status_code==200
    return a,b


@pytest.fixture
def draft():
    return chat.Draft(summary='英文與統計各兩小時，週二四晚間讀書。',assumptions=['優先安排英文，再安排統計。'],questions=[],
        windows=[chat.Window(date='2026-10-13',start_time='19:00',end_time='21:00'),chat.Window(date='2026-10-15',start_time='19:00',end_time='21:00')],
        additional_fixed_items=[],tasks=[chat.Task(subject=s,content='閱讀、練習並檢核錯題',minutes=120,date=None,start_time=None) for s in ['英文','統計']])


def test_chat_history_accounts_weeks_and_prompt_context(clients,monkeypatch):
    a,b=clients
    a.post('/data/goals',json={'subject':'個人英文目標','weekly_hours':2})
    b.post('/data/goals',json={'subject':'其他人的目標','weekly_hours':3})
    seen=[]
    async def fake(instructions,messages,output_type=None):
        seen.append((instructions,[dict(m) for m in messages]))
        return chat.ChatReply(reply='你希望安排哪些時段？',summary='英文兩小時',ready=True),'Mock AI'
    monkeypatch.setattr(chat,'ask_ai',fake)
    payload={'week_start':'2026-10-12','message':'英文兩小時，週二19:00到21:00可以讀書','revision':0}
    r=a.post('/planning-chat/message',json=payload)
    assert r.status_code==200 and r.json()['revision']==1
    assert len(r.json()['messages'])==2
    assert '個人英文目標' in seen[0][0] and '其他人的目標' not in seen[0][0]
    assert b.get('/planning-chat?week_start=2026-10-12').json()['messages']==[]
    assert a.get('/planning-chat?week_start=2026-10-19').json()['messages']==[]
    r=a.post('/planning-chat/message',json={**payload,'message':'還想讀統計','revision':1})
    assert r.status_code==200 and len(seen[1][1])==3
    assert seen[1][1][0]['content']==payload['message']
    assert TestClient(app).get('/planning-chat?week_start=2026-10-12').status_code==401
    assert TestClient(app).post('/planning-chat/generate',json={'week_start':'2026-10-12'}).status_code==401


def test_no_configuration_and_no_fake_reply(clients,monkeypatch):
    a,_=clients
    monkeypatch.setenv('AI_PROVIDER','openai');monkeypatch.setenv('OPENAI_API_KEY','')
    r=a.post('/planning-chat/message',json={'week_start':'2026-10-12','message':'幫我安排英文'})
    assert r.status_code==503
    assert a.get('/planning-chat?week_start=2026-10-12').json()['messages']==[]
    assert configuration()['configured'] is False


def test_stale_revision_reset_and_failed_request(clients,monkeypatch):
    a,_=clients
    async def fake(*args):
        return chat.ChatReply(reply='請問時間？',summary='待確認',ready=False),'Mock'
    monkeypatch.setattr(chat,'ask_ai',fake)
    p={'week_start':'2026-10-12','message':'英文','revision':0}
    assert a.post('/planning-chat/message',json=p).status_code==200
    assert a.post('/planning-chat/message',json=p).status_code==409
    assert a.post('/planning-chat/generate',json={'week_start':'2026-10-12','revision':1}).status_code==422
    async def fail(*args): raise HTTPException(503,'逾時')
    monkeypatch.setattr(chat,'ask_ai',fail)
    assert a.post('/planning-chat/message',json={**p,'revision':1}).status_code==503
    assert len(a.get('/planning-chat?week_start=2026-10-12').json()['messages'])==2
    assert a.post('/planning-chat/reset',json={'week_start':'2026-10-12'}).json()['revision']==2
    assert a.post('/planning-chat/message',json={**p,'revision':1}).status_code==409


def test_draft_only_not_saved_and_roundtrip_windows(clients,monkeypatch,draft):
    a,b=clients
    async def fake(instructions,messages,output_type=None):
        if output_type is chat.ChatReply:
            return chat.ChatReply(reply='可以安排。',summary='週二四',ready=True),'Mock'
        assert messages[-1]['role']=='user'
        assert '產生這一週' in messages[-1]['content']
        return draft,'Mock'
    monkeypatch.setattr(chat,'ask_ai',fake)
    assert a.post('/planning-chat/message',json={'week_start':'2026-10-12','message':'英文統計各兩小時，週二四19到21點'}).status_code==200
    p={'week_start':'2026-10-12','revision':1}
    r=a.post('/planning-chat/generate',json=p)
    assert r.status_code==200,r.text
    result=r.json();assert result['unplaced']==[]
    assert sum(r['minutes'] for r in result['items'])==240
    assert a.get('/data/plans').json()==[]
    saved=a.post('/plans/serialize',json={**p,'items':result['items'],'notes':result['notes'],'availability_windows':result['availability_windows']})
    assert saved.status_code==200,saved.text
    parsed=a.post('/plans/parse',json=saved.json()).json()
    assert parsed['availability_windows']==result['availability_windows']
    assert parsed['items']==result['items']
    a.post('/data/plans',json=saved.json())
    assert b.get('/data/plans').json()==[]


def test_fixed_gaps_and_unplaced_preserve_total(draft):
    fixed=dict(date='2026-10-13',start_time='19:30',minutes=30,subject='固定待辦',content='吃飯',kind='todo')
    result=chat.make_plan(draft,chat.Context(week_start=date(2026,10,12),fixed_items=[fixed]))
    assert result['fixed_items']==[fixed]
    assert sum(r['minutes'] for r in result['items'] if r['kind']=='study')+sum(r['minutes'] for r in result['unplaced'])==240
    assert sum(r['minutes'] for r in result['unplaced'])==30
    for r in result['items']:
        if r['kind']=='study' and r['date']=='2026-10-13':
            t=chat.minute(r['start_time']); assert t+r['minutes']<=1170 or t>=1200


def test_task_date_and_outside_week_validation(draft):
    draft.tasks[0].date='2026-10-13';draft.tasks[0].minutes=180
    result=chat.make_plan(draft,chat.Context(week_start=date(2026,10,12)))
    assert result['unplaced'][0]==dict(subject='英文',minutes=60)
    assert all(r['date']=='2026-10-13' for r in result['items'] if r['subject']=='英文')
    draft.tasks[0].date='2026-10-20'
    with pytest.raises(ValueError): chat.make_plan(draft,chat.Context(week_start=date(2026,10,12)))


def test_missing_requirements_and_invalid_windows(draft):
    draft.questions=['哪一天有空？']
    with pytest.raises(ValueError): chat.make_plan(draft,chat.Context(week_start=date(2026,10,12)))
    draft.questions=[]
    draft.windows.append(draft.windows[0])
    with pytest.raises(ValueError): chat.make_plan(draft,chat.Context(week_start=date(2026,10,12)))


def test_editor_respects_end_times_and_skips_unavailable_dates():
    windows=[dict(date='2026-10-13',start_time='19:30',end_time='20:30'),dict(date='2026-10-15',start_time='18:00',end_time='19:00')]
    rows=[dict(date='2026-10-12',start_time='08:00',minutes=120,subject='英文',content='練習')]
    start,text=serialize_editable_plan(rows,'',{},windows)
    restored,_=editable_plan_data(text,start)
    assert [(str(r['date']),r['start_time'],r['minutes']) for r in restored]==[('2026-10-13','19:30',30),('2026-10-13','20:00',30),('2026-10-15','18:00',60)]
    assert plan_availability(text)==windows
    with pytest.raises(ValueError): fit_calendar_slots([{**rows[0],'minutes':121}],{},windows)
    with pytest.raises(ValueError): fit_calendar_slots(rows,{},[])


def test_openai_structured_adapter_no_storage(monkeypatch):
    import openai
    seen={}
    class FakeClient:
        def __init__(self,**kwargs): self.responses=self
        async def __aenter__(self): return self
        async def __aexit__(self,*args): pass
        async def parse(self,**kwargs):
            seen.update(kwargs)
            return SimpleNamespace(output_parsed=chat.ChatReply(reply='回覆',summary='摘要',ready=False))
    monkeypatch.setattr(openai,'AsyncOpenAI',FakeClient)
    monkeypatch.setenv('AI_PROVIDER','openai');monkeypatch.setenv('OPENAI_API_KEY','test-only-secret');monkeypatch.setenv('OPENAI_MODEL','test-model')
    reply,source=asyncio.run(ask_ai('指示',[dict(role='user',content='英文')],chat.ChatReply))
    assert reply.reply=='回覆' and seen['store'] is False
    assert seen['text_format'] is chat.ChatReply
    assert 'test-only-secret' not in source


def test_exact_start_not_silently_shifted(draft):
    draft.tasks=[chat.Task(subject='英文',content='練習',minutes=30,date='2026-10-13',start_time='19:30')]
    p=chat.Context(week_start=date(2026,10,12),fixed_items=[dict(date='2026-10-13',start_time='19:30',minutes=30,kind='todo',subject='固定待辦',content='吃飯')])
    result=chat.make_plan(draft,p)
    assert result['unplaced']==[dict(subject='英文',minutes=30)]
    assert not any(r['kind']=='study' for r in result['items'])


def test_fractional_fixed_minutes_and_duplicate_detection(draft):
    p=chat.Context(week_start=date(2026,10,12),fixed_items=[dict(date='2026-10-13',start_time='19:00',minutes=0.5,kind='todo',subject='固定待辦',content='待辦')])
    result=chat.make_plan(draft,p)
    first=next(r for r in result['items'] if r['kind']=='study')
    assert first['start_time']=='19:01'


def test_deadline_does_not_spill_after_due_date(draft):
    draft.tasks=[chat.Task(subject='英文',content='作業',minutes=180,date=None,start_time=None,deadline='2026-10-14')]
    result=chat.make_plan(draft,chat.Context(week_start=date(2026,10,12)))
    assert result['unplaced']==[dict(subject='英文',minutes=60)]
    assert all(r['date']<='2026-10-14' for r in result['items'])


def test_draft_generation_ends_with_user_without_mutating_history():
    history=[dict(role='user',content='英文讀兩小時'),dict(role='assistant',content='已確認，請按產生草稿。')]
    result=chat.draft_request_messages(history)
    assert result[-1]['role']=='user'
    assert result[:-1]==history
    assert len(history)==2 and history[-1]['role']=='assistant'
    result[0]['content']='changed'
    assert history[0]['content']=='英文讀兩小時'


def test_authoritative_form_updates_override_stale_dialogue_fixed_items(draft):
    # AI can return old dialogue reservations; only the latest form controls the calendar.
    draft.additional_fixed_items=[chat.FixedItem(date='2026-10-13',start_time='19:00',minutes=120,subject='固定待辦',content='舊行程',kind='todo')]
    updated=dict(date='2026-10-13',start_time='19:30',minutes=30,subject='保留空白',content='新設定',kind='blocked')
    result=chat.make_plan(draft,chat.Context(week_start=date(2026,10,12),fixed_items=[updated],fixed_items_authoritative=True))
    assert result['fixed_items']==[updated]
    assert all(r.get('content')!='舊行程' for r in result['items'])
    assert sum(r['minutes'] for r in result['unplaced'])==30
    # Removing every form entry must also remove old dialogue reservations.
    result=chat.make_plan(draft,chat.Context(week_start=date(2026,10,12),fixed_items=[],fixed_items_authoritative=True))
    assert result['fixed_items']==[] and result['unplaced']==[]


def test_generate_uses_latest_form_and_preserves_it_in_saved_plan(clients,monkeypatch,draft):
    a,_=clients
    async def fake(instructions,messages,output_type=None):
        if output_type is chat.ChatReply:
            return chat.ChatReply(reply='已確認。',summary='英文統計各兩小時',ready=True),'Mock'
        assert '最新表單行程' in instructions
        assert 'fixed_items_authoritative' in instructions
        return draft,'Mock'
    monkeypatch.setattr(chat,'ask_ai',fake)
    assert a.post('/planning-chat/message',json={'week_start':'2026-10-12','message':'英文統計各兩小時，週二四19到21點'}).status_code==200
    fixed=dict(date='2026-10-13',start_time='19:30',minutes=30,subject='固定待辦',content='最新表單行程',kind='todo')
    p=dict(week_start='2026-10-12',revision=1,fixed_items=[fixed],fixed_items_authoritative=True)
    response=a.post('/planning-chat/generate',json=p)
    assert response.status_code==200,response.text
    result=response.json()
    assert result['fixed_items']==[fixed]
    serialized=a.post('/plans/serialize',json=dict(week_start='2026-10-12',items=result['items'],notes=result['notes'],availability_windows=result['availability_windows']))
    assert serialized.status_code==200,serialized.text
    parsed=a.post('/plans/parse',json=serialized.json()).json()
    fixed_rows=[r for r in parsed['items'] if r['kind']!='study']
    assert len(fixed_rows)==1 and fixed_rows[0]['content']=='最新表單行程'


def test_chat_weekly_distribution_and_saved_calendar_keep_seven_days(draft):
    start=date(2026,10,12)
    draft.windows=[chat.Window(date=str(start+timedelta(days=i)),start_time='09:00',end_time='17:00') for i in range(7)]
    draft.tasks=[chat.Task(subject=s,content='練習與檢核',minutes=420,date=None,start_time=None) for s in ['英文','論文','計算機概論']]
    result=chat.make_plan(draft,chat.Context(week_start=start))
    assert len(result['weekly_distribution'])==7
    values=[r['minutes'] for r in result['weekly_distribution']]
    assert all(v>0 for v in values) and max(values)-min(values)<=15
    assert sum(values)==1260 and result['unplaced']==[]
    saved_start,text=serialize_editable_plan(result['items'],result['notes'],{},result['availability_windows'])
    restored,_=editable_plan_data(text,saved_start)
    assert len({str(r['date']) for r in restored})==7
    assert sum(r['minutes'] for r in restored)==1260


def test_chat_only_confirmed_days_and_exact_date_are_respected(draft):
    start=date(2026,10,12)
    draft.tasks=[chat.Task(subject='英文',content='閱讀',minutes=120,date=None,start_time=None)]
    result=chat.make_plan(draft,chat.Context(week_start=start))
    assert {r['date'] for r in result['items']}=={'2026-10-13','2026-10-15'}
    assert [r['minutes'] for r in result['weekly_distribution'] if r['minutes']>0]==[60,60]
    draft.tasks[0].date='2026-10-13'
    result=chat.make_plan(draft,chat.Context(week_start=start))
    assert {r['date'] for r in result['items']}=={'2026-10-13'}
