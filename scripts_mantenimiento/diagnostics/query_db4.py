import sqlite3
c = sqlite3.connect('planificacion.db')
for row in c.execute("SELECT id, summary, sync_status, google_event_id, inicio, fin FROM eventos WHERE summary='Test' ORDER BY updated_at DESC LIMIT 5"):
    print(row)
