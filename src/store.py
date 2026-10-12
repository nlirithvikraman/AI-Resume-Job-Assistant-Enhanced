"""Account-scoped local storage. All record reads and writes enforce ownership."""
import hashlib
import hmac
import json
import os
import re
import secrets
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

DB = Path(os.getenv('RESUME_AI_DB', str(Path(__file__).resolve().parent.parent / 'data' / 'workspace.db')))
KINDS = {'job', 'application', 'resume', 'draft', 'preferences'}
STATUSES = ['Saved', 'Applied', 'Interview', 'Offer', 'Rejected', 'Withdrawn']

@contextmanager
def connection(path=None):
    target = Path(path or DB)
    target.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(target, timeout=15)
    con.row_factory = sqlite3.Row
    con.execute('PRAGMA foreign_keys=ON')
    con.executescript('''
    CREATE TABLE IF NOT EXISTS users (
      id INTEGER PRIMARY KEY, username TEXT UNIQUE NOT NULL, password TEXT NOT NULL,
      failed INTEGER NOT NULL DEFAULT 0, locked_until TEXT);
    CREATE TABLE IF NOT EXISTS records (
      id INTEGER PRIMARY KEY, owner INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
      kind TEXT NOT NULL, data TEXT NOT NULL, created TEXT NOT NULL, updated TEXT NOT NULL);
    CREATE INDEX IF NOT EXISTS records_owner_kind ON records(owner,kind);
    ''')
    try:
        yield con
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


def now():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def password_hash(password, salt=None):
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac('sha256', password.encode(), salt.encode(), 600_000).hex()
    return f'{salt}${digest}'


def register(username, password, path=None):
    username = username.strip().lower()
    if not re.fullmatch(r'[a-z0-9_.-]{3,40}', username):
        raise ValueError('Username: use 3–40 letters, numbers, dots, hyphens or underscores.')
    if not 10 <= len(password) <= 256:
        raise ValueError('Use a password between 10 and 256 characters.')
    encoded = password_hash(password)
    try:
        with connection(path) as con:
            return con.execute('INSERT INTO users(username,password) VALUES (?,?)', (username, encoded)).lastrowid
    except sqlite3.IntegrityError as exc:
        raise ValueError('Username unavailable. Choose another.') from exc


def authenticate(username, password, path=None):
    if len(password) > 256:
        return None
    with connection(path) as con:
        user = con.execute('SELECT * FROM users WHERE username=?', (username.strip().lower(),)).fetchone()
        if not user:
            password_hash(password, '0' * 32)
            return None
        if user['locked_until'] and user['locked_until'] > now():
            return None
        salt = user['password'].split('$')[0]
        if hmac.compare_digest(user['password'], password_hash(password, salt)):
            con.execute('UPDATE users SET failed=0,locked_until=NULL WHERE id=?', (user['id'],))
            return {'id': user['id'], 'username': user['username']}
        failures = user['failed'] + 1
        until = (datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat(timespec='seconds') if failures >= 5 else None
        con.execute('UPDATE users SET failed=?,locked_until=? WHERE id=?', (0 if until else failures, until, user['id']))
    return None


def change_password(owner, old, new, path=None):
    if not 10 <= len(new) <= 256:
        raise ValueError('Use a password between 10 and 256 characters.')
    with connection(path) as con:
        user = con.execute('SELECT * FROM users WHERE id=?', (owner,)).fetchone()
        if not user or not hmac.compare_digest(user['password'], password_hash(old, user['password'].split('$')[0])):
            raise ValueError('Current password is incorrect.')
        con.execute('UPDATE users SET password=? WHERE id=?', (password_hash(new), owner))


def _validate(kind, data):
    if kind not in KINDS or not isinstance(data, dict):
        raise ValueError('Invalid record.')
    if len(json.dumps(data)) > 500_000:
        raise ValueError('Record too large.')
    for key, value in data.items():
        if key != 'match' and not isinstance(value, str):
            raise ValueError('Record fields must contain text.')
    if 'match' in data and (not isinstance(data['match'], (int, float)) or not 0 <= data['match'] <= 100):
        raise ValueError('Match score must be between 0 and 100.')
    required = {'resume': ('label', 'text'), 'draft': ('tool', 'text'), 'preferences': ('roles', 'locations', 'notes')}
    for key in required.get(kind, ()):
        if key not in data or (kind != 'preferences' and not data[key].strip()):
            raise ValueError(f'Missing {key}.')
    if kind in {'job', 'application'}:
        if not str(data.get('company', '')).strip() or not str(data.get('role', '')).strip():
            raise ValueError('Company and role are required.')
        url = data.get('url', '')
        if url:
            from urllib.parse import urlsplit
            parts = urlsplit(url)
            if parts.scheme not in {'http', 'https'} or not parts.netloc or parts.username or parts.password:
                raise ValueError('Job link must be an http or https URL without credentials.')
    if kind == 'job' and not str(data.get('description', '')).strip():
        raise ValueError('Job description is required for matching.')
    if kind == 'application' and data.get('status') not in STATUSES:
        raise ValueError('Invalid application status.')
    for key in ('deadline', 'follow_up', 'applied_on'):
        if data.get(key):
            from datetime import date
            date.fromisoformat(data[key])


def save(owner, kind, data, record_id=None, path=None):
    _validate(kind, data)
    timestamp = now()
    with connection(path) as con:
        if record_id is None:
            return con.execute('INSERT INTO records(owner,kind,data,created,updated) VALUES (?,?,?,?,?)',
                               (owner, kind, json.dumps(data), timestamp, timestamp)).lastrowid
        if kind == 'resume':
            raise ValueError('Resume versions are immutable. Save a new version.')
        cursor = con.execute('UPDATE records SET data=?,updated=? WHERE id=? AND owner=? AND kind=?',
                             (json.dumps(data), timestamp, record_id, owner, kind))
        if not cursor.rowcount:
            raise ValueError('Record not found.')
        return record_id


def list_records(owner, kind, path=None):
    with connection(path) as con:
        rows = con.execute('SELECT * FROM records WHERE owner=? AND kind=? ORDER BY id DESC', (owner, kind)).fetchall()
    return [{**dict(row), 'data': json.loads(row['data'])} for row in rows]


def remove(owner, kind, record_id, path=None):
    with connection(path) as con:
        con.execute('DELETE FROM records WHERE owner=? AND kind=? AND id=?', (owner, kind, record_id))


def export_account(owner, path=None):
    return {'schema_version': 1, 'exported_at': now(), 'records': {kind: list_records(owner, kind, path) for kind in sorted(KINDS)}}


def import_account(owner, payload, path=None):
    """Validate all content first; import as new owned records in one transaction."""
    if payload.get('schema_version') != 1 or not isinstance(payload.get('records'), dict):
        raise ValueError('Unsupported backup format.')
    pending = []
    for kind, rows in payload['records'].items():
        if kind not in KINDS or not isinstance(rows, list):
            raise ValueError('Invalid backup records.')
        for row in rows:
            data = row.get('data')
            _validate(kind, data)
            pending.append((owner, kind, json.dumps(data), now(), now()))
    if len(pending) > 5000:
        raise ValueError('Backup exceeds 5,000 records.')
    with connection(path) as con:
        con.executemany('INSERT INTO records(owner,kind,data,created,updated) VALUES (?,?,?,?,?)', pending)
    return len(pending)
