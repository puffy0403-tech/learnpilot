"""Local database selection and explicit, backed-up recovery of existing data."""
import os
import sqlite3
from datetime import datetime
from pathlib import Path


def default_database_path(backend_dir, local_appdata=None):
    backend_dir = Path(backend_dir)
    legacy = backend_dir / 'data' / 'learnpilot.db'
    # Keep working installations on their existing database. Fresh Windows
    # downloads share user data outside the replaceable source checkout.
    if legacy.is_file():
        return legacy
    appdata = local_appdata if local_appdata is not None else (os.getenv('LOCALAPPDATA') if os.name == 'nt' else None)
    if appdata:
        return Path(appdata) / 'LearnPilot' / 'data' / 'learnpilot.db'
    return legacy


def inspect_database(path):
    path = Path(path).resolve(strict=True)
    with sqlite3.connect(path.as_uri() + '?mode=ro', uri=True) as c:
        if c.execute('PRAGMA quick_check').fetchone()[0] != 'ok':
            raise ValueError('資料庫檢查未通過，請保留原檔並使用備份。')
        required = {'users': {'id', 'email', 'password_hash', 'metadata'},
                    'goals': {'id', 'user_id', 'subject', 'weekly_hours'},
                    'study_logs': {'id', 'user_id', 'study_date', 'minutes'},
                    'plans': {'id', 'user_id', 'week_start', 'content'}}
        for table, columns in required.items():
            actual = {r[1] for r in c.execute(f'PRAGMA table_info({table})')}
            if not columns <= actual:
                raise ValueError('這不是有效的 LearnPilot 帳號與學習資料庫。')
        return {table: c.execute(f'SELECT count(*) FROM {table}').fetchone()[0] for table in required}


def copy_snapshot(source, destination):
    source, destination = Path(source).resolve(strict=True), Path(destination).resolve()
    if source == destination:
        raise ValueError('來源與目的地相同，不需還原。')
    destination.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(source.as_uri() + '?mode=ro', uri=True) as src:
        with sqlite3.connect(destination, timeout=10) as dst:
            src.backup(dst)


def restore_database(source, destination):
    """User-approved whole-database restore, never an account merge."""
    source, destination = Path(source).resolve(strict=True), Path(destination).resolve()
    counts = inspect_database(source)
    if not counts['users']:
        raise ValueError('選取的資料庫沒有帳號，請尋找原本使用的 learnpilot.db。')
    if source == destination:
        raise ValueError('這就是目前使用的資料庫，不需還原。')
    backup = None
    if destination.exists():
        inspect_database(destination)
        stamp = datetime.now().strftime('%Y%m%d-%H%M%S-%f')
        backup = destination.parent / 'backups' / f'learnpilot-before-restore-{stamp}.db'
        copy_snapshot(destination, backup)
        inspect_database(backup)
    copy_snapshot(source, destination)
    with sqlite3.connect(destination) as c:
        tables = {r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        for table in ('sessions', 'password_resets', 'reset_requests'):
            if table in tables:
                c.execute(f'DELETE FROM {table}')
    if inspect_database(destination) != counts:
        raise ValueError('還原後資料數量不符，請保留備份並停止使用。')
    return backup
