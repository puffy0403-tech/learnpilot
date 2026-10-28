import os, sqlite3, hashlib, secrets, time, json, logging
from pathlib import Path
from fastapi import HTTPException, Request, Depends
from pydantic import BaseModel, Field, ConfigDict
from datetime import date, datetime
from local_storage import default_database_path
from plan_items import ensure_schema, sync_plan_items

DB_PATH = Path(os.getenv('DATABASE_PATH') or default_database_path(Path(__file__).parent))
def connect():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB_PATH, timeout=30)
    con.row_factory = sqlite3.Row
    con.execute('PRAGMA foreign_keys=ON')
    return con

def initialize():
    with connect() as c:
        c.executescript('''
        CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY, email TEXT NOT NULL UNIQUE, password_hash TEXT NOT NULL, metadata TEXT NOT NULL DEFAULT '{}');
        CREATE TABLE IF NOT EXISTS sessions(token_hash TEXT PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE, expires INTEGER NOT NULL);
        CREATE TABLE IF NOT EXISTS goals(id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id), subject TEXT NOT NULL, weekly_hours REAL NOT NULL CHECK(weekly_hours>0), target_score REAL, target_date TEXT, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE IF NOT EXISTS study_logs(id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id), study_date TEXT NOT NULL, subject TEXT NOT NULL, minutes INTEGER NOT NULL CHECK(minutes BETWEEN 0 AND 1440), note TEXT, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE IF NOT EXISTS plans(id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id), week_start TEXT NOT NULL, content TEXT NOT NULL, selected_at TEXT, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE IF NOT EXISTS planning_chats(user_id INTEGER NOT NULL REFERENCES users(id), week_start TEXT NOT NULL, messages TEXT NOT NULL DEFAULT '[]', summary TEXT NOT NULL DEFAULT '', ready INTEGER NOT NULL DEFAULT 0, revision INTEGER NOT NULL DEFAULT 0, PRIMARY KEY(user_id,week_start));
        CREATE TABLE IF NOT EXISTS password_resets(token_hash TEXT PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE, expires INTEGER NOT NULL);
        CREATE TABLE IF NOT EXISTS reset_requests(bucket TEXT PRIMARY KEY, requested INTEGER NOT NULL);
        CREATE TABLE IF NOT EXISTS plan_completion_logs(plan_id INTEGER NOT NULL REFERENCES plans(id) ON DELETE CASCADE, item_key TEXT NOT NULL, log_id INTEGER UNIQUE REFERENCES study_logs(id) ON DELETE SET NULL, PRIMARY KEY(plan_id,item_key));
        CREATE TABLE IF NOT EXISTS learning_reports(id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id), mode TEXT NOT NULL CHECK(mode IN ('week','month')), period_start TEXT NOT NULL, period_end TEXT NOT NULL, title TEXT NOT NULL, content TEXT NOT NULL, snapshot TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
        CREATE INDEX IF NOT EXISTS reports_owner ON learning_reports(user_id);
        CREATE INDEX IF NOT EXISTS goals_owner ON goals(user_id);
        CREATE INDEX IF NOT EXISTS logs_owner ON study_logs(user_id);
        CREATE INDEX IF NOT EXISTS plans_owner ON plans(user_id);
        ''')
        ensure_schema(c, DB_PATH)
        c.execute('BEGIN IMMEDIATE')
        c.execute('''CREATE TABLE IF NOT EXISTS plan_chat_snapshots(
            id TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id),
            week_start TEXT NOT NULL,
            revision INTEGER NOT NULL,
            messages TEXT NOT NULL,
            summary TEXT NOT NULL,
            source TEXT NOT NULL,
            generated_at TEXT NOT NULL)''')
        if 'chat_snapshot_id' not in {row[1] for row in c.execute('PRAGMA table_info(plans)')}:
            c.execute('ALTER TABLE plans ADD COLUMN chat_snapshot_id TEXT REFERENCES plan_chat_snapshots(id)')
        c.execute('CREATE TABLE IF NOT EXISTS plan_number_sequence(number INTEGER PRIMARY KEY AUTOINCREMENT)')
        if 'plan_number' not in {row[1] for row in c.execute('PRAGMA table_info(plans)')}:
            c.execute('ALTER TABLE plans ADD COLUMN plan_number TEXT')
        for row in c.execute('SELECT id FROM plans WHERE plan_number IS NULL ORDER BY id').fetchall():
            c.execute('UPDATE plans SET plan_number=? WHERE id=?', (allocate_plan_number(c), row['id']))
        c.execute('CREATE UNIQUE INDEX IF NOT EXISTS plans_number_unique ON plans(plan_number)')
        count = c.execute('SELECT count(*) FROM users').fetchone()[0]
    logging.getLogger('uvicorn.error.storage').info('DATA_LOCATION: %s | 帳號數：%s', DB_PATH.resolve(), count)

