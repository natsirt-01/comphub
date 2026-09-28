"""
db.py — single source of truth for ScholarNet's persistent data.

Lives on the machine running login.py (teacher + admin side). Import this
module from teacher_dashboard/*, admin_dashboard/*, and login.py instead of
reading/writing the old loose JSON files (users.json, pending_accounts.json,
active_students.json, activity_log.txt) — those go away once this is wired in.

Usage:
    import db
    db.init_db()                      # call once at app startup
    db.seed_defaults()                # creates admin/teacher default accounts if missing

    ok, msg = db.create_student(...)
    user = db.get_user_by_username("awa")
    if db.verify_password("awa", "typed_password"):
        ...
"""

import sqlite3
import os
import sys
import hashlib
import binascii
import secrets
from contextlib import contextmanager
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if getattr(sys, "frozen", False):
    APP_DATA_DIR = os.path.join(os.environ.get("PROGRAMDATA", os.path.expanduser("~")), "CompHub")
    os.makedirs(APP_DATA_DIR, exist_ok=True)
    DB_PATH = os.path.join(APP_DATA_DIR, "scholarnet.db")
    SCHEMA_PATH = os.path.join(sys._MEIPASS, "database", "schema.sql")
else:
    DB_PATH = os.path.join(BASE_DIR, "scholarnet.db")
    SCHEMA_PATH = os.path.join(BASE_DIR, "schema.sql")

DEFAULT_RESET_PASSWORD = "comlab123456"

from datetime import timedelta

def _utc_to_local_str(utc_str, offset_hours=8):
    """Converts a stored UTC 'YYYY-MM-DD HH:MM:SS' string to local display
    time. Philippines is UTC+8 — adjust offset_hours if deployed elsewhere."""
    if not utc_str:
        return utc_str
    try:
        dt = datetime.strptime(utc_str, "%Y-%m-%d %H:%M:%S")
        local_dt = dt + timedelta(hours=offset_hours)
        return local_dt.strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return utc_str


# ---------------------------------------------------------------------------
# Connection handling
# ---------------------------------------------------------------------------

@contextmanager
def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db():
    """Create tables if they don't exist yet. Safe to call every startup."""
    with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
        schema_sql = f.read()
    with get_conn() as conn:
        conn.executescript(schema_sql)
        columns = {row[1] for row in conn.execute("PRAGMA table_info(site_alerts)")}
        if "active" not in columns:
            conn.execute("ALTER TABLE site_alerts ADD COLUMN active INTEGER NOT NULL DEFAULT 1")


# ---------------------------------------------------------------------------
# Password hashing (PBKDF2-HMAC-SHA256, stdlib only, no plaintext ever stored)
# ---------------------------------------------------------------------------

def _hash_password(password: str, salt: str = None):
    if salt is None:
        salt = secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 100_000)
    return binascii.hexlify(dk).decode("utf-8"), salt


def _check_password(password: str, stored_hash: str, salt: str) -> bool:
    test_hash, _ = _hash_password(password, salt)
    return secrets.compare_digest(test_hash, stored_hash)


# ---------------------------------------------------------------------------
# Seeding
# ---------------------------------------------------------------------------

def seed_defaults():
    """Ensure a default admin and teacher account exist so the app is usable
    on a fresh database. Safe to call every startup — does nothing if they
    already exist."""
    defaults = (
        ("admin", "admin123", "admin", "Administrator", "admin"),
        ("teacher", "teacher123", "teacher", "Sir Peter", "teacher"),
    )
    for username, password, role, full_name, legacy_password in defaults:
        user = get_user_by_username(username)
        if not user:
            create_staff_user(username, password, role, full_name=full_name)
        elif _check_password(legacy_password, user["password_hash"], user["password_salt"]):
            _update_password(user["id"], password)
    if not get_user_by_username("student"):
        create_student_user("student", "student", full_name="Patwick")


def _update_password(user_id, password):
    pw_hash, salt = _hash_password(password)
    with get_conn() as conn:
        conn.execute(
            "UPDATE users SET password_hash=?, password_salt=? WHERE id=?",
            (pw_hash, salt, user_id),
        )


