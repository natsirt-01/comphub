-- ScholarNet database schema
-- Lives on the machine that runs login.py (the "server" side: teacher + admin dashboards).
-- Students never touch this file directly; they only talk to it through socket requests
-- handled by the teacher-side listener, same as today.

PRAGMA foreign_keys = ON;

-- ---------------------------------------------------------------------------
-- Computer labs
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS labs (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    name    TEXT NOT NULL UNIQUE        -- 'Computer Lab A', 'Computer Lab B'
);

INSERT OR IGNORE INTO labs (name) VALUES ('Computer Lab A');
INSERT OR IGNORE INTO labs (name) VALUES ('Computer Lab B');

-- ---------------------------------------------------------------------------
-- Users (students, teachers, admins all live here, distinguished by role)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS users (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    username        TEXT NOT NULL UNIQUE,
    password_hash   TEXT NOT NULL,      -- PBKDF2 hash, never plaintext
    password_salt   TEXT NOT NULL,
    role            TEXT NOT NULL CHECK (role IN ('student', 'teacher', 'admin')),
    status          TEXT NOT NULL DEFAULT 'approved'
                        CHECK (status IN ('pending', 'approved', 'declined')),
                    -- teachers/admins are auto-approved; students start 'pending'

    -- Student registration fields (NULL for teacher/admin rows)
    full_name       TEXT,
    school_id       TEXT,
    email           TEXT,
    contact_number  TEXT,
    course_section  TEXT,
    year_level      TEXT,

    lab_id          INTEGER REFERENCES labs(id),   -- lab the user is currently in (set at login)
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

-- ---------------------------------------------------------------------------
-- Which teacher(s) a student registered under / has access to
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS teacher_student (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id  INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    teacher_id  INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    UNIQUE (student_id, teacher_id)
);

-- ---------------------------------------------------------------------------
-- Login sessions (drives "Activity History" for every role)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS sessions (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id         INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    lab_id          INTEGER REFERENCES labs(id),
    pc_name         TEXT,
    ip_address      TEXT,
    login_time      TEXT NOT NULL DEFAULT (datetime('now')),
    logout_time     TEXT,               -- NULL while still active
    duration_secs   INTEGER
);

-- ---------------------------------------------------------------------------
-- General activity log (window changes, commands issued, etc.)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS activity_logs (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id         INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    session_id      INTEGER REFERENCES sessions(id) ON DELETE CASCADE,
    activity_type   TEXT NOT NULL,      -- e.g. 'window_change', 'expression', 'command_received'
    details         TEXT,
    timestamp       TEXT NOT NULL DEFAULT (datetime('now'))
);

-- ---------------------------------------------------------------------------
-- Restricted-site blocklist (drives the "Immediate Report" feature)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS blocklist (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    keyword     TEXT NOT NULL UNIQUE,   -- matched against window title / URL, case-insensitive
    category    TEXT NOT NULL           -- 'betting', 'adult', 'gaming', etc.
);

INSERT OR IGNORE INTO blocklist (keyword, category) VALUES ('bet', 'betting');
INSERT OR IGNORE INTO blocklist (keyword, category) VALUES ('y8', 'gaming');
INSERT OR IGNORE INTO blocklist (keyword, category) VALUES ('pornhub', 'adult');
INSERT OR IGNORE INTO blocklist (keyword, category) VALUES ('beeg', 'adult');
INSERT OR IGNORE INTO blocklist (keyword, category) VALUES ('gemini', 'ai');
INSERT OR IGNORE INTO blocklist (keyword, category) VALUES ('blackbox', 'ai');
INSERT OR IGNORE INTO blocklist (keyword, category) VALUES ('chatgpt', 'ai');
INSERT OR IGNORE INTO blocklist (keyword, category) VALUES ('hanime', 'adult');
INSERT OR IGNORE INTO blocklist (keyword, category) VALUES ('pinayflix', 'adult');
INSERT OR IGNORE INTO blocklist (keyword, category) VALUES ('sulasok', 'adult');
INSERT OR IGNORE INTO blocklist (keyword, category) VALUES ('telegram', 'social');
INSERT OR IGNORE INTO blocklist (keyword, category) VALUES ('pornhub', 'adult');
INSERT OR IGNORE INTO blocklist (keyword, category) VALUES ('friv', 'gaming');
INSERT OR IGNORE INTO blocklist (keyword, category) VALUES ('facebook', 'social');
INSERT OR IGNORE INTO blocklist (keyword, category) VALUES ('instagram', 'social');
INSERT OR IGNORE INTO blocklist (keyword, category) VALUES ('xxx', 'adult');
INSERT OR IGNORE INTO blocklist (keyword, category) VALUES ('deepseek', 'ai');
-- Extend this list freely; the app reads it fresh each time, no code change needed.

-- ---------------------------------------------------------------------------
-- Flagged site/app visits (feeds the highlighted Teacher Inbox alerts)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS site_alerts (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id         INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    session_id      INTEGER REFERENCES sessions(id) ON DELETE CASCADE,
    matched_text    TEXT NOT NULL,      -- the window title / URL that triggered it
    category        TEXT NOT NULL,
    timestamp       TEXT NOT NULL DEFAULT (datetime('now')),
    acknowledged    INTEGER NOT NULL DEFAULT 0,  -- 0/1, so teacher can dismiss in Inbox
    active          INTEGER NOT NULL DEFAULT 1   -- 0 after the restricted window closes
);

-- ---------------------------------------------------------------------------
-- Seed accounts so the app is usable immediately after a fresh DB init
-- (password 'admin123' / 'teacher123' set via db.py's seed_defaults(), not here,
--  since hashing needs Python, not raw SQL)
-- ---------------------------------------------------------------------------
-- ---------------------------------------------------------------------------
-- Inventory (equipment borrowing, admin-managed)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS inventory_items (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    name            TEXT NOT NULL UNIQUE,
    quantity_total  INTEGER NOT NULL DEFAULT 0,
    quantity_available INTEGER NOT NULL DEFAULT 0,
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS borrow_records (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    item_id         INTEGER NOT NULL REFERENCES inventory_items(id) ON DELETE CASCADE,
    borrower_name   TEXT NOT NULL,
    quantity        INTEGER NOT NULL DEFAULT 1,
    borrowed_at     TEXT NOT NULL DEFAULT (datetime('now')),
    returned_at     TEXT,               -- NULL while still borrowed
    notes           TEXT
);