def allocate_plan_number(c):
    number = c.execute('INSERT INTO plan_number_sequence DEFAULT VALUES').lastrowid
    return f'LP-{number:06d}'

def user_view(row):
    return {'id':row['id'], 'email':row['email'], 'user_metadata':json.loads(row['metadata'])}
def token_hash(token):
    return hashlib.sha256(token.encode()).hexdigest()
def current_user(request: Request):
    token=request.cookies.get('learnpilot_session','')
    with connect() as c:
        row=c.execute('SELECT users.* FROM users JOIN sessions ON users.id=sessions.user_id WHERE token_hash=? AND expires>?',(token_hash(token),int(time.time()))).fetchone()
    if not row: raise HTTPException(401,'請重新登入')
    return user_view(row)
def password_hash(password, salt=None):
    salt=salt or secrets.token_hex(16)
    return salt+':'+hashlib.pbkdf2_hmac('sha256',password.encode(),bytes.fromhex(salt),600000).hex()
class Credentials(BaseModel):
    email: str = Field(min_length=3,max_length=254)
    password: str = Field(min_length=6,max_length=256)
    display_name: str = Field(default='',max_length=50)
class Payload(BaseModel):
    model_config=ConfigDict(extra='forbid',str_strip_whitespace=True,allow_inf_nan=False)
class Goal(Payload):
    subject: str = Field(min_length=1,max_length=200)
    weekly_hours: float = Field(gt=0)
    target_score: float | None = Field(default=None,ge=0)
    target_date: date | None = None
class Log(Payload):
    study_date: date
    subject: str = Field(min_length=1,max_length=200)
    minutes: int = Field(ge=0,le=1440)
    note: str = Field(default='',max_length=20000)
class Plan(Payload):
    week_start: date
    content: str = Field(min_length=1,max_length=500000)
    selected_at: datetime | None = None
    chat_snapshot_id: str | None = Field(default=None, pattern=r'^[0-9a-f]{32}$')
MODELS={'goals':Goal,'study_logs':Log,'plans':Plan}

