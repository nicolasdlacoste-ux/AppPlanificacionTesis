import sqlite3
c = sqlite3.connect('planificacion.db')

for row in c.execute("SELECT id, summary, sync_status, google_event_id, inicio, fin FROM eventos WHERE summary LIKE '%Test%' OR summary LIKE '%10000%' ORDER BY updated_at DESC LIMIT 10"):
    print(row)
