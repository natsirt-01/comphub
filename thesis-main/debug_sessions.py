from database import db

print("=== All users and their lab_id ===")
with db.get_conn() as conn:
    users = conn.execute("SELECT id, username, role, lab_id FROM users").fetchall()
    for u in users:
        print(dict(u))

print("\n=== All labs ===")
for lab in db.get_all_labs():
    print(lab)

print("\n=== All sessions (most recent 10) ===")
with db.get_conn() as conn:
    sessions = conn.execute(
        "SELECT id, user_id, lab_id, pc_name, login_time, logout_time FROM sessions ORDER BY id DESC LIMIT 10"
    ).fetchall()
    for s in sessions:
        print(dict(s))