def add_routes(app):
    from fastapi import Response
    from pydantic import ValidationError
    def issue(response, uid):
        token=secrets.token_urlsafe(32)
        with connect() as c:
            c.execute('DELETE FROM sessions WHERE expires<=?',(int(time.time()),))
            c.execute('INSERT INTO sessions VALUES(?,?,?)',(token_hash(token),uid,int(time.time())+30*86400))
        response.set_cookie('learnpilot_session',token,max_age=30*86400,httponly=True,samesite='lax',secure=os.getenv('COOKIE_SECURE','false').lower()=='true',path='/')
    @app.post('/auth/register')
    def register(p:Credentials,response:Response):
        email=p.email.strip().lower()
        if '@' not in email: raise HTTPException(422,'Email 格式有誤')
        try:
            with connect() as c:
                cur=c.execute('INSERT INTO users(email,password_hash,metadata) VALUES(?,?,?)',(email,password_hash(p.password),json.dumps({'display_name':p.display_name},ensure_ascii=False)))
                uid=cur.lastrowid
                row=c.execute('SELECT * FROM users WHERE id=?',(uid,)).fetchone()
        except sqlite3.IntegrityError: raise HTTPException(409,'此 Email 已註冊')
        issue(response,uid)
        return {'user':user_view(row)}
    @app.post('/auth/login')
    def login(p:Credentials,response:Response):
        with connect() as c: row=c.execute('SELECT * FROM users WHERE email=?',(p.email.strip().lower(),)).fetchone()
        if not row or not secrets.compare_digest(row['password_hash'],password_hash(p.password,row['password_hash'].split(':')[0])): raise HTTPException(401,'Email 或密碼錯誤')
        issue(response,row['id'])
        return {'user':user_view(row)}
    @app.get('/auth/session')
    def session(user=Depends(current_user)): return {'user':user}
    @app.post('/auth/logout')
    def logout(request:Request,response:Response):
        with connect() as c: c.execute('DELETE FROM sessions WHERE token_hash=?',(token_hash(request.cookies.get('learnpilot_session','')),))
        response.delete_cookie('learnpilot_session',path='/')
        return {'ok':True}
    @app.patch('/auth/profile')
    def profile(p:dict,user=Depends(current_user)):
        if set(p)-{'display_name','profile_photo'}: raise HTTPException(422,'未知欄位')
        name=p.get('display_name')
        if name is not None and (not isinstance(name,str) or not name.strip() or len(name)>50): raise HTTPException(422,'顯示名稱須為 1–50 字')
        photo=p.get('profile_photo')
        if photo is not None and (not isinstance(photo,str) or len(photo)>1400000 or not photo.startswith(('data:image/png;base64,','data:image/jpeg;base64,','data:image/webp;base64,'))): raise HTTPException(422,'照片格式或大小有誤')
        metadata={**user['user_metadata'],**p}
        with connect() as c: c.execute('UPDATE users SET metadata=? WHERE id=?',(json.dumps(metadata,ensure_ascii=False),user['id']))
        return {'user':{**user,'user_metadata':metadata}}
    def table_check(table):
        if table not in MODELS: raise HTTPException(404,'資料表不存在')
    @app.get('/data/{table}')
    def listing(table:str,user=Depends(current_user)):
        table_check(table)
        with connect() as c: return [dict(r) for r in c.execute(f'SELECT * FROM {table} WHERE user_id=? ORDER BY id DESC',(user['id'],))]
    def validate(table,p):
        try: return MODELS[table].model_validate(p).model_dump(mode='json')
        except ValidationError: raise HTTPException(422,'輸入資料有誤，請檢查日期、科目與數值')
    def validate_snapshot(c, snapshot_id, user_id):
        if snapshot_id and not c.execute('SELECT 1 FROM plan_chat_snapshots WHERE id=? AND user_id=?', (snapshot_id, user_id)).fetchone():
            raise HTTPException(404, '原始對話快照不存在')
    @app.post('/data/{table}')
    def insert(table:str,p:dict,user=Depends(current_user)):
        table_check(table); values=validate(table,p); values['user_id']=user['id']
        with connect() as c:
            if table == 'plans':
                validate_snapshot(c, values['chat_snapshot_id'], user['id'])
                values['plan_number'] = allocate_plan_number(c)
            cur=c.execute(f"INSERT INTO {table} ({','.join(values)}) VALUES ({','.join('?' for _ in values)})",list(values.values()))
            row = dict(c.execute(f'SELECT * FROM {table} WHERE id=?',(cur.lastrowid,)).fetchone())
            if table == 'plans':
                try: sync_plan_items(c, row)
                except ValueError as exc: raise HTTPException(422, str(exc)) from None
            return row
    @app.patch('/data/{table}/{record_id}')
    def update(table:str,record_id:int,p:dict,user=Depends(current_user)):
        table_check(table)
        with connect() as c:
            c.execute('BEGIN IMMEDIATE')
            row=c.execute(f'SELECT * FROM {table} WHERE id=? AND user_id=?',(record_id,user['id'])).fetchone()
            if not row: raise HTTPException(404,'資料不存在')
            original=p.pop('original_content',None)
            if original is not None and (table!='plans' or row['content']!=original): raise HTTPException(409,'資料已變更，請重新載入')
            if set(p)-set(MODELS[table].model_fields): raise HTTPException(422,'未知欄位')
            merged={k:row[k] for k in MODELS[table].model_fields}; merged.update(p); values=validate(table,merged)
            if table == 'plans':
                if row['chat_snapshot_id'] and values['chat_snapshot_id'] != row['chat_snapshot_id']:
                    raise HTTPException(409, '此計畫的原始對話已保留，若要使用另一份對話請另存新計畫。')
                validate_snapshot(c, values['chat_snapshot_id'], user['id'])
            c.execute(f"UPDATE {table} SET {','.join(k+'=?' for k in values)} WHERE id=? AND user_id=?",[*values.values(),record_id,user['id']])
            updated = dict(c.execute(f'SELECT * FROM {table} WHERE id=?',(record_id,)).fetchone())
            if table == 'plans' and (values['content'] != row['content'] or values['week_start'] != row['week_start']):
                try: sync_plan_items(c, updated)
                except ValueError as exc: raise HTTPException(422, str(exc)) from None
            return updated
    @app.delete('/data/{table}/{record_id}')
    def delete(table:str,record_id:int,user=Depends(current_user)):
        table_check(table)
        with connect() as c:
            cur=c.execute(f'DELETE FROM {table} WHERE id=? AND user_id=?',(record_id,user['id']))
            if not cur.rowcount: raise HTTPException(404,'資料已不存在')
        return {'ok':True}
