import tempfile
from pathlib import Path
import unittest
from fastapi.testclient import TestClient
import database
from main import app

class SQLiteTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        database.DB_PATH=Path(self.tmp.name)/'test.db'
        database.initialize()
        self.a=TestClient(app); self.b=TestClient(app)
        self.assertEqual(self.a.post('/auth/register',json={'email':'a@test.com','password':'test123','display_name':'A'}).status_code,200)
        self.assertEqual(self.b.post('/auth/register',json={'email':'b@test.com','password':'test123'}).status_code,200)
    def tearDown(self): self.tmp.cleanup()
    def test_auth(self):
        self.assertEqual(self.a.get('/auth/session').json()['user']['email'],'a@test.com')
        self.assertEqual(self.a.post('/auth/register',json={'email':'a@test.com','password':'test123'}).status_code,409)
        self.a.post('/auth/logout')
        self.assertEqual(self.a.get('/auth/session').status_code,401)
        self.assertEqual(self.a.post('/auth/login',json={'email':'a@test.com','password':'wrong123'}).status_code,401)
        self.assertEqual(self.a.post('/auth/login',json={'email':'a@test.com','password':'test123'}).status_code,200)
        self.assertEqual(self.a.patch('/auth/profile',json={'display_name':'新名字'}).json()['user']['user_metadata']['display_name'],'新名字')
        with database.connect() as c:
            self.assertNotIn('test123',c.execute('SELECT password_hash FROM users LIMIT 1').fetchone()[0])
            self.assertNotEqual(c.execute('SELECT token_hash FROM sessions LIMIT 1').fetchone()[0],self.a.cookies.get('learnpilot_session'))
    def test_crud_isolation_and_validation(self):
        payload={'study_date':'2026-10-09','subject':'英文','minutes':0,'note':'練習'}
        r=self.a.post('/data/study_logs',json=payload); self.assertEqual(r.status_code,200); rid=r.json()['id']
        self.assertEqual(self.b.get('/data/study_logs').json(),[])
        self.assertEqual(self.b.patch(f'/data/study_logs/{rid}',json={'minutes':10}).status_code,404)
        self.assertEqual(self.b.delete(f'/data/study_logs/{rid}').status_code,404)
        self.assertEqual(self.a.patch(f'/data/study_logs/{rid}',json={'minutes':25}).json()['minutes'],25)
        self.assertEqual(self.a.post('/data/study_logs',json={**payload,'minutes':-1}).status_code,422)
        self.assertEqual(self.a.post('/data/study_logs',json={**payload,'user_id':2}).status_code,422)
        self.assertEqual(self.a.get('/data/users').status_code,404)
        self.assertEqual(TestClient(app).get('/data/goals').status_code,401)
        self.assertEqual(self.a.delete(f'/data/study_logs/{rid}').status_code,200)
        self.assertEqual(self.a.get('/data/study_logs').json(),[])
    def test_plan_and_conflicts(self):
        self.a.post('/data/goals',json={'subject':'英文','weekly_hours':3})
        r=self.a.post('/plans/generate',json={'week_start':'2026-10-12'}); self.assertEqual(r.status_code,200)
        p=self.a.post('/plans/serialize',json={'week_start':'2026-10-12','items':r.json()['items'],'notes':r.json()['notes']}).json()
        row=self.a.post('/data/plans',json=p).json()
        parsed=self.a.post('/plans/parse',json=p); self.assertEqual(parsed.status_code,200)
        self.assertTrue(parsed.json()['items'])
        self.assertEqual(self.a.patch(f"/data/plans/{row['id']}",json={'content':p['content']+'x','original_content':p['content']}).status_code,200)
        self.assertEqual(self.a.patch(f"/data/plans/{row['id']}",json={'content':'overwrite','original_content':p['content']}).status_code,409)
        self.assertEqual(self.a.patch(f"/data/plans/{row['id']}",json={'selected_at':'2026-10-09T08:00:00Z'}).status_code,200)
        database.initialize()
        self.assertEqual(len(self.a.get('/data/plans').json()),1)
        self.assertEqual(self.b.get('/data/plans').json(),[])

if __name__=='__main__':unittest.main()
