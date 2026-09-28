from database import db

with db.get_conn() as conn:
    result = conn.execute("SELECT COUNT(*) as c FROM sessions WHERE logout_time IS NULL").fetchone()
    count = result["c"]
    print(f"Stale open sessions found: {count}")

    conn.execute("UPDATE sessions SET logout_time = datetime('now'), duration_secs = 0 WHERE logout_time IS NULL")
    print("All stale sessions closed.")