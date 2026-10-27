"""Normalized plan items and the one-to-one link to automatic learning logs."""
import sqlite3
from contextlib import closing
from datetime import date, datetime, timezone
from pathlib import Path

from planning import editable_plan_data, fit_calendar_slots, plan_daily_starts, plan_availability

VERSION = '20261027_plan_items_v1'


def timestamp():
    return datetime.now(timezone.utc).isoformat()


def decode_plan(plan):
    try:
        rows, notes = editable_plan_data(plan['content'], date.fromisoformat(plan['week_start']))
        starts, windows = plan_daily_starts(plan['content']), plan_availability(plan['content'])
        return fit_calendar_slots(rows, starts, windows), notes, starts, windows
    except (ValueError, KeyError, TypeError, AttributeError):
        raise ValueError('計畫內容或時間設定格式錯誤，請保留原資料並重新檢查。') from None


def item_rows(c, plan_id):
    result = []
    for row in c.execute('SELECT * FROM plan_items WHERE plan_id=? ORDER BY position', (plan_id,)):
        item = dict(plan_item_id=row['id'], date=row['scheduled_date'], start_time=row['start_time'],
                    subject=row['subject'], minutes=row['planned_minutes'], content=row['content'],
                    kind=row['kind'], completed=row['completed_at'] is not None, completed_at=row['completed_at'])
        if row['legacy_key']:
            item['completion_key'] = row['legacy_key']
        result.append(item)
    return result


def fingerprint(row):
    return (str(row.get('date', row.get('scheduled_date')))[:10], row['start_time'], row['subject'],
            float(row.get('minutes', row.get('planned_minutes'))), row['content'], row.get('kind', 'study'))


def sync_plan_items(c, plan, *, migrate_links=False):
    """Called inside the plan write transaction. Does not rewrite learning history."""
    rows, _, _, _ = decode_plan(plan)
    old = {row['id']: dict(row) for row in c.execute('SELECT * FROM plan_items WHERE plan_id=?', (plan['id'],))}
    remaining = set(old)
    # Free unique positions before reordering stable IDs in this transaction.
    c.execute('UPDATE plan_items SET position=-id WHERE plan_id=?', (plan['id'],))
    for position, item in enumerate(rows):
        if type(item.get('completed', False)) is not bool or (item.get('completed') and item.get('kind', 'study') != 'study'):
            raise ValueError('只有讀書項目可設定布林完成狀態。')
        item_id = item.get('plan_item_id')
        if item_id is not None and (type(item_id) is not int or item_id not in remaining):
            raise ValueError('讀書項目編號不屬於此計畫，或項目已被移除。請重新讀取計畫。')
        key = item.get('completion_key')
        if item_id is None and key:
            item_id = next((i for i in remaining if old[i]['legacy_key'] == key), None)
        if item_id is None:
            item_id = next((i for i in sorted(remaining) if fingerprint(old[i]) == fingerprint(item)), None)
        previous = old.get(item_id)
        completed_at = ((previous['completed_at'] if previous else None) or timestamp()) if item.get('completed') else None
        values = (position, item.get('kind', 'study'), item['subject'], str(item['date'])[:10],
                  item.get('start_time', '08:00'), float(item['minutes']), item.get('content', ''), completed_at, key)
        if item_id is None:
            cur = c.execute('INSERT INTO plan_items(plan_id,position,kind,subject,scheduled_date,start_time,planned_minutes,content,completed_at,legacy_key) VALUES(?,?,?,?,?,?,?,?,?,?)', (plan['id'], *values))
            item_id = cur.lastrowid
        else:
            remaining.remove(item_id)
            c.execute('UPDATE plan_items SET position=?,kind=?,subject=?,scheduled_date=?,start_time=?,planned_minutes=?,content=?,completed_at=?,legacy_key=? WHERE id=?', (*values, item_id))
        if migrate_links and key:
            link = c.execute('SELECT log_id FROM plan_completion_logs WHERE plan_id=? AND item_key=?', (plan['id'], key)).fetchone()
            if link and link['log_id'] is not None:
                log = c.execute('SELECT user_id,plan_item_id FROM study_logs WHERE id=?', (link['log_id'],)).fetchone()
                if not log or log['user_id'] != plan['user_id'] or log['plan_item_id'] not in (None, item_id):
                    raise ValueError('舊完成紀錄的歸屬不一致，已停止搬移，請保留備份。')
                c.execute('UPDATE study_logs SET plan_item_id=? WHERE id=?', (item_id, link['log_id']))
    for item_id in remaining:
        # Deleting an item detaches, rather than deletes, historical learning logs.
        c.execute('DELETE FROM plan_items WHERE id=?', (item_id,))
    return item_rows(c, plan['id'])


def ensure_schema(c, db_path):
    ledger = c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='schema_migrations'").fetchone()
    if ledger and c.execute('SELECT 1 FROM schema_migrations WHERE version=?', (VERSION,)).fetchone():
        return
    backup = None
    if any(c.execute(f'SELECT count(*) FROM {table}').fetchone()[0] for table in ('users', 'plans', 'study_logs')):
        backup = Path(db_path).parent / 'backups' / ('learnpilot-before-plan-items-' + datetime.now().strftime('%Y%m%d-%H%M%S-%f') + '.db')
        backup.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(backup)) as destination:
            c.backup(destination)
            if destination.execute('PRAGMA quick_check').fetchone()[0] != 'ok':
                raise RuntimeError('搬移前備份驗證失敗，未搬移資料。')
    try:
        c.execute('BEGIN IMMEDIATE')
        c.execute('CREATE TABLE IF NOT EXISTS schema_migrations(version TEXT PRIMARY KEY, applied_at TEXT NOT NULL)')
        if c.execute('SELECT 1 FROM schema_migrations WHERE version=?', (VERSION,)).fetchone():
            c.commit()
            return
        c.execute('''CREATE TABLE IF NOT EXISTS plan_items(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            plan_id INTEGER NOT NULL REFERENCES plans(id) ON DELETE CASCADE,
            position INTEGER NOT NULL,
            kind TEXT NOT NULL CHECK(kind IN ('study','todo','blocked')),
            subject TEXT NOT NULL,
            scheduled_date TEXT NOT NULL,
            start_time TEXT NOT NULL,
            planned_minutes REAL NOT NULL CHECK(planned_minutes BETWEEN 0 AND 1440),
            content TEXT NOT NULL DEFAULT '',
            completed_at TEXT,
            legacy_key TEXT,
            UNIQUE(plan_id,position), UNIQUE(plan_id,legacy_key))''')
        if 'plan_item_id' not in {row[1] for row in c.execute('PRAGMA table_info(study_logs)')}:
            c.execute('ALTER TABLE study_logs ADD COLUMN plan_item_id INTEGER REFERENCES plan_items(id) ON DELETE SET NULL')
        c.execute('CREATE UNIQUE INDEX IF NOT EXISTS study_logs_plan_item_unique ON study_logs(plan_item_id) WHERE plan_item_id IS NOT NULL')
        c.execute('CREATE INDEX IF NOT EXISTS plan_items_date ON plan_items(scheduled_date)')
        for plan in c.execute('SELECT * FROM plans ORDER BY id').fetchall():
            sync_plan_items(c, plan, migrate_links=True)
        c.execute('INSERT INTO schema_migrations VALUES(?,?)', (VERSION, timestamp()))
        c.commit()
    except Exception as exc:
        c.rollback()
        raise RuntimeError(f'計畫資料搬移未完成，已回復本次變更。備份位置：{backup or "尚無使用者資料，未建立備份"}') from exc
