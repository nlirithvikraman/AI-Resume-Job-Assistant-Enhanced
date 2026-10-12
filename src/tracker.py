"""Stage 4: Application tracker (SQLite)."""
import sqlite3
from datetime import date
from pathlib import Path

DB = Path(__file__).resolve().parent.parent / "applications.db"
STATUSES = ["Saved", "Applied", "Interview", "Offer", "Rejected"]


def _conn(path=None):
    c = sqlite3.connect(path or DB)
    c.execute("""CREATE TABLE IF NOT EXISTS applications(
        id INTEGER PRIMARY KEY AUTOINCREMENT, company TEXT, role TEXT, status TEXT,
        match_score INTEGER, applied_on TEXT, notes TEXT)""")
    return c


def add(company, role, status="Saved", match_score=0, notes="", path=None):
    with _conn(path) as c:
        c.execute("INSERT INTO applications(company,role,status,match_score,applied_on,notes) VALUES(?,?,?,?,?,?)",
                  (company, role, status, match_score, date.today().isoformat(), notes))


def list_all(path=None):
    with _conn(path) as c:
        return c.execute("SELECT id,company,role,status,match_score,applied_on,notes FROM applications ORDER BY id DESC").fetchall()


def update_status(app_id, status, path=None):
    with _conn(path) as c:
        c.execute("UPDATE applications SET status=? WHERE id=?", (status, app_id))


def delete(app_id, path=None):
    with _conn(path) as c:
        c.execute("DELETE FROM applications WHERE id=?", (app_id,))
