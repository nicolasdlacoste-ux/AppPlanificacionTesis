import sqlite3
db = sqlite3.connect('planificacion.db')
print("ndiaz count:", db.execute("SELECT COUNT(*) FROM eventos WHERE calendar_id = 'ndiaz@akrimet.com'").fetchone()[0])
print("test events:")
for r in db.execute("SELECT id, summary, tecnico_nombre, calendar_id, sync_status FROM eventos WHERE summary LIKE '%test%'").fetchall():
    print(r)