def create_staff_user(username, password, role, full_name=None):
    """Create a teacher or admin account. These are auto-approved (no queue)."""
    assert role in ("teacher", "admin")
    pw_hash, salt = _hash_password(password)
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO users (username, password_hash, password_salt, role, status, full_name)
               VALUES (?, ?, ?, ?, 'approved', ?)""",
            (username, pw_hash, salt, role, full_name),
        )


def create_student_user(username, password, full_name=None):
    """Create an approved student account for local/default use."""
    pw_hash, salt = _hash_password(password)
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO users
               (username, password_hash, password_salt, role, status, full_name)
               VALUES (?, ?, ?, 'student', 'approved', ?)""",
            (username, pw_hash, salt, full_name),
        )


# ---------------------------------------------------------------------------
# Student registration
# ---------------------------------------------------------------------------

def register_student(username, password, full_name, school_id, email,
                      contact_number, course_section, year_level, teacher_ids):
    """Create a pending student account and link it to the chosen teacher(s).
    Returns (True, user_id) on success or (False, error_message) on failure."""
    required = [username, password, full_name, school_id, email, contact_number, course_section, year_level]
    if any(not str(v).strip() for v in required) or not teacher_ids:
        return False, "All fields and at least one teacher are required."

    if get_user_by_username(username):
        return False, "Username already taken."

    pw_hash, salt = _hash_password(password)
    with get_conn() as conn:
        cur = conn.execute(
            """INSERT INTO users
               (username, password_hash, password_salt, role, status,
                full_name, school_id, email, contact_number, course_section, year_level)
               VALUES (?, ?, ?, 'student', 'pending', ?, ?, ?, ?, ?, ?)""",
            (username, pw_hash, salt, full_name, school_id, email, contact_number, course_section, year_level),
        )
        student_id = cur.lastrowid
        for teacher_id in teacher_ids:
            conn.execute(
                "INSERT OR IGNORE INTO teacher_student (student_id, teacher_id) VALUES (?, ?)",
                (student_id, teacher_id),
            )
    return True, student_id


def get_pending_registrations(teacher_id=None):
    """List pending students, optionally filtered to those who selected a given teacher."""
    with get_conn() as conn:
        if teacher_id is None:
            rows = conn.execute(
                "SELECT * FROM users WHERE role='student' AND status='pending'"
            ).fetchall()
        else:
            rows = conn.execute(
                """SELECT u.* FROM users u
                   JOIN teacher_student ts ON ts.student_id = u.id
                   WHERE u.role='student' AND u.status='pending' AND ts.teacher_id = ?""",
                (teacher_id,),
            ).fetchall()
        return [dict(r) for r in rows]


def approve_registration(student_id):
    with get_conn() as conn:
        conn.execute("UPDATE users SET status='approved' WHERE id=?", (student_id,))


def decline_registration(student_id):
    with get_conn() as conn:
        conn.execute("UPDATE users SET status='declined' WHERE id=?", (student_id,))


def get_teachers_for_student(student_id):
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT u.* FROM users u
               JOIN teacher_student ts ON ts.teacher_id = u.id
               WHERE ts.student_id = ?""",
            (student_id,),
        ).fetchall()
        return [dict(r) for r in rows]


def get_students_for_teacher(teacher_id, approved_only=True):
    with get_conn() as conn:
        query = """SELECT u.* FROM users u
                   JOIN teacher_student ts ON ts.student_id = u.id
                   WHERE ts.teacher_id = ?"""
        params = [teacher_id]
        if approved_only:
            query += " AND u.status = 'approved'"
        rows = conn.execute(query, params).fetchall()
        return [dict(r) for r in rows]


def get_all_teachers():
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM users WHERE role='teacher'").fetchall()
        return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

def get_user_by_username(username):
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
        return dict(row) if row else None


def get_user_by_id(user_id):
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        return dict(row) if row else None


def update_user_full_name(user_id, full_name):
    full_name = str(full_name).strip()
    if not full_name:
        return False
    with get_conn() as conn:
        cursor = conn.execute("UPDATE users SET full_name=? WHERE id=?", (full_name, user_id))
        return cursor.rowcount > 0


def update_own_full_name(username, password, full_name):
    user = verify_password(username, password)
    if not user or user["role"] != "student":
        return False
    return update_user_full_name(user["id"], full_name)


def verify_password(username, password):
    """Returns the user dict on success, or None on bad credentials /
    not-yet-approved account."""
    user = get_user_by_username(username)
    if not user:
        return None
    if user["status"] != "approved":
        return None
    if not _check_password(password, user["password_hash"], user["password_salt"]):
        return None
    return user


def change_password(username, old_password, new_password):
    user = verify_password(username, old_password)
    if not user:
        return False, "Current password is incorrect."
    pw_hash, salt = _hash_password(new_password)
    with get_conn() as conn:
        conn.execute(
            "UPDATE users SET password_hash=?, password_salt=? WHERE id=?",
            (pw_hash, salt, user["id"]),
        )
    return True, "Password updated."


def reset_to_default_password(user_id):
    """Teacher/admin action: reset a student's password to the shared default."""
    pw_hash, salt = _hash_password(DEFAULT_RESET_PASSWORD)
    with get_conn() as conn:
        conn.execute(
            "UPDATE users SET password_hash=?, password_salt=? WHERE id=?",
            (pw_hash, salt, user_id),
        )


