import sqlite3
c = sqlite3.connect('planificacion.db')
print("LIKE %Test%")
for row in c.execute("SELECT id, summary, sync_status, google_event_id, inicio, fin, tecnico_nombre FROM eventos WHERE summary LIKE '%Test%' ORDER BY updated_at DESC LIMIT 10"):
    print(row)
