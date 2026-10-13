import unittest
from datetime import date
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