# ---------------------------------------------------------------------------
# Labs
# ---------------------------------------------------------------------------

def get_all_labs():
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM labs").fetchall()
        return [dict(r) for r in rows]


def set_user_lab(user_id, lab_id):
    with get_conn() as conn:
        conn.execute("UPDATE users SET lab_id=? WHERE id=?", (lab_id, user_id))


def get_lab_occupancy(lab_id):
    """Users currently in a lab with an open (still-active) session.
    Filters on the SESSION's own lab_id, not the user's persistent lab_id
    field — the session is the true "where are they right now" record,
    since it's set at the moment they logged into that specific lab."""
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT u.*, s.pc_name, s.ip_address, s.login_time
               FROM users u
               JOIN sessions s ON s.user_id = u.id
               WHERE s.lab_id = ? AND s.logout_time IS NULL
                 AND s.id = (
                     SELECT MAX(s2.id) FROM sessions s2
                     WHERE s2.user_id = s.user_id AND s2.logout_time IS NULL
                 )""",
            (lab_id,),
        ).fetchall()
        results = [dict(r) for r in rows]
        for r in results:
            r["login_time"] = _utc_to_local_str(r["login_time"])
        return results


# ---------------------------------------------------------------------------
# Sessions (login/logout tracking -> activity history)
# ---------------------------------------------------------------------------

def start_session(user_id, lab_id=None, pc_name=None, ip_address=None):
    with get_conn() as conn:
        conn.execute(
            """UPDATE sessions
               SET logout_time=strftime('%Y-%m-%d %H:%M:%S', 'now'),
                   duration_secs=MAX(0, CAST((julianday('now') - julianday(login_time)) * 86400 AS INTEGER))
               WHERE user_id=? AND logout_time IS NULL""",
            (user_id,),
        )
        cur = conn.execute(
            """INSERT INTO sessions (user_id, lab_id, pc_name, ip_address)
               VALUES (?, ?, ?, ?)""",
            (user_id, lab_id, pc_name, ip_address),
        )
        return cur.lastrowid


def close_all_active_sessions():
    """Close sessions left open when the server process previously stopped."""
    with get_conn() as conn:
        cursor = conn.execute(
            """UPDATE sessions
               SET logout_time=strftime('%Y-%m-%d %H:%M:%S', 'now'),
                   duration_secs=MAX(0, CAST((julianday('now') - julianday(login_time)) * 86400 AS INTEGER))
               WHERE logout_time IS NULL"""
        )
        return cursor.rowcount


def end_session(session_id):
    with get_conn() as conn:
        row = conn.execute("SELECT login_time FROM sessions WHERE id=?", (session_id,)).fetchone()
        if not row:
            return
        logout_dt = datetime.utcnow()
        try:
            login_dt = datetime.strptime(row["login_time"], "%Y-%m-%d %H:%M:%S")
            duration = max(0, int((logout_dt - login_dt).total_seconds()))
        except (TypeError, ValueError):
            duration = 0
        conn.execute(
            "UPDATE sessions SET logout_time=?, duration_secs=? WHERE id=?",
            (logout_dt.strftime("%Y-%m-%d %H:%M:%S"), duration, session_id),
        )


def get_active_session_id(user_id):
    with get_conn() as conn:
        row = conn.execute(
            "SELECT id FROM sessions WHERE user_id=? AND logout_time IS NULL ORDER BY id DESC LIMIT 1",
            (user_id,),
        ).fetchone()
        return row["id"] if row else None

def get_all_sessions_history(limit=500):
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT s.*, u.username, u.full_name, u.role, l.name AS lab_name
               FROM sessions s
               JOIN users u ON u.id = s.user_id
               LEFT JOIN labs l ON l.id = s.lab_id
               ORDER BY s.id DESC LIMIT ?""",
            (limit,),
        ).fetchall()
        results = [dict(r) for r in rows]
        for r in results:
            r["login_time"] = _utc_to_local_str(r["login_time"])
            r["logout_time"] = _utc_to_local_str(r["logout_time"])
        return results

