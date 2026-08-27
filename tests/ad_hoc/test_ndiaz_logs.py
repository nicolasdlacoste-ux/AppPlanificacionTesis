import sqlite3
import json
db = sqlite3.connect('planificacion.db')
for r in db.execute("SELECT event_type, detail, timestamp, event_id FROM poll_log WHERE calendar_id = 'ndiaz@akrimet.com' AND timestamp > '2026-06-06T12:00:00Z' ORDER BY timestamp DESC LIMIT 20").fetchall():
    print(r)
