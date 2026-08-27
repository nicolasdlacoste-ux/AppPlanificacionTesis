import sqlite3
import json
db = sqlite3.connect('planificacion.db')
print("Logs for ndiaz at 12:21:")
for r in db.execute("SELECT event_type, detail, timestamp, event_id FROM poll_log WHERE calendar_id = 'ndiaz@akrimet.com' AND timestamp LIKE '2026-06-06T12:21%' ORDER BY timestamp ASC").fetchall():
    print(r)
