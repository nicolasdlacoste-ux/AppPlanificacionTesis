import sqlite3
db = sqlite3.connect('planificacion.db')
print("Logs for test 1:")
for r in db.execute("SELECT event_type, detail, timestamp FROM poll_log WHERE event_id = '5o4lvicj6ok6hvnejollrvuc9c'").fetchall():
    print(r)