def get_history_for_user(user_id, limit=200):
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT s.*, l.name AS lab_name FROM sessions s
               LEFT JOIN labs l ON l.id = s.lab_id
               WHERE s.user_id = ? ORDER BY s.id DESC LIMIT ?""",
            (user_id, limit),
        ).fetchall()
        results = [dict(r) for r in rows]
        for r in results:
            r["login_time"] = _utc_to_local_str(r["login_time"])
            r["logout_time"] = _utc_to_local_str(r["logout_time"])
        return results


# ---------------------------------------------------------------------------
# Activity log (window changes, commands, etc.)
# ---------------------------------------------------------------------------

def log_activity(user_id, session_id, activity_type, details=""):
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO activity_logs (user_id, session_id, activity_type, details)
               VALUES (?, ?, ?, ?)""",
            (user_id, session_id, activity_type, details),
        )


def get_activity_for_user(user_id, limit=500):
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM activity_logs WHERE user_id=? ORDER BY id DESC LIMIT ?",
            (user_id, limit),
        ).fetchall()
        return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Site blocklist / alerts ("Immediate Report" feature)
# ---------------------------------------------------------------------------

def get_blocklist():
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM blocklist").fetchall()
        return [dict(r) for r in rows]


def add_blocklist_entry(keyword, category):
    keyword = str(keyword).strip()
    category = str(category).strip()
    if not keyword or not category:
        return False
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO blocklist (keyword, category) VALUES (?, ?)",
            (keyword, category),
        )
    return True


def remove_blocklist_entry(entry_id):
    with get_conn() as conn:
        cursor = conn.execute("DELETE FROM blocklist WHERE id=?", (entry_id,))
        return cursor.rowcount > 0


def check_against_blocklist(window_title_or_url: str):
    """Returns (matched_keyword, category) if the text matches a blocklist
    entry (case-insensitive substring match), else (None, None)."""
    text = (window_title_or_url or "").lower()
    for entry in get_blocklist():
        if entry["keyword"].lower() in text:
            return entry["keyword"], entry["category"]
    return None, None


def log_site_alert(user_id, session_id, matched_text, category, active=True):
    with get_conn() as conn:
        if active:
            cur = conn.execute(
                """SELECT id FROM site_alerts
                   WHERE user_id=? AND active=1
                   ORDER BY id DESC LIMIT 1""",
                (user_id,),
            )
            existing = cur.fetchone()
            if existing:
                conn.execute(
                    "UPDATE site_alerts SET matched_text=?, category=?, session_id=?, acknowledged=0 WHERE id=?",
                    (matched_text, category, session_id, existing["id"]),
                )
                return existing["id"]
        cur = conn.execute(
            """INSERT INTO site_alerts (user_id, session_id, matched_text, category, active)
               VALUES (?, ?, ?, ?, ?)""",
            (user_id, session_id, matched_text, category, int(active)),
        )
        return cur.lastrowid


def close_active_site_alert(user_id):
    with get_conn() as conn:
        conn.execute("UPDATE site_alerts SET active=0 WHERE user_id=? AND active=1", (user_id,))


