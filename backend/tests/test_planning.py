import unittest
from datetime import date, timedelta
from planning import editable_plan_data, serialize_editable_plan
class PlanningTests(unittest.TestCase):
 def test_legacy(self):
  rows, notes = editable_plan_data('分析\n- 週一：英文｜1.5 小時｜單字複習', date(2026,10,12))
  self.assertEqual(rows[0]['minutes'],90)
  self.assertEqual(rows[0]['subject'],'英文')
  self.assertEqual(notes,'分析')
 def test_roundtrip_zero(self):
  original=[dict(date='2026-10-12',subject='Python',minutes=0,content='回顧')]
  start,text=serialize_editable_plan(original,'反思')
  rows,notes=editable_plan_data(text,start)
  self.assertEqual(rows[0]['minutes'],0)
  self.assertEqual(rows[0]['content'],'回顧')
  self.assertEqual(notes,'反思')
 def test_crossweek(self):
  with self.assertRaises(ValueError):
   serialize_editable_plan([dict(date='2026-10-12',subject='英文',minutes=30),dict(date='2026-10-19',subject='英文',minutes=30)],'')
 def test_invalid(self):
  for minutes in [-1,float('nan'),1441]:
   with self.assertRaises(ValueError): serialize_editable_plan([dict(date='2026-10-12',subject='英文',minutes=minutes)],'')
if __name__=='__main__': unittest.main()

from planning import schedule_available
import pytest

def test_reserved_gaps_and_roundtrip():
    start=date(2026,10,12)
    fixed=[dict(date='2026-10-12',start_time='08:30',minutes=60,subject='保留',content='休息',kind='blocked')]
    tasks=[dict(date=start,subject='英文',minutes=180,content='單字')]
    rows,left=schedule_available(tasks,fixed,start)
    assert left==0 and rows[0]==fixed[0]
    _,text=serialize_editable_plan(rows,'備註')
    restored,_=editable_plan_data(text,start)
    assert restored[0]['start_time']=='08:30' and restored[0]['kind']=='blocked'
    assert sum(r['minutes'] for r in rows if r['kind']=='study')==180

def test_overlap_and_midnight():
    row=dict(date='2026-10-12',start_time='23:00',minutes=120,subject='英文',kind='blocked')
    with pytest.raises(ValueError): serialize_editable_plan([row],'')
    row.update(start_time='08:00',minutes=60)
    with pytest.raises(ValueError): serialize_editable_plan([row,row],'')

def test_full_week_has_no_available_time():
    start=date(2026,10,12)
    fixed=[dict(date=(start+timedelta(days=i)).isoformat(),start_time='00:00',minutes=1440,subject='保留',kind='blocked') for i in range(7)]
    rows,left=schedule_available([dict(subject='英文',minutes=120,content='閱讀')],fixed,start)
    assert rows==fixed and left==120

import pandas as pd
from planning import build_rule_based_plan, ensure_study_content

def test_generated_plan_includes_concrete_content():
    goals=pd.DataFrame([dict(subject='英文',weekly_hours=2)])
    logs=pd.DataFrame(columns=['subject','minutes','study_date','note'])
    text=build_rule_based_plan(goals,logs)
    rows,_=editable_plan_data(text,date(2026,10,12))
    assert rows and all(r['content'].strip() for r in rows)
    assert any('單字' in r['content'] or '聆聽' in r['content'] for r in rows)

def test_ai_empty_content_is_filled_and_original_preserved():
    logs=pd.DataFrame([dict(subject='統計',note='條件機率不熟悉')])
    rows=ensure_study_content([dict(subject='統計',content=''),dict(subject='英文',content='閱讀指定短文並回答五題')],logs)
    assert '條件機率不熟悉' in rows[0]['content']
    assert rows[1]['content']=='閱讀指定短文並回答五題'


