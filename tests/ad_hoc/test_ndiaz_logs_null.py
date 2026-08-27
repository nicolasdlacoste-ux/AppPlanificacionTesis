import sqlite3
db = sqlite3.connect('planificacion.db')
print("Logs at 12:21 for test 1:")
for r in db.execute("SELECT event_type, detail, timestamp, detail FROM poll_log WHERE detail LIKE '%5o4lvicj6ok6hvnejollrvuc9c%' OR timestamp LIKE '2026-06-06T12:21%'").fetchall():
    print(r)