def get_alerts_for_teacher(teacher_id, unacknowledged_only=True, active_only=False):
    """Alerts for students belonging to this teacher, newest first."""
    with get_conn() as conn:
        query = """SELECT sa.*, u.full_name, u.username, s.ip_address FROM site_alerts sa
                   JOIN users u ON u.id = sa.user_id
                   JOIN teacher_student ts ON ts.student_id = u.id
               LEFT JOIN sessions s ON s.id = sa.session_id
                   WHERE ts.teacher_id = ?"""
        params = [teacher_id]
        if unacknowledged_only:
            query += " AND sa.acknowledged = 0"
        if active_only:
            query += " AND sa.active = 1 AND s.logout_time IS NULL"
        query += " ORDER BY sa.id DESC"
        rows = conn.execute(query, params).fetchall()
        return [dict(r) for r in rows]


def get_alerts_for_admin(unacknowledged_only=True, active_only=False):
    """Return all restricted-site alerts, including the student's IP."""
    with get_conn() as conn:
        query = """SELECT sa.*, u.full_name, u.username, s.ip_address
                   FROM site_alerts sa
                   JOIN users u ON u.id = sa.user_id
                   LEFT JOIN sessions s ON s.id = sa.session_id
                   WHERE 1=1"""
        if unacknowledged_only:
            query += " AND sa.acknowledged = 0"
        if active_only:
            query += " AND sa.active = 1 AND s.logout_time IS NULL"
        query += " ORDER BY sa.id DESC"
        return [dict(row) for row in conn.execute(query).fetchall()]


def acknowledge_alert(alert_id):
    with get_conn() as conn:
        conn.execute("UPDATE site_alerts SET acknowledged=1 WHERE id=?", (alert_id,))


if __name__ == "__main__":
    # Quick manual smoke test: `python db.py`
    init_db()
    seed_defaults()
    print("DB initialized at:", DB_PATH)
    print("Admin user:", get_user_by_username("admin"))
    print("Labs:", get_all_labs())
    print("Blocklist:", get_blocklist())


# ---------------------------------------------------------------------------
# Inventory (borrowing)
# ---------------------------------------------------------------------------

def add_inventory_item(name, quantity_total):
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO inventory_items (name, quantity_total, quantity_available)
               VALUES (?, ?, ?)""",
            (name, quantity_total, quantity_total),
        )


def get_all_inventory_items():
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM inventory_items ORDER BY name").fetchall()
        return [dict(r) for r in rows]


def borrow_item(item_id, borrower_name, quantity=1, notes=""):
    """Returns (True, None) on success, or (False, error_message) if not enough stock."""
    with get_conn() as conn:
        item = conn.execute("SELECT * FROM inventory_items WHERE id=?", (item_id,)).fetchone()
        if not item:
            return False, "Item not found."
        if item["quantity_available"] < quantity:
            return False, f"Only {item['quantity_available']} available."

        conn.execute(
            "UPDATE inventory_items SET quantity_available = quantity_available - ? WHERE id=?",
            (quantity, item_id),
        )
        conn.execute(
            """INSERT INTO borrow_records (item_id, borrower_name, quantity, notes)
               VALUES (?, ?, ?, ?)""",
            (item_id, borrower_name, quantity, notes),
        )
    return True, None


def return_item(borrow_record_id):
    with get_conn() as conn:
        record = conn.execute("SELECT * FROM borrow_records WHERE id=?", (borrow_record_id,)).fetchone()
        if not record or record["returned_at"] is not None:
            return
        conn.execute(
            "UPDATE borrow_records SET returned_at=? WHERE id=?",
            (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), borrow_record_id),
        )
        conn.execute(
            "UPDATE inventory_items SET quantity_available = quantity_available + ? WHERE id=?",
            (record["quantity"], record["item_id"]),
        )


def get_active_borrows():
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT br.*, i.name AS item_name FROM borrow_records br
               JOIN inventory_items i ON i.id = br.item_id
               WHERE br.returned_at IS NULL
               ORDER BY br.borrowed_at DESC"""
        ).fetchall()
        return [dict(r) for r in rows]


def get_borrow_history(limit=200):
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT br.*, i.name AS item_name FROM borrow_records br
               JOIN inventory_items i ON i.id = br.item_id
               ORDER BY br.borrowed_at DESC LIMIT ?""",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]