def test_explicit_start_survives_save_read():
    start=date(2026,10,12)
    _,text=serialize_editable_plan([dict(date=str(start),subject='英文',minutes=120,content='閱讀與練習',start_time='14:00')],'')
    rows,_=editable_plan_data(text,start)
    assert rows[0]['start_time']=='14:00'
    assert '｜14:00｜' in text

def test_legacy_time_range_recovered():
    from planning import extract_start_time
    assert extract_start_time('14:00–16:00 閱讀')=='14:00'
    rows,_=editable_plan_data('- 週一：英文｜2 小時｜14:00–16:00 閱讀',date(2026,10,12))
    assert rows[0]['start_time']=='14:00'


def test_generated_starts_match_two_hour_slots():
    start=date(2026,10,12)
    fixed=[dict(date=str(start),subject='待辦',kind='todo',start_time='08:30',minutes=30)]
    rows,left=schedule_available([dict(subject='英文',minutes=250,content='閱讀')],fixed,start)
    study=[r for r in rows if r['kind']=='study']
    assert left==0
    assert study[0]['start_time']=='10:00'
    assert all(int(r['start_time'][:2])%2==0 and r['start_time'].endswith(':00') and r['minutes']<=120 for r in study)
    assert sum(r['minutes'] for r in study)==250


@pytest.mark.parametrize('time,minutes,valid',[('14:00',120,True),('14:00',121,False),('14:30',90,True),('14:30',91,False),('15:45',15,True),('15:45',30,False)])
def test_study_fits_calendar_slot(time,minutes,valid):
    row=dict(date='2026-10-12',subject='英文',start_time=time,minutes=minutes,kind='study')
    start,text=serialize_editable_plan([row],'')
    result,_=editable_plan_data(text,start)
    assert sum(r['minutes'] for r in result)==minutes
    assert all(r['minutes']<=120 for r in result)

def test_long_reservation_allowed():
    serialize_editable_plan([dict(date='2026-10-12',subject='保留空白',start_time='08:00',minutes=240,kind='blocked')],'')


def test_combined_subject_overflow():
    rows=[dict(date='2026-10-12',subject=s,minutes=90,start_time='14:00') for s in ['英文','數學']]
    start,text=serialize_editable_plan(rows,'')
    result,_=editable_plan_data(text,start)
    assert [(r['subject'],r['start_time'],r['minutes']) for r in result]==[('英文','14:00',90),('數學','15:30',30),('數學','16:00',60)]


def test_daily_start_roundtrip_and_fixed_preserved():
    from planning import plan_daily_starts
    fixed=dict(date='2026-10-12',subject='待辦',kind='todo',start_time='08:00',minutes=60)
    task=dict(date='2026-10-12',subject='英文',kind='study',start_time='08:00',minutes=120)
    start,text=serialize_editable_plan([fixed,task], '保留內容', {'0':'13:30'})
    rows,notes=editable_plan_data(text,start)
    assert plan_daily_starts(text)=={'0':'13:30'}
    assert rows[0]['start_time']=='08:00'
    assert rows[1]['start_time']=='13:30'
    assert sum(r['minutes'] for r in rows if r['kind']=='study')==120
    assert notes=='保留內容'


def test_daily_start_generation_and_non_monday_week():
    start=date(2026,10,15)
    rows,left=schedule_available([dict(subject='英文',minutes=120)],[],start,{'3':'13:30'})
    assert rows[0]['start_time']=='13:30'
    assert len({r['date'] for r in rows})==7
    assert sum(r['minutes'] for r in rows)==120 and left==0
    assert all(r['date']>='2026-10-15' and r['date']<='2026-10-21' for r in rows)


def test_daily_start_overflow_next_day_and_validation():
    from planning import fit_calendar_slots, validate_daily_starts
    rows=fit_calendar_slots([dict(date='2026-10-12',subject='英文',minutes=120,start_time='23:30')],{'1':'10:30'})
    assert [(r['date'],r['start_time'],r['minutes']) for r in rows]==[('2026-10-12','23:30',30),('2026-10-13','10:30',90)]
    for values in [{'7':'08:00'},{'0':'22:00'},{'0':'wrong'}]:
        with pytest.raises(ValueError): validate_daily_starts(values)


def test_weekly_goals_distributed_over_all_seven_days_and_totals_preserved():
    start=date(2026,10,12)
    tasks=[dict(subject=s,minutes=420,content='練習') for s in ['英文','論文','計算機概論']]
    fixed=[dict(date=str(start),start_time='12:00',minutes=120,subject='待辦',kind='todo')]
    rows,left=schedule_available(tasks,fixed,start)
    study=[r for r in rows if r.get('kind')=='study']
    totals={str(start+timedelta(days=i)):sum(r['minutes'] for r in study if r['date']==str(start+timedelta(days=i))) for i in range(7)}
    assert all(v>0 for v in totals.values())
    assert max(totals.values())-min(totals.values())<=15
    assert left==0 and sum(totals.values())==1260
    assert rows[0]==fixed[0]
    for subject in ['英文','論文','計算機概論']:
        assert sum(r['minutes'] for r in study if r['subject']==subject)==420
    assert not any(r['date']==str(start) and int(r['start_time'][:2]) in (12,13) for r in study)


def test_fully_blocked_weekend_not_given_invented_study_hours():
    start=date(2026,10,12)
    fixed=[dict(date=str(start+timedelta(days=i)),start_time='00:00',minutes=1440,subject='休息',kind='blocked') for i in (5,6)]
    rows,left=schedule_available([dict(subject='英文',minutes=600)],fixed,start)
    study=[r for r in rows if r.get('kind')=='study']
    assert len({r['date'] for r in study})==5
    assert all(date.fromisoformat(r['date']).weekday()<5 for r in study)
    assert sum(r['minutes'] for r in study)==600 and left==0


@pytest.mark.parametrize("duration,expected", [("1.4 小時", 84), ("90 分鐘", 90), ("0 小時", 0), ("1.5 hours", 90)])
@pytest.mark.parametrize("start_field", ["", "14:00｜"])
def test_duration_field_ignores_times_in_description(duration, expected, start_field):
    text = f"- 週一：英文｜{start_field}{duration}｜練習 10 分鐘，最後保留 5 分鐘回顧與 2 小時延伸材料"
    rows, _ = editable_plan_data(text, date(2026, 10, 12))
    assert rows[0]['minutes'] == expected
    assert '5 分鐘回顧' in rows[0]['content']


def test_rule_plan_duration_survives_parsing_and_scheduling():
    goals = pd.DataFrame([dict(subject='英文', weekly_hours=7)])
    logs = pd.DataFrame(columns=['subject', 'minutes', 'study_date', 'note'])
    text = build_rule_based_plan(goals, logs)
    rows, _ = editable_plan_data(text, date(2026, 10, 12))
    assert sum(r['minutes'] for r in rows) == 420
    scheduled, unplaced = schedule_available(rows, [], date(2026, 10, 12))
    assert unplaced == 0
    assert sum(r['minutes'] for r in scheduled) == 420


def test_generate_api_preserves_seven_hour_goal(tmp_path, monkeypatch):
    import database
    import ai_service
    from fastapi.testclient import TestClient
    from main import app
    monkeypatch.setattr(database, 'DB_PATH', tmp_path / 'duration.db')
    monkeypatch.setattr(ai_service, 'configuration', lambda: {'configured': False})
    database.initialize()
    with TestClient(app) as client:
        assert client.post('/auth/register', json={'email': 'duration@example.test', 'password': 'test-duration'}).status_code == 200
        assert client.post('/data/goals', json={'subject': '英文', 'weekly_hours': 7}).status_code == 200
        response = client.post('/plans/generate', json={'week_start': '2026-10-12'})
        assert response.status_code == 200
        assert sum(r['minutes'] for r in response.json()['items']) == 420
